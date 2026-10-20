#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#include <OneWire.h>
#include <DallasTemperature.h>

#include <ArduinoOTA.h>
#include <ESP8266mDNS.h>
#include <WiFiUdp.h>
#include <math.h>

// ----------- WIFI / MQTT -----------
const char* WIFI_SSID = "***";
const char* WIFI_PASS = "***";
const char* MQTT_HOST = "192.168.1.77";
const uint16_t MQTT_PORT = 1883;

// ----------- PWM -----------
static const int PWM_RANGE = 1023;

static const uint8_t PWM_PINS[4] = {
  D5, // GPIO14
  D6, // GPIO12
  D7, // GPIO13
  D1  // GPIO5
};

// ----------- SMOOTH RAMP -----------
static const uint32_t DEFAULT_RAMP_STEP_MS = 50;   // 1% every 50 ms => 0-100% in ~5 sec
static const uint32_t MIN_RAMP_STEP_MS = 10;
static const uint32_t MAX_RAMP_STEP_MS = 500;

// ----------- LOW DUTY ANTI-FLICKER BOOST -----------
static const float DEFAULT_LOW_DUTY_LIMIT_PCT = 10.0f;
static const float DEFAULT_BOOST_DUTY_PCT = 12.0f;
static const uint32_t DEFAULT_BOOST_RAMP_STEP_MS = 10;  // fast: 1% every 10 ms
static const uint32_t DEFAULT_BOOST_HOLD_MS = 100;      // short SMPS/PT4115 stabilization hold

bool gAntiFlickerEnabled = true;
float gLowDutyLimitPct = DEFAULT_LOW_DUTY_LIMIT_PCT;
float gBoostDutyPct = DEFAULT_BOOST_DUTY_PCT;
uint32_t gBoostRampStepMs = DEFAULT_BOOST_RAMP_STEP_MS;
uint32_t gBoostHoldMs = DEFAULT_BOOST_HOLD_MS;

// ----------- DS18B20 -----------
const uint8_t TEMP_PIN = D2;    // GPIO4
OneWire oneWire(TEMP_PIN);
DallasTemperature dallas(&oneWire);
DeviceAddress tempAddr;

bool tempPresent = false;

// 9-bit DS18B20 resolution gives ~0.5°C resolution and fast conversion.
// Typical/max conversion time is much shorter than high resolution mode.
static const uint32_t TEMP_CONV_MS = 100;

bool tempAutoEnabled = true;
uint32_t tempIntervalMs = 25000;

bool tempRequestPending = false;
unsigned long tempRequestMs = 0;
unsigned long lastTempMs = 0;

String tempRequestReason = "auto";

// ----------- GLOBALS -----------
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

String devId;
String topicAssign;
String topicSet;
String topicStatus;
String topicTele;
String topicApplied;

char lwtBuf[96];

uint32_t gFreqHz = 1000;

float gDutyPct[4] = {0, 0, 0, 0};
float gTargetDutyPct[4] = {0, 0, 0, 0};
float gFinalTargetDutyPct[4] = {0, 0, 0, 0};

uint32_t gRampStepMs = DEFAULT_RAMP_STEP_MS;
uint32_t gFinalRampStepMs = DEFAULT_RAMP_STEP_MS;
bool gRampActive = false;
String gTransitionMode = "immediate";

unsigned long gLastRampMs = 0;

enum RampMode {
  RAMP_NONE,
  RAMP_NORMAL,
  RAMP_BOOST_UP,
  RAMP_BOOST_HOLD,
  RAMP_BOOST_DOWN
};

RampMode gRampMode = RAMP_NONE;
unsigned long gBoostHoldStartMs = 0;

uint32_t gLastCmdId = 0;

bool otaReady = false;
volatile bool otaInProgress = false;

// reconnect timers
unsigned long lastWifiTryMs = 0;
unsigned long lastMqttTryMs = 0;

