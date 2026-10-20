import streamlit as st
import json
import time
import os
import threading
import pandas as pd

from mqtt_backend import MQTTBackend
from calibration import CalibrationRunner
from optimizer_lp import (
    solve_lighting_lp_decimal,
    solve_uniform_lighting_optimization_decimal_with_diagnostics,
    integerize_duties_ceil,
    estimate_lux_after_control,
    estimate_panel_contribution,
    estimate_ambient_lux,
    build_presence_control_problem,
    get_allowed_panels_for_active_sensors,
)

from ui_style import (
    apply_ui_style,
    render_app_header,
    render_dashboard_summary,
    render_fixed_refresh,
    render_fixed_power_watch,
    device_info_row,
    calibration_start_controls,
    calibration_status_card,
    calibration_step_list,
    calibration_result_grid,
    style_gain_matrix_by_sensor,
    style_ambient_lux_by_value,
    calibration_problem_card,
    calibration_history_card,
    auto_mode_panel,
)

from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="Lighting Controller",
    layout="wide"
)

apply_ui_style()
render_fixed_refresh()


PANEL_LABELS = {
    "esp-4923B2": "Panel 1",
    "esp-61DD37": "Panel 2",
    "esp-E05DAC": "Panel 3",
    "esp-F88DED": "Panel 4",
    "esp-67BB28": "Panel 5",
    "esp-680D4C": "Panel 6",
    "esp-6741B4": "Panel 7",
    "esp-682BCE": "Panel 8",
    "esp-67B009": "Panel 9",
}

PANEL_POWER_WATTS = {
    "esp-4923B2": 36,
    "esp-61DD37": 36,
    "esp-E05DAC": 36,
    "esp-F88DED": 100,
    "esp-67BB28": 40,
    "esp-680D4C": 40,
    "esp-6741B4": 30,
    "esp-682BCE": 36,
    "esp-67B009": 36,
}

# Only Panel 1 to Panel 4 currently have DS18B20 temperature sensors.
TEMP_PANEL_IDS = {
    "esp-4923B2",
    "esp-61DD37",
    "esp-E05DAC",
    "esp-F88DED",
}

SENSOR_LABELS = {
    "esp-6720EA": "Sensor 1",
    "esp-66B5E2": "Sensor 2",
    "esp-4A7D20": "Sensor 3",
    "esp-680DBB": "Sensor 4",
    "esp-684212": "Sensor 5",
    "esp-67A642": "Sensor 6",
    "esp-67D0E0": "R1 Reference",
    "esp-67A5B2": "R2 Reference",
}

REFERENCE_SENSOR_IDS = {
    "R1": "esp-67D0E0",
    "R2": "esp-67A5B2",
}

ZONE_SENSOR_IDS = [
    "esp-6720EA",
    "esp-66B5E2",
    "esp-4A7D20",
    "esp-680DBB",
    "esp-684212",
    "esp-67A642",
]

REFERENCE_SENSOR_ORDER = [
    REFERENCE_SENSOR_IDS["R1"],
    REFERENCE_SENSOR_IDS["R2"],
]

LIGHTING_CONTROL_ZONES = {
    "LZ1": {
        "label": "Zone 1",
        "occupancy_zones": ["Z1"],
        "sensor_ids": ["esp-6720EA", "esp-66B5E2"],
        "panel_ids": ["esp-4923B2", "esp-61DD37", "esp-67B009"],
    },
    "LZ2": {
        "label": "Zone 2",
        "occupancy_zones": ["Z2"],
        "sensor_ids": ["esp-4A7D20"],
        "panel_ids": ["esp-E05DAC"],
    },
    "LZ3": {
        "label": "Zone 3",
        "occupancy_zones": ["Z3"],
        "sensor_ids": ["esp-680DBB", "esp-684212"],
        "panel_ids": ["esp-F88DED", "esp-67BB28", "esp-680D4C"],
    },
    "LZ4": {
        "label": "Zone 4",
        "occupancy_zones": ["Z4"],
        "sensor_ids": ["esp-67A642"],
        "panel_ids": ["esp-6741B4", "esp-682BCE"],
    },
}

RADAR_PRESENCE_STALE_SECONDS = 15.0

RADAR_LIGHTING_CONTROL_ZONES = {
    "RZ1": {
        "label": "Radar Zone 1",
        "radar_key": "z1",
        "sensor_ids": ["esp-66B5E2", "esp-4A7D20", "esp-680DBB", "esp-684212"],
        "panel_ids": [
            "esp-61DD37",
            "esp-E05DAC",
            "esp-F88DED",
            "esp-67BB28",
            "esp-680D4C",
        ],
    },
    "RZ2": {
        "label": "Radar Zone 2",
        "radar_key": "z2",
        "sensor_ids": ["esp-6720EA", "esp-66B5E2", "esp-684212", "esp-67A642"],
        "panel_ids": [
            "esp-4923B2",
            "esp-61DD37",
            "esp-680D4C",
            "esp-6741B4",
            "esp-682BCE",
            "esp-67B009",
        ],
    },
}

SENSOR_TO_LIGHTING_ZONE = {
    sensor_id: zone_id
    for zone_id, zone in LIGHTING_CONTROL_ZONES.items()
    for sensor_id in zone["sensor_ids"]
}

STANDARD_LUX = 300
UNOCCUPIED_LUX = 0

PRESENCE_COMFORT_LUX_BY_SENSOR = {
    "esp-6720EA": 350.0,  # Lighting Zone 1
    "esp-66B5E2": 320.0,  # Lighting Zone 1
    "esp-4A7D20": 355.0,  # Lighting Zone 2
    "esp-680DBB": 420.0,  # Lighting Zone 3
    "esp-684212": 350.0,  # Lighting Zone 3
    "esp-67A642": 350.0,  # Lighting Zone 4
}

PRESENCE_UNOCCUPIED_COMFORT_LUX = 0.0

EFFICIENT_PANELS_BY_SENSOR = {
    sensor_id: list(zone["panel_ids"])
    for zone in LIGHTING_CONTROL_ZONES.values()
    for sensor_id in zone["sensor_ids"]
}

UNCONTROLLED_REGRESSION_BY_SENSOR = {
    "esp-6720EA": (0.330890, 0.438524, 0.160926),
    "esp-66B5E2": (-0.294129, 0.419730, 0.186707),
    "esp-4A7D20": (-2.084686, 0.442324, 0.363509),
    "esp-680DBB": (2.738228, -0.106772, 0.367658),
    "esp-684212": (4.053825, 0.043861, 0.134482),
    "esp-67A642": (4.434541, 0.022711, 0.145059),
}

LUX_CALIBRATION_A = 1.040783
LUX_CALIBRATION_B = 1.486988

LOW_DUTY_LIMIT_PCT = 10.0
LOW_DUTY_BOOST_PCT = 20.0
LOW_DUTY_BOOST_STEP_MS = 10
LOW_DUTY_BOOST_HOLD_MS = 100
RAMP_SETTLE_MARGIN_SECONDS = 1.0
MIN_AUTO_CONTROL_CYCLE_SECONDS = 5.0
LOW_DUTY_LOCK_THRESHOLD_PCT = 10

PANEL_ORDER = list(PANEL_LABELS.keys())
SENSOR_ORDER = list(SENSOR_LABELS.keys())

CALIBRATION_PATH = r"C:\SmartLighting\calibration.json"

def get_panel_label(panel_id: str) -> str:
    return PANEL_LABELS.get(panel_id, "Unknown Panel")


def get_panel_power_watts(panel_id: str, duty: float = 100) -> str:
    max_power = PANEL_POWER_WATTS.get(panel_id)

    if max_power is None:
        return "-"

    duty = max(0, min(100, float(duty)))
    power = (max_power * duty / 100.0) - 0.5
    power = max(0.0, power)

    return f"{power:.1f} W"


def get_panel_power_list(panel_ids):
    return [
        float(PANEL_POWER_WATTS.get(panel_id, 1.0))
        for panel_id in panel_ids
    ]


def calculate_live_power_watch():
    panels = backend.get_panels()
    rows = []
    total_power = 0.0
    max_total_power = sum(PANEL_POWER_WATTS.values())

    for panel_id in PANEL_ORDER:
        max_power = float(PANEL_POWER_WATTS.get(panel_id, 0.0))
        panel = panels.get(panel_id)

        if panel is not None and panel.duty:
            duty = sum(float(value) for value in panel.duty) / len(panel.duty)
        else:
            duty = 0.0

        duty = max(0.0, min(100.0, duty))
        watts = max_power * duty / 100.0
        total_power += watts

        rows.append(
            {
                "label": get_panel_label(panel_id),
                "watts": watts,
            }
        )

    savings_percent = 0.0
    if max_total_power > 0:
        savings_percent = 100.0 * (1.0 - (total_power / max_total_power))
        savings_percent = max(0.0, min(100.0, savings_percent))

    return rows, total_power, savings_percent


def get_sensor_label(sensor_id: str) -> str:
    return SENSOR_LABELS.get(sensor_id, sensor_id)


def get_sensor_role(sensor_id: str) -> str:
    if sensor_id == REFERENCE_SENSOR_IDS["R1"]:
        return "Reference R1"
    if sensor_id == REFERENCE_SENSOR_IDS["R2"]:
        return "Reference R2"
    return "Zone sensor"


def raw_lux_to_calibrated(raw_lux):
    if raw_lux is None:
        return None

    calibrated = (LUX_CALIBRATION_A * float(raw_lux)) + LUX_CALIBRATION_B
    return round(max(0.0, calibrated), 2)


def calibrated_lux_to_raw(calibrated_lux):
    calibrated = max(0.0, float(calibrated_lux))
    return max(0.0, (calibrated - LUX_CALIBRATION_B) / LUX_CALIBRATION_A)


def default_occupied_comfort_lux(sensor_id):
    return float(PRESENCE_COMFORT_LUX_BY_SENSOR.get(sensor_id, STANDARD_LUX))


def default_unoccupied_comfort_lux(sensor_id):
    return float(PRESENCE_UNOCCUPIED_COMFORT_LUX)


def default_zone_occupied_lux(zone_id, zone_map=None):
    zone_map = zone_map or LIGHTING_CONTROL_ZONES
    sensor_ids = zone_map[zone_id]["sensor_ids"]
    values = [default_occupied_comfort_lux(sensor_id) for sensor_id in sensor_ids]
    return float(round(sum(values) / len(values))) if values else float(STANDARD_LUX)


def default_zone_unoccupied_lux(zone_id):
    return float(PRESENCE_UNOCCUPIED_COMFORT_LUX)


def lighting_zone_sensor_labels(zone):
    return ", ".join(get_sensor_label(sensor_id) for sensor_id in zone["sensor_ids"])


def lighting_zone_panel_labels(zone, available_panel_ids):
    return (
        ", ".join(
            get_panel_label(panel_id)
            for panel_id in zone["panel_ids"]
            if panel_id in available_panel_ids
        )
        or "-"
    )


def get_active_lighting_zone_ids_from_occupancy(occupancy_result):
    if occupancy_result is None:
        return []

    occupied = occupancy_result.get("occupied", {})
    active_zone_ids = []

    for zone_id, zone in LIGHTING_CONTROL_ZONES.items():
        if any(occupied.get(occ_zone, False) for occ_zone in zone["occupancy_zones"]):
            active_zone_ids.append(zone_id)

    return active_zone_ids


def get_fresh_radar_presence_state():
    now = time.time()
    combined = {
        "z1": False,
        "z2": False,
        "fresh_node_ids": [],
        "stale_node_ids": [],
        "max_age_seconds": None,
    }

    for node_id, state in backend.get_radar_presence().items():
        received_at = float(state.get("_received_at", 0.0) or 0.0)
        age_seconds = now - received_at if received_at > 0 else None

        if age_seconds is None or age_seconds > RADAR_PRESENCE_STALE_SECONDS:
            combined["stale_node_ids"].append(node_id)
            continue

        combined["fresh_node_ids"].append(node_id)
        combined["max_age_seconds"] = max(
            float(combined["max_age_seconds"] or 0.0),
            age_seconds,
        )
        combined["z1"] = combined["z1"] or bool(state.get("z1", 0))
        combined["z2"] = combined["z2"] or bool(state.get("z2", 0))

    return combined


