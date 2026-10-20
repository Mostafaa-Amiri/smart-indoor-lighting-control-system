/*
  NodeMCU ESP8266 + Hi-Link LD2420 presence output.

  Wiring:
    LD2420 OUT -> NodeMCU D5 (GPIO14)
    LD2420 GND -> NodeMCU GND
    LD2420 must use a suitable 3.3 V supply.

  The input handling is intentionally asymmetric:
    - HIGH must remain active for 50 ms before it is accepted.
    - LOW is accepted only after off_ms without another HIGH.

  Arduino libraries:
    - PubSubClient by Nick O'Leary
    - ArduinoJson by Benoit Blanchon

  MQTT:
    The node ID is generated as <partition>_zone_<zone number>.
    presence/<id>/state -> {"ip":"192.168.1.91","z1":1,"z2":0}
    presence/<id>/set   -> {"off_ms":30000}
    presence/<id>/info  -> configuration/status every 5 minutes and when requested
*/

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <EEPROM.h>

// ----------- WiFi / MQTT -----------
const char* WIFI_SSID = "***";
const char* WIFI_PASS = "***";
const char* MQTT_HOST = "192.168.1.77";
const uint16_t MQTT_PORT = 1883;

// These are the only two values to change for each physical sensor node.
const char* PARTITION_ID = "partition_1";
constexpr uint8_t ZONE_NUMBER = 2;  // Must be 1 or 2.
static_assert(ZONE_NUMBER == 2 || ZONE_NUMBER == 2, "ZONE_NUMBER must be 1 or 2");

// D5 on NodeMCU is ESP8266 GPIO14.
constexpr uint8_t PRESENCE_PIN = D5;
constexpr bool PRESENCE_LEVEL = HIGH;

// ----------- Presence / publishing defaults -----------
constexpr uint32_t SAMPLE_MS = 10;
constexpr uint32_t MIN_HIGH_US = 50000;
constexpr uint32_t DEFAULT_OFF_MS = 30000;
constexpr uint32_t DEFAULT_PUBLISH_MS = 5000;
constexpr uint32_t DEFAULT_INFO_MS = 300000;

constexpr uint32_t CONFIG_MAGIC = 0x4C443234;  // "LD24"
constexpr uint16_t CONFIG_VERSION = 2;

struct StoredConfig {
  uint32_t magic;
  uint16_t version;
  uint16_t reserved;
  uint32_t offMs;
  uint32_t checksum;
};

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
StoredConfig cfg;

String topicState;
String topicSet;
String topicInfo;
String nodeId;

bool occupied = false;
bool lastPublishedOccupied = false;
bool hasPublishedState = false;
bool otaReady = false;

volatile uint32_t highStartedUs = 0;
volatile bool qualifiedPulseLatched = false;

uint32_t lastSampleMs = 0;
uint32_t lastConfirmedPresenceMs = 0;
uint32_t lastStatePublishMs = 0;
uint32_t lastInfoPublishMs = 0;
uint32_t lastWifiTryMs = 0;
uint32_t lastMqttTryMs = 0;

// ===================== Configuration =====================
uint32_t boundedU32(uint32_t value, uint32_t minimum, uint32_t maximum) {
  if (value < minimum) return minimum;
  if (value > maximum) return maximum;
  return value;
}

uint32_t configChecksum(const StoredConfig& value) {
  const uint8_t* bytes = reinterpret_cast<const uint8_t*>(&value);
  uint32_t hash = 2166136261UL;
  const size_t count = offsetof(StoredConfig, checksum);

  for (size_t i = 0; i < count; ++i) {
    hash ^= bytes[i];
    hash *= 16777619UL;
  }
  return hash;
}

void setDefaultConfig() {
  memset(&cfg, 0, sizeof(cfg));
  cfg.magic = CONFIG_MAGIC;
  cfg.version = CONFIG_VERSION;
  cfg.offMs = DEFAULT_OFF_MS;
  cfg.checksum = configChecksum(cfg);
}

void normalizeConfig() {
  cfg.offMs = boundedU32(cfg.offMs, 1000, 3600000);
}

void loadConfig() {
  EEPROM.begin(sizeof(StoredConfig));
  EEPROM.get(0, cfg);

  const bool valid =
      cfg.magic == CONFIG_MAGIC &&
      cfg.version == CONFIG_VERSION &&
      cfg.checksum == configChecksum(cfg);

  if (!valid) {
    setDefaultConfig();
    EEPROM.put(0, cfg);
    EEPROM.commit();
  }

  normalizeConfig();
}

void saveConfig() {
  cfg.magic = CONFIG_MAGIC;
  cfg.version = CONFIG_VERSION;
  cfg.checksum = configChecksum(cfg);
  EEPROM.put(0, cfg);
  EEPROM.commit();
}

// ===================== Presence input =====================
void ICACHE_RAM_ATTR onPresenceChange() {
  const uint32_t nowUs = micros();

  if (digitalRead(PRESENCE_PIN) == PRESENCE_LEVEL) {
    highStartedUs = nowUs;
    return;
  }

  if (highStartedUs != 0 && nowUs - highStartedUs >= MIN_HIGH_US) {
    qualifiedPulseLatched = true;
  }
  highStartedUs = 0;
}

