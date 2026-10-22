# Embedded Firmware

**Smart Indoor Lighting Control System**  
*CST Lab · University of Tehran*

## Overview

This section contains the implemented ESP8266 and ESP32 firmware for the **Smart Indoor Lighting Control System**. The firmware provides wireless panel dimming, illuminance acquisition, occupancy detection, and image capture, integrated with the central controller through MQTT or HTTP as applicable.

## Architecture and Communication

The embedded nodes acquire measurements or receive dimming commands over Wi-Fi. The LED-panel controller applies PWM output and reports its status; sensing nodes provide illuminance and occupancy information for daylight-aware and occupancy-responsive control.

## Firmware Modules

### LED Panel Controller — ESP8266

**[View Arduino sketch](led-panel-controller/Panel_nodemcu_v6_OTA_temp_anti_flicker/Panel_nodemcu_v6_OTA_temp_anti_flicker.ino)**

Implements four PWM dimming outputs with immediate and smooth transitions, anti-flicker control logic, MQTT communication, DS18B20 temperature monitoring, and over-the-air (OTA) firmware updates.

### Wi-Fi Illuminance Sensor — BH1750 / GY-30

**[View Arduino sketch](bh1750-illuminance-sensor/gy30_nodemcu_OTA_v2/gy30_nodemcu_OTA_v2.ino)**

Uses a NodeMCU (ESP8266) and I²C-connected BH1750 to measure illuminance. Ten samples are averaged on request and transmitted to the central controller through MQTT. OTA updates are supported.

### Wi-Fi Presence Sensor — LD2420

**[View Arduino sketch](ld2420-presence-sensor/nodemcu_ld2420_presence/nodemcu_ld2420_presence.ino)**

Reads LD2420 mmWave presence information, applies configurable detection and hold timing, and publishes occupancy states via MQTT. Includes persistent settings and OTA support.

### Multi-Radar Occupancy Sensor — LD2450

**[View Arduino sketch](ld2450-occupancy-sensor/esp32_ld2450_occupancy/esp32_ld2450_occupancy.ino)**

Uses an ESP32 to receive UART data from two LD2450 radars, process detected targets (up to three per radar), and publish zone-level occupancy states over MQTT. Includes filtering, saved settings, and OTA updates.

### ESP32-CAM — Image Acquisition

**[View Arduino sketch](esp32-camera-node/ESP32_CAM_V1_OTA/ESP32_CAM_V1_OTA.ino)**

Provides JPEG image capture and HTTP endpoints for the separate computer-vision occupancy pipeline, along with camera status/configuration and OTA functionality. YOLO inference is implemented in the central-controller software, not in this camera sketch.

## Implementation Notes

The Arduino sketches preserve their original device settings, MQTT topics, hardware assignments, and program logic. Wi-Fi SSIDs and passwords are represented by `***` in the publicly shared copies.

## Related Documentation

[Main Project Overview](../README.md) · [Hardware Development](../hardware/README.md) · [Control and Optimization](../control-and-optimization/README.md)