def get_active_radar_lighting_zone_ids(radar_state):
    if not radar_state or not radar_state.get("fresh_node_ids"):
        return []

    active_zone_ids = []

    for zone_id, zone in RADAR_LIGHTING_CONTROL_ZONES.items():
        if radar_state.get(zone["radar_key"], False):
            active_zone_ids.append(zone_id)

    return active_zone_ids


def sensor_ids_for_lighting_zones(zone_ids, available_sensor_ids=None, zone_map=None):
    zone_map = zone_map or LIGHTING_CONTROL_ZONES
    available = set(available_sensor_ids) if available_sensor_ids is not None else None
    selected = []

    for zone_id in zone_ids:
        for sensor_id in zone_map[zone_id]["sensor_ids"]:
            if available is None or sensor_id in available:
                selected.append(sensor_id)

    return selected


def efficient_panels_by_sensor_for_lighting_zones(zone_ids, zone_map):
    panel_order = list(PANEL_LABELS.keys())
    by_sensor = {sensor_id: [] for sensor_id in ZONE_SENSOR_IDS}

    for zone_id in zone_ids:
        zone = zone_map[zone_id]

        for sensor_id in zone["sensor_ids"]:
            existing = set(by_sensor.setdefault(sensor_id, []))

            for panel_id in zone["panel_ids"]:
                if panel_id not in existing:
                    by_sensor[sensor_id].append(panel_id)
                    existing.add(panel_id)

    for sensor_id, panel_ids in by_sensor.items():
        panel_ids.sort(
            key=lambda panel_id: panel_order.index(panel_id)
            if panel_id in panel_order
            else 999
        )

    return by_sensor


def sort_by_defined_order(device_ids, defined_order):
    order_map = {device_id: index for index, device_id in enumerate(defined_order)}
    return sorted(device_ids, key=lambda x: (order_map.get(x, 999), x))


def known_then_extra_device_ids(device_ids, defined_order):
    available = set(device_ids)
    ordered = [device_id for device_id in defined_order if device_id in available]
    extras = sorted(device_id for device_id in available if device_id not in defined_order)
    return ordered + extras


def load_previous_calibration():
    if not os.path.exists(CALIBRATION_PATH):
        return None

    try:
        with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_resource
def get_backend():
    backend = MQTTBackend(host="192.168.1.77", port=1883)
    backend.start()
    return backend


backend = get_backend()

power_watch_rows, power_watch_total, power_watch_savings = calculate_live_power_watch()
render_fixed_power_watch(
    power_rows=power_watch_rows,
    total_power=power_watch_total,
    savings_percent=power_watch_savings,
)


def clamp_manual_step_ms(value) -> int:
    try:
        step_ms = int(value)
    except Exception:
        step_ms = 25

    return max(10, min(500, step_ms))


VALID_PAGES = ["Control", "Calibration", "Occupancy", "Auto Control"]
PRESENCE_SOURCE_OPTIONS = ["Camera", "Radar sensors"]
PRESENCE_SOURCE_LABEL_TO_VALUE = {
    "Camera": "camera",
    "Radar sensors": "radar",
}
PRESENCE_SOURCE_VALUE_TO_LABEL = {
    value: label
    for label, value in PRESENCE_SOURCE_LABEL_TO_VALUE.items()
}


def get_query_page():
    try:
        page = st.query_params.get("page")
    except Exception:
        try:
            page_values = st.experimental_get_query_params().get("page", [])
            page = page_values[0] if page_values else None
        except Exception:
            page = None

    if isinstance(page, list):
        page = page[0] if page else None

    return page if page in VALID_PAGES else None


def set_query_page(page):
    if get_query_param_value("page") == page:
        return

    try:
        st.query_params["page"] = page
    except Exception:
        try:
            params = st.experimental_get_query_params()
            normalized = {
                key: values[0] if isinstance(values, list) and values else values
                for key, values in params.items()
            }
            normalized["page"] = page
            st.experimental_set_query_params(**normalized)
        except Exception:
            pass


def get_query_param_value(name):
    try:
        value = st.query_params.get(name)
    except Exception:
        try:
            values = st.experimental_get_query_params().get(name, [])
            value = values[0] if values else None
        except Exception:
            value = None

    if isinstance(value, list):
        value = value[0] if value else None

    return value


def set_query_param_value(name, value):
    if get_query_param_value(name) == value:
        return

    try:
        st.query_params[name] = value
        return
    except Exception:
        pass

    try:
        params = st.experimental_get_query_params()
        normalized = {
            key: values[0] if isinstance(values, list) and values else values
            for key, values in params.items()
        }
        normalized[name] = value
        st.experimental_set_query_params(**normalized)
    except Exception:
        pass


def normalize_presence_source(value):
    if value in PRESENCE_SOURCE_VALUE_TO_LABEL:
        return value
    if value in PRESENCE_SOURCE_LABEL_TO_VALUE:
        return PRESENCE_SOURCE_LABEL_TO_VALUE[value]
    return "camera"


def get_selected_presence_source():
    query_value = normalize_presence_source(get_query_param_value("presence_source"))
    session_value = normalize_presence_source(
        st.session_state.get("occupancy_presence_source_value")
        or st.session_state.get("occupancy_presence_source_widget")
        or st.session_state.get("occupancy_presence_source")
    )

    source_value = query_value
    if get_query_param_value("presence_source") is None:
        source_value = session_value

    source_label = PRESENCE_SOURCE_VALUE_TO_LABEL[source_value]
    st.session_state["occupancy_presence_source_value"] = source_value
    st.session_state["occupancy_presence_source_label"] = source_label
    return source_value, source_label


def set_selected_presence_source(source_label):
    source_value = normalize_presence_source(source_label)
    st.session_state["occupancy_presence_source_value"] = source_value
    st.session_state["occupancy_presence_source_label"] = PRESENCE_SOURCE_VALUE_TO_LABEL[source_value]
    set_query_param_value("presence_source", source_value)
    return source_value


def request_auto_control_stop(message="Manual panel command requested. Auto control will stop safely."):
    # The MQTT backend is shared across Streamlit sessions, so this also stops
    # workers created by another tab or by a disconnected browser session.
    backend.stop_all_auto_control()
    job = st.session_state.get("auto_control_job")

    if not job:
        st.session_state["auto_control_checkbox"] = False
        return

    stop_event = job.get("stop_event")
    if stop_event is not None:
        stop_event.set()

    lock = job.get("lock")
    if lock is None:
        st.session_state["auto_control_checkbox"] = False
        return

    with lock:
        if job.get("status") in ["running", "stopping"]:
            job["status"] = "stopping"
            job["message"] = message
            job["updated_at"] = time.time()

    st.session_state["auto_control_checkbox"] = False


def send_manual_panel_duty_from_slider(panel_id):
    slider_key = f"duty_{panel_id}"
    mode_key = f"manual_transition_{panel_id}"
    step_key = f"manual_step_ms_{panel_id}"

    duty_to_send = int(round(float(st.session_state.get(slider_key, 0))))
    manual_mode = st.session_state.get(mode_key, "Smooth")
    panel_label = get_panel_label(panel_id)

    request_auto_control_stop()

    if manual_mode == "Immediate":
        backend.send_panel_duty(
            panel_id,
            duty_to_send,
            transition="immediate",
        )

        transition_text = "immediate"
    else:
        smooth_step_ms = clamp_manual_step_ms(st.session_state.get(step_key, 25))

        backend.send_panel_duty(
            panel_id,
            duty_to_send,
            transition="smooth",
            step_ms=smooth_step_ms,
        )

        transition_text = f"smooth, {smooth_step_ms} ms"

    st.session_state["manual_message"] = (
        f"{panel_label}: sent {duty_to_send}% "
        f"({transition_text}) - Auto Mode stopped"
    )


def detect_missing_devices(panel_ids, sensor_ids):
    problems = []

    panels = backend.get_panels()
    sensors = backend.get_sensors()

    for panel_id in panel_ids:
        panel = panels.get(panel_id)

        if panel is None:
            problems.append(f"{get_panel_label(panel_id)} is missing.")
        elif not panel.online:
            problems.append(f"{get_panel_label(panel_id)} is offline.")

    for sensor_id in sensor_ids:
        sensor = sensors.get(sensor_id)

        if sensor is None:
            problems.append(f"{get_sensor_label(sensor_id)} is missing.")
        elif not sensor.online:
            problems.append(f"{get_sensor_label(sensor_id)} is offline.")

    return problems


def clean_calibration_log_message(msg: str) -> str:
    clean_msg = msg

    for pid, label in PANEL_LABELS.items():
        clean_msg = clean_msg.replace(pid, label)

    for sid, label in SENSOR_LABELS.items():
        clean_msg = clean_msg.replace(sid, label)

    return clean_msg


def infer_calibration_step(clean_msg: str, panel_ids) -> str | None:
    lower_msg = clean_msg.lower()

    if "ambient" in lower_msg or "uncontrolled" in lower_msg:
        return "Daylight / uncontrolled illuminance estimated."

    for panel_id in panel_ids:
        panel_label = get_panel_label(panel_id)

        if panel_label.lower() in lower_msg and (
            "completed" in lower_msg
            or "gain" in lower_msg
            or "calibrated" in lower_msg
        ):
            return f"{panel_label} calibration completed."

    return None


def get_calibration_job():
    job = st.session_state.get("calibration_job")

    if job is None:
        job = {
            "status": "idle",
            "logs": [],
            "steps": [],
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
            "stop_event": None,
            "lock": threading.RLock(),
            "thread": None,
            "panel_ids": [],
            "sensor_ids": [],
        }
        st.session_state["calibration_job"] = job

    return job


def store_last_calibration_result(result, logs, duration_seconds, done_time=None):
    if done_time is None:
        done_time = time.strftime("%H:%M:%S")

    st.session_state["last_calibration_result"] = {
        "done_time": done_time,
        "duration_seconds": duration_seconds,
        "ambient_lux": result.ambient_lux,
        "gain_matrix": result.gain_matrix,
        "panel_ids": result.panel_ids,
        "sensor_ids": result.sensor_ids,
        "logs": list(logs),
        "status": result.status,
        "fallback_used": result.fallback_used,
        "warnings": result.warnings,
        "completed_panel_ids": result.completed_panel_ids,
        "stopped_at_panel_id": result.stopped_at_panel_id,
        "ambient_completed": result.ambient_completed,
    }


def calibration_json_to_display_result(calibration):
    created_at = calibration.get("created_at")

    if created_at:
        done_time = time.strftime("%H:%M:%S", time.localtime(float(created_at)))
    else:
        done_time = "Saved file"

    return {
        "done_time": done_time,
        "duration_seconds": float(calibration.get("duration_seconds", 0.0)),
        "ambient_lux": calibration.get("ambient_lux", []),
        "gain_matrix": calibration.get("gain_matrix", []),
        "panel_ids": calibration.get("panel_ids", []),
        "sensor_ids": calibration.get("sensor_ids", []),
        "logs": [],
        "status": calibration.get("status", "success"),
        "fallback_used": bool(calibration.get("fallback_used", False)),
        "warnings": calibration.get("warnings", []),
        "completed_panel_ids": calibration.get("panel_ids", []),
        "stopped_at_panel_id": None,
        "ambient_completed": True,
    }


def build_gain_matrix_dataframe(saved):
    gain_rows = []

    for sensor_index, sensor_id in enumerate(saved["sensor_ids"]):
        row = {
            "Sensor": get_sensor_label(sensor_id),
            "Role": get_sensor_role(sensor_id),
        }

        for panel_index, panel_id in enumerate(saved["panel_ids"]):
            row[get_panel_label(panel_id)] = saved["gain_matrix"][sensor_index][panel_index]

        gain_rows.append(row)

    gain_df = pd.DataFrame(gain_rows)

    panel_columns = [
        get_panel_label(panel_id)
        for panel_id in saved["panel_ids"]
    ]

    for col in panel_columns:
        gain_df[col] = gain_df[col].round(0).astype(int)

    return gain_df, panel_columns