void processPresenceInput(uint32_t now) {
  if (now - lastSampleMs < SAMPLE_MS) return;
  lastSampleMs = now;

  noInterrupts();
  const bool sawQualifiedPulse = qualifiedPulseLatched;
  qualifiedPulseLatched = false;
  uint32_t startedUs = highStartedUs;
  interrupts();

  const bool pinHigh = digitalRead(PRESENCE_PIN) == PRESENCE_LEVEL;
  const uint32_t nowUs = micros();

  // Handle the uncommon case where D5 was already HIGH during startup and no
  // rising interrupt was observed.
  if (pinHigh && startedUs == 0) {
    noInterrupts();
    if (highStartedUs == 0) highStartedUs = nowUs;
    startedUs = highStartedUs;
    interrupts();
  }

  const bool sustainedHigh =
      pinHigh && startedUs != 0 && nowUs - startedUs >= MIN_HIGH_US;

  // A completed qualified pulse is remembered even if networking prevented
  // regular sampling during the LD2420's one-second output.
  if (sustainedHigh || sawQualifiedPulse) {
    lastConfirmedPresenceMs = now;
    occupied = true;
  } else if (occupied && now - lastConfirmedPresenceMs >= cfg.offMs) {
    occupied = false;
  }

}

// ===================== WiFi / OTA =====================
void connectWifi(uint32_t now) {
  if (WiFi.status() == WL_CONNECTED) return;
  if (now - lastWifiTryMs < 10000) return;

  lastWifiTryMs = now;
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void setupOTA() {
  ArduinoOTA.setHostname(nodeId.c_str());
  ArduinoOTA.begin();
  otaReady = true;
}

// ===================== MQTT =====================
void publishState(bool force = false) {
  if (!mqtt.connected()) return;

  const uint32_t now = millis();
  const bool changed = !hasPublishedState || occupied != lastPublishedOccupied;

  if (!force && !changed && now - lastStatePublishMs < DEFAULT_PUBLISH_MS) return;

  StaticJsonDocument<96> doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["z1"] = ZONE_NUMBER == 1 && occupied ? 1 : 0;
  doc["z2"] = ZONE_NUMBER == 2 && occupied ? 1 : 0;

  char payload[128];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  if (mqtt.publish(topicState.c_str(), reinterpret_cast<const uint8_t*>(payload), length, true)) {
    lastPublishedOccupied = occupied;
    hasPublishedState = true;
    lastStatePublishMs = now;
  }
}

void publishInfo() {
  if (!mqtt.connected()) return;

  StaticJsonDocument<384> doc;
  doc["id"] = nodeId;
  doc["partition"] = PARTITION_ID;
  doc["zone"] = ZONE_NUMBER;
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["up"] = millis();

  JsonObject config = doc.createNestedObject("cfg");
  config["off_ms"] = cfg.offMs;

  JsonObject sensor = doc.createNestedObject("s1");
  sensor["raw"] = digitalRead(PRESENCE_PIN) == PRESENCE_LEVEL ? 1 : 0;
  sensor["occ"] = occupied ? 1 : 0;
  sensor["last"] = lastConfirmedPresenceMs == 0
      ? -1
      : static_cast<int32_t>(millis() - lastConfirmedPresenceMs);

  char payload[448];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  mqtt.publish(topicInfo.c_str(), reinterpret_cast<const uint8_t*>(payload), length, false);
  lastInfoPublishMs = millis();
}

void applySetPayload(byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, length)) return;

  bool changed = false;

  if (doc.containsKey("off_ms")) {
    cfg.offMs = doc["off_ms"].as<uint32_t>();
    changed = true;
  }

  if (changed) {
    normalizeConfig();
    saveConfig();
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

void connectMqtt(uint32_t now) {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (now - lastMqttTryMs < 5000) return;

  lastMqttTryMs = now;
  const String clientId = String("presence-") + nodeId + "-" + String(ESP.getChipId(), HEX);

  if (mqtt.connect(clientId.c_str())) {
    mqtt.subscribe(topicSet.c_str(), 1);
    publishState(true);
  }
}

// ===================== Arduino =====================
void setup() {
  pinMode(PRESENCE_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PRESENCE_PIN), onPresenceChange, CHANGE);
  loadConfig();

  nodeId = String(PARTITION_ID) + "_zone_" + String(ZONE_NUMBER);
  topicState = String("presence/") + nodeId + "/state";
  topicSet = String("presence/") + nodeId + "/set";
  topicInfo = String("presence/") + nodeId + "/info";

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(5);
  mqtt.setBufferSize(512);
  mqtt.setCallback(onMqttMessage);

  const uint32_t now = millis();
  lastSampleMs = now;
  lastWifiTryMs = now - 10000;
  lastMqttTryMs = now - 5000;

  connectWifi(now);
}

void loop() {
  const uint32_t now = millis();

  // Presence handling runs before networking. The interrupt latch also
  // remembers a HIGH pulse that occurs during a blocking network operation.
  processPresenceInput(now);

  connectWifi(now);
  if (WiFi.status() == WL_CONNECTED && !otaReady) {
    setupOTA();
  }
  connectMqtt(now);

  if (mqtt.connected()) {
    mqtt.loop();
    publishState();
    if (now - lastInfoPublishMs >= DEFAULT_INFO_MS) publishInfo();
  }

  if (otaReady) ArduinoOTA.handle();
  yield();
}