const unsigned long WIFI_RETRY_MS = 10000;
const unsigned long MQTT_RETRY_MS = 3000;
const unsigned long TELEMETRY_INTERVAL_MS = 25000;

unsigned long lastTelemetryMs = 0;

// ===================== helpers =====================

float clampDuty(float d) {
  if (d < 0) return 0;
  if (d > 100) return 100;
  return d;
}

uint32_t clampRampStepMs(uint32_t stepMs) {
  if (stepMs < MIN_RAMP_STEP_MS) return MIN_RAMP_STEP_MS;
  if (stepMs > MAX_RAMP_STEP_MS) return MAX_RAMP_STEP_MS;
  return stepMs;
}

float clampLowDutyLimit(float value) {
  if (value < 1.0f) return 1.0f;
  if (value > 30.0f) return 30.0f;
  return value;
}

float clampBoostDuty(float value) {
  if (value < 1.0f) return 1.0f;
  if (value > 60.0f) return 60.0f;
  return value;
}

uint32_t clampBoostStepMs(uint32_t value) {
  if (value < 1) return 1;
  if (value > 100) return 100;
  return value;
}

uint32_t clampBoostHoldMs(uint32_t value) {
  if (value > 2000) return 2000;
  return value;
}

uint32_t clampTempIntervalMs(uint32_t intervalMs) {
  if (intervalMs < 2000) return 2000;
  if (intervalMs > 3600000) return 3600000;
  return intervalMs;
}

int dutyToRaw(float dutyPct) {
  dutyPct = clampDuty(dutyPct);
  return (int)lroundf(dutyPct * PWM_RANGE / 100.0f);
}

void applyPWMDutyCh(uint8_t ch, float dutyPct) {
  if (ch > 3) return;
  gDutyPct[ch] = clampDuty(dutyPct);
  analogWrite(PWM_PINS[ch], dutyToRaw(gDutyPct[ch]));
}

void applyPWMDutyAll(float dutyPct) {
  dutyPct = clampDuty(dutyPct);

  for (uint8_t i = 0; i < 4; i++) {
    applyPWMDutyCh(i, dutyPct);
  }
}

void applyPWMFreq(uint32_t freq) {
  if (freq < 1) freq = 1;
  if (freq > 5000) freq = 5000;

  gFreqHz = freq;
  analogWriteFreq(gFreqHz);

  for (uint8_t i = 0; i < 4; i++) {
    analogWrite(PWM_PINS[i], dutyToRaw(gDutyPct[i]));
  }
}

bool allTargetsReached() {
  for (uint8_t i = 0; i < 4; i++) {
    if (fabsf(gDutyPct[i] - gTargetDutyPct[i]) >= 0.01f) {
      return false;
    }
  }

  return true;
}

bool isImmediateTransition(const char* transition) {
  if (transition == nullptr) return false;

  String t = String(transition);
  t.toLowerCase();

  return (
    t == "immediate" ||
    t == "fast" ||
    t == "direct" ||
    t == "instant"
  );
}

// ===================== MQTT publish =====================

void publishApplied(const char* eventName) {
  if (!mqtt.connected()) return;
  if (otaInProgress) return;

  StaticJsonDocument<220> msg;

  msg["id"] = devId;
  msg["event"] = eventName;
  msg["applied"] = true;
  msg["duty"] = gDutyPct[0];
  msg["target_duty"] = gTargetDutyPct[0];
  msg["final_target_duty"] = gFinalTargetDutyPct[0];
  msg["transition"] = gTransitionMode;
  msg["step_ms"] = gRampStepMs;
  msg["target_reached"] = !gRampActive && allFinalTargetsReached();

  if (strcmp(eventName, "anti_flicker_config_accepted") == 0) {
    msg["anti_flicker_enabled"] = gAntiFlickerEnabled;
    msg["low_duty_limit"] = gLowDutyLimitPct;
    msg["boost_duty"] = gBoostDutyPct;
    msg["boost_step_ms"] = gBoostRampStepMs;
    msg["boost_hold_ms"] = gBoostHoldMs;
  }

  if (gLastCmdId != 0) {
    msg["cmd_id"] = gLastCmdId;
  }

  char buf[240];
  size_t n = serializeJson(msg, buf, sizeof(buf));

  mqtt.publish(topicApplied.c_str(), (const uint8_t*)buf, n, false);
}

