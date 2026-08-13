from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model, UserMixin):
    """用户模型"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(20), default='operator')  # admin or operator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    port_configs = db.relationship('PortConfiguration', backref='creator', lazy=True, cascade='all, delete-orphan')
    ships = db.relationship('Ship', backref='owner', lazy=True, cascade='all, delete-orphan')
    schedule_histories = db.relationship('ScheduleHistory', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.username}>'


class PortConfiguration(db.Model):
    """泊位配置模型"""
    __tablename__ = 'port_configurations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    total_berths = db.Column(db.Integer, nullable=False)
    berth_config = db.Column(db.Text, nullable=False)  # JSON格式: [{"id": 1, "length": 300, "name": "B01"}, ...]
    total_qcs = db.Column(db.Integer, nullable=False)
    qc_efficiency = db.Column(db.Float, default=48.0)
    max_qc_per_vessel = db.Column(db.Integer, default=3)
    per_qc_pow = db.Column(db.Float, default=1000.0)
    qc_load_factor = db.Column(db.Float, default=0.5)
    auv_money = db.Column(db.Float, default=10.0)
    qc_money = db.Column(db.Float, default=30.0)
    co2_emission_factor = db.Column(db.Float, default=3.15)
    safety_interval = db.Column(db.Float, default=0.167)  # 10分钟 = 10/60小时
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_berth_config(self):
        """解析JSON格式的泊位配置"""
        return json.loads(self.berth_config)

    def set_berth_config(self, config_list):
        """设置泊位配置为JSON"""
        self.berth_config = json.dumps(config_list)

    def get_berth_lengths(self):
        """返回泊位长度列表"""
        config = self.get_berth_config()
        return [berth['length'] for berth in config]

    def __repr__(self):
        return f'<PortConfiguration {self.name} (Active: {self.is_active})>'


class Ship(db.Model):
    """船舶模型"""
    __tablename__ = 'ships'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    length = db.Column(db.Float, nullable=False)
    teu = db.Column(db.Float, nullable=False)  # 货物量
    arrival_time = db.Column(db.String(10), nullable=False)  # 格式: HH:MM
    aux_fuel_cons = db.Column(db.Float, nullable=False)  # kg/kWh
    aux_rated_pow = db.Column(db.Float, nullable=False)  # kW
    aux_lf = db.Column(db.Float, nullable=False)  # 负载因子 0-1
    main_fuel_cons = db.Column(db.Float, default=0.0)
    main_rated_pow = db.Column(db.Float, default=0.0)
    main_lf = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'length': self.length,
            'teu': self.teu,
            'arrivalTime': self.arrival_time,
            'auxFuelCons': self.aux_fuel_cons,
            'auxRatedPow': self.aux_rated_pow,
            'auxLF': self.aux_lf,
            'mainFuelCons': self.main_fuel_cons,
            'mainRatedPow': self.main_rated_pow,
            'mainLF': self.main_lf
        }

    def __repr__(self):
        return f'<Ship {self.name}>'


class ScheduleHistory(db.Model):
    """调度历史记录模型"""
    __tablename__ = 'schedule_histories'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    port_config_id = db.Column(db.Integer, db.ForeignKey('port_configurations.id'), nullable=True)
    ships_data = db.Column(db.Text, nullable=False)  # JSON格式的船舶数据
    solutions = db.Column(db.Text, nullable=False)  # JSON格式的Pareto方案
    weights = db.Column(db.Text, nullable=False)  # JSON格式的权重配置
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    port_config = db.relationship('PortConfiguration', backref='histories', lazy=True)

    def get_ships_data(self):
        """解析船舶数据"""
        return json.loads(self.ships_data)

    def set_ships_data(self, data):
        """设置船舶数据"""
        self.ships_data = json.dumps(data)

    def get_solutions(self):
        """解析调度方案"""
        return json.loads(self.solutions)

    def set_solutions(self, solutions):
        """设置调度方案"""
        self.solutions = json.dumps(solutions)

    def get_weights(self):
        """解析权重"""
        return json.loads(self.weights)

    def set_weights(self, weights):
        """设置权重"""
        self.weights = json.dumps(weights)

    def __repr__(self):
        return f'<ScheduleHistory {self.id} at {self.created_at}>'
