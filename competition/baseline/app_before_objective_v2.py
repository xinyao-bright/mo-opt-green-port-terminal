import json
import numpy as np
import pandas as pd
import copy
import io
import random
import os
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_cors import CORS
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, PortConfiguration, Ship, ScheduleHistory
from auth import login_manager, register_user, authenticate_user

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# =============================================================================
# 0. 数据库初始化
# =============================================================================
with app.app_context():
    db.create_all()


class PortConfig:
    TOTAL_BERTHS = 10
    BERTH_LENGTHS = [350]*10
    BERTH_NAMES = [f"B{i:02d}" for i in range(1, 11)]
    TOTAL_QCS = 15
    MAX_QC_PER_VESSEL = 3
    QC_EFFICIENCY = 48
    perQcPow = 1000
    qc_load_factor = 0.5
    auv_money = 1
    qc_money = 3
    co2_emission_factor = 3.15
    SAFETY_INTERVAL = 10.0 / 60.0


# PortConfig 的出厂缺省值，用于没有激活配置时回滚
PORT_CONFIG_DEFAULTS = {
    'TOTAL_BERTHS': 10,
    'BERTH_LENGTHS': [350] * 10,
    'BERTH_NAMES': [f"B{i:02d}" for i in range(1, 11)],
    'TOTAL_QCS': 15,
    'MAX_QC_PER_VESSEL': 3,
    'QC_EFFICIENCY': 48.0,
    'perQcPow': 1000.0,
    'qc_load_factor': 0.5,
    'auv_money': 1.0,
    'qc_money': 3.0,
    'co2_emission_factor': 3.15,
    'SAFETY_INTERVAL': 10.0 / 60.0,
}


def reset_port_config():
    """把 PortConfig 恢复为出厂缺省值"""
    for key, value in PORT_CONFIG_DEFAULTS.items():
        setattr(PortConfig, key, copy.deepcopy(value))


def _safe_float(value, default):
    """取字段值，None 时回退到 default；0 / 0.0 被保留而非误判为 falsy。"""
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default):
    if value is None:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def load_active_port_config(user_id=None):
    """把当前用户已激活的泊位配置写入全局 PortConfig。

    没有激活配置时回滚到出厂缺省值，保证求解器读到的参数始终自洽
    （BERTH_LENGTHS / BERTH_NAMES 长度恒等于 TOTAL_BERTHS）。
    返回被应用的 PortConfiguration 实例，没有则返回 None。
    """
    if user_id is None:
        try:
            user_id = getattr(current_user, 'id', None)
        except RuntimeError:
            user_id = None

    config = None
    if user_id is not None:
        try:
            config = PortConfiguration.query.filter_by(user_id=user_id, is_active=True).first()
        except Exception:
            config = None

    if config is None:
        reset_port_config()
        return None

    total_berths = max(1, _safe_int(config.total_berths, 1))

    try:
        berth_rows = config.get_berth_config() or []
    except (ValueError, TypeError):
        berth_rows = []

    lengths, names = [], []
    for idx in range(total_berths):
        row = berth_rows[idx] if idx < len(berth_rows) and isinstance(berth_rows[idx], dict) else {}
        try:
            length = float(row.get('length', 350.0))
        except (TypeError, ValueError):
            length = 350.0
        lengths.append(length if length > 0 else 350.0)
        names.append(str(row.get('name') or f"B{idx + 1:02d}"))

    total_qcs = max(1, _safe_int(config.total_qcs, 1))
    max_qc = _safe_int(config.max_qc_per_vessel, 3)
    max_qc = max(1, min(max_qc, total_qcs))

    PortConfig.TOTAL_BERTHS = total_berths
    PortConfig.BERTH_LENGTHS = lengths
    PortConfig.BERTH_NAMES = names
    PortConfig.TOTAL_QCS = total_qcs
    PortConfig.MAX_QC_PER_VESSEL = max_qc
    PortConfig.QC_EFFICIENCY = _safe_float(config.qc_efficiency, 48.0)
    PortConfig.perQcPow = _safe_float(config.per_qc_pow, 1000.0)
    PortConfig.qc_load_factor = _safe_float(config.qc_load_factor, 0.5)
    PortConfig.auv_money = _safe_float(config.auv_money, 1.0)
    PortConfig.qc_money = _safe_float(config.qc_money, 3.0)
    PortConfig.co2_emission_factor = _safe_float(config.co2_emission_factor, 3.15)
    safety = _safe_float(config.safety_interval, 10.0 / 60.0)
    PortConfig.SAFETY_INTERVAL = max(0.0, safety)

    return config


def berth_display_name(berth_index):
    """泊位序号转展示名，越界时回退到 Bxx"""
    idx = int(berth_index) - 1
    if 0 <= idx < len(PortConfig.BERTH_NAMES):
        return PortConfig.BERTH_NAMES[idx]
    return f"B{int(berth_index):02d}"


def berth_length_of(berth_index):
    """泊位序号转泊位长度，越界时回退到缺省长度"""
    idx = int(berth_index) - 1
    if 0 <= idx < len(PortConfig.BERTH_LENGTHS):
        return PortConfig.BERTH_LENGTHS[idx]
    return 350.0


def load_vessel_data(file_path="ship_data(SS).csv"):
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding='gbk')
    except FileNotFoundError:
        print(f"-> 错误: 找不到文件 {file_path}。")
        return []
    df.columns = df.columns.str.strip()
    vessels = []
    id_col = df.columns[0]
    time_col = [c for c in df.columns if 'time_of_reachport' in c.lower()][0]
    teu = [c for c in df.columns if 'volume_of_goods' in c.lower()][0]
    len_col = [c for c in df.columns if 'length_of_ship' in c.lower()][0] 
    auv1 = [c for c in df.columns if 'auxfuelcons' in c.lower().replace('(kg/kwh)', '') or 'auxfuelcons' in c.lower()][0]
    auv2 = [c for c in df.columns if 'auxratedpow' in c.lower()][0]
    auv3 = [c for c in df.columns if 'auxlf' in c.lower()][0]
    for _, row in df.iterrows():
        time_val = str(row[time_col]).strip()
        if ':' in time_val:
            parts = time_val.split(':')
            eta_hours = float(parts[0]) + (float(parts[1]) / 60.0)
        else:
            eta_hours = float(time_val) * 24.0

        vessels.append({
            'id': str(row[id_col]),
            'eta': eta_hours,
            'workload': float(row[teu]),
            'len': float(row[len_col]),
            'auv1': float(row[auv1]),
            "auv2": float(row[auv2]),
            "auv3": float(row[auv3]),
        })
    return vessels