void publishTemperature(float tC, const char* reason) {
  if (!mqtt.connected()) return;
  if (otaInProgress) return;

  StaticJsonDocument<192> tele;

  tele["id"] = devId;
  tele["status"] = "online";
  tele["tC"] = tC;
  tele["temp_present"] = tempPresent;
  tele["temp_mode"] = tempAutoEnabled ? "auto" : "manual";
  tele["temp_interval_ms"] = tempIntervalMs;
  tele["reason"] = reason;

  char buf[220];
  size_t n = serializeJson(tele, buf, sizeof(buf));

  mqtt.publish(topicTele.c_str(), (const uint8_t*)buf, n, false);
}

void publishTempStatus(const char* eventName) {
  if (!mqtt.connected()) return;
  if (otaInProgress) return;

  StaticJsonDocument<192> tele;

  tele["id"] = devId;
  tele["status"] = "online";
  tele["event"] = eventName;
  tele["temp_present"] = tempPresent;
  tele["temp_mode"] = tempAutoEnabled ? "auto" : "manual";
  tele["temp_interval_ms"] = tempIntervalMs;

  char buf[220];
  size_t n = serializeJson(tele, buf, sizeof(buf));

  mqtt.publish(topicTele.c_str(), (const uint8_t*)buf, n, false);
}

void announceOnline() {
  if (!mqtt.connected()) return;

  StaticJsonDocument<160> ann;

  ann["id"] = devId;
  ann["ip"] = WiFi.localIP().toString();
  ann["chip"] = (uint32_t)ESP.getChipId();
  ann["ota"] = devId;
  ann["type"] = "panel";
  ann["pwm_pins"] = "D5,D6,D7,D1";
  ann["temp"] = tempPresent;

  char msg[200];
  size_t n = serializeJson(ann, msg, sizeof(msg));

  mqtt.publish("lights/announce", (const uint8_t*)msg, n, true);
}

void publishPanelStatusOnline() {
  if (!mqtt.connected()) return;

  mqtt.publish(topicStatus.c_str(), "online", true);
}

// ===================== ramp engine =====================

void setTargetsAll(float dutyPct) {
  dutyPct = clampDuty(dutyPct);

  for (uint8_t i = 0; i < 4; i++) {
    gTargetDutyPct[i] = dutyPct;
  }
}

void setTargetCh(uint8_t ch, float dutyPct) {
  if (ch > 3) return;
  gTargetDutyPct[ch] = clampDuty(dutyPct);
}

void copyTargetsToFinalTargets() {
  for (uint8_t i = 0; i < 4; i++) {
    gFinalTargetDutyPct[i] = gTargetDutyPct[i];
  }
}

void copyFinalTargetsToTargets() {
  for (uint8_t i = 0; i < 4; i++) {
    gTargetDutyPct[i] = gFinalTargetDutyPct[i];
  }
}

bool allFinalTargetsReached() {
  for (uint8_t i = 0; i < 4; i++) {
    if (fabsf(gDutyPct[i] - gFinalTargetDutyPct[i]) >= 0.01f) {
      return false;
    }
  }

  return true;
}

void applyTargetsImmediately() {
  for (uint8_t i = 0; i < 4; i++) {
    applyPWMDutyCh(i, gTargetDutyPct[i]);
  }
}

