# optimizer_lp.py - hard-target lighting optimizer
#
# The optimizer is intentionally pure math/control preparation:
# - main.py decides occupancy, reads MQTT, and supplies calibration data.
# - this file builds lamp targets/effective gains and solves the LP.
#
# Solver variables:
#   x = [duty_1 ... duty_N]
#
# Constraint per controlled zone/sensor:
#   sum_j(gain_ij * duty_j / 100) >= max(target_i - daylight_i, 0)
#
# Minimum-energy LP objective:
#   minimize sum_j(power_j * duty_j / 100)
#
# Uniform optimization objective:
#   minimize weighted power + weighted duty variance + weighted duty change

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import linprog, minimize


DEFAULT_POWER_WEIGHTS = [36, 36, 36, 100, 40, 40, 30, 36, 36]


def _get_power_weights(
    num_panels: int,
    panel_power_watts: Optional[List[float]] = None,
) -> np.ndarray:
    if panel_power_watts is not None:
        power = np.array(panel_power_watts, dtype=float)
        if len(power) != num_panels:
            raise ValueError("panel_power_watts length must match number of panels.")
        return power

    if num_panels == len(DEFAULT_POWER_WEIGHTS):
        return np.array(DEFAULT_POWER_WEIGHTS, dtype=float)

    return np.ones(num_panels, dtype=float)


