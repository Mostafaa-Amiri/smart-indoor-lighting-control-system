#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ====== OTA includes ======
#include <ArduinoOTA.h>
#include <ESP8266mDNS.h>
#include <WiFiUdp.h>

// ====== I2C + BH1750 ======
#include <Wire.h>
#include <BH1750.h>

// ----------- WIFI / MQTT -----------
#include "config.h"  // Create locally from config.example.h; do not commit config.h
const uint16_t MQTT_PORT = 1883;

// ----------- globals -----------
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
BH1750 lightMeter;

String devId;           // e.g., "esp-3FA12B"
String topicAnnounce;   // gy30/<id>/announce
String topicStatus;     // gy30/<id>/status
String topicLuxAvg;     // gy30/<id>/lux_avg
String topicGetLux;     // gy30/<id>/get_lux  <-- NEW

// LWT buffer must remain valid across reconnects
char lwtBuf[96];
size_t lwtLen = 0;

const unsigned long HEARTBEAT_INTERVAL_MS = 30000;
unsigned long lastHeartbeatMs = 0;

// OTA state
bool otaReady = false;
volatile bool otaInProgress = false;

// ===================== WiFi =====================
void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);        // avoid flash wear
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(200);
    yield();
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleepMode(WIFI_NONE_SLEEP);  // low latency / stable
  }
}

// ===================== OTA setup =====================
void setupOTA() {
  ArduinoOTA.setHostname(devId.c_str());

  ArduinoOTA.onStart([]() {
    otaInProgress = true;
    // reduce traffic during flashing
    if (mqtt.connected()) mqtt.disconnect();
  });

  ArduinoOTA.onEnd([]() {
    otaInProgress = false;
  });

  ArduinoOTA.onError([](ota_error_t error) {
    otaInProgress = false;
  });

  ArduinoOTA.begin();
  otaReady = true;
}

// ===================== MQTT =====================
void initMqttClient() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(5);
}

// Send retained announce with id/ip/chip/ota
void announceOnline() {
  StaticJsonDocument<128> ann;
  ann["id"]   = devId;
  ann["ip"]   = WiFi.localIP().toString();
  ann["chip"] = (uint32_t)ESP.getChipId();
  ann["ota"]  = devId;
  ann["sensor"] = "BH1750/GY-30";

  char msg[160];
  size_t n = serializeJson(ann, msg, sizeof(msg));

  mqtt.publish(topicAnnounce.c_str(), (const uint8_t*)msg, n, true); // retained
  mqtt.publish(topicStatus.c_str(), "online", true);                  // retained
}

void publishHeartbeat() {
  if (!mqtt.connected()) return;
  if (otaInProgress) return;

  mqtt.publish(topicStatus.c_str(), "online", true);
}

void updateHeartbeat() {
  if (!mqtt.connected()) return;
  if (otaInProgress) return;

  unsigned long now = millis();

  if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = now;
    publishHeartbeat();
  }
}

// ===================== Lux acquisition (ON DEMAND) =====================
float readAverageLux10() {
  float sum = 0.0f;
  int valid = 0;

  for (int i = 0; i < 10; i++) {
    float lux = lightMeter.readLightLevel();

    if (lux >= 0) {   // BH1750 may return negative on error
      sum += lux;
      valid++;
    }
    delay(50);  // quick spacing between reads
    yield();
  }

  if (valid == 0) return -1.0f;
  return sum / valid;
}

void publishLuxNow() {
  float avgLux = readAverageLux10();

  char payload[32];
  dtostrf(avgLux, 0, 2, payload);

  mqtt.publish(topicLuxAvg.c_str(), payload, false);

  Serial.print("Published on-demand avg lux: ");
  Serial.println(payload);
}

// MQTT callback for on-demand lux requests
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  // We only care about gy30/<id>/get_lux
  if (String(topic) == topicGetLux) {
    if (!otaInProgress && mqtt.connected()) {
      publishLuxNow();
    }
  }
}

// Non-blocking reconnect attempt
bool connectMqttOnce() {
  if (mqtt.connected()) return true;
  if (WiFi.status() != WL_CONNECTED) return false;
  if (otaInProgress) return false;  // OTA first

  String clientId = "gy30-" + devId;

  bool ok = mqtt.connect(
      clientId.c_str(),
      nullptr, nullptr,
      topicStatus.c_str(), // LWT topic
      1, true,              // qos=1 retained
      lwtBuf, true          // LWT payload retained
  );

  if (ok) {
    announceOnline();

    // subscribe to on-demand request topic
    mqtt.subscribe(topicGetLux.c_str(), 1);

    Serial.print("Subscribed to ");
    Serial.println(topicGetLux);
  }
  return ok;
}

// ===================== Arduino =====================
void setup() {
  Serial.begin(115200);
  delay(50);

  // Device ID
  char idbuf[20];
  sprintf(idbuf, "esp-%06X", ESP.getChipId());
  devId = String(idbuf);

  // Topics
  topicAnnounce = "gy30/" + devId + "/announce";
  topicStatus   = "gy30/" + devId + "/status";
  topicLuxAvg   = "gy30/" + devId + "/lux_avg";
  topicGetLux   = "gy30/" + devId + "/get_lux";   // <-- NEW

  // Prepare LWT once (retained "offline")
  StaticJsonDocument<64> lwt;
  lwt["id"] = devId;
  lwt["status"] = "offline";
  lwtLen = serializeJson(lwt, lwtBuf, sizeof(lwtBuf));

  // I2C init (NodeMCU: SDA=D2 GPIO4, SCL=D1 GPIO5)
  Wire.begin(D2, D1);

  // BH1750 init
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println("BH1750 init failed!");
  } else {
    Serial.println("BH1750 ready.");
  }

  initMqttClient();
  mqtt.setCallback(onMqttMessage);   // <-- NEW callback

  // WiFi + OTA + MQTT
  connectWifi();
  if (WiFi.status() == WL_CONNECTED && !otaReady) {
    setupOTA();
  }

  connectMqttOnce();  // first try
}

void loop() {
  // ---- WiFi keep alive ----
  if (WiFi.status() != WL_CONNECTED) {
    otaReady = false;
    connectWifi();
  }
  if (WiFi.status() == WL_CONNECTED && !otaReady) {
    setupOTA();
  }

  // ---- MQTT non-blocking reconnect ----
  static unsigned long lastMqttTry = 0;
  if (!mqtt.connected() && millis() - lastMqttTry > 1000) {
    lastMqttTry = millis();
    connectMqttOnce();
  }

  if (!otaInProgress) {
    mqtt.loop();
  }

  updateHeartbeat();

  // ---- OTA handler (highest priority) ----
  ArduinoOTA.handle();

  yield(); // keep WiFi/MQTT background healthy
}