void startDutyCommand(bool immediate, uint32_t requestedStepMs) {
  copyTargetsToFinalTargets();
  gFinalRampStepMs = clampRampStepMs(requestedStepMs);
  gRampStepMs = gFinalRampStepMs;

  if (immediate) {
    gTransitionMode = "immediate";
    gRampActive = false;
    gRampMode = RAMP_NONE;

    applyTargetsImmediately();

    publishApplied("accepted");
    publishApplied("reached");

    return;
  }

  bool targetIsLowButNotOff =
    gAntiFlickerEnabled && gFinalTargetDutyPct[0] > 0.0f && gFinalTargetDutyPct[0] < gLowDutyLimitPct;

  bool currentIsLow = gDutyPct[0] < gLowDutyLimitPct;

  if (targetIsLowButNotOff && currentIsLow) {
    gTransitionMode = "low_duty_boost";
    setTargetsAll(gBoostDutyPct);
    gRampStepMs = gBoostRampStepMs;
    gRampActive = true;
    gRampMode = RAMP_BOOST_UP;
    gLastRampMs = millis();

    publishApplied("accepted");
    return;
  }

  gTransitionMode = "smooth";
  gRampMode = RAMP_NORMAL;

  if (allTargetsReached()) {
    gRampActive = false;
    gRampMode = RAMP_NONE;

    publishApplied("accepted");
    publishApplied("reached");

    return;
  }

  gRampActive = true;
  gLastRampMs = millis();

  publishApplied("accepted");
}

void updateSmoothRamp() {
  if (!gRampActive) return;
  if (otaInProgress) return;

  unsigned long now = millis();

  if (gRampMode == RAMP_BOOST_HOLD) {
    if (now - gBoostHoldStartMs >= gBoostHoldMs) {
      copyFinalTargetsToTargets();
      gRampStepMs = gFinalRampStepMs;
      gRampMode = RAMP_BOOST_DOWN;
      gLastRampMs = now;
    }
    return;
  }

  if (now - gLastRampMs < gRampStepMs) {
    return;
  }

  gLastRampMs = now;

  for (uint8_t i = 0; i < 4; i++) {
    float diff = gTargetDutyPct[i] - gDutyPct[i];

    if (fabsf(diff) <= 1.0f) {
      applyPWMDutyCh(i, gTargetDutyPct[i]);
    } else if (diff > 0) {
      applyPWMDutyCh(i, gDutyPct[i] + 1.0f);
    } else {
      applyPWMDutyCh(i, gDutyPct[i] - 1.0f);
    }
  }

  if (allTargetsReached()) {
    if (gRampMode == RAMP_BOOST_UP) {
      gRampMode = RAMP_BOOST_HOLD;
      gBoostHoldStartMs = now;
      return;
    }

    gRampActive = false;
    gRampMode = RAMP_NONE;
    copyFinalTargetsToTargets();
    publishApplied("reached");
  }
}


bool applyAntiFlickerConfigObject(JsonVariantConst cfg) {
  if (cfg.isNull() || !cfg.is<JsonObjectConst>()) return false;

  JsonObjectConst obj = cfg.as<JsonObjectConst>();
  bool changed = false;

  if (obj.containsKey("enabled")) {
    gAntiFlickerEnabled = obj["enabled"] | gAntiFlickerEnabled;
    changed = true;
  }

  if (obj.containsKey("low_limit")) {
    gLowDutyLimitPct = clampLowDutyLimit(obj["low_limit"] | gLowDutyLimitPct);
    changed = true;
  }

  if (obj.containsKey("low_duty_limit")) {
    gLowDutyLimitPct = clampLowDutyLimit(obj["low_duty_limit"] | gLowDutyLimitPct);
    changed = true;
  }

  if (obj.containsKey("boost_duty")) {
    gBoostDutyPct = clampBoostDuty(obj["boost_duty"] | gBoostDutyPct);
    changed = true;
  }

  if (obj.containsKey("boost_step_ms")) {
    gBoostRampStepMs = clampBoostStepMs(obj["boost_step_ms"] | gBoostRampStepMs);
    changed = true;
  }

  if (obj.containsKey("hold_ms")) {
    gBoostHoldMs = clampBoostHoldMs(obj["hold_ms"] | gBoostHoldMs);
    changed = true;
  }

  if (obj.containsKey("boost_hold_ms")) {
    gBoostHoldMs = clampBoostHoldMs(obj["boost_hold_ms"] | gBoostHoldMs);
    changed = true;
  }

  return changed;
}

