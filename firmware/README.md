# Embedded Firmware — Smart Indoor Lighting Control System

**University of Tehran | Smart Lighting Research Platform**

This section contains the implemented and experimentally validated ESP8266/ESP32 firmware developed for the smart lighting platform. The modules provide dimming control, illuminance measurement, occupancy detection, and camera-based image acquisition, with wireless communication and integration into the central control system.

## Firmware modules

### 1. Smart LED Panel Controller — ESP8266

[View Arduino code](led-panel-controller/Panel_nodemcu_v6_OTA_temp_anti_flicker/Panel_nodemcu_v6_OTA_temp_anti_flicker.ino)

Controls **four PWM dimming channels** through MQTT, with smooth transitions and an anti-flicker control routine. A **DS18B20 temperature sensor** provides thermal measurements for monitoring and control. Supports OTA firmware updates.

### 2. Wi-Fi Illuminance Sensor — BH1750 / GY-30

[View Arduino code](bh1750-illuminance-sensor/gy30_nodemcu_OTA_v2/gy30_nodemcu_OTA_v2.ino)

Uses a **NodeMCU and BH1750 sensor** to acquire illuminance over I²C. Averages ten samples on request and reports the result to the central controller through MQTT. Supports OTA updates.

### 3. Wi-Fi Presence Sensor — LD2420

[View Arduino code](ld2420-presence-sensor/nodemcu_ld2420_presence/nodemcu_ld2420_presence.ino)

Processes the **LD2420 mmWave radar's digital presence output** using configurable detection and hold timing. Publishes occupancy status through MQTT and supports persistent settings and OTA updates.

### 4. Multi-Radar Occupancy Sensor — LD2450

[View Arduino code](ld2450-occupancy-sensor/esp32_ld2450_occupancy/esp32_ld2450_occupancy.ino)

An **ESP32 interfaces with two LD2450 mmWave radars over UART**, processes target detections (up to three targets per radar), and publishes zone occupancy states over MQTT. Includes configurable filtering, stored settings, and OTA updates.

### 5. ESP32-CAM — Image Acquisition

[View Arduino code](esp32-camera-node/ESP32_CAM_V1_OTA/ESP32_CAM_V1_OTA.ino)

Provides **Wi-Fi JPEG image capture** and HTTP endpoints for camera configuration and status, with OTA support. Images can be consumed by the separate Raspberry Pi / YOLO computer-vision software.

## Configuration

The original sketch settings and MQTT configuration are preserved. Wi-Fi network names and passwords are replaced with `***` for public sharing; enter your own credentials before uploading.

**Related:** [Hardware design, schematics and prototypes](../hardware/README.md).