#解码
def decode_solution(position, vessels):
    num_vessels = len(vessels)
    # 1. 泊位分配
    berths = (np.abs(np.round(position[0:num_vessels]).astype(int)) % PortConfig.TOTAL_BERTHS) + 1
    # 2. 靠泊时间
    raw_berthing_times = np.clip(position[num_vessels:2 * num_vessels], 0.0, 36.0)
    # 3. 岸桥分配数量
    assigned_qcs = np.clip(np.round(position[2 * num_vessels:3 * num_vessels]).astype(int), 1, PortConfig.MAX_QC_PER_VESSEL)
    # 4. 连续岸桥的起始编号 
    # 确保起始编号 + 数量 - 1 不会超过总岸桥数，预留工艺冗余边界
    max_start_idx = PortConfig.TOTAL_QCS - assigned_qcs + 1
    qc_start_idx = np.clip(np.round(position[3 * num_vessels:4 * num_vessels]).astype(int), 1, max_start_idx)

    handling_times = [vessels[i]['workload'] / (assigned_qcs[i] * PortConfig.QC_EFFICIENCY) for i in range(num_vessels)]

    actual_berthing = np.zeros(num_vessels)
    departures = np.zeros(num_vessels)
    
    sort_idx = np.argsort(raw_berthing_times)
    berth_last_departure = {b: 0.0 for b in range(1, PortConfig.TOTAL_BERTHS + 1)}

    for i in sort_idx:
        b = berths[i]
        t_ready = max(raw_berthing_times[i], vessels[i]['eta'])
        if berth_last_departure[b] > 0 and t_ready < (berth_last_departure[b] + PortConfig.SAFETY_INTERVAL):
            t_ready = berth_last_departure[b] + PortConfig.SAFETY_INTERVAL

        actual_berthing[i] = t_ready
        departures[i] = t_ready + handling_times[i]
        berth_last_departure[b] = departures[i]

    return berths, actual_berthing, assigned_qcs, qc_start_idx, departures
def calculate_penalty(num_vessels, berth_id, berthing_times, departures, qc_start_idx, assigned_qcs, total_qc):
    base_p = 5e4
    penalty = 0.0
    berth_id = np.asarray(berth_id)
    berthing_times = np.asarray(berthing_times, dtype=float)
    departures = np.asarray(departures, dtype=float)
    qc_start_idx = np.asarray(qc_start_idx)
    assigned_qcs = np.asarray(assigned_qcs)
    qc_end_idx = qc_start_idx + assigned_qcs - 1
    invalid = (qc_start_idx < 1) | (qc_end_idx > total_qc) | (assigned_qcs < 1)
    penalty += base_p * 3 * np.count_nonzero(invalid)

    if num_vessels > 1:
        iu, ju = np.triu_indices(num_vessels, k=1)
        time_overlap = (np.maximum(berthing_times[iu], berthing_times[ju])
                         < np.minimum(departures[iu], departures[ju]))
        overlap_amount = (np.minimum(qc_end_idx[iu], qc_end_idx[ju])
                           - np.maximum(qc_start_idx[iu], qc_start_idx[ju]) + 1)
        qc_overlap_mask = time_overlap & (overlap_amount > 0)
        penalty += base_p * overlap_amount[qc_overlap_mask].sum()
        cross_penalty = base_p * 4
        cond1 = (berth_id[iu] < berth_id[ju]) & (qc_end_idx[iu] > qc_start_idx[ju])
        cond2 = (berth_id[ju] < berth_id[iu]) & (qc_end_idx[ju] > qc_start_idx[iu])
        penalty += cross_penalty * (np.count_nonzero(cond1) + np.count_nonzero(cond2))
    return penalty


