/*
  ESP32-WROOM + two Hi-Link LD2450 presence sensors.

  Purpose:
    - Read two LD2450 UART streams continuously.
    - Convert each sensor to one held occupancy bit.
    - Publish only the compact central-controller state by default.

  Wiring:
    LD2450 #1 TX -> ESP32 GPIO16 (RX2)
    LD2450 #1 RX -> ESP32 GPIO17 (TX2, optional for future commands)

    LD2450 #2 TX -> ESP32 GPIO26 (RX1)
    LD2450 #2 RX -> ESP32 GPIO27 (TX1, optional for future commands)

    Both LD2450 modules:
      5V  -> 5V supply
      GND -> ESP32 GND / supply GND

  Arduino libraries:
    - PubSubClient by Nick O'Leary
    - ArduinoJson by Benoit Blanchon

  MQTT:
    presence/<id>/state -> {"ip":"192.168.1.91","z1":1,"z2":0}
    presence/<id>/set   -> {"on_windows":4,"off_ms":30000,"window_ms":500,"threshold":5}
    presence/<id>/info  -> diagnostics/config, every 5 minutes and when requested
*/

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <Preferences.h>

// ----------- WiFi / MQTT -----------
const char* WIFI_SSID = "***";
const char* WIFI_PASS = "***";
const char* MQTT_HOST = "192.168.1.77";
const uint16_t MQTT_PORT = 1883;

// Change this per physical partition if you flash multiple ESP32 nodes.
const char* NODE_ID = "partition_1";

// ----------- UART pins -----------
constexpr int S1_RX_PIN = 16;
constexpr int S1_TX_PIN = 17;
constexpr int S2_RX_PIN = 26;
constexpr int S2_TX_PIN = 27;

// ----------- LD2450 frame format -----------
constexpr size_t LD2450_FRAME_SIZE = 30;
constexpr uint8_t LD2450_HEADER[4] = {0xAA, 0xFF, 0x03, 0x00};
constexpr uint8_t LD2450_TAIL[2] = {0x55, 0xCC};

// Presence validity guardrails. These are not "location tracking"; they only
// reject impossible/irrelevant ghost points before counting presence.
constexpr int16_t MIN_VALID_Y_MM = 150;
constexpr int16_t MAX_VALID_Y_MM = 6000;
constexpr int16_t MAX_VALID_ABS_X_MM = 4500;

// ----------- Defaults -----------
constexpr uint32_t DEFAULT_BAUD = 256000;
constexpr uint32_t DEFAULT_WINDOW_MS = 500;
constexpr uint16_t DEFAULT_ON_WINDOWS = 4;
constexpr uint32_t DEFAULT_OFF_MS = 30000;
constexpr uint16_t DEFAULT_THRESHOLD = 5;
constexpr uint32_t DEFAULT_PUBLISH_MS = 5000;
constexpr uint32_t DEFAULT_INFO_MS = 300000;

// ----------- Globals -----------
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Preferences prefs;

HardwareSerial radarSerial1(2);
HardwareSerial radarSerial2(1);

String devId;
String topicState;
String topicSet;
String topicInfo;

bool otaReady = false;
volatile bool otaInProgress = false;

struct Config {
  uint32_t baud = DEFAULT_BAUD;
  uint32_t windowMs = DEFAULT_WINDOW_MS;
  uint16_t onWindows = DEFAULT_ON_WINDOWS;
  uint32_t offMs = DEFAULT_OFF_MS;
  uint16_t threshold = DEFAULT_THRESHOLD;
  uint32_t publishMs = DEFAULT_PUBLISH_MS;
  uint32_t infoMs = DEFAULT_INFO_MS;
};

struct RadarPresence {
  HardwareSerial* serial = nullptr;
  uint8_t frame[LD2450_FRAME_SIZE] = {0};
  size_t frameIndex = 0;

  uint16_t validFramesWindow = 0;
  uint16_t presenceFramesWindow = 0;
  uint16_t lastValidFrames = 0;
  uint16_t lastPresenceFrames = 0;

  uint16_t consecutivePresentWindows = 0;
  bool rawPresent = false;
  bool occupied = false;
  bool lastPublishedOccupied = false;
  uint32_t lastSeenMs = 0;
  uint32_t lastFrameMs = 0;
  uint32_t badFrames = 0;
};

Config cfg;
RadarPresence s1;
RadarPresence s2;