def _validate_inputs(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    current = np.array(current_lux, dtype=float)
    target = np.array(target_lux, dtype=float)
    gains = np.array(gain_matrix, dtype=float)

    if current.shape != target.shape:
        raise ValueError("current_lux and target_lux must have the same length.")

    if gains.ndim != 2:
        raise ValueError("gain_matrix must be a 2D matrix: sensors x panels.")

    if gains.shape[0] != len(current):
        raise ValueError("gain_matrix rows must match number of sensors.")

    if np.any(target < 0):
        raise ValueError("target_lux values must be non-negative.")

    return current, target, gains


def _calculate_power_watts(duties: np.ndarray, power_weights: np.ndarray) -> float:
    return float(np.sum(power_weights * (duties / 100.0)))


def _get_allowed_panel_indices(
    num_panels: int,
    allowed_panel_indices: Optional[List[int]] = None,
) -> List[int]:
    if allowed_panel_indices is None:
        return list(range(num_panels))

    return sorted(
        {
            int(index)
            for index in allowed_panel_indices
            if 0 <= int(index) < num_panels
        }
    )


def _mean_squared(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0

    return float(np.mean(values * values))


def get_allowed_panels_for_active_sensors(
    active_sensor_ids: List[str],
    panel_ids: List[str],
    efficient_panels_by_sensor: Dict[str, List[str]],
) -> List[str]:
    available_panels = set(panel_ids)
    allowed = set()

    for sensor_id in active_sensor_ids:
        allowed.update(
            panel_id
            for panel_id in efficient_panels_by_sensor.get(sensor_id, [])
            if panel_id in available_panels
        )

    return [panel_id for panel_id in panel_ids if panel_id in allowed]


def build_effective_gain_matrix(
    gain_matrix: List[List[float]],
    panel_ids: List[str],
    allowed_panel_ids: List[str],
) -> List[List[float]]:
    allowed = set(allowed_panel_ids)
    effective = []

    for row in gain_matrix:
        effective.append(
            [
                float(value) if panel_ids[index] in allowed else 0.0
                for index, value in enumerate(row)
            ]
        )

    return effective


def build_presence_control_problem(
    sensor_ids: List[str],
    panel_ids: List[str],
    gain_matrix: List[List[float]],
    daylight_lux: List[float],
    active_sensor_ids: List[str],
    occupied_target_lux: Dict[str, float],
    unoccupied_target_lux: Dict[str, float],
    efficient_panels_by_sensor: Dict[str, List[str]],
    default_occupied_lux: float = 300.0,
    default_unoccupied_lux: float = 0.0,
) -> Dict[str, Any]:
    """
    Builds the LP inputs for presence/manual-zone control.

    Inefficient panels are kept in the matrix but their gains are set to zero.
    This preserves panel order and output duty mapping while preventing the LP
    from using panels that should not serve the active zones.
    """
    if len(sensor_ids) != len(daylight_lux):
        raise ValueError("daylight_lux length must match sensor_ids length.")

    active_sensor_set = set(active_sensor_ids)
    allowed_panel_ids = get_allowed_panels_for_active_sensors(
        active_sensor_ids=active_sensor_ids,
        panel_ids=panel_ids,
        efficient_panels_by_sensor=efficient_panels_by_sensor,
    )
    effective_gain_matrix = build_effective_gain_matrix(
        gain_matrix=gain_matrix,
        panel_ids=panel_ids,
        allowed_panel_ids=allowed_panel_ids,
    )

    lamp_targets = []
    total_targets = []
    efficient_capacities = []
    rows = []

    for sensor_index, sensor_id in enumerate(sensor_ids):
        is_active = sensor_id in active_sensor_set
        target = (
            float(occupied_target_lux.get(sensor_id, default_occupied_lux))
            if is_active
            else float(unoccupied_target_lux.get(sensor_id, default_unoccupied_lux))
        )
        daylight = max(0.0, float(daylight_lux[sensor_index]))
        required_lamp_lux = max(0.0, target - daylight)
        efficient_capacity = float(sum(effective_gain_matrix[sensor_index]))
        lamp_target = min(required_lamp_lux, efficient_capacity)

        lamp_targets.append(round(lamp_target, 2))
        total_targets.append(round(daylight + lamp_target, 2))
        efficient_capacities.append(round(efficient_capacity, 2))
        rows.append(
            {
                "Sensor": sensor_id,
                "Active": bool(is_active),
                "Target Lux": round(target, 2),
                "Daylight Lux": round(daylight, 2),
                "Efficient Capacity Lux": round(efficient_capacity, 2),
                "Lamp Target Lux": round(lamp_target, 2),
                "Total Target Used": round(daylight + lamp_target, 2),
            }
        )

    return {
        "active_sensor_ids": list(active_sensor_ids),
        "allowed_panel_ids": allowed_panel_ids,
        "effective_gain_matrix": effective_gain_matrix,
        "lamp_targets": lamp_targets,
        "total_targets": total_targets,
        "efficient_capacities": efficient_capacities,
        "rows": rows,
    }


def solve_lighting_lp_decimal_with_diagnostics(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
    min_duty: int = 0,
    max_duty: int = 100,
    panel_power_watts: Optional[List[float]] = None,
    **_unused_compat_kwargs: Any,
) -> Dict[str, Any]:
    """
    Hard-target LP.

    Solves:
        minimize sum(power_j * duty_j / 100)
        subject to gain_matrix @ duty/100 >= target_lux - current_lux
        min_duty <= duty_j <= max_duty
    """
    current, target, gains = _validate_inputs(current_lux, target_lux, gain_matrix)
    num_sensors, num_panels = gains.shape
    power_weights = _get_power_weights(num_panels, panel_power_watts)
    required_lux = np.maximum(target - current, 0)

    if np.all(required_lux <= 0):
        duties = np.zeros(num_panels, dtype=float)
        estimated_lux = current.copy()
        return {
            "success": True,
            "message": "No additional light required.",
            "duties_decimal": np.round(duties, 2).tolist(),
            "estimated_lux": np.rint(estimated_lux).astype(int).tolist(),
            "power_watts": 0.0,
            "objective_value": 0.0,
        }

    c = power_weights / 100.0
    A_ub = -gains / 100.0
    b_ub = -required_lux
    bounds = [(min_duty, max_duty) for _ in range(num_panels)]

    result = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
    )

    if not result.success:
        duties = np.zeros(num_panels, dtype=float)
        estimated_lux = current.copy()
        return {
            "success": False,
            "message": result.message,
            "duties_decimal": np.round(duties, 2).tolist(),
            "estimated_lux": np.rint(estimated_lux).astype(int).tolist(),
            "power_watts": 0.0,
            "objective_value": None,
        }

    duties = np.clip(result.x, min_duty, max_duty)
    estimated_lux = current + gains @ (duties / 100.0)
    power_watts = _calculate_power_watts(duties, power_weights)

    return {
        "success": True,
        "message": result.message,
        "duties_decimal": np.round(duties, 2).tolist(),
        "estimated_lux": np.rint(estimated_lux).astype(int).tolist(),
        "power_watts": round(power_watts, 2),
        "objective_value": round(float(result.fun), 4),
    }


def solve_lighting_lp_decimal(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
    min_duty: int = 0,
    max_duty: int = 100,
    panel_power_watts: Optional[List[float]] = None,
    **compat_kwargs: Any,
) -> List[float]:
    result = solve_lighting_lp_decimal_with_diagnostics(
        current_lux=current_lux,
        target_lux=target_lux,
        gain_matrix=gain_matrix,
        min_duty=min_duty,
        max_duty=max_duty,
        panel_power_watts=panel_power_watts,
        **compat_kwargs,
    )

    return result["duties_decimal"]


def solve_uniform_lighting_optimization_decimal_with_diagnostics(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
    min_duty: int = 0,
    max_duty: int = 100,
    panel_power_watts: Optional[List[float]] = None,
    current_duties: Optional[List[float]] = None,
    allowed_panel_indices: Optional[List[int]] = None,
    weight_power: float = 1.0,
    weight_uniformity: float = 0.02,
    weight_change: float = 0.005,
    **_unused_compat_kwargs: Any,
) -> Dict[str, Any]:
    """
    Hard-target uniform-duty optimization.

    Solves:
        minimize
            weight_power * panel_power
          + weight_uniformity * duty_variance_on_allowed_panels
          + weight_change * duty_change_from_current_on_allowed_panels

        subject to gain_matrix @ duty/100 >= target_lux - current_lux

    Non-allowed panels are forced to zero. Duty uniformity is calculated only
    across the allowed active panels so inactive zero-duty panels do not pull
    the active zone toward darkness.
    """
    current, target, gains = _validate_inputs(current_lux, target_lux, gain_matrix)
    num_sensors, num_panels = gains.shape
    power_weights = _get_power_weights(num_panels, panel_power_watts)
    allowed_indices = _get_allowed_panel_indices(num_panels, allowed_panel_indices)
    allowed_set = set(allowed_indices)

    if current_duties is None:
        current_duty_vector = np.zeros(num_panels, dtype=float)
    else:
        current_duty_vector = np.array(current_duties, dtype=float)
        if len(current_duty_vector) != num_panels:
            raise ValueError("current_duties length must match number of panels.")

    required_lux = np.maximum(target - current, 0)

    if np.all(required_lux <= 0) or not allowed_indices:
        duties = np.zeros(num_panels, dtype=float)
        estimated_lux = current.copy()
        return {
            "success": True,
            "message": "No additional light required.",
            "duties_decimal": np.round(duties, 2).tolist(),
            "estimated_lux": np.rint(estimated_lux).astype(int).tolist(),
            "power_watts": 0.0,
            "objective_value": 0.0,
            "uniformity_value": 0.0,
            "change_value": 0.0,
            "fallback_used": False,
        }

    lp_seed = solve_lighting_lp_decimal_with_diagnostics(
        current_lux=current_lux,
        target_lux=target_lux,
        gain_matrix=gain_matrix,
        min_duty=min_duty,
        max_duty=max_duty,
        panel_power_watts=panel_power_watts,
    )

    if lp_seed.get("success"):
        x0 = np.array(lp_seed["duties_decimal"], dtype=float)
    else:
        x0 = np.clip(current_duty_vector, min_duty, max_duty)

    for index in range(num_panels):
        if index not in allowed_set:
            x0[index] = 0.0

    bounds = [
        (min_duty, max_duty) if index in allowed_set else (0.0, 0.0)
        for index in range(num_panels)
    ]

    safe_weight_power = max(0.0, float(weight_power))
    safe_weight_uniformity = max(0.0, float(weight_uniformity))
    safe_weight_change = max(0.0, float(weight_change))

    def objective(duties: np.ndarray) -> float:
        allowed_duties = duties[allowed_indices]
        duty_mean = float(np.mean(allowed_duties)) if allowed_duties.size else 0.0
        uniformity = _mean_squared(allowed_duties - duty_mean)
        change = _mean_squared(allowed_duties - current_duty_vector[allowed_indices])
        power_watts = _calculate_power_watts(duties, power_weights)
        return (
            safe_weight_power * power_watts
            + safe_weight_uniformity * uniformity
            + safe_weight_change * change
        )

    constraints = [
        {
            "type": "ineq",
            "fun": lambda duties: current + gains @ (duties / 100.0) - target,
        }
    ]

    result = minimize(
        objective,
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 300, "ftol": 1e-6},
    )

    fallback_used = False
    if result.success:
        duties = np.clip(result.x, min_duty, max_duty)
        message = result.message
        objective_value = float(result.fun)
    elif lp_seed.get("success"):
        duties = np.array(lp_seed["duties_decimal"], dtype=float)
        message = f"Uniform optimizer failed; used LP fallback. {result.message}"
        objective_value = objective(duties)
        fallback_used = True
    else:
        duties = np.zeros(num_panels, dtype=float)
        message = result.message
        objective_value = None

    estimated_lux = current + gains @ (duties / 100.0)
    allowed_duties = duties[allowed_indices]
    duty_mean = float(np.mean(allowed_duties)) if allowed_duties.size else 0.0
    uniformity = _mean_squared(allowed_duties - duty_mean)
    change = _mean_squared(allowed_duties - current_duty_vector[allowed_indices])
    power_watts = _calculate_power_watts(duties, power_weights)

    return {
        "success": bool(result.success or fallback_used),
        "message": message,
        "duties_decimal": np.round(duties, 2).tolist(),
        "estimated_lux": np.rint(estimated_lux).astype(int).tolist(),
        "power_watts": round(power_watts, 2),
        "objective_value": round(objective_value, 4) if objective_value is not None else None,
        "uniformity_value": round(uniformity, 4),
        "change_value": round(change, 4),
        "fallback_used": fallback_used,
    }