def build_lux_per_watt_dataframe(saved):
    rows = []
    panel_columns = []

    for panel_id in saved["panel_ids"]:
        panel_label = get_panel_label(panel_id)
        max_power = PANEL_POWER_WATTS.get(panel_id, 0)
        panel_columns.append(f"{panel_label}-{max_power:g}W")

    for sensor_index, sensor_id in enumerate(saved["sensor_ids"]):
        row = {
            "Sensor": get_sensor_label(sensor_id),
            "Role": get_sensor_role(sensor_id),
        }

        for panel_index, panel_id in enumerate(saved["panel_ids"]):
            max_power = float(PANEL_POWER_WATTS.get(panel_id, 0.0))
            panel_column = panel_columns[panel_index]
            gain = float(saved["gain_matrix"][sensor_index][panel_index])
            row[panel_column] = gain / max_power if max_power > 0 else 0.0

        rows.append(row)

    lux_per_watt_df = pd.DataFrame(rows)

    for col in panel_columns:
        lux_per_watt_df[col] = lux_per_watt_df[col].round(2)

    return lux_per_watt_df, panel_columns


def start_calibration_background(panel_ids, sensor_ids, strict_mode):
    stop_event = threading.Event()
    lock = threading.RLock()
    started_at = time.time()

    job = {
        "status": "running",
        "logs": [],
        "steps": ["Calibration started."],
        "result": None,
        "error": None,
        "started_at": started_at,
        "finished_at": None,
        "stop_event": stop_event,
        "lock": lock,
        "thread": None,
        "panel_ids": list(panel_ids),
        "sensor_ids": list(sensor_ids),
        "strict_mode": strict_mode,
    }

    def log_callback(msg):
        clean_msg = clean_calibration_log_message(msg)
        step = infer_calibration_step(clean_msg, panel_ids)

        with lock:
            job["logs"].append(clean_msg)

            if step and step not in job["steps"]:
                job["steps"].append(step)

    def worker():
        try:
            runner = CalibrationRunner(
                backend=backend,
                panel_ids=panel_ids,
                sensor_ids=sensor_ids,
                panel_labels=PANEL_LABELS,
                sensor_labels=SENSOR_LABELS,
                settle_seconds=3.0,
                strict_mode=strict_mode,
                log_callback=log_callback,
                history_path=CALIBRATION_PATH,
                use_history_fallback=True,
                stop_event=stop_event,
            )

            result = runner.run_full_calibration()
            CalibrationRunner.save_result(result, CALIBRATION_PATH)
            finished_at = time.time()
            duration_seconds = finished_at - started_at

            with lock:
                if result.stopped_at_panel_id:
                    job["status"] = "stopped"
                elif result.status == "partial":
                    job["status"] = "partial"
                else:
                    job["status"] = "success"

                job["result"] = result
                job["finished_at"] = finished_at

        except Exception as exc:
            with lock:
                job["status"] = "error"
                job["error"] = str(exc)
                job["finished_at"] = time.time()

    thread = threading.Thread(
        target=worker,
        name="calibration-worker",
        daemon=True,
    )
    job["thread"] = thread

    st.session_state["calibration_job"] = job
    st.session_state["calibration_running"] = True
    st.session_state["active_page"] = "Calibration"
    set_query_page("Calibration")

    thread.start()


def get_auto_control_job():
    job = st.session_state.get("auto_control_job")

    if job is None:
        job = {
            "status": "idle",
            "message": "Auto control is stopped.",
            "error": None,
            "last_result": None,
            "last_cycle_seconds": None,
            "cycle_count": 0,
            "started_at": None,
            "updated_at": None,
            "stop_event": None,
            "lock": threading.RLock(),
            "thread": None,
            "config": {},
        }
        st.session_state["auto_control_job"] = job

    return job


def get_auto_control_snapshot(job=None):
    job = job or get_auto_control_job()

    with job["lock"]:
        thread = job.get("thread")
        thread_alive = bool(thread is not None and thread.is_alive())
        status = job.get("status", "idle")

        if status in ["running", "stopping"] and not thread_alive:
            job["status"] = "stopped"
            job["message"] = "Auto control stopped."
            job["error"] = None
            job["updated_at"] = time.time()
            status = "stopped"

        if status == "running" and job.get("stop_event") is not None:
            if job["stop_event"].is_set():
                job["status"] = "stopping"
                job["message"] = "Stop requested. Auto control will stop safely."
                job["updated_at"] = time.time()
                status = "stopping"

        active = status in ["running", "stopping"] and thread_alive
        snapshot = {
            "status": status,
            "active": active,
            "running": status == "running" and active,
            "stopping": status == "stopping" and thread_alive,
            "message": job.get("message", "Auto control is stopped."),
            "error": job.get("error"),
            "last_result": job.get("last_result"),
            "last_cycle_seconds": job.get("last_cycle_seconds"),
            "cycle_count": job.get("cycle_count", 0),
            "retry_count": job.get("retry_count", 0),
            "last_retry_error": job.get("last_retry_error"),
        }

    st.session_state["auto_control_checkbox"] = active
    return snapshot


def get_presence_active_sensor_ids(occupancy_result, sensor_ids):
    if occupancy_result is None:
        return []

    occupied = occupancy_result.get("occupied", {})
    active_sensor_ids = set()

    for lighting_zone in LIGHTING_CONTROL_ZONES.values():
        lighting_zone_active = any(
            occupied.get(occupancy_zone, False)
            for occupancy_zone in lighting_zone["occupancy_zones"]
        )

        if not lighting_zone_active:
            continue

        for sensor_id in lighting_zone["sensor_ids"]:
            if sensor_id in sensor_ids:
                active_sensor_ids.add(sensor_id)

    return [
        sensor_id
        for sensor_id in sensor_ids
        if sensor_id in active_sensor_ids
    ]

def require_sensor_indices(sensor_ids, required_sensor_ids, context):
    missing = [
        sensor_id
        for sensor_id in required_sensor_ids
        if sensor_id not in sensor_ids
    ]

    if missing:
        raise RuntimeError(
            f"{context} requires missing calibrated sensors: "
            + ", ".join(get_sensor_label(sensor_id) for sensor_id in missing)
        )

    return [sensor_ids.index(sensor_id) for sensor_id in required_sensor_ids]


def select_rows(values, row_indices):
    return [values[index] for index in row_indices]


def select_matrix_rows(matrix, row_indices):
    return [matrix[index] for index in row_indices]


def estimate_zone_uncontrolled_from_references(
    reference_readings,
    reference_gain_matrix,
    current_duties,
    zone_sensor_ids,
):
    reference_contribution = estimate_panel_contribution(
        gain_matrix=reference_gain_matrix,
        current_duties=current_duties,
    )
    r1_measured_lux = float(reference_readings[0]["lux"])
    r2_measured_lux = float(reference_readings[1]["lux"])
    r1_uncontrolled_lux = max(0.0, r1_measured_lux - float(reference_contribution[0]))
    r2_uncontrolled_lux = max(0.0, r2_measured_lux - float(reference_contribution[1]))
    r1_uncontrolled_raw = calibrated_lux_to_raw(r1_uncontrolled_lux)
    r2_uncontrolled_raw = calibrated_lux_to_raw(r2_uncontrolled_lux)

    uncontrolled_lux = []
    rows = []

    for sensor_id in zone_sensor_ids:
        intercept, r1_coef, r2_coef = UNCONTROLLED_REGRESSION_BY_SENSOR[sensor_id]
        uncontrolled_raw = max(
            0.0,
            intercept
            + (r1_coef * r1_uncontrolled_raw)
            + (r2_coef * r2_uncontrolled_raw),
        )
        uncontrolled = raw_lux_to_calibrated(uncontrolled_raw)
        uncontrolled_lux.append(float(uncontrolled))
        rows.append(
            {
                "Sensor": get_sensor_label(sensor_id),
                "Estimated Zone Uncontrolled Raw": round(uncontrolled_raw, 2),
                "Estimated Zone Uncontrolled Lux": uncontrolled,
                "R1 Uncontrolled Raw": round(r1_uncontrolled_raw, 2),
                "R2 Uncontrolled Raw": round(r2_uncontrolled_raw, 2),
                "R1 Uncontrolled Lux": round(r1_uncontrolled_lux, 2),
                "R2 Uncontrolled Lux": round(r2_uncontrolled_lux, 2),
            }
        )

    return uncontrolled_lux, reference_contribution, rows


def build_live_regression_check_rows(sensors):
    r1_id = REFERENCE_SENSOR_IDS["R1"]
    r2_id = REFERENCE_SENSOR_IDS["R2"]
    r1 = sensors.get(r1_id)
    r2 = sensors.get(r2_id)

    if r1 is None or r2 is None or r1.raw_lux is None or r2.raw_lux is None:
        return None

    r1_raw = float(r1.raw_lux)
    r2_raw = float(r2.raw_lux)
    rows = []

    for sensor_id in ZONE_SENSOR_IDS:
        intercept, r1_coef, r2_coef = UNCONTROLLED_REGRESSION_BY_SENSOR[sensor_id]
        estimated_raw = max(0.0, intercept + (r1_coef * r1_raw) + (r2_coef * r2_raw))
        estimated_lux = raw_lux_to_calibrated(estimated_raw)
        sensor = sensors.get(sensor_id)

        real_raw = None
        real_lux = None
        error_lux = None
        abs_error_lux = None

        if sensor is not None and sensor.raw_lux is not None and sensor.lux is not None:
            real_raw = float(sensor.raw_lux)
            real_lux = float(sensor.lux)
            error_lux = float(estimated_lux) - real_lux
            abs_error_lux = abs(error_lux)

        rows.append(
            {
                "Sensor": get_sensor_label(sensor_id),
                "Estimated Raw": round(estimated_raw, 2),
                "Estimated Lux": round(float(estimated_lux), 2),
                "Real Raw": round(real_raw, 2) if real_raw is not None else None,
                "Real Lux": round(real_lux, 2) if real_lux is not None else None,
                "Error Lux": round(error_lux, 2) if error_lux is not None else None,
                "Abs Error Lux": round(abs_error_lux, 2) if abs_error_lux is not None else None,
            }
        )

    return rows


def lux_text_input(label, key, default_value, max_value, disabled=False):
    raw_value = st.text_input(
        label,
        value=str(int(st.session_state.get(key, default_value))),
        disabled=disabled,
        key=key,
        label_visibility="collapsed",
    )

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = float(default_value)

    return max(0.0, min(float(max_value), value))