uint32_t lastWindowMs = 0;
uint32_t lastStatePublishMs = 0;
uint32_t lastInfoPublishMs = 0;
uint32_t lastMqttTryMs = 0;

// ===================== LD2450 parsing =====================
int16_t decodeLd2450Signed(uint8_t lo, uint8_t hi) {
  uint16_t raw = ((uint16_t)hi << 8) | lo;
  int16_t value = raw & 0x7FFF;
  return (raw & 0x8000) ? value : -value;
}

uint16_t decodeU16(uint8_t lo, uint8_t hi) {
  return ((uint16_t)hi << 8) | lo;
}

bool targetLooksValid(const uint8_t* data) {
  int16_t xMm = decodeLd2450Signed(data[0], data[1]);
  int16_t yMm = decodeLd2450Signed(data[2], data[3]);
  int16_t speed = decodeLd2450Signed(data[4], data[5]);
  uint16_t resolution = decodeU16(data[6], data[7]);

  if (xMm == 0 && yMm == 0 && speed == 0 && resolution == 0) {
    return false;
  }

  if (yMm < MIN_VALID_Y_MM || yMm > MAX_VALID_Y_MM) {
    return false;
  }

  return abs(xMm) <= MAX_VALID_ABS_X_MM;
}

bool frameHasPresence(const uint8_t* frame) {
  for (size_t targetIndex = 0; targetIndex < 3; targetIndex++) {
    const size_t offset = 4 + targetIndex * 8;
    if (targetLooksValid(&frame[offset])) {
      return true;
    }
  }

  return false;
}

void resetParserToHeaderCandidate(RadarPresence& radar, uint8_t latestByte) {
  radar.frameIndex = 0;
  if (latestByte == LD2450_HEADER[0]) {
    radar.frame[radar.frameIndex++] = latestByte;
  }
}

void handleRadarByte(RadarPresence& radar, uint8_t value) {
  if (radar.frameIndex == 0 && value != LD2450_HEADER[0]) {
    return;
  }

  radar.frame[radar.frameIndex++] = value;

  if (radar.frameIndex <= 4 &&
      radar.frame[radar.frameIndex - 1] != LD2450_HEADER[radar.frameIndex - 1]) {
    resetParserToHeaderCandidate(radar, value);
    return;
  }

  if (radar.frameIndex < LD2450_FRAME_SIZE) {
    return;
  }

  bool goodTail =
      radar.frame[28] == LD2450_TAIL[0] &&
      radar.frame[29] == LD2450_TAIL[1];

  if (goodTail) {
    radar.lastFrameMs = millis();
    radar.validFramesWindow++;

    if (frameHasPresence(radar.frame)) {
      radar.presenceFramesWindow++;
      radar.lastSeenMs = millis();
    }
  } else {
    radar.badFrames++;
  }

  radar.frameIndex = 0;
}

void drainRadarSerial(RadarPresence& radar) {
  while (radar.serial->available() > 0) {
    handleRadarByte(radar, (uint8_t)radar.serial->read());
  }
}

void processPresenceWindow(RadarPresence& radar, uint32_t now) {
  radar.lastValidFrames = radar.validFramesWindow;
  radar.lastPresenceFrames = radar.presenceFramesWindow;
  radar.rawPresent = radar.presenceFramesWindow >= cfg.threshold;

  if (radar.rawPresent) {
    if (radar.consecutivePresentWindows < 65535) {
      radar.consecutivePresentWindows++;
    }
  } else {
    radar.consecutivePresentWindows = 0;
  }

  if (radar.consecutivePresentWindows >= cfg.onWindows) {
    radar.occupied = true;
  }

  if (radar.occupied && !radar.rawPresent && now - radar.lastSeenMs >= cfg.offMs) {
    radar.occupied = false;
  }

  radar.validFramesWindow = 0;
  radar.presenceFramesWindow = 0;
}

// ===================== Settings =====================
uint32_t boundedU32(uint32_t value, uint32_t minValue, uint32_t maxValue) {
  if (value < minValue) return minValue;
  if (value > maxValue) return maxValue;
  return value;
}

uint16_t boundedU16(uint32_t value, uint16_t minValue, uint16_t maxValue) {
  if (value < minValue) return minValue;
  if (value > maxValue) return maxValue;
  return (uint16_t)value;
}

