# Central Lighting Controller

**Smart Indoor Lighting Control System · University of Tehran**

This experimentally developed Python controller integrates wireless lighting hardware, illuminance measurements, occupancy sensing, automated calibration, daylight estimation, and optimization-based dimming in a real-time management dashboard.

## Architecture

**Streamlit dashboard** (`main.py`, `ui_style.py`) ↔ **MQTT communication** (`mqtt_backend.py`) ↔ **LED panels and wireless sensors**

The controller combines measured lux, occupancy information, and the experimentally obtained sensor–panel gain matrix to calculate new dimming commands and publish them to the lighting network.

## System block diagrams

### Simple high-level architecture

![Simple block diagram](images/block_diagram_simple.png)

This simplified view shows the main signal flow from user target illuminance and sensing units to the central controller, and from the controller to the PWM-dimmed lighting panels.

### Detailed control architecture

![Detailed block diagram](images/block_diagram_detailed.png)

This detailed view shows the controller block in more explicit form, including occupancy conditions, measured illuminance inputs, preprocessing, occupancy and illuminance matrices, and the final control signals sent to the lighting drivers and lamps.

## Software modules

| File | Engineering function |
| --- | --- |
| [`main.py`](central-controller/main.py) | Central Streamlit application for panel control, sensor monitoring, calibration, occupancy management, and automatic lighting control. |
| [`mqtt_backend.py`](central-controller/mqtt_backend.py) | MQTT device discovery, telemetry, command publishing, acknowledgements, and connection monitoring. |
| [`optimizer_lp.py`](central-controller/optimizer_lp.py) | Optimization engine: hard-target linear programming and weighted duty optimization. |
| [`calibration.py`](central-controller/calibration.py) | Experimental calibration: measure ambient light, activate panels one by one, acquire sensor responses, construct the gain matrix, and preserve calibration history. |
| [`calibration.json`](central-controller/calibration.json) | Recorded calibration dataset for nine panels and four illuminance sensors (4 × 9 gain matrix). |
| [`occupancy_backend.py`](central-controller/occupancy_backend.py) | Camera-based person detection with YOLO, perspective-zone mapping, temporal occupancy filtering, and MQTT publishing. |
| [`ui_style.py`](central-controller/ui_style.py) | Dashboard styling and UI components for status, power, calibration results, and controls. |

## Controller capabilities

- **Manual lighting control:** individual panel dimming with immediate or smooth transitions.
- **Automated experimental calibration:** ambient measurement, per-panel activation, sensor response acquisition, and gain-matrix generation.
- **Optimization-based control:** calculates dimming levels from target lux, estimated daylight, calibration gains, and panel-power data.
- **Daylight-aware operation:** estimates uncontrolled lux by subtracting the estimated electric-light contribution from measured lux.
- **Occupancy-aware lighting:** camera-based four-zone occupancy detection and mmWave-based occupancy support.
- **Live monitoring:** panel duty, measured lux, estimated power, target lux, and automatic-control diagnostics.

## Optimization approach

The controller uses two optimization strategies.

### 1) Minimum-energy linear programming

The LP computes panel duties that satisfy the illuminance constraints while minimizing estimated electrical power.

- **Decision variables:** panel duty cycles
- **Constraint:** each controlled sensor or zone must reach its required lamp lux
- **Objective:** minimize total weighted electrical power

This mode is used when the goal is the lowest-power feasible lighting solution.

### 2) Weighted smooth-duty optimization

A second optimization mode extends the power-minimization problem with additional weighted penalties. Its objective combines:

- **power consumption**
- **duty non-uniformity** among the allowed active panels
- **duty change** relative to the current panel settings

The implemented solver uses `scipy.optimize.minimize` with **SLSQP**. Because the objective includes mean-squared penalty terms, it can be interpreted as a **weighted quadratic-like nonlinear optimization**. In practice, this mode explores a more balanced compromise between minimum power, smoother transitions, and more regular panel utilization.

### About nonlinear and quadratic optimization

The released implementation contains the LP solver and the weighted SLSQP-based optimizer. The advanced method is therefore not a pure textbook quadratic-programming implementation, but it does realize a nonlinear weighted objective with quadratic-like penalties. This formulation was useful for studying trade-offs beyond strict power minimization, especially when visual smoothness and reduced duty fluctuations were important.

## Calibration data

The included `calibration.json` belongs to this controller version and records **nine panels and four sensors**. The application also defines a wider configuration of **six zone sensors and two reference sensors** for its reference-based automatic-control path. Both the source configuration and the supplied recorded dataset are retained unchanged.

## Dashboard screenshots

### Control page and panel monitoring

![Control page and panels](images/control_panels.png)

### Sensors page and regression-model check

![Sensors and regression model](images/sensors_regression.png)

### Occupancy page

![Occupancy dashboard](images/occupancy_dashboard.png)

### Occupancy-based target-lux configuration

![Target lux configuration](images/target_lux_configuration.png)

### Auto-control diagnostics

![Auto control status](images/auto_control_status.png)

### Reference-sensor daylight estimate and final panel duties

![Reference sensor estimate and duties](images/reference_sensor_estimate_and_duties.png)

### Calibration / lux-per-watt matrix

![Lux per watt matrix](images/lux_watt_matrix.png)

### YOLO occupancy-zone detection

![YOLO occupancy zones](images/yolo_zone_detection.png)

For circuit designs, devices and sensor hardware, see the [hardware documentation](../hardware/README.md). Arduino/ESP device firmware is documented in the [firmware directory](../firmware/README.md).
