"""Dimensionally consistent, auditable objectives for the berth/QC scheduler.

Accounting boundary: vessel auxiliary engines throughout port stay + QC electricity.
No change to the scheduling constraints or linear handling-time model.
"""
import math
import numpy as np

MODEL_VERSION = 'physical-v2'
DEFAULT_PARAMETERS = {
    'gridEmissionFactor': 0.5306,  # kg CO2/kWh; China national 2023 average (MEE).
    'electricityPrice': 0.8,      # CNY/kWh; illustrative scenario, not a tariff quote.
    'qcCoordinationCost': 20.0,   # CNY/(QC pair h); illustrative scenario, calibrate locally.
    'serviceAuxRatio': 1.0,      # service/wait auxiliary load ratio; no shore power assumed.
}
PARAMETER_UNITS = {
    'gridEmissionFactor': 'kgCO2/kWh', 'electricityPrice': 'CNY/kWh',
    'qcCoordinationCost': 'CNY/(QC pair h)', 'serviceAuxRatio': 'dimensionless',
}


def validate_parameters(values=None):
    result = dict(DEFAULT_PARAMETERS)
    if values is not None and not isinstance(values, dict):
        raise ValueError('目标核算参数必须是对象')
    for key, value in (values or {}).items():
        if key not in result:
            raise ValueError(f'未知目标核算参数: {key}')
        try:
            number = float(value)
        except (ValueError, TypeError):
            raise ValueError(f'{key} 必须为非负有限数') from None
        if not math.isfinite(number) or number < 0:
            raise ValueError(f'{key} 必须为非负有限数')
        result[key] = number
    return result


def objective_breakdown(vessels, starts, departures, qcs, config):
    """Return raw objectives [kg CO2, vessel h, CNY] and per-vessel components.

    Constraint violations are deliberately kept out of physical quantities.
    auv_money: cargo waiting opportunity cost CNY/(TEU h).
    qc_money: operating equipment charge CNY/(QC h), excluding electricity.
    qcCoordinationCost: coordination/management allowance per concurrent QC pair h;
    this objective term does not reduce productivity or create a new constraint.
    """
    parameters = validate_parameters(getattr(config, 'OBJECTIVE_PARAMETERS', None))
    rows = []
    for i, vessel in enumerate(vessels):
        wait = max(0.0, float(starts[i]) - float(vessel['eta']))
        work = max(0.0, float(departures[i]) - float(starts[i]))
        qc = int(qcs[i])
        aux_rate = float(vessel['auv1']) * float(vessel['auv2']) * float(vessel['auv3'])
        waiting_carbon = wait * aux_rate * config.co2_emission_factor
        service_carbon = work * parameters['serviceAuxRatio'] * aux_rate * config.co2_emission_factor
        energy = work * qc * config.perQcPow * config.qc_load_factor
        grid_carbon = energy * parameters['gridEmissionFactor']
        waiting_cost = wait * config.auv_money * float(vessel['workload'])
        operating_cost = work * qc * config.qc_money
        electricity_cost = energy * parameters['electricityPrice']
        coordination_cost = work * qc * (qc - 1) / 2 * parameters['qcCoordinationCost']
        rows.append({
            'waitingCarbon': waiting_carbon, 'serviceCarbon': service_carbon,
            'electricityCarbon': grid_carbon, 'qcEnergyKwh': energy,
            'waitingCost': waiting_cost, 'qcOperatingCost': operating_cost,
            'electricityCost': electricity_cost, 'coordinationCost': coordination_cost,
            'co2': waiting_carbon + service_carbon + grid_carbon,
            'stayTime': wait + work,
            'cost': waiting_cost + operating_cost + electricity_cost + coordination_cost,
        })
    keys = tuple(rows[0]) if rows else ('co2', 'stayTime', 'cost')
    totals = {key: math.fsum(row[key] for row in rows) for key in keys}
    return np.array([totals['co2'], totals['stayTime'], totals['cost']]), rows, totals


def preference_scores(objectives, weights):
    """Weighted Euclidean distance to the observed ideal; smaller is better.

    The front's observed min/max are not global optimality bounds.
    Constant columns contribute zero; zero weights are truly ignored.
    """
    values = np.asarray(objectives, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] != 3:
        raise ValueError('至少需要一个包含三项目标的方案')
    if weights.shape != (3,) or not np.all(np.isfinite(weights)) or np.any(weights < 0):
        raise ValueError('目标权重必须为三个非负有限数')
    if not np.all(np.isfinite(values)):
        raise ValueError('目标函数产生了非有限值')
    weights = weights / weights.sum() if weights.sum() > 0 else np.full(3, 1 / 3)
    low, high = values.min(axis=0), values.max(axis=0)
    span = high - low
    normalized = np.divide(values - low, span, out=np.zeros_like(values), where=span > 1e-12)
    return np.sqrt((normalized ** 2 * weights).sum(axis=1)), normalized, weights