void loadConfig() {
  prefs.begin("presence", true);
  cfg.baud = prefs.getUInt("baud", DEFAULT_BAUD);
  cfg.windowMs = prefs.getUInt("window_ms", DEFAULT_WINDOW_MS);
  cfg.onWindows = prefs.getUShort("on_windows", DEFAULT_ON_WINDOWS);
  cfg.offMs = prefs.getUInt("off_ms", DEFAULT_OFF_MS);
  cfg.threshold = prefs.getUShort("threshold", DEFAULT_THRESHOLD);
  cfg.publishMs = prefs.getUInt("publish_ms", DEFAULT_PUBLISH_MS);
  cfg.infoMs = prefs.getUInt("info_ms", DEFAULT_INFO_MS);
  prefs.end();

  cfg.baud = boundedU32(cfg.baud, 9600, 921600);
  cfg.windowMs = boundedU32(cfg.windowMs, 100, 5000);
  cfg.onWindows = boundedU16(cfg.onWindows, 1, 100);
  cfg.offMs = boundedU32(cfg.offMs, 1000, 3600000);
  cfg.threshold = boundedU16(cfg.threshold, 1, 500);
  cfg.publishMs = boundedU32(cfg.publishMs, 500, 600000);
  cfg.infoMs = boundedU32(cfg.infoMs, 5000, 3600000);
}

void saveConfig() {
  prefs.begin("presence", false);
  prefs.putUInt("baud", cfg.baud);
  prefs.putUInt("window_ms", cfg.windowMs);
  prefs.putUShort("on_windows", cfg.onWindows);
  prefs.putUInt("off_ms", cfg.offMs);
  prefs.putUShort("threshold", cfg.threshold);
  prefs.putUInt("publish_ms", cfg.publishMs);
  prefs.putUInt("info_ms", cfg.infoMs);
  prefs.end();
}

void beginRadars() {
  radarSerial1.end();
  radarSerial2.end();
  delay(20);
  radarSerial1.begin(cfg.baud, SERIAL_8N1, S1_RX_PIN, S1_TX_PIN);
  radarSerial2.begin(cfg.baud, SERIAL_8N1, S2_RX_PIN, S2_TX_PIN);
}

// ===================== WiFi / OTA =====================
void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    drainRadarSerial(s1);
    drainRadarSerial(s2);
    delay(10);
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
  }
}

