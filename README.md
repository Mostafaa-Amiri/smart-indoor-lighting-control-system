# Smart Indoor Lighting Control System

**CST Lab · University of Tehran**  
*Daylight-Aware · Occupancy-Adaptive · Optimization-Based Lighting*

## Overview

The **Smart Indoor Lighting Control System** is an integrated research platform designed, implemented, and experimentally evaluated at **CST Lab, University of Tehran**. It brings together custom LED lighting hardware, networked illuminance and occupancy sensors, daylight modeling, experimental calibration, and optimization-based control.

The system adjusts lighting at occupied workstations according to available daylight and the desired illuminance level, while minimizing estimated electrical power consumption. The repository documents the electronics, firmware, central controller, physical modeling, MATLAB signal processing, and laboratory demonstrations.

## System Architecture

![High-level smart lighting system architecture](control-and-optimization/images/block_diagram_simple.png)

*High-level signal flow from user-defined illuminance targets and environmental sensing to the central controller and dimmable lighting panels.*

Occupancy information determines which workstations require artificial lighting. Illuminance measurements and daylight estimates establish the remaining lighting demand. The controller then uses an experimentally calibrated **luminaire-to-sensor gain matrix** and panel-power information to select appropriate lighting panels and calculate PWM duty-cycle commands.

[View the detailed control architecture](control-and-optimization/images/block_diagram_detailed.png).

## Experimental Testbed

The project was developed and evaluated at **CST Lab, University of Tehran**, using installed ceiling-mounted LED panels, workstation partitions, illuminance and occupancy sensing, measurement instruments, and a central monitoring and control station.

<p align="center">
  <img src="assets/cst-lab-control-station.jpg" alt="CST Lab workstations and central lighting-control and simulation displays" width="49%">
  <img src="assets/cst-lab-installed-lighting.jpg" alt="Ceiling-mounted lighting panels installed in the CST Lab experimental testbed" width="49%">
</p>

<p align="center"><em>CST Lab experimental setup: monitoring and simulation workstations (left), and installed ceiling lighting panels (right).</em></p>

## Experimental Demonstration

The video demonstrates **daylight-aware, occupancy-responsive lighting with a 400 lx target** at the occupied desk. Initially, all lighting panels are off. The researcher moves between workstations to test different occupancy locations; the system activates the relevant lighting panels and computes dimming levels based on available daylight and each panel's contribution to the target area.

After a desk becomes vacant, the panels serving that desk switch off following a **15-second delay**. The newly occupied area is illuminated using the optimized panel settings. All panels are off again at the end of the demonstration.

[![Watch the smart indoor lighting experimental demonstration](results-and-media/images/demo-thumbnail.jpg)](https://youtube.com/shorts/Hcsu9ZKmqog?feature=share)

**[Watch the full experimental demonstration on YouTube](https://youtube.com/shorts/Hcsu9ZKmqog?feature=share)** · [Results and Media](results-and-media/README.md)

## Engineering Contributions

- **Lighting hardware:** three generations of custom LED panels, modular constant-current drivers, capacitive touch switching, and optical flicker-measurement hardware.
- **Embedded systems:** ESP8266/ESP32 firmware, Wi-Fi illuminance sensors, mmWave occupancy sensors, camera acquisition, and MQTT communication.
- **Modeling and simulation:** DIALux electric-light evaluation and Honeybee/Radiance daylight simulations for illuminance distribution and uniformity analysis.
- **Experimental calibration:** measured luminaire-to-sensor gain coefficients, estimates of individual panel contributions, and lux-per-watt comparisons.
- **Control and optimization:** energy-minimizing linear programming (LP), a weighted quadratic-objective optimization solved using SLSQP, and occupancy-aware automatic dimming.
- **Signal processing:** MATLAB waveform analysis, FFT, windowing, spectral peak identification, and frequency-oriented lighting characterization.

## Repository Sections

| Section | Description |
| --- | --- |
| **[Hardware](hardware/README.md)** | LED panel development (V1–V3), LED drivers, sensors, smart touch switches, and flicker-measurement circuits, with schematics and photographs. |
| **[Embedded Firmware](firmware/README.md)** | ESP8266/ESP32 firmware for dimming, measurement, occupancy sensing, and camera acquisition. |
| **[Control and Optimization](control-and-optimization/README.md)** | Python/Streamlit central controller, MQTT backend, calibration, daylight estimation, LP and weighted optimization, and dashboard figures. |
| **[Modeling and Simulation](modeling-and-simulation/README.md)** | DIALux and Honeybee/Radiance models, daylight and electric-light analysis, zoning, and reduced-sensor prediction studies. |
| **[Signal Processing](signal-processing/README.md)** | MATLAB FFT scripts and measured optical-signal waveforms for flicker and frequency analysis. |
| **[Results and Media](results-and-media/README.md)** | The occupancy-adaptive lighting demonstration video and laboratory media. |

## Related Publications

- **Design of a Flicker-Free Smart Lighting Panel with a Custom Low-Cost Flicker Measurement Module** — IEEE SGC 2025. [DOI: 10.1109/SGC69320.2025.11372343](https://doi.org/10.1109/sgc69320.2025.11372343)
- **On-the-Fly Frequency-Oriented Calibration for Real-Time, Power-Efficient, and Dynamic Control of Smart Lighting Systems** — IEEE ICEE 2026. [DOI: 10.1109/ICEE70628.2026.11710520](https://doi.org/10.1109/icee70628.2026.11710520)

---

## Copyright and Citation

Copyright © 2026 Mostafa Amiri. All rights reserved.

This repository is publicly accessible for research visibility
and professional portfolio purposes. No open-source license
is currently granted.

For reuse permissions, see [Copyright and Permissions](COPYRIGHT.md).

For academic attribution, see [CITATION.cff](CITATION.cff)
and the related scientific publications.

---

**Research, engineering, implementation, and experimental evaluation:** [Mostafa Amiri](https://github.com/Mostafaa-Amiri) · CST Lab, University of Tehran.