def solve_uniform_lighting_optimization_decimal(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
    min_duty: int = 0,
    max_duty: int = 100,
    panel_power_watts: Optional[List[float]] = None,
    current_duties: Optional[List[float]] = None,
    allowed_panel_indices: Optional[List[int]] = None,
    weight_power: float = 1.0,
    weight_uniformity: float = 0.02,
    weight_change: float = 0.005,
    **compat_kwargs: Any,
) -> List[float]:
    result = solve_uniform_lighting_optimization_decimal_with_diagnostics(
        current_lux=current_lux,
        target_lux=target_lux,
        gain_matrix=gain_matrix,
        min_duty=min_duty,
        max_duty=max_duty,
        panel_power_watts=panel_power_watts,
        current_duties=current_duties,
        allowed_panel_indices=allowed_panel_indices,
        weight_power=weight_power,
        weight_uniformity=weight_uniformity,
        weight_change=weight_change,
        **compat_kwargs,
    )

    return result["duties_decimal"]


def integerize_duties_ceil(duties_decimal: List[float]) -> List[int]:
    duties = np.array(duties_decimal, dtype=float)
    duties = np.ceil(duties).astype(int)
    return duties.tolist()


def solve_lighting_lp(
    current_lux: List[float],
    target_lux: List[float],
    gain_matrix: List[List[float]],
    min_duty: int = 0,
    max_duty: int = 100,
    panel_power_watts: Optional[List[float]] = None,
    **compat_kwargs: Any,
) -> List[int]:
    duties_decimal = solve_lighting_lp_decimal(
        current_lux=current_lux,
        target_lux=target_lux,
        gain_matrix=gain_matrix,
        min_duty=min_duty,
        max_duty=max_duty,
        panel_power_watts=panel_power_watts,
        **compat_kwargs,
    )

    return integerize_duties_ceil(duties_decimal)