void setupOTA() {
  ArduinoOTA.setHostname(devId.c_str());

  ArduinoOTA.onStart([]() {
    otaInProgress = true;
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

// ===================== MQTT publishing =====================
void publishState(bool force = false) {
  if (!mqtt.connected() || otaInProgress) return;

  bool changed =
      s1.occupied != s1.lastPublishedOccupied ||
      s2.occupied != s2.lastPublishedOccupied;

  uint32_t now = millis();
  if (!force && !changed && now - lastStatePublishMs < cfg.publishMs) {
    return;
  }

  StaticJsonDocument<96> doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["z1"] = s1.occupied ? 1 : 0;
  doc["z2"] = s2.occupied ? 1 : 0;

  char msg[128];
  size_t n = serializeJson(doc, msg, sizeof(msg));
  mqtt.publish(topicState.c_str(), (const uint8_t*)msg, n, true);

  s1.lastPublishedOccupied = s1.occupied;
  s2.lastPublishedOccupied = s2.occupied;
  lastStatePublishMs = now;
}

void addSensorInfo(JsonObject obj, const RadarPresence& radar) {
  obj["raw"] = radar.rawPresent ? 1 : 0;
  obj["occ"] = radar.occupied ? 1 : 0;
  obj["pf"] = radar.lastPresenceFrames;
  obj["vf"] = radar.lastValidFrames;
  obj["last"] = radar.lastSeenMs == 0 ? -1 : (int32_t)(millis() - radar.lastSeenMs);
  obj["age"] = radar.lastFrameMs == 0 ? -1 : (int32_t)(millis() - radar.lastFrameMs);
  obj["bad"] = radar.badFrames;
}

void publishInfo() {
  if (!mqtt.connected() || otaInProgress) return;

  StaticJsonDocument<512> doc;
  doc["id"] = devId;
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["up"] = millis();

  JsonObject cfgObj = doc.createNestedObject("cfg");
  cfgObj["baud"] = cfg.baud;
  cfgObj["window_ms"] = cfg.windowMs;
  cfgObj["on_windows"] = cfg.onWindows;
  cfgObj["off_ms"] = cfg.offMs;
  cfgObj["threshold"] = cfg.threshold;
  cfgObj["publish_ms"] = cfg.publishMs;
  cfgObj["info_ms"] = cfg.infoMs;

  addSensorInfo(doc.createNestedObject("s1"), s1);
  addSensorInfo(doc.createNestedObject("s2"), s2);

  char msg[640];
  size_t n = serializeJson(doc, msg, sizeof(msg));
  mqtt.publish(topicInfo.c_str(), (const uint8_t*)msg, n, false);
  lastInfoPublishMs = millis();
}

void updatePeriodicInfo() {
  if (cfg.infoMs == 0) return;
  if (millis() - lastInfoPublishMs >= cfg.infoMs) {
    publishInfo();
  }
}

void applySetPayload(byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;

  bool changedConfig = false;
  bool changedBaud = false;

  if (doc.containsKey("baud")) {
    uint32_t nextBaud = boundedU32(doc["baud"].as<uint32_t>(), 9600, 921600);
    if (nextBaud != cfg.baud) {
      cfg.baud = nextBaud;
      changedConfig = true;
      changedBaud = true;
    }
  }
  if (doc.containsKey("window_ms")) {
    cfg.windowMs = boundedU32(doc["window_ms"].as<uint32_t>(), 100, 5000);
    changedConfig = true;
  }
  if (doc.containsKey("on_windows")) {
    cfg.onWindows = boundedU16(doc["on_windows"].as<uint32_t>(), 1, 100);
    changedConfig = true;
  }
  if (doc.containsKey("off_ms")) {
    cfg.offMs = boundedU32(doc["off_ms"].as<uint32_t>(), 1000, 3600000);
    changedConfig = true;
  }
  if (doc.containsKey("threshold")) {
    cfg.threshold = boundedU16(doc["threshold"].as<uint32_t>(), 1, 500);
    changedConfig = true;
  }
  if (doc.containsKey("publish_ms")) {
    cfg.publishMs = boundedU32(doc["publish_ms"].as<uint32_t>(), 500, 600000);
    changedConfig = true;
  }
  if (doc.containsKey("info_ms")) {
    cfg.infoMs = boundedU32(doc["info_ms"].as<uint32_t>(), 0, 3600000);
    changedConfig = true;
  }

  if (changedConfig) {
    saveConfig();
    if (changedBaud) {
      beginRadars();
    }
    publishInfo();
  }

  if (doc["info"] == 1 || doc["config"] == 1) {
    publishInfo();
  }
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  if (String(topic) == topicSet) {
    applySetPayload(payload, length);
  }
}

bool connectMqttOnce() {
  if (mqtt.connected()) return true;
  if (WiFi.status() != WL_CONNECTED) return false;
  if (otaInProgress) return false;

  String clientId = "presence-" + devId;
  bool ok = mqtt.connect(clientId.c_str());

  if (ok) {
    mqtt.subscribe(topicSet.c_str(), 1);
    publishState(true);
  }

  return ok;
}

void initMqttClient() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(5);
  mqtt.setBufferSize(768);
  mqtt.setCallback(onMqttMessage);
}

// ===================== Arduino =====================
void setup() {
  Serial.begin(115200);
  delay(50);

  devId = String(NODE_ID);

  topicState = "presence/" + devId + "/state";
  topicSet = "presence/" + devId + "/set";
  topicInfo = "presence/" + devId + "/info";

  loadConfig();

  s1.serial = &radarSerial1;
  s2.serial = &radarSerial2;
  beginRadars();

  initMqttClient();
  connectWifi();
  if (WiFi.status() == WL_CONNECTED && !otaReady) {
    setupOTA();
  }
  connectMqttOnce();

  lastWindowMs = millis();
  lastStatePublishMs = 0;
  lastInfoPublishMs = millis();
}

void loop() {
  drainRadarSerial(s1);
  drainRadarSerial(s2);

  if (WiFi.status() != WL_CONNECTED) {
    otaReady = false;
    connectWifi();
  }

  if (WiFi.status() == WL_CONNECTED && !otaReady) {
    setupOTA();
  }

  if (!mqtt.connected() && millis() - lastMqttTryMs > 1000) {
    lastMqttTryMs = millis();
    connectMqttOnce();
  }

  if (!otaInProgress) {
    mqtt.loop();
  }

  uint32_t now = millis();
  if (now - lastWindowMs >= cfg.windowMs) {
    processPresenceWindow(s1, now);
    processPresenceWindow(s2, now);
    lastWindowMs = now;
    publishState(false);
  }

  publishState(false);
  updatePeriodicInfo();
  ArduinoOTA.handle();
}