bool handleAntiFlickerCommand(const JsonDocument& doc) {
  bool changed = false;

  if (doc.containsKey("anti_flicker")) {
    changed = applyAntiFlickerConfigObject(doc["anti_flicker"]) || changed;
  }

  if (doc.containsKey("anti_flicker_enabled")) {
    gAntiFlickerEnabled = doc["anti_flicker_enabled"] | gAntiFlickerEnabled;
    changed = true;
  }

  if (doc.containsKey("low_duty_limit")) {
    gLowDutyLimitPct = clampLowDutyLimit(doc["low_duty_limit"] | gLowDutyLimitPct);
    changed = true;
  }

  if (doc.containsKey("boost_duty")) {
    gBoostDutyPct = clampBoostDuty(doc["boost_duty"] | gBoostDutyPct);
    changed = true;
  }

  if (doc.containsKey("boost_step_ms")) {
    gBoostRampStepMs = clampBoostStepMs(doc["boost_step_ms"] | gBoostRampStepMs);
    changed = true;
  }

  if (doc.containsKey("boost_hold_ms")) {
    gBoostHoldMs = clampBoostHoldMs(doc["boost_hold_ms"] | gBoostHoldMs);
    changed = true;
  }

  return changed;
}

// ===================== temperature =====================

void initTemperature() {
  dallas.begin();

  tempPresent = dallas.getAddress(tempAddr, 0);

  if (tempPresent) {
    dallas.setResolution(tempAddr, 9);
    dallas.setWaitForConversion(false);
  }
}

void startTemperatureRequest(const char* reason) {
  if (!tempPresent) {
    publishTempStatus("temp_not_present");
    return;
  }

  if (otaInProgress) return;

  if (tempRequestPending) {
    tempRequestReason = reason;
    return;
  }

  dallas.requestTemperatures();
  tempRequestPending = true;
  tempRequestMs = millis();
  tempRequestReason = reason;
}

void finishTemperatureAndPublish() {
  if (!tempRequestPending) return;

  if (!tempPresent || otaInProgress) {
    tempRequestPending = false;
    return;
  }

  float tC = dallas.getTempC(tempAddr);

  tempRequestPending = false;

  if (tC == DEVICE_DISCONNECTED_C) {
    publishTempStatus("temp_disconnected");
    return;
  }

  // 0.5°C precision is enough for your use case.
  float tC_05 = roundf(tC * 2.0f) / 2.0f;

  publishTemperature(tC_05, tempRequestReason.c_str());
}

void handleTempCommandFromVariant(JsonVariantConst vTemp) {
  if (vTemp.isNull()) return;

  if (vTemp.is<JsonObjectConst>()) {
    JsonObjectConst obj = vTemp.as<JsonObjectConst>();

    if (obj.containsKey("auto")) {
      tempAutoEnabled = obj["auto"] | tempAutoEnabled;
    }

    if (obj.containsKey("mode")) {
      const char* mode = obj["mode"] | "";
      String m = String(mode);
      m.toLowerCase();

      if (m == "auto") {
        tempAutoEnabled = true;
      } else if (m == "manual") {
        tempAutoEnabled = false;
        startTemperatureRequest("manual");
      } else if (m == "off" || m == "disabled") {
        tempAutoEnabled = false;
      }
    }

    if (obj.containsKey("interval_ms")) {
      tempIntervalMs = clampTempIntervalMs(obj["interval_ms"] | tempIntervalMs);
    }

    if (obj.containsKey("interval_s")) {
      uint32_t sec = obj["interval_s"] | (tempIntervalMs / 1000);
      tempIntervalMs = clampTempIntervalMs(sec * 1000UL);
    }

    if (obj["now"] | false) {
      startTemperatureRequest("manual");
    }

    publishTempStatus("temp_config");
  }
}