def estimate_lux_after_control(
    current_lux: List[float],
    gain_matrix: List[List[float]],
    duties: List[float],
) -> List[int]:
    current = np.array(current_lux, dtype=float)
    gains = np.array(gain_matrix, dtype=float)
    duty_vector = np.array(duties, dtype=float)

    estimated = current + gains @ (duty_vector / 100.0)
    return np.rint(estimated).astype(int).tolist()


def estimate_panel_contribution(
    gain_matrix: List[List[float]],
    current_duties: List[float],
) -> List[float]:
    gains = np.array(gain_matrix, dtype=float)
    duty_vector = np.array(current_duties, dtype=float)

    contribution = gains @ (duty_vector / 100.0)
    return np.round(contribution, 2).tolist()


def estimate_ambient_lux(
    measured_lux: List[float],
    gain_matrix: List[List[float]],
    current_duties: List[float],
) -> List[float]:
    measured = np.array(measured_lux, dtype=float)
    contribution = np.array(
        estimate_panel_contribution(gain_matrix, current_duties),
        dtype=float,
    )

    ambient = measured - contribution
    ambient = np.maximum(ambient, 0)
    return np.round(ambient, 2).tolist()


def load_calibration(path: str = "calibration.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    calibration = load_calibration("calibration.json")
    panel_ids = calibration["panel_ids"]
    sensor_ids = calibration["sensor_ids"]
    panel_labels = calibration.get("panel_labels", {})
    sensor_labels = calibration.get("sensor_labels", {})
    gain_matrix = calibration["gain_matrix"]

    measured_lux = [300 for _ in sensor_ids]
    current_duties = [0 for _ in panel_ids]
    ambient_lux = estimate_ambient_lux(
        measured_lux=measured_lux,
        gain_matrix=gain_matrix,
        current_duties=current_duties,
    )
    target_lux = [500 for _ in sensor_ids]

    result = solve_lighting_lp_decimal_with_diagnostics(
        current_lux=ambient_lux,
        target_lux=target_lux,
        gain_matrix=gain_matrix,
    )
    duties_decimal = result["duties_decimal"]
    duties_integer = integerize_duties_ceil(duties_decimal)
    estimated_lux = estimate_lux_after_control(
        current_lux=ambient_lux,
        gain_matrix=gain_matrix,
        duties=duties_integer,
    )

    print("\n=== Hard LP Test Using calibration.json ===\n")
    print("LP success:", result["success"])
    print("Message:", result["message"])
    print("Estimated power:", result["power_watts"], "W")
    print("Objective value:", result["objective_value"])

    print("\nSensors:")
    for i, sensor_id in enumerate(sensor_ids):
        label = sensor_labels.get(sensor_id, sensor_id)
        print(
            f"  {label}: measured={measured_lux[i]} lux, "
            f"ambient={ambient_lux[i]} lux, "
            f"target={target_lux[i]} lux, "
            f"estimated_after_integer={estimated_lux[i]} lux"
        )

    print("\nCalculated panel duties:")
    for i, panel_id in enumerate(panel_ids):
        label = panel_labels.get(panel_id, panel_id)
        print(
            f"  {label}: decimal={duties_decimal[i]}%, "
            f"integer={duties_integer[i]}%"
        )
