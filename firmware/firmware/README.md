# Embedded Firmware — Smart Indoor Lighting Control System

**University of Tehran · Smart Lighting Research Platform**

This directory contains five Arduino sketches for the lighting controller, illuminance measurement, mmWave occupancy sensing, and a camera-image acquisition node. The modules were developed as parts of an integrated, MQTT-connected indoor lighting research platform.

> **Project status:** These are research/development snapshots of the supplied source code. They have not been compiled or hardware-tested as part of this documentation release. Review pin assignments, electrical safety, network security, and library compatibility before deployment.

## Firmware at a glance

| Module | Platform | Main functions | Source |
| --- | --- | --- | --- |
| Smart LED panel controller | ESP8266 / NodeMCU | Four PWM outputs, smooth dimming, low-duty anti-flicker routines, DS18B20 temperature telemetry, MQTT and OTA | [Open sketch](led-panel-controller/Panel_nodemcu_v6_OTA_temp_anti_flicker/Panel_nodemcu_v6_OTA_temp_anti_flicker.ino) |
| Wireless illuminance sensor | ESP8266 / NodeMCU + GY-30/BH1750 | I²C lux measurements, on-request 10-sample averaging, MQTT announcements and OTA | [Open sketch](bh1750-illuminance-sensor/gy30_nodemcu_OTA_v2/gy30_nodemcu_OTA_v2.ino) |
| LD2420 presence node | ESP8266 / NodeMCU + LD2420 | Digital presence input, debounce/hold logic, zone status reporting, MQTT and OTA | [Open sketch](ld2420-presence-sensor/nodemcu_ld2420_presence/nodemcu_ld2420_presence.ino) |
| LD2450 dual-radar occupancy node | ESP32-WROOM + two LD2450 sensors | Two UART radar streams, presence extraction, configurable occupancy filtering, MQTT and OTA | [Open sketch](ld2450-occupancy-sensor/esp32_ld2450_occupancy/esp32_ld2450_occupancy.ino) |
| ESP32-CAM snapshot node | AI Thinker ESP32-CAM | JPEG capture and HTTP image/status endpoints, adjustable image settings, OTA | [Open sketch](esp32-camera-node/ESP32_CAM_V1_OTA/ESP32_CAM_V1_OTA.ino) |

## 1. Smart LED panel controller

**Source:** [`Panel_nodemcu_v6_OTA_temp_anti_flicker.ino`](led-panel-controller/Panel_nodemcu_v6_OTA_temp_anti_flicker/Panel_nodemcu_v6_OTA_temp_anti_flicker.ino)

Firmware for a wireless, dimmable lighting panel. It drives **four software-PWM output channels** (NodeMCU pins `D5`, `D6`, `D7`, and `D1`) and receives assignments and dimming commands over MQTT. It includes configurable transitions, smooth duty-cycle ramps, and a *low-duty anti-flicker boost routine* to address unwanted flicker during certain dimming conditions. A **DS18B20** sensor on `D2` provides temperature measurements and associated control/status handling. The implementation supports over-the-air firmware updates.

**MQTT interfaces:** `lights/announce`, `lights/panel/<id>/assign`, `lights/panel/<id>/set`, `lights/panel/<id>/status`, `lights/panel/<id>/tele`, and `lights/panel/<id>/applied`.

**Engineering note:** The presence of an anti-flicker routine is not itself evidence that the finished system is flicker-free across all settings; waveform/optical measurements are needed to establish performance.

## 2. Wireless illuminance measurement — BH1750 / GY-30

**Source:** [`gy30_nodemcu_OTA_v2.ino`](bh1750-illuminance-sensor/gy30_nodemcu_OTA_v2/gy30_nodemcu_OTA_v2.ino)

An ESP8266 reads a **BH1750 illuminance sensor over I²C** and communicates with the central controller over MQTT. In this firmware version, the node reads and averages **10 samples when requested** rather than continuously streaming raw samples. It also publishes discovery/availability information and supports OTA updates.

**MQTT interfaces:** `gy30/<id>/announce`, `gy30/<id>/status`, `gy30/<id>/get_lux` (request), and `gy30/<id>/lux_avg` (response).

## 3. LD2420 digital-output presence sensor

**Source:** [`nodemcu_ld2420_presence.ino`](ld2420-presence-sensor/nodemcu_ld2420_presence/nodemcu_ld2420_presence.ino)

A NodeMCU reads the **digital occupancy output** of an LD2420 mmWave sensor on `D5` (`GPIO14`). The logic confirms a HIGH signal after approximately **50 ms** and delays vacancy detection using a configurable **30-second default off-hold**. Zone presence is reported over MQTT; the firmware also uses EEPROM for persistent configuration and supports OTA.