bool handleTempCommand(const JsonDocument& doc) {
  bool configTouched = false;

  if (doc.containsKey("temp")) {
    handleTempCommandFromVariant(doc["temp"]);
    configTouched = true;
  }

  if (doc.containsKey("temp_auto")) {
    tempAutoEnabled = doc["temp_auto"] | tempAutoEnabled;
    configTouched = true;
  }

  if (doc.containsKey("temp_mode")) {
    const char* mode = doc["temp_mode"] | "";
    String m = String(mode);
    m.toLowerCase();

    if (m == "auto") {
      tempAutoEnabled = true;
      configTouched = true;
    } else if (m == "manual") {
      tempAutoEnabled = false;
      startTemperatureRequest("manual");
      configTouched = true;
    } else if (m == "off" || m == "disabled") {
      tempAutoEnabled = false;
      configTouched = true;
    }
  }

  if (doc.containsKey("temp_interval_ms")) {
    tempIntervalMs = clampTempIntervalMs(doc["temp_interval_ms"] | tempIntervalMs);
    configTouched = true;
  }

  if (doc.containsKey("temp_interval_s")) {
    uint32_t sec = doc["temp_interval_s"] | (tempIntervalMs / 1000);
    tempIntervalMs = clampTempIntervalMs(sec * 1000UL);
    configTouched = true;
  }

  if (doc["temp_now"] | false) {
    startTemperatureRequest("manual");
    configTouched = true;
  }

  if (configTouched) {
    publishTempStatus("temp_config");
  }

  return configTouched;
}

void updateTemperatureScheduler() {
  if (otaInProgress) return;

  unsigned long now = millis();

  if (tempAutoEnabled && !tempRequestPending && (now - lastTempMs >= tempIntervalMs)) {
    lastTempMs = now;
    startTemperatureRequest("auto");
  }

  if (tempRequestPending && (now - tempRequestMs >= TEMP_CONV_MS)) {
    finishTemperatureAndPublish();
  }
}

// ===================== payload handling =====================

void handleAssign(const JsonDocument& doc) {
  uint32_t f = doc["freq"] | gFreqHz;
  applyPWMFreq(f);

  publishApplied("status");
}

bool parseDutyCommand(const JsonDocument& doc) {
  JsonVariantConst vDuty = doc["duty"];

  if (vDuty.isNull()) {
    return false;
  }

  // PC should send one scalar duty only.
  // Example: {"duty": 65}
  if (vDuty.is<JsonArrayConst>()) {
    return false;
  }

  float requestedDuty = vDuty.as<float>();

  // Internally apply same duty to all 4 PWM channels.
  setTargetsAll(requestedDuty);

  return true;
}

void handleSet(const JsonDocument& doc) {
  bool tempConfigChanged = handleTempCommand(doc);
  bool antiFlickerConfigChanged = handleAntiFlickerCommand(doc);

  bool hasDutyCommand = parseDutyCommand(doc);

  if (!hasDutyCommand) {
    if (antiFlickerConfigChanged) {
      publishApplied("anti_flicker_config_accepted");
    } else if (tempConfigChanged) {
      publishApplied("temp_config_accepted");
    } else {
      publishApplied("set_received_no_duty");
    }
    return;
  }

  const char* transition = doc["transition"] | "smooth";
  bool immediate = isImmediateTransition(transition);

  uint32_t requestedStepMs = doc["step_ms"] | DEFAULT_RAMP_STEP_MS;

  startDutyCommand(immediate, requestedStepMs);
}