def repair_qc_conflict(position, vessels):
    num_vessels = len(vessels)
    berths, raw_berthing, assigned_qcs, qc_starts, _ = decode_solution(position, vessels)

    handling_times = np.array([
        vessels[i]['workload'] / (assigned_qcs[i] * PortConfig.QC_EFFICIENCY)
        for i in range(num_vessels)
    ])

    # ========== Step 1: 基于泊位排序，一次性消除空间倒挂 ==========
    # 按泊位升序排列，泊位相同时保留原始 qc_starts 的相对顺序
    berth_order = np.argsort(berths, kind='stable')
    # 将原始 qc_starts 按升序重新分配给按泊位排序后的船舶
    sorted_original_starts = np.sort(qc_starts)
    new_qc_starts = np.zeros(num_vessels, dtype=int)
    for rank, vessel_idx in enumerate(berth_order):
        candidate = sorted_original_starts[rank]
        # 确保不越界
        max_allowed = PortConfig.TOTAL_QCS - assigned_qcs[vessel_idx] + 1
        new_qc_starts[vessel_idx] = min(max(candidate, 1), max_allowed)

    # ========== Step 2: 按靠泊时间顺序逐船放置，解决时空冲突 ==========
    sorted_idx = np.argsort(raw_berthing)
    # 已分配记录: (靠泊时间, 离泊时间, 泊位号, 岸桥起始, 岸桥结束)
    allocated_ships = []
    berth_last_departure = {b: 0.0 for b in range(1, PortConfig.TOTAL_BERTHS + 1)}

    repaired_berthing = np.zeros(num_vessels)
    repaired_qc_starts = np.zeros(num_vessels, dtype=int)

    MAX_DELAY_ITERS = 50  # 防止无限循环

    for idx in sorted_idx:
        qc_need = assigned_qcs[idx]
        ship_eta = vessels[idx]['eta']
        current_berth = berths[idx]
        # 考虑泊位安全间隔
        current_berth_time = max(raw_berthing[idx], ship_eta,
                                 berth_last_departure[current_berth] + PortConfig.SAFETY_INTERVAL
                                 if berth_last_departure[current_berth] > 0 else 0.0)

        placed = False
        for _attempt in range(MAX_DELAY_ITERS):
            current_depart_time = current_berth_time + handling_times[idx]

            # 确定受空间非交叉约束限制的岸桥可用边界
            allowed_min_qc = 1
            allowed_max_qc = PortConfig.TOTAL_QCS
            conflict_depart_times = []

            for alloc_bt, alloc_dt, alloc_berth, alloc_qs, alloc_qe in allocated_ships:
                time_overlap = (current_berth_time < alloc_dt) and (alloc_bt < current_depart_time)
                if time_overlap:
                    conflict_depart_times.append(alloc_dt)
                    if current_berth > alloc_berth:
                        allowed_min_qc = max(allowed_min_qc, alloc_qe + 1)
                    elif current_berth < alloc_berth:
                        allowed_max_qc = min(allowed_max_qc, alloc_qs - 1)
                    else:
                        # 同泊位时间重叠，必须推迟
                        allowed_max_qc = -1

            available_capacity = allowed_max_qc - allowed_min_qc + 1

            if available_capacity >= qc_need:
                preferred_start = new_qc_starts[idx]
                valid_start = max(allowed_min_qc, min(preferred_start, allowed_max_qc - qc_need + 1))

                repaired_berthing[idx] = current_berth_time
                repaired_qc_starts[idx] = valid_start
                allocated_ships.append((current_berth_time, current_depart_time,
                                        current_berth, valid_start, valid_start + qc_need - 1))
                berth_last_departure[current_berth] = current_depart_time
                placed = True
                break
            else:
                if not conflict_depart_times:
                    # 无时间冲突但空间不够（极端情况），小幅推迟
                    current_berth_time += PortConfig.SAFETY_INTERVAL
                else:
                    earliest_conflict_depart = min(conflict_depart_times)
                    current_berth_time = earliest_conflict_depart + PortConfig.SAFETY_INTERVAL
                current_berth_time = max(current_berth_time, ship_eta)

        if not placed:
            # 达到最大尝试次数，接受当前时间强行放置
            repaired_berthing[idx] = current_berth_time
            repaired_qc_starts[idx] = max(1, min(new_qc_starts[idx],
                                                  PortConfig.TOTAL_QCS - qc_need + 1))
            dep_time = current_berth_time + handling_times[idx]
            allocated_ships.append((current_berth_time, dep_time, current_berth,
                                    repaired_qc_starts[idx],
                                    repaired_qc_starts[idx] + qc_need - 1))
            berth_last_departure[current_berth] = dep_time

    # ========== Step 3: 写回 position 向量，直接计算惩罚（不再二次 decode）==========
    repaired_pos = position.copy()
    repaired_pos[num_vessels: 2 * num_vessels] = repaired_berthing
    repaired_pos[3 * num_vessels: 4 * num_vessels] = repaired_qc_starts

    # 基于修复结果直接计算离泊时间和惩罚
    departures = repaired_berthing + handling_times
    new_penalty = calculate_penalty(num_vessels, berths, repaired_berthing, departures,
                                    repaired_qc_starts, assigned_qcs, PortConfig.TOTAL_QCS)

    return repaired_pos, new_penalty

def calculate_objectives(position, vessels):
    berths, berthing_times, assigned_qcs, qc_start_idx, departures = decode_solution(position, vessels)
    num_vessels = len(vessels)
    penalty = calculate_penalty(num_vessels, berths, berthing_times, departures, qc_start_idx, assigned_qcs, PortConfig.TOTAL_QCS)
    f1_emission, f2_money = 0, 0
    for i in range(num_vessels):
        wait_time = berthing_times[i] - vessels[i]['eta']
        handling_time = departures[i] - berthing_times[i]
        f1_emission += (wait_time * PortConfig.co2_emission_factor * vessels[i]['auv1'] * vessels[i]['auv2'] * vessels[i]['auv3'] + 
                        handling_time * assigned_qcs[i] * PortConfig.perQcPow * PortConfig.qc_load_factor)
        f2_money += (wait_time * assigned_qcs[i] * PortConfig.qc_money + wait_time * PortConfig.auv_money * vessels[i]['workload'])
    f3_stay_time = sum([departures[i] - vessels[i]['eta'] for i in range(num_vessels)])
    return np.array([
        f1_emission + penalty * 10, 
        f3_stay_time + penalty * 10, 
        f2_money + penalty * 10
    ]), penalty
def dominates(obj1, obj2):
    return np.all(obj1 <= obj2) and np.any(obj1 < obj2)
def fast_non_dominated_sort_cdp(objs, penalties):
    pop_size = objs.shape[0]
    S = [[] for _ in range(pop_size)]
    n = np.zeros(pop_size, dtype=int)
    fronts = [[]]
    
    def dominates(p, q):
        # 规则 1: p 可行, q 不可行
        if penalties[p] == 0 and penalties[q] > 0:
            return True
        # 规则 2: p 和 q 都不可行, p 的约束违反度更小
        elif penalties[p] > 0 and penalties[q] > 0 and penalties[p] < penalties[q]:
            return True
        # 规则 3: p 和 q 都可行, 退化为标准的帕累托支配 (假设所有目标都是最小化)
        elif penalties[p] == 0 and penalties[q] == 0:
            return np.all(objs[p] <= objs[q]) and np.any(objs[p] < objs[q])
        return False

    # 计算支配关系
    for p in range(pop_size):
        for q in range(pop_size):
            if p == q:
                continue
            if dominates(p, q):
                S[p].append(q)
            elif dominates(q, p):
                n[p] += 1
        if n[p] == 0:
            fronts[0].append(p)
            
    # 生成后续前沿
    i = 0
    while len(fronts[i]) > 0:
        next_front = []
        for p in fronts[i]:
            for q in S[p]:
                n[q] -= 1  # 移除 p 的支配影响
                if n[q] == 0:
                    next_front.append(q)
        if len(next_front) == 0:
            break
            
        fronts.append(next_front)
        i += 1
        
    return fronts



