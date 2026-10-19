"""Frozen pure algorithm snapshot of app.py; no Flask/database imports. Generated 2026-10-16."""

import numpy as np

from scheduling_objectives import DEFAULT_PARAMETERS, objective_breakdown

class PortConfig:
    OBJECTIVE_PARAMETERS = dict(DEFAULT_PARAMETERS)
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

    # Revalidate the encoded candidate, including the existing 36-hour raw-time clipping.
    # This changes no constraint; it prevents a pre-encoding penalty from labeling another schedule.
    rb, rt, rq, rs, rd = decode_solution(repaired_pos, vessels)
    new_penalty = calculate_penalty(num_vessels, rb, rt, rd, rs, rq, PortConfig.TOTAL_QCS)

    return repaired_pos, new_penalty

def calculate_objectives(position, vessels):
    berths, berthing_times, assigned_qcs, qc_start_idx, departures = decode_solution(position, vessels)
    num_vessels = len(vessels)
    penalty = calculate_penalty(num_vessels, berths, berthing_times, departures, qc_start_idx, assigned_qcs, PortConfig.TOTAL_QCS)
    objectives, _, _ = objective_breakdown(vessels, berthing_times, departures, assigned_qcs, PortConfig)
    return objectives, penalty

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

    # Two feasible anchors use disjoint, permanently ordered QC segments.
    # The berth decoder serializes ships on each berth; no constraint is relaxed.
    for anchor, qc_count in enumerate((PortConfig.MAX_QC_PER_VESSEL, 1)):
        if anchor >= pop_size:
            break
        active_berths = min(PortConfig.TOTAL_BERTHS, PortConfig.TOTAL_QCS // qc_count)
        anchor_berths = np.arange(num_vessels) % active_berths
        pop[anchor, :num_vessels] = anchor_berths
        pop[anchor, num_vessels:2 * num_vessels] = etas
        pop[anchor, 2 * num_vessels:3 * num_vessels] = qc_count
        pop[anchor, 3 * num_vessels:] = anchor_berths * qc_count + 1

    eval_results = [calculate_objectives(p, vessels) for p in pop]
    objs = np.array([res[0] for res in eval_results])
    penalties = np.array([res[1] for res in eval_results])

    # 初始种群整体修复一次，让算法从可行/接近可行的解开始迭代，而不是从头进化出来
    for i in range(pop_size):
        if penalties[i] > 0:
            repaired_pos, new_penalty = repair_qc_conflict(pop[i], vessels)
            new_objs, new_penalty = calculate_objectives(repaired_pos, vessels)
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
                new_objs, new_penalty = calculate_objectives(repaired_pos, vessels)
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
