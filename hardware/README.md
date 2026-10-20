# Hardware Development — Smart Indoor Lighting Control System

**University of Tehran | Custom lighting, sensing, control and measurement hardware**

This page documents the hardware developed and evaluated for the **Smart Indoor Lighting Control System** research platform. It includes three generations of smart LED lighting panels, two LED-driver approaches, networked illuminance and occupancy sensing, capacitive wall switches, and a custom flicker-measurement instrument.

The project combines **PCB and circuit design, embedded electronics, communication interfaces, thermal considerations, prototyping and experimental evaluation**. Some modules are completed prototypes; conceptual designs are labeled accordingly. Photographs, PCB renders and diagrams are provided below.

> **Documentation status:** Research and prototype documentation. Specifications and comparative results are reported from project notes; they are not product certifications or safety approvals. Detailed test conditions are being added.

## Contents

1. [Why custom hardware?](#why-custom-lighting-hardware)
2. [Smart LED lighting panels — V1, V2, V3a and V3b](#1-smart-led-lighting-panels)
3. [Smart LED drivers — V1 and V2](#2-smart-led-drivers)
4. [Wi-Fi illuminance sensor](#3-wi-fi-illuminance-sensor)
5. [Presence sensing — mmWave radar and camera](#4-presence-sensing)
6. [Smart capacitive touch switch](#5-smart-capacitive-touch-switch)
7. [Flicker measurement device — V1 and proposed V2](#6-flicker-measurement-device)
8. [Scope and technical notes](#scope-and-technical-notes)

## Why custom lighting hardware?

Although commercial smart luminaires were considered, a custom platform better suited the research requirements:

| Design consideration | Reason for a custom implementation |
|---|---|
| **Research access and control** | Direct access to dimming, electronics and communication signals, without dependence on undocumented vendor interfaces. |
| **Cost and maintainability** | Target lower prototyping costs and enable local replacement and repair of modules. |
| **Long-term availability** | Avoid dependence on a particular manufacturer's product lifecycle or cloud infrastructure. |
| **Supply constraints** | Use accessible parts and alternative sources where importing complete products is difficult. |
| **Design flexibility** | Adjust panel geometry, output power, light distribution, color characteristics and communication architecture for experiments. |
| **System integration** | Maintain control over local communication, sensing, testing and laboratory integration. |

**The goal was not simply to build another lamp:** it was to produce an adaptable experimental platform whose electrical, optical and control behavior could be investigated and modified.

---

## 1. Smart LED Lighting Panels

Three principal generations were developed. **V1** explored two LED placement geometries; **V2** prioritized electrical isolation and PWM integrity; **V3** adopted a modular architecture designed for easier fabrication, cooling, servicing and power scaling.

### V1 — Integrated PCB prototypes

The first generation integrated the **ESP32 Wi-Fi controller**, LED-driver circuitry and LED arrays on a single PCB. An I²C header was provided for connecting illuminance sensors.

Two layouts were explored:

- **Circular arrangement:** square PCB with LEDs positioned in concentric/circular patterns and angled placement.
- **Matrix arrangement:** rectangular PCB with LEDs laid out in a regular grid. The rectangular prototype was approximately **30 × 15 cm**.

This approach offered a compact, self-contained test platform without separate external control boards.

![V1 layout A: circular/angled LED arrangement — 3D PCB render](images/led-panel-v1/pcb-v1-3d-altium.png)

*V1 layout A: circular/angled LED arrangement — 3D PCB render*

![V1 layout B: rectangular LED matrix — 3D PCB render](images/led-panel-v1/pcb-v2-3d-altium.png)

*V1 layout B: rectangular LED matrix — 3D PCB render*

![First-generation PCB assembly](images/led-panel-v1/assembled-real-pcb.jpg)

*First-generation PCB assembly*

**What we learned.** In prototype testing, visible flicker was observed and associated with interference involving the on-board Wi-Fi/control circuitry and the driver stages. The single-board architecture made control and power circuitry harder to separate. FR-4 construction without a dedicated heatsink also limited thermal management; the large, densely populated PCB was expensive and time-consuming to assemble and difficult to scale.

<details>
<summary><strong>V1 system diagram and driver schematic</strong> (2 images)</summary>

![V1 integrated power, Wi-Fi control and driver arrangement](images/led-panel-v1/block-diagram.png)

*V1 integrated power, Wi-Fi control and driver arrangement*

![Representative PT4115 driver circuit supplied for V1](images/led-panel-v1/circuit-schematic.png)

*Representative PT4115 driver circuit supplied for V1*

</details>

### V2 — Isolated Wi-Fi control, standardized panel dimensions

The second generation moved to a **30 × 30 cm** panel and separated the Wi-Fi control electronics from the LED board. The control unit used an **ESP-12F (ESP8266)** instead of ESP32 to reduce cost.

The PWM signal was electrically isolated before reaching the LED board and then distributed through a buffer/line-driver stage. A temperature sensor was also placed on the rear of the board. The controller could **reduce dimming duty cycle (and therefore power) when elevated temperature was detected**.

![V2 30 × 30 cm panel — Altium 3D PCB render](images/led-panel-v2/pcb-3d-altium.png)

*V2 30 × 30 cm panel — Altium 3D PCB render*

![V2 isolated Wi-Fi/PWM control and LED-board architecture](images/led-panel-v2/block-diagram.png)

*V2 isolated Wi-Fi/PWM control and LED-board architecture*

![V2 system demonstrator: panel, controller, supply and phone](images/led-panel-v2/working-setup.jpg)

*V2 system demonstrator: panel, controller, supply and phone*

**Observed improvements:** the redesign eliminated the previously observed RF-related visible flicker under the tested conditions, improved PWM signal integrity, provided a standard panel form factor and introduced temperature-based power reduction.

**Remaining limitations:** the large PCB, high component count and prolonged assembly made production and repair difficult. Thermal control relied on derating rather than a physical heatsink. The distributed **PT4115** driver stages were not used near their available output capability; project notes indicate approximately **1.2 W per stage**, increasing overall component count.

<details>
<summary><strong>More V2 prototype photos, PCB and schematic</strong> (5 images)</summary>

![Three completed panel assemblies](images/led-panel-v2/3panels-built.jpg)

*Three completed panel assemblies*

![Populated second-generation board](images/led-panel-v2/assembled-real-pcb.jpg)

*Populated second-generation board*

![LED array powered during tests](images/led-panel-v2/assembled-real-pcb-2.jpg)

*LED array powered during tests*

![Complete V2 luminaire with enclosure](images/led-panel-v2/single-complete-lighting-panel.jpg)

*Complete V2 luminaire with enclosure*

![Representative PT4115 driver circuit supplied for V2](images/led-panel-v2/circuit-schematic.png)

*Representative PT4115 driver circuit supplied for V2*

</details>

### V3a and V3b — Modular, scalable lighting panels

The third generation changed the construction approach: instead of mounting many individual LED chips on a custom large-area PCB, it used **commercially available 24 V LED strips (180 LEDs/m)** on a metal heat-dissipation structure, driven by **small replaceable PT4115 constant-current driver modules**.

- **V3a:** **30 × 30 cm**.
- **V3b:** **60 × 30 cm**. The core architecture is shared; the panel size and arrangement differ.

The selected LED strip was described as having **seven series LEDs plus a series resistor per branch**. For the experimental constant-current-driven implementation, the project changed the branch resistor from approximately **180 Ω to 10 Ω** to reduce resistive losses while retaining some series resistance. This is a **prototype modification**, not a general recommendation for operating commercial constant-voltage strips without verifying current-sharing, fault behavior and thermal limits.

The separate PT4115 module was laid out with attention to short switching loops, capacitor placement, inductor/current-sense separation, PWM return routing and provision for heat dissipation.

![V3a: complete modular lighting test setup](images/led-panel-v3a/assembled-lighting-panel.jpg)

*V3a: complete modular lighting test setup*

![V3a: LED strips and distribution among PT4115 driver modules](images/led-panel-v3a/leds-setup.jpg)

*V3a: LED strips and distribution among PT4115 driver modules*

![V3: small, assembled PT4115 driver module](images/led-panel-v3a/assembled-real-pcb.jpg)

*V3: small, assembled PT4115 driver module*

![V3b: 60 × 30 cm strip-based luminaire](images/led-panel-v3b/lighting-panel-2.jpg)

*V3b: 60 × 30 cm strip-based luminaire*

**Advantages in the project:** lower custom-PCB area and assembly effort, simpler replacement of driver modules, heat sinking, and more flexible changes to panel size, power and LED arrangement. A separate-controller architecture also avoided the earlier co-location of Wi-Fi electronics and LED power stages.

<details>
<summary><strong>V3 driver circuit and mechanical views</strong> (2 images)</summary>

![Representative V3 constant-current driver/strip branches](images/led-panel-v3a/circuit-schematic.png)

*Representative V3 constant-current driver/strip branches*

![V3 discrete modular-driver PCB render](images/led-panel-v3a/pcb-3d-altium.png)

*V3 discrete modular-driver PCB render*

</details>

<details>
<summary><strong>V3b rear assembly</strong> (1 images)</summary>

![V3b: rear of panel showing driver distribution and wiring](images/led-panel-v3b/lighting-panel.jpg)

*V3b: rear of panel showing driver distribution and wiring*

</details>

### Panel evolution — comparison

The following values come from the project's version-comparison notes. **Illuminance measurements are not directly comparable without documented measurement geometry and conditions**, so they are included here as reported project results rather than standardized performance ratings.

| Parameter | V1 | V2 | V3 family |
|---|---:|---:|---:|
| Reported panel power | 18 W | 36 W | 100 W |
| Reported illuminance | 120 lx | 300 lx | 650 lx |
| Thermal approach | No dedicated control | Temperature monitoring and power derating | Temperature monitoring, derating and physical heatsink |
| Visible RF-related flicker in project tests | Observed | Not observed after redesign | Not observed in reported tests |
| Reported assembly time | 2 days | 3.5 days | 1 day |
| Repairability | Difficult | Difficult | Modular replacement |
| Production suitability (qualitative) | Low | Low | Improved |

**Cost estimates** from the original notes were about **4.0 M, 5.5 M and 3.5 M** respectively (local currency and date to be documented). Because cost and illuminance measurement methods are not yet recorded here, they should not be treated as externally validated product comparisons.

---

## 2. Smart LED Drivers

Beyond building complete lighting panels, another objective was a **retrofit path for making suitable commercially available LED panels controllable via custom Wi-Fi PWM electronics**.

### Driver V1 — Low-cost PWM switching experiment

The first driver was an inexpensive proof of concept. It used an ESP-generated PWM command and a MOSFET switching stage. **Series resistance** was used to limit LED current, including current changes associated with temperature. It was **not a regulated constant-current driver**, and therefore was not the preferred final architecture.

![First low-cost PWM/MOSFET LED switching prototype](images/smart-driver-v1/assembled.jpg)

*First low-cost PWM/MOSFET LED switching prototype*

### Driver V2 — Integrated Wi-Fi constant-current dimming design

The later design combines a high-power **constant-current LED-driver IC**, **ESP-12F (ESP8266) Wi-Fi controller**, and an on-board **3.3 V regulator**. The goal is to provide dimmable current-regulated control for compatible external LED loads.

**Reported design targets/features:**

- **Input supply range:** approximately **5–60 V**, subject to device, regulator and component operating limits.
- **LED output current:** configurable **up to 2 A**, subject to electrical and thermal derating.
- **Control:** Wi-Fi-based dimming using the embedded controller.
- **Current-setting:** sense/configuration resistors set the target **LED current**. In a constant-current design, the LED-string voltage is determined by the load and available converter operating range; it is **not independently programmable by a resistor**.
- **Protection objectives:** undervoltage lockout, overcurrent and thermal protection, open/short-load handling, and controlled startup, as applicable to the selected circuitry and driver IC. These features must be verified against the final schematic and test results; they are not claimed here as independently certified.

![Second-generation Wi-Fi LED driver: integrated ESP-12F PCB render](images/smart-driver-v2/pcb-3d-altium.png)

*Second-generation Wi-Fi LED driver: integrated ESP-12F PCB render*

![Wireless PWM dimming and LED-panel connection concept](images/smart-driver-v2/block-diagram.png)

*Wireless PWM dimming and LED-panel connection concept*

---

## 3. Wi-Fi Illuminance Sensor

A simple networked illuminance node uses a **BH1750/GY-30 digital lux sensor** with a **NodeMCU (ESP8266)**. The microcontroller acquires multiple illuminance samples, averages or filters the readings, and transmits them to the central gateway/controller for daylight estimation and feedback control.

![BH1750/GY-30 and NodeMCU Wi-Fi illuminance node](images/illuminance-sensor/bh1750-esp.jpg)

*BH1750/GY-30 and NodeMCU Wi-Fi illuminance node*

---

## 4. Presence Sensing

Occupancy feedback was investigated using **mmWave radar** and **camera-based detection**. Both approaches support adaptive lighting decisions, but they have different measurement capabilities and privacy implications.

### Wi-Fi mmWave radar sensors

**HLK-LD2420** and **HLK-LD2450** radar modules were evaluated with NodeMCU-based communication. Their outputs can be transmitted to the central gateway/controller.

- **LD2420:** presence and small-motion detection; the module was used for **single-target presence detection**, not multi-person tracking.
- **LD2450:** supports tracking information for **up to three targets**, including estimated positions under suitable conditions.
- **Benefit:** mmWave sensing can respond to small movements from otherwise stationary occupants, addressing some limitations of simple motion-triggered sensing.

![LD2420 radar sensor with ESP/NodeMCU module](images/radar-presence-sensor/ld2420-esp.jpg)

*LD2420 radar sensor with ESP/NodeMCU module*

![Hi-Link visualization of detected target positions](images/radar-presence-sensor/hilink-ui-app.png)

*Hi-Link visualization of detected target positions*

### Raspberry Pi camera + YOLO

An alternative prototype used a **Raspberry Pi 3 with camera** and **YOLO-based people detection**. Camera-based detection can support vision-based occupancy analysis, but it creates **privacy and data-handling requirements** that do not arise in the same way with non-imaging radar. For a deployment, on-device inference, image-retention policies and user consent must be considered.

![Raspberry Pi 3 and camera hardware for YOLO presence detection](images/camera-presence-sensor/rbpi3-camera.jpg)

*Raspberry Pi 3 and camera hardware for YOLO presence detection*

---

## 5. Smart Capacitive Touch Switch

A custom **up-to-three-gang capacitive touch switch** was designed for local and Wi-Fi-enabled lighting control. The assembly integrates a touch/ESP control board with an appropriate mains-interface/power-board configuration. Designs were explored for installations **with and without a neutral conductor** (the photos and PCB renders document both variants).

The objective was to combine physical wall-switch operation with remote/app-based control for the smart-lighting system.

![3-gang capacitive touch and ESP PCB render](images/smart-touch-switch/pcb-touch-esp-3d-altium-1.png)

*3-gang capacitive touch and ESP PCB render*

![Assembled Wi-Fi capacitive touch board](images/smart-touch-switch/assembled-1.jpg)

*Assembled Wi-Fi capacitive touch board*

![Mains power board — neutral required](images/smart-touch-switch/pcb-powerboard-nullrequired-3d-altium.png)

*Mains power board — neutral required*

![Mains power board — no neutral required](images/smart-touch-switch/pcb-powerboard-nonullrequired-3d-altium-1.png)

*Mains power board — no neutral required*

<details>
<summary><strong>Additional switch photographs and PCB renders</strong> (5 images)</summary>

![Touch board mounted in switch enclosure](images/smart-touch-switch/assembled-2.jpg)

*Touch board mounted in switch enclosure*

![Assembled no-neutral power board](images/smart-touch-switch/assembled-powerboard-no-null-required.jpg)

*Assembled no-neutral power board*

![Assembled neutral-required power board](images/smart-touch-switch/assembled-powerboard-null-required.jpg)

*Assembled neutral-required power board*

![Reverse/detail view of no-neutral power-board render](images/smart-touch-switch/pcb-powerboard-nonullrequired-3d-altium-2.png)

*Reverse/detail view of no-neutral power-board render*

![Additional capacitive touch PCB render](images/smart-touch-switch/pcb-touch-esp-3d-altium-2.png)

*Additional capacitive touch PCB render*

</details>

> **Electrical safety:** the power-board concepts involve mains-connected circuitry. The images document research prototypes and do not constitute installation instructions or evidence of regulatory compliance. Isolation, creepage/clearance, touch safety, thermal performance and enclosure requirements require proper verification before practical deployment.

---

## 6. Flicker Measurement Device

Lighting flicker was characterized using a custom optical acquisition system and signal processing. Measurements can be transferred to a computer for **MATLAB-based time- and frequency-domain analysis**, including FFT-based characterization. An ESP32-based onboard processing approach was also considered.

### V1 — Phototransistor-based instrument (built)

The constructed prototype uses a **phototransistor illuminance sensor**, signal conversion/interface circuitry, a microcontroller and a computer connection. A reduced phototransistor load resistance can improve response speed, but decreases signal amplitude, creating a noise-versus-bandwidth trade-off. Higher-speed operation may therefore require low-noise amplification and careful analog front-end design.

![Built V1 phototransistor-based flicker measurement prototype](images/flicker-meter/assembled-v1.jpg)

*Built V1 phototransistor-based flicker measurement prototype*

![Flicker measurement setup with PC, light source, oscilloscope and supply](images/flicker-meter/test-setup.png)

*Flicker measurement setup with PC, light source, oscilloscope and supply*

![V1 acquisition chain: phototransistor, MCU and USB transfer](images/flicker-meter/block-diagram-v1.png)

*V1 acquisition chain: phototransistor, MCU and USB transfer*

### V2 — Photodiode-based architecture (proposed, not built)

A second conceptual architecture replaces the phototransistor with a **photodiode**, offering a potentially faster optical response. Its schematic/block diagram illustrates a possible amplification/ADC and wireless-processing chain.

**Status:** block-diagram design only. No physical V2 device, measured bandwidth or validated performance is claimed.

![Proposed V2 photodiode signal acquisition and wireless node](images/flicker-meter/block-diagram-v2.png)

*Proposed V2 photodiode signal acquisition and wireless node*

---

## Scope and technical notes

- **Images:** original project photographs, PCB renders and diagrams, converted into web-friendly formats for display in GitHub. Image metadata is stripped from the copies in this documentation package.
- **Hardware status:** development prototypes and experiments, not commercial product documentation or completed compliance testing.
- **Results:** values reported in the project comparison need test geometry, instruments, operating conditions and uncertainty information for scientific comparison.
- **Research links:** [Flicker-free smart lighting panel (SGC 2025)](https://doi.org/10.1109/sgc69320.2025.11372343) · [Frequency-oriented calibration (ICEE 2026)](https://doi.org/10.1109/icee70628.2026.11710520).

[← Return to main project overview](../README.md)