def crowding_distance(objs, front):
    l = len(front)
    distances = np.zeros(l)
    if l <= 2:
        return np.full(l, np.inf)
        
    num_objs = objs.shape[1]
    front_objs = objs[front]
    
    # 对每个目标做min-max归一化，消除量级差异
    obj_min = np.min(front_objs, axis=0)
    obj_max = np.max(front_objs, axis=0)
    obj_range = obj_max - obj_min
    obj_range[obj_range == 0] = 1e-9  
    
    norm_objs = (front_objs - obj_min) / obj_range
    
    for m in range(num_objs):
        sorted_indices = np.argsort(norm_objs[:, m])
        distances[sorted_indices[0]] = np.inf
        distances[sorted_indices[-1]] = np.inf
        
        for i in range(1, l - 1):
            distances[sorted_indices[i]] += (
                norm_objs[sorted_indices[i + 1], m] 
                - norm_objs[sorted_indices[i - 1], m]
            )
    return distances

def compute_metrics(objs):
    mu = np.mean(objs, axis=0)
    std = np.std(objs, axis=0)
    cv = np.mean(std / (mu + 1e-9)) 
    if len(objs) > 1:
        d_matrix = np.sum(np.abs(objs[:, np.newaxis, :] - objs[np.newaxis, :, :]), axis=-1)
        np.fill_diagonal(d_matrix, np.inf)
        d_min = np.min(d_matrix, axis=1)
        d_mean = np.mean(d_min)
        sp = np.sqrt(np.mean((d_min - d_mean)**2))
    else:
        sp = 0.0
    return cv, sp


def nsga2_solver(vessels, max_iter=200, pop_size=100):
    
    num_vessels = len(vessels)
    dim = 4 * num_vessels  # 增加了一维岸桥起始索引
    etas = np.array([v['eta'] for v in vessels])
    
    # 1. 初始化种群
    # 岸桥起始编号按泊位顺序均匀铺开，从源头减少空间交叉冲突，加快收敛到可行解
    pop = np.zeros((pop_size, dim))
    for i in range(pop_size):
        berth_assignment = np.random.uniform(1, PortConfig.TOTAL_BERTHS, num_vessels)
        pop[i, 0:num_vessels] = berth_assignment
        pop[i, num_vessels:2 * num_vessels] = etas + np.random.uniform(0, 2.0, num_vessels)
        pop[i, 2 * num_vessels:3 * num_vessels] = np.random.uniform(1, PortConfig.MAX_QC_PER_VESSEL, num_vessels)

        berth_order = np.argsort(berth_assignment, kind='stable')
        qc_starts_by_rank = np.linspace(1, PortConfig.TOTAL_QCS, num_vessels)
        qc_starts = np.zeros(num_vessels)
        qc_starts[berth_order] = qc_starts_by_rank
        pop[i, 3 * num_vessels:4 * num_vessels] = qc_starts

    eval_results = [calculate_objectives(p, vessels) for p in pop]
    objs = np.array([res[0] for res in eval_results])
    penalties = np.array([res[1] for res in eval_results])

    # 初始种群整体修复一次，让算法从可行/接近可行的解开始迭代，而不是从头进化出来
    for i in range(pop_size):
        if penalties[i] > 0:
            repaired_pos, new_penalty = repair_qc_conflict(pop[i], vessels)
            new_objs, _ = calculate_objectives(repaired_pos, vessels)
            pop[i] = repaired_pos
            objs[i] = new_objs
            penalties[i] = new_penalty

    for gen in range(max_iter):
        fronts = fast_non_dominated_sort_cdp(objs, penalties)
        ranks = np.zeros(pop_size, dtype=int)
        crowding = np.zeros(pop_size)
        for r, f in enumerate(fronts):
            for idx in f: ranks[idx] = r
            dists = crowding_distance(objs, f)
            for i, idx in enumerate(f): crowding[idx] = dists[i]
                
        def tournament_selection():
            idx1, idx2 = np.random.choice(pop_size, 2, replace=False)
            if ranks[idx1] != ranks[idx2]: return idx1 if ranks[idx1] < ranks[idx2] else idx2
            return idx1 if crowding[idx1] >= crowding[idx2] else idx2

        # 2. 生成子代
        offspring = np.zeros_like(pop)
        for i in range(0, pop_size, 2):
            p1_idx, p2_idx = tournament_selection(), tournament_selection()
            p1, p2 = pop[p1_idx], pop[p2_idx]
            
            c1, c2 = p1.copy(), p2.copy()
            if np.random.rand() < 0.7:  
                alpha = np.random.rand(dim)
                c1 = alpha * p1 + (1 - alpha) * p2
                c2 = alpha * p2 + (1 - alpha) * p1
                
            for c in [c1, c2]:
                for j in range(dim):
                    if np.random.rand() < 1.0 / dim: 
                        if j < num_vessels:
                            c[j] = np.random.uniform(1, PortConfig.TOTAL_BERTHS) if np.random.rand() < 0.3 else c[j] + np.random.normal(0, 5.0)
                        else:
                            c[j] += np.random.normal(0, 2.0)
            offspring[i] = c1
            if i + 1 < pop_size: offspring[i + 1] = c2
                
        off_eval_results = [calculate_objectives(p, vessels) for p in offspring]
        offspring_objs = np.array([res[0] for res in off_eval_results])
        offspring_penalties = np.array([res[1] for res in off_eval_results])
        
        # 3. 精英保留机制
        combined_pop = np.vstack((pop, offspring))
        combined_objs = np.vstack((objs, offspring_objs))
        combined_penalties = np.concatenate((penalties, offspring_penalties))

       
       
        # 修正1：必须对 combined_objs 和 combined_penalties 排序
        temp_fronts = fast_non_dominated_sort_cdp(combined_objs, combined_penalties) 
        temp_ranks = np.zeros(len(combined_objs), dtype=int)
        
        # 修正2：遍历 temp_fronts 而不是 temp_ranks
        for rank, front in enumerate(temp_fronts): 
            for idx in front:
                temp_ranks[idx] = rank

        # 筛选所有不可行解（惩罚值大于0）
        infeasible_indices = np.where(combined_penalties > 0)[0]
        
        if len(infeasible_indices) > 0:
            # 按非支配层级排序，修复前排的高潜力不可行解（惩罚计算已向量化，可承受更大修复量）
            infeasible_sorted = sorted(infeasible_indices, key=lambda x: temp_ranks[x])
            repair_indices = infeasible_sorted[:min(30, len(infeasible_sorted))]

            for idx in repair_indices:
                original_pos = combined_pop[idx]
                repaired_pos, new_penalty = repair_qc_conflict(original_pos, vessels)
                new_objs, _ = calculate_objectives(repaired_pos, vessels)
                combined_pop[idx] = repaired_pos
                combined_objs[idx] = new_objs
                combined_penalties[idx] = new_penalty

        combined_fronts = fast_non_dominated_sort_cdp(combined_objs, combined_penalties)
        next_pop, next_objs, next_penalties = [], [], []
        
        for front in combined_fronts:
            if len(next_pop) + len(front) <= pop_size:
                for idx in front:
                    next_pop.append(combined_pop[idx])
                    next_objs.append(combined_objs[idx])
                    next_penalties.append(combined_penalties[idx])
            else:
                dists = crowding_distance(combined_objs, front)
                sorted_idx = np.argsort(dists)[::-1]  
                needed = pop_size - len(next_pop)
                for i in range(needed):
                    idx = front[sorted_idx[i]]
                    next_pop.append(combined_pop[idx])
                    next_objs.append(combined_objs[idx])
                    next_penalties.append(combined_penalties[idx])
                break


        pop = np.array(next_pop)
        objs = np.array(next_objs)
        penalties = np.array(next_penalties)


    final_fronts = fast_non_dominated_sort_cdp(objs, penalties)
    pareto_indices = final_fronts[0]
    return objs[pareto_indices], pop[pareto_indices], penalties[pareto_indices]