**MQTT interfaces:** `presence/<id>/state`, `presence/<id>/set`, and `presence/<id>/info`.

**Scope:** This sketch reads a digital presence signal; it does **not** implement LD2420 UART target tracking. Check the `ZONE_NUMBER` compile-time assertion if using zone 1 (the supplied expression repeats the zone-2 test).

## 4. LD2450 dual-radar occupancy sensor

**Source:** [`esp32_ld2450_occupancy.ino`](ld2450-occupancy-sensor/esp32_ld2450_occupancy/esp32_ld2450_occupancy.ino)

An ESP32 receives UART frames from **two LD2450 radar sensors**, using `GPIO16/17` and `GPIO26/27`. It parses the frame data and checks up to **three target slots per radar**, then converts the observations into two held occupancy states (`z1` and `z2`) using configurable time windows and thresholds. Configuration is stored using ESP32 Preferences, and status/diagnostics are sent over MQTT. OTA is supported.

**MQTT interfaces:** `presence/<id>/state`, `presence/<id>/set`, and `presence/<id>/info`.

**Scope:** Although LD2450 target frames contain position-related fields, **this firmware reports compact occupancy bits, not a continuous person-location stream**.

## 5. ESP32-CAM image acquisition node

**Source:** [`ESP32_CAM_V1_OTA.ino`](esp32-camera-node/ESP32_CAM_V1_OTA/ESP32_CAM_V1_OTA.ino)

A network-connected camera node based on the **AI Thinker ESP32-CAM**. It serves a JPEG snapshot and exposes status and camera-setting endpoints over HTTP, alongside OTA updates. This enables a separate computer-vision application to retrieve camera images for research experiments.

**HTTP endpoints:** `/capture` (JPEG image), `/status` (device/camera status), and `/set` (image parameters).

**Scope:** **YOLO inference is not performed in this sketch.** If person detection runs elsewhere (for example, on a Raspberry Pi or gateway), that code belongs in the software/computer-vision section.

## Preparing and uploading a sketch

These source files have been placed in **separate Arduino-compatible sketch folders** so each `.ino` has a parent directory with the matching name.

1. Choose a module and open its sketch folder.
2. Copy `config.example.h` to `config.h` **in the same folder** as its `.ino` file.
3. Edit the new `config.h` with your own Wi-Fi details and (when applicable) MQTT broker address. **Never commit `config.h`.**
4. Install the matching ESP8266 or ESP32 board support and the libraries listed below.
5. Select the correct target board, review UART/PWM/I²C wiring, and compile/upload using Arduino IDE or a compatible tool.
6. Confirm the device's MQTT/HTTP behavior on an isolated, trusted test network before integration.

### Libraries used

- **ESP8266 sketches:** ESP8266 Arduino core, ESP8266WiFi, ArduinoOTA; also PubSubClient and ArduinoJson for the MQTT nodes.
- **ESP32 sketches:** ESP32 Arduino core, WiFi, ArduinoOTA; the occupancy sketch additionally uses PubSubClient and ArduinoJson.
- **Illuminance node:** Wire and BH1750 library.
- **Panel controller:** OneWire and DallasTemperature.
- **Persistence:** EEPROM (LD2420) and Preferences (LD2450).
- **ESP32-CAM:** `esp_camera.h` / ESP32 camera support and WebServer.

Exact library/core versions have not been verified for this release; the supplied code may need version-specific adjustments before it compiles on a current toolchain.

## Network and deployment security

- The supplied original sketches contained hardcoded Wi-Fi credentials. **Those literal values have been removed from these public copies**, and the broker address moved to a local configuration header.
- `config.h` is ignored by the included `firmware/.gitignore`. Check GitHub Desktop's proposed files before committing, and ensure you have **not previously committed** the original sketches with passwords.
- If the original Wi-Fi password remains active, **rotate it**. Removing it from new files does not revoke a leaked password.
- MQTT uses port `1883` and the camera exposes HTTP endpoints. These sketches do not demonstrate end-to-end encrypted/authenticated communications. Use only on a trusted/isolated network unless security is added.
- Review and secure OTA update access before use on untrusted networks.
- Camera access raises privacy obligations. Obtain appropriate consent, avoid distributing identifiable images, and safeguard recordings.

## Hardware documentation

The matching circuit boards, sensors, test photographs, and schematics are presented in the repository's [Hardware documentation](../hardware/README.md).

## Versioning and attribution

The original sketch filenames have been retained for traceability. This documentation reflects the supplied snapshots; not every sketch has undergone an independent compile, hardware validation, or security audit. If reusing this research code, cite the corresponding papers and project repository where appropriate.