def input_group_label(text):
    st.markdown(
        f"""
        <div style="
            color: #000000;
            font-size: 14px;
            line-height: 1.6;
            margin: 0 0 0.35rem 0;
        ">
            {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_calibration_styled_table(styler):
    try:
        html = styler.hide(axis="index").to_html()
    except Exception:
        html = styler.to_html()

    st.markdown(
        f'<div class="calibration-table-wrap">{html}</div>',
        unsafe_allow_html=True,
    )


def average_panel_duties(panel_ids):
    panels = backend.get_panels()
    duties = []

    for panel_id in panel_ids:
        panel = panels.get(panel_id)

        if panel is None or not panel.duty:
            duties.append(0.0)
        else:
            duties.append(round(sum(panel.duty) / len(panel.duty), 2))

    return duties


def wait_for_fresh_lux(sensor_ids, timeout_seconds, stop_event):
    request_time = time.time()

    for sensor_id in sensor_ids:
        backend.request_sensor_lux(sensor_id)

    current_lux_map = {}
    start = time.time()

    while time.time() - start < timeout_seconds:
        if stop_event.is_set():
            raise RuntimeError("Auto control stopped by user.")

        sensors = backend.get_sensors()

        for sensor_id in sensor_ids:
            sensor = sensors.get(sensor_id)

            if sensor is None or not sensor.online:
                continue

            if sensor.lux is None:
                continue

            if sensor.last_lux >= request_time:
                current_lux_map[sensor_id] = float(sensor.lux)

        if len(current_lux_map) == len(sensor_ids):
            return [current_lux_map[sensor_id] for sensor_id in sensor_ids]

        time.sleep(0.1)

    missing = [
        sensor_id
        for sensor_id in sensor_ids
        if sensor_id not in current_lux_map
    ]
    missing_labels = ", ".join(get_sensor_label(sensor_id) for sensor_id in missing)
    raise RuntimeError(f"Missing fresh lux values from: {missing_labels}")


def wait_for_fresh_sensor_readings(sensor_ids, timeout_seconds, stop_event):
    request_time = time.time()

    for sensor_id in sensor_ids:
        backend.request_sensor_lux(sensor_id)

    readings = {}
    start = time.time()

    while time.time() - start < timeout_seconds:
        if stop_event.is_set():
            raise RuntimeError("Auto control stopped by user.")

        sensors = backend.get_sensors()

        for sensor_id in sensor_ids:
            sensor = sensors.get(sensor_id)

            if sensor is None or not sensor.online:
                continue

            if sensor.raw_lux is None or sensor.lux is None:
                continue

            if sensor.last_lux >= request_time:
                readings[sensor_id] = {
                    "raw": float(sensor.raw_lux),
                    "lux": float(sensor.lux),
                }

        if len(readings) == len(sensor_ids):
            return [readings[sensor_id] for sensor_id in sensor_ids]

        time.sleep(0.1)

    missing = [
        sensor_id
        for sensor_id in sensor_ids
        if sensor_id not in readings
    ]
    missing_labels = ", ".join(get_sensor_label(sensor_id) for sensor_id in missing)
    raise RuntimeError(f"Missing fresh raw/calibrated lux values from: {missing_labels}")


def wait_for_panel_ack(panel_cmd_ids, timeout_seconds, stop_event):
    start = time.time()
    pending = set(panel_cmd_ids.keys())

    while time.time() - start < timeout_seconds:
        if stop_event.is_set():
            raise RuntimeError("Auto control stopped by user.")

        panels = backend.get_panels()

        for panel_id in list(pending):
            panel = panels.get(panel_id)

            if panel is None or not panel.online:
                continue

            if panel.last_cmd_id == panel_cmd_ids[panel_id]:
                pending.remove(panel_id)

        if not pending:
            return

        time.sleep(0.1)

    missing_labels = ", ".join(get_panel_label(panel_id) for panel_id in sorted(pending))
    raise RuntimeError(f"Missing panel acknowledgement from: {missing_labels}")


def sleep_interruptible(seconds, stop_event):
    deadline = time.time() + max(0.0, seconds)

    while time.time() < deadline:
        if stop_event.is_set():
            raise RuntimeError("Auto control stopped by user.")

        time.sleep(min(0.1, max(0.0, deadline - time.time())))


def estimate_panel_ramp_seconds(current_duty, target_duty, ramp_step_ms):
    current = max(0.0, min(100.0, float(current_duty)))
    target = max(0.0, min(100.0, float(target_duty)))
    step_ms = max(1, int(ramp_step_ms))

    if target <= 0.0:
        return abs(target - current) * step_ms / 1000.0

    if target < LOW_DUTY_LIMIT_PCT and current < LOW_DUTY_LIMIT_PCT:
        boost_up = abs(LOW_DUTY_BOOST_PCT - current) * LOW_DUTY_BOOST_STEP_MS
        boost_hold = LOW_DUTY_BOOST_HOLD_MS
        boost_down = abs(LOW_DUTY_BOOST_PCT - target) * step_ms
        return (boost_up + boost_hold + boost_down) / 1000.0

    return abs(target - current) * step_ms / 1000.0


def apply_low_duty_lock(current_duty, ideal_duty):
    current = int(round(max(0.0, min(100.0, float(current_duty)))))
    ideal = int(round(max(0.0, min(100.0, float(ideal_duty)))))

    if ideal == 0:
        return 0, "off"

    if current < LOW_DUTY_LOCK_THRESHOLD_PCT and ideal < LOW_DUTY_LOCK_THRESHOLD_PCT:
        return current, "low-duty lock"

    return ideal, "lp"


def start_auto_control_background(calibration, initial_config):
    existing_job = st.session_state.get("auto_control_job")
    if existing_job is not None and get_auto_control_snapshot(existing_job)["active"]:
        return
    if backend.has_active_auto_control():
        return

    stop_event = threading.Event()
    generation = backend.begin_auto_control()

    class SharedAutoControlStopSignal:
        def is_set(self):
            return stop_event.is_set() or not backend.is_auto_control_active(generation)

    stop_signal = SharedAutoControlStopSignal()
    lock = threading.RLock()
    started_at = time.time()

    job = {
        "status": "running",
        "message": "Auto control is starting...",
        "error": None,
        "last_result": None,
        "last_cycle_seconds": None,
        "cycle_count": 0,
        "retry_count": 0,
        "last_retry_error": None,
        "started_at": started_at,
        "updated_at": started_at,
        "stop_event": stop_event,
        "generation": generation,
        "lock": lock,
        "thread": None,
        "config": dict(initial_config),
    }

    panel_ids = list(calibration["panel_ids"])
    sensor_ids = list(calibration["sensor_ids"])
    gain_matrix = calibration["gain_matrix"]

    def set_status(message, status="running"):
        with lock:
            job["status"] = status
            job["message"] = message
            job["updated_at"] = time.time()

    def get_config():
        with lock:
            return dict(job["config"])

    def ensure_auto_control_running():
        if stop_signal.is_set():
            raise RuntimeError("Auto control stopped by user.")

    def mark_cycle_retry(error_text, cycle_started):
        elapsed = time.time() - cycle_started
        retry_wait_seconds = max(MIN_AUTO_CONTROL_CYCLE_SECONDS - elapsed, 0.0)

        with lock:
            job["retry_count"] += 1
            job["last_retry_error"] = error_text
            job["last_cycle_seconds"] = elapsed
            job["message"] = (
                f"Temporary cycle issue: {error_text}. "
                f"Retrying in {retry_wait_seconds:.1f}s."
            )
            job["error"] = None
            job["updated_at"] = time.time()

        sleep_interruptible(retry_wait_seconds, stop_signal)

    def worker():
        completed_one_shot = False
        try:
            while not stop_signal.is_set():
                cycle_started = time.time()
                try:
                    cfg = get_config()
                    mode = cfg.get("mode", "presence")
                    presence_source = cfg.get("presence_source")
                    if presence_source is None:
                        presence_source = "radar" if mode == "radar_presence" else "camera"
                    control_strategy = cfg.get("control_strategy", "lp")
                    uniform_weights = cfg.get("uniform_weights", {})
                    ramp_step_ms = int(cfg.get("ramp_step_ms", 25))
                    occupied_comfort_lux = cfg.get("occupied_comfort_lux", {})
                    unoccupied_comfort_lux = cfg.get("unoccupied_comfort_lux", {})
                    manual_active_sensor_ids = cfg.get("manual_active_sensor_ids", [])
                    one_shot = bool(cfg.get("one_shot", False))

                    occupancy_result = None
                    radar_state = None
                    active_radar_zone_ids = []
                    occupancy_source = "not requested"
                    if mode == "manual_zones":
                        occupancy_source = "manual zone selection"
                    elif presence_source == "radar":
                        radar_state = get_fresh_radar_presence_state()
                        active_radar_zone_ids = get_active_radar_lighting_zone_ids(radar_state)
                        occupancy_source = (
                            "fresh radar presence"
                            if radar_state.get("fresh_node_ids")
                            else "no fresh radar data; using inactive zones"
                        )
                    else:
                        set_status("Requesting latest occupancy from camera...")
                        occupancy_request_id = backend.request_occupancy()
                        occupancy_result = backend.wait_for_occupancy_response(
                            request_id=occupancy_request_id,
                            timeout_seconds=2.0,
                            stop_event=stop_signal,
                        )
                        ensure_auto_control_running()

                        if occupancy_result is None:
                            occupancy_source = "no occupancy data; using inactive zones"
                        elif occupancy_result.get("request_id") == occupancy_request_id:
                            occupancy_source = "fresh requested occupancy"
                        else:
                            occupancy_source = "request timeout; using previous occupancy"

                    set_status("Requesting fresh lux from R1/R2 reference sensors...")
                    reference_readings = wait_for_fresh_sensor_readings(
                        sensor_ids=REFERENCE_SENSOR_ORDER,
                        timeout_seconds=6.0,
                        stop_event=stop_signal,
                    )
                    measured_lux = [reading["lux"] for reading in reference_readings]

                    set_status("Solving lighting optimizer...")
                    current_duties = average_panel_duties(panel_ids)
                    zone_row_indices = require_sensor_indices(sensor_ids, ZONE_SENSOR_IDS, "Auto control")
                    reference_row_indices = require_sensor_indices(sensor_ids, REFERENCE_SENSOR_ORDER, "Auto control")
                    zone_gain_matrix = select_matrix_rows(gain_matrix, zone_row_indices)
                    reference_gain_matrix = select_matrix_rows(gain_matrix, reference_row_indices)
                    active_gain_matrix = zone_gain_matrix
                    active_sensor_ids = ZONE_SENSOR_IDS
                    panel_contribution = estimate_panel_contribution(
                        gain_matrix=zone_gain_matrix,
                        current_duties=current_duties,
                    )
                    ambient_lux, reference_contribution, uncontrolled_rows = (
                        estimate_zone_uncontrolled_from_references(
                            reference_readings=reference_readings,
                            reference_gain_matrix=reference_gain_matrix,
                            current_duties=current_duties,
                            zone_sensor_ids=ZONE_SENSOR_IDS,
                        )
                    )

                    if mode == "manual_zones":
                        active_target_sensor_ids = [
                            sensor_id
                            for sensor_id in active_sensor_ids
                            if sensor_id in set(manual_active_sensor_ids)
                        ]
                        efficient_panels_by_sensor = EFFICIENT_PANELS_BY_SENSOR
                    elif presence_source == "radar":
                        active_target_sensor_ids = sensor_ids_for_lighting_zones(
                            active_radar_zone_ids,
                            available_sensor_ids=active_sensor_ids,
                            zone_map=RADAR_LIGHTING_CONTROL_ZONES,
                        )
                        efficient_panels_by_sensor = efficient_panels_by_sensor_for_lighting_zones(
                            active_radar_zone_ids,
                            RADAR_LIGHTING_CONTROL_ZONES,
                        )
                    else:
                        active_target_sensor_ids = get_presence_active_sensor_ids(
                            occupancy_result,
                            active_sensor_ids,
                        )
                        efficient_panels_by_sensor = EFFICIENT_PANELS_BY_SENSOR

                    presence_target_details = build_presence_control_problem(
                        sensor_ids=active_sensor_ids,
                        panel_ids=panel_ids,
                        gain_matrix=active_gain_matrix,
                        daylight_lux=ambient_lux,
                        active_sensor_ids=active_target_sensor_ids,
                        occupied_target_lux=occupied_comfort_lux,
                        unoccupied_target_lux=unoccupied_comfort_lux,
                        efficient_panels_by_sensor=efficient_panels_by_sensor,
                        default_occupied_lux=STANDARD_LUX,
                        default_unoccupied_lux=PRESENCE_UNOCCUPIED_COMFORT_LUX,
                    )
                    for row in presence_target_details["rows"]:
                        sensor_id = row["Sensor"]
                        row["Sensor"] = get_sensor_label(sensor_id)
                        row["Occupied"] = row.pop("Active")

                    optimizer_current_lux = [0.0 for _ in active_sensor_ids]
                    optimizer_target_lux = list(presence_target_details["lamp_targets"])
                    optimizer_gain_matrix = presence_target_details["effective_gain_matrix"]
                    target_lux = list(presence_target_details["total_targets"])
                    panel_power_list = get_panel_power_list(panel_ids)

                    if control_strategy == "uniform":
                        allowed_panel_ids = presence_target_details.get("allowed_panel_ids", [])
                        allowed_panel_indices = [
                            index
                            for index, panel_id in enumerate(panel_ids)
                            if panel_id in set(allowed_panel_ids)
                        ]
                        optimizer_result = solve_uniform_lighting_optimization_decimal_with_diagnostics(
                            current_lux=optimizer_current_lux,
                            target_lux=optimizer_target_lux,
                            gain_matrix=optimizer_gain_matrix,
                            min_duty=0,
                            max_duty=100,
                            panel_power_watts=panel_power_list,
                            current_duties=current_duties,
                            allowed_panel_indices=allowed_panel_indices,
                            weight_power=float(uniform_weights.get("power", 1.0)),
                            weight_uniformity=float(uniform_weights.get("uniformity", 0.02)),
                            weight_change=float(uniform_weights.get("change", 0.005)),
                        )
                        duties_decimal = optimizer_result["duties_decimal"]
                    else:
                        optimizer_result = {
                            "success": True,
                            "message": "Minimum energy LP solved.",
                            "power_watts": None,
                            "objective_value": None,
                        }
                        duties_decimal = solve_lighting_lp_decimal(
                            current_lux=optimizer_current_lux,
                            target_lux=optimizer_target_lux,
                            gain_matrix=optimizer_gain_matrix,
                            min_duty=0,
                            max_duty=100,
                            panel_power_watts=panel_power_list,
                        )

                    # Optimizer calls are not interruptible. Never publish their
                    # result if Stop was requested while a solve was in progress.
                    ensure_auto_control_running()
                    duties_integer = integerize_duties_ceil(duties_decimal)

                    ensure_auto_control_running()
                    set_status("Sending panel duties and waiting for acknowledgements...")
                    panel_cmd_ids = {}
                    duties_sent = []
                    flicker_rules = []

                    for index, panel_id in enumerate(panel_ids):
                        ensure_auto_control_running()
                        duty_to_send, flicker_rule = apply_low_duty_lock(
                            current_duty=current_duties[index],
                            ideal_duty=duties_integer[index],
                        )
                        cmd_id = backend.send_panel_duty(
                            panel_id,
                            duty_to_send,
                            transition="smooth",
                            step_ms=ramp_step_ms,
                        )
                        panel_cmd_ids[panel_id] = cmd_id

                        duties_sent.append(duty_to_send)
                        flicker_rules.append(flicker_rule)

                    estimated_lux = estimate_lux_after_control(
                        current_lux=ambient_lux,
                        gain_matrix=active_gain_matrix,
                        duties=duties_sent,
                    )

                    wait_for_panel_ack(
                        panel_cmd_ids=panel_cmd_ids,
                        timeout_seconds=5.0,
                        stop_event=stop_signal,
                    )

                    max_ramp_seconds = 0.0

                    for current_duty, sent_duty in zip(current_duties, duties_sent):
                        max_ramp_seconds = max(
                            max_ramp_seconds,
                            estimate_panel_ramp_seconds(
                                current_duty=current_duty,
                                target_duty=sent_duty,
                                ramp_step_ms=ramp_step_ms,
                            ),
                        )

                    ramp_wait_seconds = max_ramp_seconds + RAMP_SETTLE_MARGIN_SECONDS
                    elapsed_before_wait = time.time() - cycle_started
                    ramp_wait_seconds = max(
                        ramp_wait_seconds,
                        MIN_AUTO_CONTROL_CYCLE_SECONDS - elapsed_before_wait,
                    )
                    set_status(
                        f"Waiting {ramp_wait_seconds:.1f}s for ramp and sensor settling..."
                    )
                    sleep_interruptible(ramp_wait_seconds, stop_signal)

                    cycle_finished = time.time()
                    cycle_seconds = cycle_finished - cycle_started
                    result = {
                        "ok": True,
                        "mode": mode,
                        "presence_source": presence_source,
                        "control_strategy": control_strategy,
                        "uniform_weights": uniform_weights,
                        "measured_lux": measured_lux,
                        "display_sensor_ids": active_sensor_ids,
                        "reference_raw_lux": [
                            reading["raw"]
                            for reading in reference_readings
                        ],
                        "reference_measured_lux": [
                            reading["lux"]
                            for reading in reference_readings
                        ],
                        "reference_panel_contribution": reference_contribution,
                        "current_duties": current_duties,
                        "panel_contribution": panel_contribution,
                        "ambient_lux": ambient_lux,
                        "uncontrolled_rows": uncontrolled_rows,
                        "target_lux": list(target_lux),
                        "optimizer_lamp_target_lux": list(optimizer_target_lux),
                        "presence_target_details": presence_target_details,
                        "optimizer_result": optimizer_result,
                        "occupancy_source": occupancy_source,
                        "duties_decimal": duties_decimal,
                        "duties_integer": duties_integer,
                        "duties_sent": duties_sent,
                        "flicker_rules": flicker_rules,
                        "estimated_lux": estimated_lux,
                        "ramp_step_ms": ramp_step_ms,
                        "ramp_wait_seconds": ramp_wait_seconds,
                        "cycle_seconds": cycle_seconds,
                        "timestamp": time.strftime("%H:%M:%S"),
                    }

                    with lock:
                        job["cycle_count"] += 1
                        job["retry_count"] = 0
                        job["last_retry_error"] = None
                        job["last_result"] = result
                        job["last_cycle_seconds"] = cycle_seconds
                        job["message"] = f"Last control cycle completed in {cycle_seconds:.1f}s."
                        job["updated_at"] = cycle_finished

                    if one_shot:
                        completed_one_shot = True
                        break

                except RuntimeError as exc:
                    if stop_signal.is_set():
                        raise
                    mark_cycle_retry(str(exc), cycle_started)

            with lock:
                job["status"] = "stopped"
                job["message"] = (
                    "Manual zone one-shot completed."
                    if completed_one_shot
                    else "Auto control stopped."
                )
                job["error"] = None
                job["updated_at"] = time.time()

        except RuntimeError as exc:
            with lock:
                if stop_signal.is_set():
                    job["status"] = "stopped"
                    job["message"] = "Auto control stopped."
                    job["error"] = None
                else:
                    job["status"] = "error"
                    job["message"] = "Auto control stopped because of an error."
                    job["error"] = str(exc)
                job["updated_at"] = time.time()
        except Exception as exc:
            with lock:
                job["status"] = "error"
                job["message"] = "Auto control stopped because of an error."
                job["error"] = str(exc)
                job["updated_at"] = time.time()
        finally:
            backend.finish_auto_control(generation)

    thread = threading.Thread(
        target=worker,
        name="auto-control-worker",
        daemon=True,
    )
    job["thread"] = thread

    st.session_state["auto_control_job"] = job
    st.session_state["auto_control_checkbox"] = True
    thread.start()


def render_live_dashboard():
    panels_live = backend.get_panels()
    sensors_live = backend.get_sensors()
    current_mode_live = "Auto" if get_auto_control_snapshot()["active"] else "Manual"

    render_app_header(backend.connected)
    
    online_panel_count = sum(
        1 for panel in panels_live.values()
        if panel.online
    )

    online_sensor_count = sum(
        1 for sensor in sensors_live.values()
        if sensor.online
    )

    render_dashboard_summary(
        panel_count=online_panel_count,
        sensor_count=online_sensor_count,
        mqtt_connected=backend.connected,
        mode_text=current_mode_live,
    )

def render_control_devices():
    panels_live = backend.get_panels()
    sensors_live = backend.get_sensors()

    ordered_panel_ids = sort_by_defined_order(list(panels_live.keys()), PANEL_ORDER)
    ordered_sensor_ids = sort_by_defined_order(list(sensors_live.keys()), SENSOR_ORDER)

    st.header("Panels")

    panel_cols = st.columns(4)

    for index, panel_id in enumerate(ordered_panel_ids):
        panel = panels_live[panel_id]
        panel_label = get_panel_label(panel_id)

        with panel_cols[index % 4]:
            with st.expander(panel_label, expanded=True):
                avg_duty = 0

                if panel.duty:
                    avg_duty = int(round(sum(panel.duty) / len(panel.duty)))

                info_items = [
                    f"IP: {panel.ip or '-'}",
                    f"Power: {get_panel_power_watts(panel_id, avg_duty)}",
                ]

                if panel_id in TEMP_PANEL_IDS:
                    temp_text = "-"
                    if panel.temp_c is not None:
                        temp_text = f"{panel.temp_c:.1f}"
                    info_items.insert(1, f"Temp: {temp_text} C")

                device_info_row(
                    panel.online,
                    info_items,
                )

                mode_key = f"manual_transition_{panel_id}"
                step_key = f"manual_step_ms_{panel_id}"

                if mode_key not in st.session_state:
                    st.session_state[mode_key] = "Smooth"

                if step_key not in st.session_state:
                    st.session_state[step_key] = 25
                else:
                    st.session_state[step_key] = clamp_manual_step_ms(
                        st.session_state[step_key]
                    )

                mode_col, step_col = st.columns([2, 1])

                with mode_col:
                    manual_mode = st.radio(
                        "Dimming mode",
                        options=["Smooth", "Immediate"],
                        horizontal=True,
                        key=mode_key,
                    )

                with step_col:
                    step_ms = st.number_input(
                        "Step ms",
                        min_value=10,
                        max_value=500,
                        step=10,
                        key=step_key,
                        disabled=(manual_mode == "Immediate"),
                    )

                slider_key = f"duty_{panel_id}"
                if slider_key not in st.session_state:
                    st.session_state[slider_key] = avg_duty

                st.slider(
                    "Duty %",
                    min_value=0,
                    max_value=100,
                    key=slider_key,
                    on_change=send_manual_panel_duty_from_slider,
                    args=(panel_id,),
                )


    st.header("Sensors")

    if st.button("Request lux from all sensors"):
        backend.request_all_lux()
        st.success("Lux request sent to all sensors")

    sensor_cols = st.columns(4)

    for index, sensor_id in enumerate(ordered_sensor_ids):
        sensor = sensors_live[sensor_id]
        sensor_label = get_sensor_label(sensor_id)

        with sensor_cols[index % 4]:
            with st.expander(sensor_label, expanded=True):
                device_info_row(
                    sensor.online,
                    [
                        f"IP: {sensor.ip or '-'}",
                        f"Raw: {sensor.raw_lux if sensor.raw_lux is not None else '-'} lx",
                        f"Lux: {sensor.lux if sensor.lux is not None else '-'} lx",
                    ],
                )

                if st.button("Request Lux", key=f"lux_{sensor_id}"):
                    backend.request_sensor_lux(sensor_id)
                    st.success(f"Lux request sent to {sensor_label}")

    st.subheader("Regression Model Check")
    regression_rows = build_live_regression_check_rows(sensors_live)

    if regression_rows is None:
        st.info("Request lux from R1 and R2 to estimate S1-S6 with the regression model.")
    else:
        st.dataframe(
            regression_rows,
            width="stretch",
            hide_index=True,
        )

    # MQTT log rendering is disabled for now to keep the Streamlit UI lighter.
    # st.header("MQTT Logs")
    # logs = backend.get_logs(limit=80)
    # st.code("\n".join(logs[-80:]))


def render_occupancy_zone_table():
    occupancy = backend.get_occupancy()

    if occupancy is None:
        st.warning("No occupancy data received yet. Run desk_presence.py.")
        return

    occupied = occupancy.get("occupied", {})
    raw_occupied = occupancy.get("raw_occupied", occupied)
    persons_per_zone = occupancy.get("persons_per_zone", {})
    raw_persons_per_zone = occupancy.get("raw_persons_per_zone", persons_per_zone)
    stable = occupancy.get("stable", {})
    person_count = occupancy.get("person_count", occupancy.get("raw_person_count", 0))

    zone_table = []

    for zone_name in sorted(set(raw_occupied.keys()) | set(occupied.keys())):
        zone_table.append(
            {
                "Zone": zone_name,
                "Occupied": bool(raw_occupied.get(zone_name, False)),
                "Persons": int(raw_persons_per_zone.get(zone_name, 0) or 0),
                "Stable": stable.get(
                    zone_name,
                    "occupied stable" if occupied.get(zone_name, False) else "unoccupied stable",
                ),
            }
        )

    st.dataframe(zone_table, width="stretch")
    st.caption(
        f"People detected: {person_count} | Last update: {occupancy.get('timestamp', '-')}"
    )


def get_radar_node_zone(node_id, state=None):
    if state:
        try:
            zone_number = int(state.get("zone", 0))
        except (TypeError, ValueError):
            zone_number = 0
        if zone_number in (1, 2):
            return zone_number

    marker = "_zone_"
    if marker not in node_id:
        return None

    try:
        zone_number = int(node_id.rsplit(marker, 1)[1])
    except (TypeError, ValueError):
        return None

    return zone_number if zone_number in (1, 2) else None


def render_radar_presence_table():
    radar_nodes = backend.get_radar_presence()
    radar_info = backend.get_radar_presence_info()

    if not radar_nodes:
        st.warning("No radar presence data received yet.")
        st.caption("Waiting for MQTT topic: presence/<node_id>/state")
        return

    now = time.time()
    rows = []

    for node_id, state in sorted(radar_nodes.items()):
        received_at = float(state.get("_received_at", 0.0) or 0.0)
        age_seconds = now - received_at if received_at > 0 else None
        fresh = age_seconds is not None and age_seconds <= 15.0
        assigned_zone = get_radar_node_zone(node_id, state)
        if assigned_zone is None:
            assigned_zone = get_radar_node_zone(node_id, radar_info.get(node_id, {}))

        zone_numbers = [assigned_zone] if assigned_zone else [1, 2]
        for zone_number in zone_numbers:
            rows.append(
                {
                    "Node": node_id,
                    "IP": state.get("ip", "-"),
                    "Zone": f"Zone {zone_number}",
                    "Occupied": bool(state.get(f"z{zone_number}", 0)),
                    "Fresh": fresh,
                    "Age (s)": round(age_seconds, 1) if age_seconds is not None else "-",
                }
            )

    st.dataframe(rows, width="stretch", hide_index=True)


def render_radar_presence_settings():
    radar_nodes = backend.get_radar_presence()
    radar_info = backend.get_radar_presence_info()
    known_node_ids = sorted(set(radar_nodes.keys()) | set(radar_info.keys()))

    st.subheader("Radar Sensor Settings")

    if not known_node_ids:
        st.caption("Waiting for a radar sensor node.")
        return

    selected_node = st.selectbox(
        "Radar node",
        known_node_ids,
        index=0,
        key="radar_presence_config_node",
    )

    info = radar_info.get(selected_node, {})
    cfg = info.get("cfg", {})
    off_input_key = f"radar_off_seconds_{selected_node}"
    info_sync_key = f"{off_input_key}_info_received_at"
    info_received_at = float(info.get("_received_at", 0.0) or 0.0)
    saved_off_seconds = int(float(cfg.get("off_ms", 30000)) / 1000)

    if off_input_key not in st.session_state:
        st.session_state[off_input_key] = saved_off_seconds

    if (
        info_received_at > 0
        and st.session_state.get(info_sync_key) != info_received_at
    ):
        st.session_state[off_input_key] = saved_off_seconds
        st.session_state[info_sync_key] = info_received_at

    off_seconds = st.number_input(
        "Off time (s)",
        min_value=1,
        max_value=3600,
        step=1,
        key=off_input_key,
    )

    action_cols = st.columns([1, 1, 4])

    with action_cols[0]:
        if st.button("Apply settings", key=f"radar_apply_{selected_node}"):
            payload = {
                "off_ms": int(off_seconds) * 1000,
            }
            backend.set_radar_presence_config(selected_node, payload)
            st.success(f"Settings sent to {selected_node}")

    with action_cols[1]:
        if st.button("Request config", key=f"radar_config_{selected_node}"):
            backend.set_radar_presence_config(selected_node, {"config": 1})
            st.success(f"Config request sent to {selected_node}")

    if info:
        sensor_info = info.get("s1", {})
        raw_high = bool(sensor_info.get("raw", 0))
        last_high_ms = sensor_info.get("last", -1)
        last_high_text = (
            "never"
            if last_high_ms is None or float(last_high_ms) < 0
            else f"{float(last_high_ms) / 1000:.1f}s ago"
        )
        st.caption(
            f"Saved off time: {saved_off_seconds}s | "
            f"D5: {'HIGH' if raw_high else 'LOW'} | "
            f"Last accepted HIGH: {last_high_text} | "
            f"Info received {time.time() - info_received_at:.1f}s ago"
        )


if "auto_control_checkbox" not in st.session_state:
    st.session_state["auto_control_checkbox"] = False

render_live_dashboard()

if "manual_message" in st.session_state:
    st.toast(st.session_state.pop("manual_message"))


def render_fast_navigation():
    if "active_page" not in st.session_state:
        st.session_state["active_page"] = get_query_page() or "Control"
    else:
        query_page = get_query_page()
        if query_page is not None and query_page != st.session_state["active_page"]:
            st.session_state["active_page"] = query_page

    nav_items = VALID_PAGES
    nav_cols = st.columns(4, gap="small")

    for index, item in enumerate(nav_items):
        with nav_cols[index]:
            is_active = st.session_state["active_page"] == item
            button_label = item

            if st.button(
                button_label,
                key=f"nav_{item}",
                width="stretch",
                type="primary" if is_active else "secondary",
            ):
                st.session_state["active_page"] = item
                set_query_page(item)
                st.rerun()

    set_query_page(st.session_state["active_page"])
    return st.session_state["active_page"]


selected_tab = render_fast_navigation()
# =========================
# CONTROL TAB
# =========================

if selected_tab == "Control":
    st_autorefresh(
        interval=2000,
        key="control_tab_refresh",
    )

    render_control_devices()
    st.stop()


# =========================
# CALIBRATION TAB
# =========================

elif selected_tab == "Calibration":

    st.header("Calibration")

    panels = backend.get_panels()
    sensors = backend.get_sensors()

    panel_ids = [pid for pid in PANEL_ORDER if pid in panels]
    sensor_ids = known_then_extra_device_ids(sensors.keys(), SENSOR_ORDER)

    missing_panels = [get_panel_label(pid) for pid in PANEL_ORDER if pid not in panels]
    configured_missing_sensors = [
        get_sensor_label(sid)
        for sid in SENSOR_ORDER
        if sid not in sensors
    ]

    if len(panel_ids) == 0 or len(sensor_ids) == 0:
        calibration_status_card(
            status="error",
            message="Need at least 1 panel and 1 sensor for calibration.",
        )
        st.stop()

    if missing_panels:
        st.warning(f"Missing panels: {missing_panels}")

    st.info(
        "Calibration will use "
        f"{len(sensor_ids)} detected sensor(s): "
        + ", ".join(
            f"{get_sensor_label(sensor_id)} ({get_sensor_role(sensor_id)})"
            for sensor_id in sensor_ids
        )
    )

    # Missing zone sensors are acceptable during partial tests; calibration uses only
    # sensors that are online now.

    job = get_calibration_job()

    with job["lock"]:
        job_status = job.get("status", "idle")

    is_running = job_status == "running"
    is_stopping = job_status == "stopping"
    st.session_state["calibration_running"] = is_running or is_stopping

    if is_running or is_stopping:
        st_autorefresh(interval=2000, key="calibration_auto_refresh")

    strict_mode, start_calibration, stop_calibration = calibration_start_controls(
        is_running=is_running,
        is_stopping=is_stopping,
    )

    previous_calibration = load_previous_calibration()

    if previous_calibration is not None:
        calibration_history_card(
            history_path=CALIBRATION_PATH,
            loaded=True,
            message="A previous calibration file is available and can be used if the new calibration fails.",
        )
    else:
        calibration_history_card(
            history_path=CALIBRATION_PATH,
            loaded=False,
            message="No previous calibration file found.",
        )

    if stop_calibration and is_running:
        stop_event = job.get("stop_event")

        if stop_event is not None:
            stop_event.set()

        with job["lock"]:
            job["status"] = "stopping"

        st.session_state["calibration_running"] = True
        st.rerun()

    if start_calibration and not (is_running or is_stopping):
        device_problems = detect_missing_devices(panel_ids, sensor_ids)

        if device_problems:
            previous_calibration = load_previous_calibration()

            if previous_calibration is not None:
                calibration_problem_card(
                    title="Calibration cannot run cleanly. Previous calibration will remain active.",
                    problems=device_problems,
                    fallback_used=True,
                )
            else:
                calibration_problem_card(
                    title="Calibration cannot run. No previous calibration is available.",
                    problems=device_problems,
                    fallback_used=False,
                )

            st.stop()

        start_calibration_background(panel_ids, sensor_ids, strict_mode)
        st.session_state["calibration_running"] = True
        st.rerun()

    with job["lock"]:
        job_status = job.get("status", "idle")
        job_logs = list(job.get("logs", []))
        job_steps = list(job.get("steps", []))
        job_result = job.get("result")
        job_error = job.get("error")
        job_started_at = job.get("started_at")
        job_finished_at = job.get("finished_at")

    if job_status in ["running", "stopping"]:
        elapsed = time.time() - job_started_at if job_started_at else None
        message = (
            "Stop requested. Finishing the current safe step and saving partial calibration..."
            if job_status == "stopping"
            else "Calibration is running..."
        )

        calibration_status_card(
            status="running",
            message=message,
            elapsed_seconds=elapsed,
        )
        calibration_step_list(job_steps)

        if job_logs:
            st.subheader("Live Calibration Logs")
            st.code("\n".join(job_logs[-80:]), language="text")

        st.stop()

    if job_status == "error":
        duration_seconds = (
            job_finished_at - job_started_at
            if job_started_at and job_finished_at
            else None
        )

        calibration_problem_card(
            title="Calibration failed. Previous calibration remains active.",
            problems=[job_error or "Unknown calibration error."],
            fallback_used=previous_calibration is not None,
        )
        calibration_status_card(
            status="error",
            message="Calibration failed.",
            elapsed_seconds=duration_seconds,
        )

        if job_logs:
            st.subheader("Calibration Logs")
            st.code("\n".join(job_logs[-80:]), language="text")

        st.stop()

    if job_result is not None:
        duration_seconds = (
            job_finished_at - job_started_at
            if job_started_at and job_finished_at
            else 0.0
        )
        done_time = (
            time.strftime("%H:%M:%S", time.localtime(job_finished_at))
            if job_finished_at
            else None
        )
        store_last_calibration_result(
            job_result,
            job_logs,
            duration_seconds,
            done_time=done_time,
        )

        if job_status == "stopped":
            completed_labels = [
                get_panel_label(pid)
                for pid in job_result.completed_panel_ids
            ]
            stopped_label = (
                get_panel_label(job_result.stopped_at_panel_id)
                if job_result.stopped_at_panel_id
                else "the next panel"
            )
            problems = [
                f"You stopped calibration at {stopped_label}.",
            ]

            if job_result.ambient_completed:
                problems.append("Daylight / uncontrolled illuminance was saved.")
            else:
                problems.append("Daylight / uncontrolled illuminance did not finish; previous ambient values were kept where available.")

            if completed_labels:
                problems.append(
                    "New gain values were saved for: "
                    + ", ".join(completed_labels)
                    + "."
                )
            else:
                problems.append("No panel gain values finished before the stop.")

            problems.append("Unfinished panels kept previous gain values where available.")

            calibration_problem_card(
                title="Calibration stopped by user. Partial calibration was saved.",
                problems=problems,
                fallback_used=True,
            )

    saved = st.session_state.get("last_calibration_result")

    if saved is None and previous_calibration is not None:
        saved = calibration_json_to_display_result(previous_calibration)

    if saved is not None:

        if saved.get("status") == "partial" or saved.get("fallback_used"):
            calibration_problem_card(
                title="Calibration completed with warnings. History/fallback values were used.",
                problems=[
                    warning.get("message", str(warning))
                    for warning in saved.get("warnings", [])
                ],
                fallback_used=True,
            )

            calibration_status_card(
                status="partial",
                message="Partial calibration: system is using fallback/history values.",
                elapsed_seconds=saved["duration_seconds"],
            )
        else:
            calibration_status_card(
                status="success",
                message="Calibration completed successfully.",
                elapsed_seconds=saved["duration_seconds"],
            )

        calibration_result_grid(
            done_time=saved["done_time"],
            duration_seconds=saved["duration_seconds"],
            panel_count=len(saved["panel_ids"]),
            sensor_count=len(saved["sensor_ids"]),
        )

        st.subheader("Daylight / Uncontrolled Illuminance")

        ambient_df = pd.DataFrame(
            [
                {
                    "Sensor": get_sensor_label(saved["sensor_ids"][i]),
                    "Role": get_sensor_role(saved["sensor_ids"][i]),
                    "Uncontrolled Lux": int(round(saved["ambient_lux"][i])),
                }
                for i in range(len(saved["sensor_ids"]))
            ]
        )

        styled_ambient_df = style_ambient_lux_by_value(
            ambient_df,
            lux_column="Uncontrolled Lux",
        )

        render_calibration_styled_table(styled_ambient_df)

        st.subheader("Gain Matrix")

        gain_df, panel_columns = build_gain_matrix_dataframe(saved)

        styled_gain_df = style_gain_matrix_by_sensor(
            gain_df,
            panel_columns,
        )

        render_calibration_styled_table(styled_gain_df)

        st.subheader("Lux / Watt Matrix")

        lux_per_watt_df, lux_per_watt_columns = build_lux_per_watt_dataframe(saved)
        styled_lux_per_watt_df = style_gain_matrix_by_sensor(
            lux_per_watt_df,
            lux_per_watt_columns,
        ).format(
            {
                col: "{:.2f}"
                for col in lux_per_watt_columns
            }
        )

        render_calibration_styled_table(styled_lux_per_watt_df)

        if saved.get("logs"):
            st.subheader("Calibration Logs")
            st.code("\n".join(saved["logs"][-80:]), language="text")


# =========================
# OCCUPANCY TAB
# =========================

elif selected_tab == "Occupancy":

    st.header("Occupancy Detection")

    st_autorefresh(
        interval=2000,
        key="occupancy_tab_refresh",
    )

    _, selected_presence_source_label = get_selected_presence_source()
    occupancy_source = st.radio(
        "Presence source",
        PRESENCE_SOURCE_OPTIONS,
        index=PRESENCE_SOURCE_OPTIONS.index(selected_presence_source_label),
        horizontal=True,
        key="occupancy_presence_source_widget",
    )
    set_selected_presence_source(occupancy_source)

    if occupancy_source == "Camera":
        render_occupancy_zone_table()
    else:
        render_radar_presence_table()
        render_radar_presence_settings()

    st.stop()


# =========================
# AUTO CONTROL TAB
# =========================

elif selected_tab == "Auto Control":

    st.header("Auto Control")

    auto_job = get_auto_control_job()
    auto_snapshot = get_auto_control_snapshot(auto_job)
    auto_status = auto_snapshot["status"]
    auto_message = auto_snapshot["message"]
    auto_error = auto_snapshot["error"]
    auto_result = auto_snapshot["last_result"]
    auto_cycle_seconds = auto_snapshot["last_cycle_seconds"]
    auto_cycle_count = auto_snapshot["cycle_count"]
    auto_retry_count = auto_snapshot["retry_count"]
    auto_last_retry_error = auto_snapshot["last_retry_error"]
    local_auto_active = auto_snapshot["active"]
    shared_auto_active = backend.has_active_auto_control()
    external_auto_active = shared_auto_active and not local_auto_active
    auto_active = local_auto_active or shared_auto_active
    auto_stopping = auto_snapshot["stopping"]

    if external_auto_active:
        auto_status = "running"
        auto_message = "Auto control is active in another browser session."

    if auto_active:
        st_autorefresh(interval=1000, key="auto_control_auto_refresh")

    if not os.path.exists(CALIBRATION_PATH):
        st.warning("No calibration.json found. Run calibration first.")
        st.stop()

    with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
        calibration = json.load(f)

    calibration_panel_ids = calibration["panel_ids"]
    calibration_sensor_ids = calibration["sensor_ids"]

    missing_calibrated_panels = [
        panel_id
        for panel_id in PANEL_ORDER
        if panel_id not in calibration_panel_ids
    ]

    if missing_calibrated_panels:
        st.error(
            "The loaded calibration file does not include all 9 panels. "
            "Run calibration again with all panels online before using Auto Control. "
            "Missing from calibration: "
            + ", ".join(get_panel_label(panel_id) for panel_id in missing_calibrated_panels)
        )
        st.stop()

    missing_presence_sensors = [
        sensor_id
        for sensor_id in ZONE_SENSOR_IDS + REFERENCE_SENSOR_ORDER
        if sensor_id not in calibration_sensor_ids
    ]

    calibration_created_at = calibration.get("created_at")

    if calibration_created_at:
        calibration_time_text = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(float(calibration_created_at)),
        )
    else:
        calibration_time_text = "Unknown time"

    calibration_status = calibration.get("status", "success")
    st.info(
        f"Calibration coefficients loaded - created at {calibration_time_text} - status: {calibration_status}"
    )

    auto_mode_panel(auto_active)

    presence_source, selected_presence_source_label = get_selected_presence_source()

    if "auto_control_method_label" not in st.session_state:
        with auto_job["lock"]:
            saved_config = auto_job.get("config", {})
            saved_mode = saved_config.get("mode", "presence")
            saved_strategy = saved_config.get("control_strategy", "lp")

        st.session_state["auto_control_method_label"] = (
            "Manual zones one-shot"
            if saved_mode in ["manual", "manual_zones"]
            else "Uniform optimization"
            if saved_strategy == "uniform"
            else "Minimum energy LP"
        )

    method_label = st.radio(
        "Control method",
        options=[
            "Minimum energy LP",
            "Uniform optimization",
            "Manual zones one-shot",
        ],
        horizontal=True,
        disabled=auto_active,
        key="auto_control_method_label",
    )

    control_strategy = "uniform" if method_label == "Uniform optimization" else "lp"
    if method_label == "Manual zones one-shot":
        auto_mode = "manual_zones"
    else:
        auto_mode = "radar_presence" if presence_source == "radar" else "presence"

    if auto_mode == "manual_zones":
        st.caption("One-shot mode uses manual zone selection below.")
    else:
        st.caption(f"Presence source: {selected_presence_source_label}. Change it in the Occupancy tab.")

    if missing_presence_sensors:
        st.error(
            "Auto control requires calibration with 6 virtual zone rows plus R1/R2 references. "
            "Missing from calibration: "
            + ", ".join(get_sensor_label(sensor_id) for sensor_id in missing_presence_sensors)
        )
        st.stop()

    occupied_comfort_lux = {}
    unoccupied_comfort_lux = {}
    manual_active_sensor_ids = []

    config_cols = st.columns(4 if control_strategy == "uniform" else 3)
    auto_ramp_step_key = "auto_ramp_step_ms"
    uniform_power_weight_key = "uniform_weight_power"
    uniform_duty_weight_key = "uniform_weight_duty"
    uniform_change_weight_key = "uniform_weight_change"

    if auto_ramp_step_key not in st.session_state:
        st.session_state[auto_ramp_step_key] = 25
    else:
        st.session_state[auto_ramp_step_key] = clamp_manual_step_ms(
            st.session_state[auto_ramp_step_key]
        )

    with config_cols[0]:
        ramp_step_ms = st.number_input(
            "Panel ramp step ms",
            min_value=10,
            max_value=500,
            step=10,
            disabled=auto_active,
            key=auto_ramp_step_key,
        )

    if control_strategy == "uniform":
        if uniform_power_weight_key not in st.session_state:
            st.session_state[uniform_power_weight_key] = 1.0
        if uniform_duty_weight_key not in st.session_state:
            st.session_state[uniform_duty_weight_key] = 0.02
        if uniform_change_weight_key not in st.session_state:
            st.session_state[uniform_change_weight_key] = 0.005

        with config_cols[1]:
            uniform_power_weight = st.number_input(
                "Power weight",
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                format="%.4f",
                disabled=auto_active,
                key=uniform_power_weight_key,
            )
        with config_cols[2]:
            uniform_duty_weight = st.number_input(
                "Uniform duty weight",
                min_value=0.0,
                max_value=100.0,
                step=0.005,
                format="%.4f",
                disabled=auto_active,
                key=uniform_duty_weight_key,
            )
        with config_cols[3]:
            uniform_change_weight = st.number_input(
                "Duty change weight",
                min_value=0.0,
                max_value=100.0,
                step=0.005,
                format="%.4f",
                disabled=auto_active,
                key=uniform_change_weight_key,
            )
    else:
        uniform_power_weight = 1.0
        uniform_duty_weight = 0.02
        uniform_change_weight = 0.005

    occupancy_result = backend.get_occupancy() if auto_mode == "presence" else None
    radar_state = get_fresh_radar_presence_state() if auto_mode == "radar_presence" else None
    control_zone_map = (
        RADAR_LIGHTING_CONTROL_ZONES
        if auto_mode == "radar_presence"
        else LIGHTING_CONTROL_ZONES
    )
    preview_sensor_ids = [
        sensor_id
        for sensor_id in ZONE_SENSOR_IDS
        if sensor_id in calibration_sensor_ids
    ]

    if auto_mode == "presence":
        active_sensor_ids = get_presence_active_sensor_ids(
            occupancy_result,
            preview_sensor_ids,
        )
    else:
        active_sensor_ids = []

    st.subheader("Lighting Zone Target Lux")
    target_header = st.columns([1.0, 1.8, 1.2, 1.2, 1.2, 3.0])
    target_header[0].markdown("**Zone**")
    target_header[1].markdown("**Virtual sensors**")
    target_header[2].markdown("**Active**")
    target_header[3].markdown("**Occupied lux**")
    target_header[4].markdown("**Unoccupied lux**")
    target_header[5].markdown("**Efficient panels**")

    if auto_mode == "presence":
        active_lighting_zone_ids = get_active_lighting_zone_ids_from_occupancy(occupancy_result)
    elif auto_mode == "radar_presence":
        active_lighting_zone_ids = get_active_radar_lighting_zone_ids(radar_state)
    else:
        active_lighting_zone_ids = []

    for zone_id, zone in control_zone_map.items():
        zone_sensor_ids = [
            sensor_id
            for sensor_id in zone["sensor_ids"]
            if sensor_id in preview_sensor_ids
        ]
        if not zone_sensor_ids:
            continue

        occupied_key = f"lighting_zone_occupied_lux_{zone_id}"
        unoccupied_key = f"lighting_zone_unoccupied_lux_{zone_id}"
        manual_active_key = f"manual_lighting_zone_active_{zone_id}"

        if occupied_key not in st.session_state:
            st.session_state[occupied_key] = int(
                default_zone_occupied_lux(zone_id, control_zone_map)
            )

        if unoccupied_key not in st.session_state:
            st.session_state[unoccupied_key] = int(default_zone_unoccupied_lux(zone_id))

        if manual_active_key not in st.session_state:
            st.session_state[manual_active_key] = False

        row_cols = st.columns([1.0, 1.8, 1.2, 1.2, 1.2, 3.0])
        row_cols[0].write(zone["label"])
        row_cols[1].write(", ".join(get_sensor_label(sensor_id) for sensor_id in zone_sensor_ids))

        if auto_mode == "presence":
            is_active = zone_id in active_lighting_zone_ids
            row_cols[2].write("Yes" if is_active else "No")
        elif auto_mode == "radar_presence":
            is_active = zone_id in active_lighting_zone_ids
            row_cols[2].write("Yes" if is_active else "No")
        else:
            with row_cols[2]:
                is_active = st.checkbox(
                    f"{zone['label']} active",
                    key=manual_active_key,
                    disabled=auto_active,
                    label_visibility="collapsed",
                )
            if is_active:
                active_lighting_zone_ids.append(zone_id)

        with row_cols[3]:
            occupied_value = st.number_input(
                f"{zone['label']} occupied target lux",
                min_value=0,
                max_value=2000,
                step=10,
                key=occupied_key,
                disabled=auto_active,
                label_visibility="collapsed",
            )

        with row_cols[4]:
            unoccupied_value = st.number_input(
                f"{zone['label']} unoccupied target lux",
                min_value=0,
                max_value=2000,
                step=10,
                key=unoccupied_key,
                disabled=auto_active,
                label_visibility="collapsed",
            )

        row_cols[5].write(lighting_zone_panel_labels(zone, calibration_panel_ids))

        for sensor_id in zone_sensor_ids:
            occupied_comfort_lux[sensor_id] = max(
                float(occupied_value),
                float(occupied_comfort_lux.get(sensor_id, 0.0)),
            )
            unoccupied_comfort_lux[sensor_id] = max(
                float(unoccupied_value),
                float(unoccupied_comfort_lux.get(sensor_id, 0.0)),
            )

    active_sensor_ids = sensor_ids_for_lighting_zones(
        active_lighting_zone_ids,
        available_sensor_ids=preview_sensor_ids,
        zone_map=control_zone_map,
    )
    manual_active_sensor_ids = list(active_sensor_ids) if auto_mode == "manual_zones" else []

    control_efficient_panels_by_sensor = (
        efficient_panels_by_sensor_for_lighting_zones(
            active_lighting_zone_ids,
            control_zone_map,
        )
        if auto_mode == "radar_presence"
        else EFFICIENT_PANELS_BY_SENSOR
    )

    allowed_panel_ids = get_allowed_panels_for_active_sensors(
        active_sensor_ids=active_sensor_ids,
        panel_ids=calibration_panel_ids,
        efficient_panels_by_sensor=control_efficient_panels_by_sensor,
    )

    st.subheader("Lighting Zone Target Preview")
    st.dataframe(
        [
            {
                "Zone": zone["label"],
                "Presence Source": (
                    ", ".join(zone["occupancy_zones"])
                    if "occupancy_zones" in zone
                    else zone.get("radar_key", "-")
                ),
                "Virtual Sensors": ", ".join(
                    get_sensor_label(sensor_id)
                    for sensor_id in zone["sensor_ids"]
                    if sensor_id in preview_sensor_ids
                ),
                "Active": zone_id in active_lighting_zone_ids,
                "Target Lux": (
                    st.session_state.get(
                        f"lighting_zone_occupied_lux_{zone_id}",
                        default_zone_occupied_lux(zone_id, control_zone_map),
                    )
                    if zone_id in active_lighting_zone_ids
                    else st.session_state.get(
                        f"lighting_zone_unoccupied_lux_{zone_id}",
                        default_zone_unoccupied_lux(zone_id),
                    )
                ),
            }
            for zone_id, zone in control_zone_map.items()
            if any(sensor_id in preview_sensor_ids for sensor_id in zone["sensor_ids"])
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Allowed panels this cycle: "
        + (
            ", ".join(get_panel_label(panel_id) for panel_id in allowed_panel_ids)
            if allowed_panel_ids
            else "none"
        )
    )

    if auto_mode == "presence":
        if occupancy_result is None:
            st.warning("No occupancy data available yet. Presence mode will use unoccupied targets until occupancy arrives.")
        else:
            st.caption(f"Occupancy updated at {occupancy_result.get('timestamp', '-')}")
    elif auto_mode == "radar_presence":
        if not radar_state or not radar_state.get("fresh_node_ids"):
            st.warning(
                "No fresh radar presence data. Radar mode will use unoccupied targets until a fresh state arrives."
            )
        else:
            st.caption(
                "Radar fresh from "
                + ", ".join(radar_state["fresh_node_ids"])
                + f" | max age {float(radar_state.get('max_age_seconds') or 0.0):.1f}s"
            )

    current_config = {
        "mode": auto_mode,
        "presence_source": presence_source,
        "control_strategy": control_strategy,
        "uniform_weights": {
            "power": float(uniform_power_weight),
            "uniformity": float(uniform_duty_weight),
            "change": float(uniform_change_weight),
        },
        "ramp_step_ms": int(ramp_step_ms),
        "occupied_comfort_lux": occupied_comfort_lux,
        "unoccupied_comfort_lux": unoccupied_comfort_lux,
        "manual_active_sensor_ids": manual_active_sensor_ids,
        "one_shot": auto_mode == "manual_zones",
    }

    if auto_active:
        with auto_job["lock"]:
            auto_job["config"] = dict(current_config)

    button_cols = st.columns(2)

    with button_cols[0]:
        if st.button(
            "Solve and Send Once" if auto_mode == "manual_zones" else "Start Auto Control",
            width="stretch",
            type="primary",
            disabled=auto_active,
        ):
            start_auto_control_background(calibration, current_config)
            st.rerun()

    with button_cols[1]:
        if st.button(
            "Stopping..." if auto_stopping else "Stop Auto Control",
            width="stretch",
            type="primary" if auto_active else "secondary",
            disabled=auto_stopping,
        ):
            request_auto_control_stop(
                "Stop requested. Auto control will stop safely."
            )
            st.rerun()

    status_text = auto_status.capitalize()
    st.info(f"Status: {status_text} - {auto_message}")

    if auto_error:
        st.error(auto_error)

    metric_cols = st.columns(3)
    metric_cols[0].metric("Completed cycles", auto_cycle_count)
    metric_cols[1].metric(
        "Last control interval",
        f"{auto_cycle_seconds:.1f}s" if auto_cycle_seconds is not None else "-",
    )
    metric_cols[2].metric(
        "Ramp step",
        f"{int(ramp_step_ms)} ms",
    )

    if auto_last_retry_error:
        st.warning(
            f"Temporary issue, retry #{auto_retry_count}: {auto_last_retry_error}"
        )

    if auto_result is not None:
        st.subheader("Last Sensor / Lux Analysis")
        lux_table = []
        presence_rows_by_sensor = {}
        display_sensor_ids = auto_result.get("display_sensor_ids", calibration_sensor_ids)

        if auto_result.get("presence_target_details"):
            for row in auto_result["presence_target_details"].get("rows", []):
                presence_rows_by_sensor[row["Sensor"]] = row

        for index, sensor_id in enumerate(display_sensor_ids):
            sensor_label = get_sensor_label(sensor_id)
            row = {"Sensor": sensor_label}

            if auto_result.get("mode") in ["presence", "radar_presence", "manual_zones"]:
                presence_row = presence_rows_by_sensor.get(sensor_label, {})
                row.update(
                    {
                        "Occupied": presence_row.get("Occupied", False),
                        "Target Lux": presence_row.get("Target Lux", 0),
                        "Estimated Zone Uncontrolled Lux": auto_result["ambient_lux"][index],
                        "Current Estimated Panel Contribution": auto_result["panel_contribution"][index],
                        "Efficient Capacity Lux": presence_row.get("Efficient Capacity Lux", 0),
                        "Required Lamp Lux": presence_row.get("Lamp Target Lux", 0),
                        "Total Target Used": auto_result["target_lux"][index],
                    }
                )
            else:
                row.update(
                    {
                        "Measured Lux": auto_result["measured_lux"][index],
                        "Estimated Panel Contribution": auto_result["panel_contribution"][index],
                        "Estimated Ambient / Daylight": auto_result["ambient_lux"][index],
                        "Target Lux Used": auto_result["target_lux"][index],
                    }
                )

            row.update(
                {
                    "Estimated Lux After New Duties": auto_result["estimated_lux"][index],
                }
            )
            lux_table.append(row)

        st.dataframe(lux_table, width="stretch", hide_index=True)

        if auto_result.get("mode") in ["presence", "radar_presence", "manual_zones"]:
            reference_rows = []
            reference_raw_lux = auto_result.get("reference_raw_lux", [])
            reference_measured_lux = auto_result.get("reference_measured_lux", [])
            reference_panel_contribution = auto_result.get("reference_panel_contribution", [])

            for index, sensor_id in enumerate(REFERENCE_SENSOR_ORDER):
                if index >= len(reference_measured_lux):
                    continue

                raw_measured = (
                    float(reference_raw_lux[index])
                    if index < len(reference_raw_lux)
                    else 0.0
                )
                measured = float(reference_measured_lux[index])
                contribution = (
                    float(reference_panel_contribution[index])
                    if index < len(reference_panel_contribution)
                    else 0.0
                )

                reference_rows.append(
                    {
                        "Reference": get_sensor_label(sensor_id),
                        "Raw Measured": round(raw_measured, 2),
                        "Calibrated Measured Lux": round(measured, 2),
                        "Estimated Panel Contribution": round(contribution, 2),
                        "Uncontrolled Lux": round(max(0.0, measured - contribution), 2),
                    }
                )

            if reference_rows:
                st.subheader("Reference Sensor / Uncontrolled Estimate")
                st.dataframe(reference_rows, width="stretch", hide_index=True)

        if auto_result.get("mode") in ["presence", "radar_presence", "manual_zones"]:
            allowed_panel_ids = auto_result.get("presence_target_details", {}).get(
                "allowed_panel_ids",
                [],
            )
            st.caption(
                "Efficient panels allowed in last cycle: "
                + (
                    ", ".join(get_panel_label(panel_id) for panel_id in allowed_panel_ids)
                    if allowed_panel_ids
                    else "none"
                )
            )

        st.subheader("Last Panel Duties")
        duty_table = []
        duty_method_label = (
            "Uniform Optimization Decimal Duty %"
            if auto_result.get("control_strategy") == "uniform"
            else "LP Decimal Duty %"
        )
        duty_integer_label = (
            "Uniform Integer Duty %"
            if auto_result.get("control_strategy") == "uniform"
            else "LP Integer Duty %"
        )

        for index, panel_id in enumerate(calibration_panel_ids):
            duty_table.append(
                {
                    "Panel": get_panel_label(panel_id),
                    "Current Duty %": auto_result["current_duties"][index],
                    duty_method_label: auto_result["duties_decimal"][index],
                    duty_integer_label: auto_result["duties_integer"][index],
                    "Sent Duty %": auto_result["duties_sent"][index],
                    "Flicker Rule": auto_result.get("flicker_rules", [""] * len(calibration_panel_ids))[index],
                }
            )

        st.dataframe(duty_table, width="stretch", hide_index=True)
        mode_text = (
            "Presence detection"
            if auto_result.get("mode") == "presence"
            else "Radar presence"
            if auto_result.get("mode") == "radar_presence"
            else "Manual zones one-shot"
        )
        optimizer_text = (
            "Uniform optimization"
            if auto_result.get("control_strategy") == "uniform"
            else "Minimum energy LP"
        )
        st.caption(
            f"Last cycle: {auto_result['timestamp']} | "
            f"Mode: {mode_text} | "
            f"Optimizer: {optimizer_text} | "
            f"Occupancy: {auto_result.get('occupancy_source', '-')} | "
            f"Ramp wait: {auto_result['ramp_wait_seconds']:.1f}s | "
            f"Total interval: {auto_result['cycle_seconds']:.1f}s"
        )

        optimizer_result = auto_result.get("optimizer_result", {})
        if optimizer_result and auto_result.get("control_strategy") == "uniform":
            st.caption(
                "Uniform optimizer: "
                f"power {optimizer_result.get('power_watts', '-')} W | "
                f"duty variance {optimizer_result.get('uniformity_value', '-')} | "
                f"change penalty {optimizer_result.get('change_value', '-')} | "
                f"{optimizer_result.get('message', '')}"
            )

    st.stop()