# =============================================================================
# 2. 认证路由
# =============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)

        user, message = authenticate_user(username, password)
        if user:
            login_user(user, remember=remember)
            if request.is_json:
                return jsonify({"success": True, "message": message})
            return redirect(url_for('index'))
        else:
            if request.is_json:
                return jsonify({"success": False, "error": message}), 401
            flash(message, 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        success, message = register_user(username, email, password)
        if success:
            if request.is_json:
                return jsonify({"success": True, "message": message})
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            if request.is_json:
                return jsonify({"success": False, "error": message}), 400
            flash(message, 'error')

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# =============================================================================
# 3. 港口配置API
# =============================================================================
@app.route('/api/port-config', methods=['GET'])
@login_required
def get_port_configs():
    configs = PortConfiguration.query.filter_by(user_id=current_user.id).order_by(PortConfiguration.created_at.desc()).all()
    return jsonify([{
        "id": c.id,
        "name": c.name,
        "totalBerths": c.total_berths,
        "berthConfig": c.get_berth_config(),
        "totalQcs": c.total_qcs,
        "qcEfficiency": c.qc_efficiency,
        "maxQcPerVessel": c.max_qc_per_vessel,
        "safetyInterval": c.safety_interval,
        "isActive": c.is_active,
        "createdAt": c.created_at.isoformat()
    } for c in configs])

@app.route('/api/port-config', methods=['POST'])
@login_required
def create_port_config():
    data = request.get_json()

    config = PortConfiguration(
        user_id=current_user.id,
        name=data.get('name', '默认配置'),
        total_berths=data.get('totalBerths', 17),
        total_qcs=data.get('totalQcs', 30),
        qc_efficiency=data.get('qcEfficiency', 48.0),
        max_qc_per_vessel=data.get('maxQcPerVessel', 3),
        per_qc_pow=data.get('perQcPow', 1000.0),
        qc_load_factor=data.get('qcLoadFactor', 0.5),
        auv_money=data.get('auvMoney', 10.0),
        qc_money=data.get('qcMoney', 30.0),
        co2_emission_factor=data.get('co2EmissionFactor', 3.15),
        safety_interval=data.get('safetyInterval', 0.167),
        is_active=False
    )
    config.set_berth_config(data.get('berthConfig', []))

    try:
        db.session.add(config)
        db.session.commit()
        return jsonify({"success": True, "id": config.id, "message": "配置创建成功"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/port-config/<int:config_id>', methods=['PUT'])
@login_required
def update_port_config(config_id):
    config = PortConfiguration.query.filter_by(id=config_id, user_id=current_user.id).first()
    if not config:
        return jsonify({"success": False, "error": "配置不存在"}), 404

    data = request.get_json()
    config.name = data.get('name', config.name)
    config.total_berths = data.get('totalBerths', config.total_berths)
    config.total_qcs = data.get('totalQcs', config.total_qcs)
    config.qc_efficiency = data.get('qcEfficiency', config.qc_efficiency)
    config.max_qc_per_vessel = data.get('maxQcPerVessel', config.max_qc_per_vessel)
    config.per_qc_pow = data.get('perQcPow', config.per_qc_pow)
    config.qc_load_factor = data.get('qcLoadFactor', config.qc_load_factor)
    config.auv_money = data.get('auvMoney', config.auv_money)
    config.qc_money = data.get('qcMoney', config.qc_money)
    config.co2_emission_factor = data.get('co2EmissionFactor', config.co2_emission_factor)
    config.safety_interval = data.get('safetyInterval', config.safety_interval)
    config.set_berth_config(data.get('berthConfig', config.get_berth_config()))

    try:
        db.session.commit()
        if config.is_active:
            load_active_port_config()
        return jsonify({"success": True, "id": config.id, "message": "配置已更新"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/port-config/<int:config_id>/activate', methods=['POST'])
@login_required
def activate_config(config_id):
    config = PortConfiguration.query.filter_by(id=config_id, user_id=current_user.id).first()
    if not config:
        return jsonify({"success": False, "error": "配置不存在"}), 404

    PortConfiguration.query.filter_by(user_id=current_user.id, is_active=True).update({"is_active": False})
    config.is_active = True

    try:
        db.session.commit()
        load_active_port_config()
        return jsonify({"success": True, "message": "配置已激活"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/port-config/<int:config_id>', methods=['DELETE'])
@login_required
def delete_config(config_id):
    config = PortConfiguration.query.filter_by(id=config_id, user_id=current_user.id).first()
    if not config:
        return jsonify({"success": False, "error": "配置不存在"}), 404

    if config.is_active:
        return jsonify({"success": False, "error": "无法删除激活的配置"}), 400

    try:
        db.session.delete(config)
        db.session.commit()
        return jsonify({"success": True, "message": "配置已删除"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

# =============================================================================
# 4. 船舶管理API
# =============================================================================
def minutes_to_time_str(hours):
    tot_min = int(round(hours * 60))
    return f"{(tot_min // 60) % 24:02d}:{tot_min % 60:02d}"


def parse_arrival_hours(raw):
    """把到港时间解析为小时浮点数。

    兼容 "08:30"、"2026-07-07 08:30"、"8.5"（小时）等写法，
    解析失败返回 0.0 而不是抛错，避免单条脏数据让整次调度失败。
    """
    text = str(raw or '').strip()
    match = re.search(r'(\d{1,2})\s*:\s*(\d{1,2})', text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        return (hour * 60 + minute) / 60.0
    try:
        return max(0.0, float(text))
    except ValueError:
        return 0.0

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/port-config')
@login_required
def port_config():
    return render_template('port_config.html')

@app.route('/history')
@login_required
def history():
    return render_template('history.html')

@app.route('/api/ships', methods=['GET'])
@login_required
def get_ships():
    ships = Ship.query.filter_by(user_id=current_user.id).order_by(Ship.created_at.asc()).all()
    return jsonify([s.to_dict() for s in ships])

@app.route('/api/ships/import', methods=['POST'])
@login_required
def import_csv():
    if 'file' not in request.files:
        return jsonify({"error": "没有发现上传的文件"}), 400

    file = request.files['file']
    try:
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except:
            df = pd.read_csv(file, encoding='gbk')

        df.columns = df.columns.str.strip()
        df = df.fillna("")

        name_col = [c for c in df.columns if 'id' in c.lower() or 'name' in c.lower()][0] if any('id' in c.lower() or 'name' in c.lower() for c in df.columns) else df.columns[0]
        time_col = [c for c in df.columns if 'time' in c.lower() or 'reachport' in c.lower()][0]
        teu_col = [c for c in df.columns if 'volume' in c.lower() or 'teu' in c.lower()][0]
        len_col = [c for c in df.columns if 'length' in c.lower() or '长' in c][0]
        aux_fuel_col = [c for c in df.columns if 'auxfuelcons' in c.lower()][0] if any('auxfuelcons' in c.lower() for c in df.columns) else None
        aux_pow_col = [c for c in df.columns if 'auxratedpow' in c.lower()][0] if any('auxratedpow' in c.lower() for c in df.columns) else None
        aux_lf_col = [c for c in df.columns if 'auxlf' in c.lower()][0] if any('auxlf' in c.lower() for c in df.columns) else None

        count = 0
        for _, row in df.iterrows():
            def safe_float(val, default_val=0.0):
                try: return float(val) if val != "" else default_val
                except: return default_val

            raw_fuel = safe_float(row[aux_fuel_col], 220.0) if aux_fuel_col else 220.0
            fuel_cons = raw_fuel / 1000.0 if raw_fuel > 10 else raw_fuel

            val_a = safe_float(row[aux_pow_col], 520.0) if aux_pow_col else 520.0
            val_b = safe_float(row[aux_lf_col], 0.55) if aux_lf_col else 0.55

            if val_a < 1.0 and val_b > 1.0:
                rated_pow = val_b
                load_factor = val_a
            else:
                rated_pow = val_a
                load_factor = val_b

            ship = Ship(
                user_id=current_user.id,
                name=str(row[name_col]),
                length=safe_float(row[len_col], 0.0),
                teu=safe_float(row[teu_col], 0.0),
                arrival_time=str(row[time_col]),
                aux_fuel_cons=fuel_cons,
                aux_rated_pow=rated_pow,
                aux_lf=load_factor
            )
            db.session.add(ship)
            count += 1

        db.session.commit()
        return jsonify({"message": f"成功读取并解析文件，共导入 {count} 条船舶记录"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"解析失败: {str(e)}"}), 500

@app.route('/api/ships/clear', methods=['POST'])
@login_required
def clear_ships():
    Ship.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"message": "已清空缓存池内所有待调度船舶"})

@app.route('/api/schedule', methods=['POST'])
@login_required
def schedule():
    ships = Ship.query.filter_by(user_id=current_user.id).all()
    if not ships:
        return jsonify({"error": "泊位待调度船舶为空，请先执行文件导入或数据模拟"}), 400

    load_active_port_config()

    try:
        req_data = request.get_json() or {}
        w_co2 = float(req_data.get('w_co2', 0.4))
        w_time = float(req_data.get('w_time', 0.3))
        w_cost = float(req_data.get('w_cost', 0.3))
        pop_size = int(req_data.get('pop_size', 60))
        max_iter = int(req_data.get('max_iter', 200))

        vessels = []
        for s in ships:
            vessels.append({
                'id': s.id, 'name': s.name, 'len': s.length, 'workload': s.teu,
                'eta': parse_arrival_hours(s.arrival_time),
                'auv1': s.aux_fuel_cons, 'auv2': s.aux_rated_pow, 'auv3': s.aux_lf
            })

        objs, positions, penalties = nsga2_solver(vessels, max_iter=max_iter, pop_size=pop_size)

        feasible = penalties == 0
        valid_objs = objs[feasible] if np.any(feasible) else objs
        valid_pos = positions[feasible] if np.any(feasible) else positions

        _, u_idx = np.unique(np.round(valid_objs, 1), axis=0, return_index=True)
        u_objs, u_pos = valid_objs[u_idx], valid_pos[u_idx]

        pref = np.array([w_co2, w_time, w_cost], dtype=float)
        pref_sum = pref.sum()
        pref = pref / pref_sum if pref_sum > 0 else np.array([1 / 3, 1 / 3, 1 / 3])
        # 权重为 0 时不能直接做除数，兜底一个极小值代表"几乎不关心该目标"
        pref = np.clip(pref, 1e-3, None)
        f_min, f_max = u_objs.min(axis=0), u_objs.max(axis=0)
        norm = (u_objs - f_min) / (f_max - f_min + 1e-6)
        best_idx = int(np.argmin(np.sqrt(np.sum((norm / pref) ** 2, axis=1))))

        pareto_solutions = []
        for idx in range(len(u_objs)):
            berths, b_times, qcs, qc_starts, departures = decode_solution(u_pos[idx], vessels)
            asgs = []
            for i, v in enumerate(vessels):
                berth_idx = int(berths[i])
                wait_h = float(b_times[i] - v['eta'])
                work_h = float(departures[i] - b_times[i])
                stay_h = float(departures[i] - v['eta'])
                # 单船指标拆解：等待期靠辅机供电，作业期靠岸桥耗电
                ship_co2 = (wait_h * PortConfig.co2_emission_factor * v['auv1'] * v['auv2'] * v['auv3']
                            + work_h * int(qcs[i]) * PortConfig.perQcPow * PortConfig.qc_load_factor)
                ship_cost = (wait_h * int(qcs[i]) * PortConfig.qc_money
                             + wait_h * PortConfig.auv_money * v['workload'])
                asgs.append({
                    "shipId": v['id'], "shipName": v['name'], "length": v['len'],
                    "teu": v['workload'],
                    "etaStr": minutes_to_time_str(v['eta']),
                    "etaHours": round(float(v['eta']), 4),
                    "berthIndex": berth_idx,
                    "berthName": berth_display_name(berth_idx),
                    "berthLength": berth_length_of(berth_idx),
                    "qcCount": int(qcs[i]), "qcStart": int(qc_starts[i]),
                    "qcEnd": int(qc_starts[i]) + int(qcs[i]) - 1,
                    "startTimeStr": minutes_to_time_str(b_times[i]),
                    "endTimeStr": minutes_to_time_str(departures[i]),
                    "startHours": round(float(b_times[i]), 4),
                    "endHours": round(float(departures[i]), 4),
                    "waitTimeMin": int(round(wait_h * 60)),
                    "workTimeMin": int(round(work_h * 60)),
                    "stayTimeMin": int(round(stay_h * 60)),
                    "shipCo2": round(ship_co2, 2),
                    "shipCost": round(ship_cost, 2)
                })

            total_wait = sum(a['waitTimeMin'] for a in asgs) / 60.0
            waited = [a for a in asgs if a['waitTimeMin'] > 0]
            pareto_solutions.append({
                "id": idx,
                "co2": round(float(u_objs[idx][0]), 2),
                "stayTime": round(float(u_objs[idx][1]), 2),
                "cost": round(float(u_objs[idx][2]), 2),
                "isRecommended": (idx == best_idx),
                "metrics": {
                    "shipCount": len(asgs),
                    "totalWaitHours": round(total_wait, 2),
                    "avgWaitMin": round(total_wait * 60 / len(asgs), 1) if asgs else 0.0,
                    "maxWaitMin": max((a['waitTimeMin'] for a in asgs), default=0),
                    "waitingShips": len(waited),
                    "avgStayHours": round(sum(a['stayTimeMin'] for a in asgs) / 60.0 / len(asgs), 2) if asgs else 0.0,
                    "totalQcHours": round(sum(a['workTimeMin'] * a['qcCount'] for a in asgs) / 60.0, 2),
                    "berthsUsed": len({a['berthIndex'] for a in asgs}),
                    "makespanHours": round(max((a['endHours'] for a in asgs), default=0.0), 2)
                },
                "assignments": asgs
            })

        active_config = PortConfiguration.query.filter_by(user_id=current_user.id, is_active=True).first()
        history = ScheduleHistory(
            user_id=current_user.id,
            port_config_id=active_config.id if active_config else None
        )
        history.set_ships_data([s.to_dict() for s in ships])
        history.set_solutions(pareto_solutions)
        history.set_weights({"w_co2": w_co2, "w_time": w_time, "w_cost": w_cost})
        db.session.add(history)
        db.session.commit()

        return jsonify({
            "solutions": pareto_solutions,
            "historyId": history.id,
            "portConfig": {
                "totalBerths": PortConfig.TOTAL_BERTHS,
                "totalQcs": PortConfig.TOTAL_QCS,
                "berthNames": list(PortConfig.BERTH_NAMES),
                "berthLengths": [float(x) for x in PortConfig.BERTH_LENGTHS],
                "configName": active_config.name if active_config else '系统缺省配置'
            },
            "info": f"寻优成功！计算得出 {len(pareto_solutions)} 个帕累托非支配调度策略。"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"核心进化算法抛出错误: {str(e)}"}), 500

# =============================================================================
# 5. 历史记录API
# =============================================================================
@app.route('/api/history', methods=['GET'])
@login_required
def get_schedule_history():
    histories = ScheduleHistory.query.filter_by(user_id=current_user.id).order_by(ScheduleHistory.created_at.desc()).all()

    result = []
    for h in histories:
        config_name = '默认配置'
        if h.port_config_id:
            config = PortConfiguration.query.get(h.port_config_id)
            if config:
                config_name = config.name

        result.append({
            'id': h.id,
            'createdAt': h.created_at.isoformat(),
            'shipsData': h.get_ships_data(),
            'solutions': h.get_solutions(),
            'weights': h.get_weights(),
            'configName': config_name
        })

    return jsonify(result)

@app.route('/api/history/<int:history_id>', methods=['GET'])
@login_required
def get_history_detail(history_id):
    history = ScheduleHistory.query.filter_by(id=history_id, user_id=current_user.id).first()

    if not history:
        return jsonify({"error": "记录不存在"}), 404

    config_name = '默认配置'
    if history.port_config_id:
        config = PortConfiguration.query.get(history.port_config_id)
        if config:
            config_name = config.name

    return jsonify({
        'id': history.id,
        'createdAt': history.created_at.isoformat(),
        'shipsData': history.get_ships_data(),
        'solutions': history.get_solutions(),
        'weights': history.get_weights(),
        'configName': config_name
    })

EXPORT_COLUMNS = [
    ('shipName', '船舶名称'),
    ('teu', '货量(TEU)'),
    ('length', '船长(m)'),
    ('etaStr', '预计到港'),
    ('berthName', '指派泊位'),
    ('berthLength', '泊位长度(m)'),
    ('qcRange', '岸桥区间'),
    ('qcCount', '岸桥数(台)'),
    ('startTimeStr', '靠泊时刻'),
    ('endTimeStr', '离泊时刻'),
    ('waitTimeMin', '等待(分钟)'),
    ('workTimeMin', '作业(分钟)'),
    ('stayTimeMin', '在港(分钟)'),
    ('shipCo2', '碳排放(kg)'),
    ('shipCost', '成本(元)'),
]


def build_schedule_workbook(history, solution):
    """把单个调度方案渲染为 xlsx 字节流：方案总览 + 逐船明细两张表"""
    weights = history.get_weights() or {}
    metrics = solution.get('metrics') or {}
    assignments = solution.get('assignments') or []

    rows = []
    for a in assignments:
        row = dict(a)
        row['qcRange'] = f"QC{int(a.get('qcStart', 0)):02d}-QC{int(a.get('qcEnd', 0)):02d}"
        rows.append([row.get(key, '') for key, _ in EXPORT_COLUMNS])

    detail_df = pd.DataFrame(rows, columns=[label for _, label in EXPORT_COLUMNS])

    summary_pairs = [
        ('调度记录编号', history.id),
        ('生成时间', history.created_at.strftime('%Y-%m-%d %H:%M:%S')),
        ('方案编号', f"策略 #{int(solution.get('id', 0)) + 1}"),
        ('是否系统推荐', '是' if solution.get('isRecommended') else '否'),
        ('目标一 · 碳排放总量(kg)', solution.get('co2')),
        ('目标二 · 总在港停留(小时)', solution.get('stayTime')),
        ('目标三 · 联合调度成本(元)', solution.get('cost')),
        ('碳排放权重', weights.get('w_co2')),
        ('停留时间权重', weights.get('w_time')),
        ('成本权重', weights.get('w_cost')),
        ('参与调度船舶数', metrics.get('shipCount', len(assignments))),
        ('启用泊位数', metrics.get('berthsUsed')),
        ('平均等待(分钟)', metrics.get('avgWaitMin')),
        ('最长等待(分钟)', metrics.get('maxWaitMin')),
        ('发生等待的船舶数', metrics.get('waitingShips')),
        ('平均在港(小时)', metrics.get('avgStayHours')),
        ('岸桥总工时(台·小时)', metrics.get('totalQcHours')),
        ('全部作业完成时刻(小时)', metrics.get('makespanHours')),
    ]
    summary_df = pd.DataFrame(summary_pairs, columns=['指标项', '数值'])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='方案总览', index=False)
        detail_df.to_excel(writer, sheet_name='逐船调度明细', index=False)

        for sheet_name, frame in (('方案总览', summary_df), ('逐船调度明细', detail_df)):
            worksheet = writer.sheets[sheet_name]
            for col_idx, column in enumerate(frame.columns, start=1):
                longest = max([len(str(column))] + [len(str(v)) for v in frame[column].tolist()] or [0])
                worksheet.column_dimensions[
                    worksheet.cell(row=1, column=col_idx).column_letter
                ].width = min(32, max(10, longest + 4))
            worksheet.freeze_panes = 'A2'

    buffer.seek(0)
    return buffer


@app.route('/api/history/<int:history_id>/export', methods=['GET'])
@login_required
def export_history_solution(history_id):
    """导出指定历史记录中某个方案的逐船调度表（xlsx）"""
    history = ScheduleHistory.query.filter_by(id=history_id, user_id=current_user.id).first()
    if not history:
        return jsonify({"error": "记录不存在"}), 404

    solutions = history.get_solutions() or []
    if not solutions:
        return jsonify({"error": "该记录没有可导出的方案"}), 400

    raw_id = request.args.get('solution')
    if raw_id is None:
        solution = next((s for s in solutions if s.get('isRecommended')), solutions[0])
    else:
        try:
            wanted = int(raw_id)
        except ValueError:
            return jsonify({"error": "方案编号无效"}), 400
        solution = next((s for s in solutions if int(s.get('id', -1)) == wanted), None)
        if solution is None:
            return jsonify({"error": "方案编号不存在"}), 404

    try:
        buffer = build_schedule_workbook(history, solution)
    except Exception as e:
        return jsonify({"error": f"导出失败: {str(e)}"}), 500

    filename = f"schedule_{history.id}_plan{int(solution.get('id', 0)) + 1}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/history/<int:history_id>', methods=['DELETE'])
@login_required
def delete_history(history_id):
    history = ScheduleHistory.query.filter_by(id=history_id, user_id=current_user.id).first()

    if not history:
        return jsonify({"success": False, "error": "记录不存在"}), 404

    try:
        db.session.delete(history)
        db.session.commit()
        return jsonify({"success": True, "message": "历史记录已删除"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