void onMqttMsg(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<512> doc;

  DeserializationError err = deserializeJson(doc, payload, len);

  if (err) return;

  gLastCmdId = doc["cmd_id"] | 0;

  if (strcmp(topic, topicAssign.c_str()) == 0) {
    handleAssign(doc);
  } else if (strcmp(topic, topicSet.c_str()) == 0) {
    handleSet(doc);
  }
}

// ===================== WiFi =====================

void startWifiIfNeeded() {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();

  if (now - lastWifiTryMs < WIFI_RETRY_MS) return;

  lastWifiTryMs = now;

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

// ===================== OTA =====================

void setupOTA() {
  if (otaReady) return;
  if (WiFi.status() != WL_CONNECTED) return;

  ArduinoOTA.setHostname(devId.c_str());

  ArduinoOTA.onStart([]() {
    otaInProgress = true;

    gRampActive = false;

    for (uint8_t i = 0; i < 4; i++) {
      gTargetDutyPct[i] = 0;
    }

    gTransitionMode = "immediate";
    applyPWMDutyAll(0);

    if (mqtt.connected()) {
      mqtt.disconnect();
    }
  });

  ArduinoOTA.onEnd([]() {
    otaInProgress = false;
  });

  ArduinoOTA.onError([](ota_error_t error) {
    (void)error;
    otaInProgress = false;
  });

  ArduinoOTA.begin();
  otaReady = true;
}

// ===================== MQTT =====================

void initMqttClient() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(2);
  mqtt.setCallback(onMqttMsg);
}

void connectMqttIfNeeded() {
  if (mqtt.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if (otaInProgress) return;

  unsigned long now = millis();

  if (now - lastMqttTryMs < MQTT_RETRY_MS) return;

  lastMqttTryMs = now;

  String clientId = "panel-" + devId;

  bool ok = mqtt.connect(
    clientId.c_str(),
    nullptr,
    nullptr,
    topicStatus.c_str(),
    1,
    true,
    lwtBuf,
    true
  );

  if (ok) {
    mqtt.subscribe(topicAssign.c_str(), 1);
    mqtt.subscribe(topicSet.c_str(), 1);

    announceOnline();
    publishPanelStatusOnline();
    publishApplied("status");
    publishTempStatus("temp_status");
  }
}

// ===================== Arduino =====================

void setup() {
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(PWM_PINS[i], OUTPUT);
  }

  analogWriteRange(PWM_RANGE);

  gFreqHz = 1000;
  analogWriteFreq(gFreqHz);

  for (uint8_t i = 0; i < 4; i++) {
    gDutyPct[i] = 0;
    gTargetDutyPct[i] = 0;
  }

  gRampActive = false;
  gTransitionMode = "immediate";

  applyPWMDutyAll(0);

  char idbuf[20];
  snprintf(idbuf, sizeof(idbuf), "esp-%06X", ESP.getChipId());
  devId = String(idbuf);

  topicAssign  = "lights/panel/" + devId + "/assign";
  topicSet     = "lights/panel/" + devId + "/set";
  topicStatus  = "lights/panel/" + devId + "/status";
  topicTele    = "lights/panel/" + devId + "/tele";
  topicApplied = "lights/panel/" + devId + "/applied";

  strncpy(lwtBuf, "offline", sizeof(lwtBuf));
  lwtBuf[sizeof(lwtBuf) - 1] = '\0';

  initTemperature();
  initMqttClient();

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void loop() {
  startWifiIfNeeded();

  if (WiFi.status() == WL_CONNECTED) {
    setupOTA();
  }

  if (otaReady) {
    ArduinoOTA.handle();
  }

  connectMqttIfNeeded();

  if (!otaInProgress && mqtt.connected()) {
    mqtt.loop();
  }

  updateSmoothRamp();
  updateTemperatureScheduler();

  yield();
}
