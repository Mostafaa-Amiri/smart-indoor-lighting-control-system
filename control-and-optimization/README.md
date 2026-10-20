# Central Lighting Controller

**Smart Indoor Lighting Control System · University of Tehran**

This experimentally developed Python controller integrates wireless lighting hardware, illuminance measurements, occupancy sensing, automated calibration, and optimization-based dimming in a real-time management dashboard.

## Architecture

**Streamlit dashboard** (`main.py`, `ui_style.py`) ↔ **MQTT communication** (`mqtt_backend.py`) ↔ **LED panels and wireless sensors**

The controller combines measurements and occupancy information with the experimentally measured lamp-to-sensor gain matrix to calculate and issue lighting commands.

## Software modules

| File | Engineering function |
| --- | --- |
| [`main.py`](central-controller/main.py) | Central Streamlit application: panel control, sensor monitoring, calibration, occupancy management, and automatic lighting control. |
| [`mqtt_backend.py`](central-controller/mqtt_backend.py) | MQTT device discovery, telemetry, command publishing, acknowledgements, and connection monitoring. |
| [`optimizer_lp.py`](central-controller/optimizer_lp.py) | Minimum-power linear programming with illuminance constraints; weighted alternative penalizing power consumption, differences among permitted panel duty cycles, and duty changes. |
| [`calibration.py`](central-controller/calibration.py) | Experimental calibration: measure ambient light, activate panels individually, acquire sensor responses, construct the gain matrix, and preserve calibration history. |
| [`calibration.json`](central-controller/calibration.json) | Recorded calibration dataset for nine panels and four illuminance sensors (4 × 9 gain matrix). |
| [`occupancy_backend.py`](central-controller/occupancy_backend.py) | Camera-based person detection with YOLO, perspective-zone mapping, temporal occupancy filtering, and MQTT publishing. |
| [`ui_style.py`](central-controller/ui_style.py) | Dashboard styling and components for device status, power display, calibration results, and controls. |

## Controller capabilities

- **Manual lighting control:** individual panel dimming with immediate or smooth transitions.
- **Automated experimental calibration:** measurement-based luminaire contributions, sensor-by-panel gain matrix, and saved calibration results.
- **Optimization-based control:** power-minimizing linear programming and a weighted duty-regularized optimization method; target illuminance and panel-power constraints are represented in the optimization models.
- **Daylight-aware operation:** separates estimated electric-light contributions from measured illuminance and supports reference-sensor-based uncontrolled illuminance estimation.
- **Occupancy-aware lighting:** camera-based four-zone person detection and mmWave radar inputs, with zone-specific targets and panel selection.
- **Live monitoring:** panel status, sensor values, temperature telemetry where available, and estimated lighting power.

### Calibration data

The included `calibration.json` belongs to this controller version and records **nine panels and four sensors**. The application also defines a wider configuration of **six zone sensors and two reference sensors** for its reference-based automatic-control path. Both the source configuration and the supplied recorded dataset are retained unchanged.

For circuit designs, devices and sensor hardware, see the [hardware documentation](../hardware/README.md). Arduino/ESP device firmware is documented in the [firmware directory](../firmware/README.md).
