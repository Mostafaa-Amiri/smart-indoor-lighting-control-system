#include "esp_camera.h"
#include <Arduino.h>
#include <ArduinoOTA.h>
#include <WebServer.h>
#include <WiFi.h>

// ----------- WIFI -----------
const char* WIFI_SSID = "***";
const char* WIFI_PASS = "***";

// ----------- CAMERA DEFAULTS -----------
static const uint32_t XCLK_FREQ_HZ = 10000000;
static const framesize_t DEFAULT_FRAME_SIZE = FRAMESIZE_HD;  // 1280x720. Use FRAMESIZE_SVGA if HD is not available.
static const int DEFAULT_JPEG_QUALITY = 14;                  // Lower number = better quality/larger image.

// AI Thinker ESP32-CAM pin map. This matches the common working CameraWebServer setup.
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WebServer server(80);

String frameSizeName(framesize_t size) {
  switch (size) {
    case FRAMESIZE_QQVGA: return "qqvga";
    case FRAMESIZE_QVGA: return "qvga";
    case FRAMESIZE_VGA: return "vga";
    case FRAMESIZE_SVGA: return "svga";
    case FRAMESIZE_XGA: return "xga";
    case FRAMESIZE_HD: return "hd";
    case FRAMESIZE_SXGA: return "sxga";
    case FRAMESIZE_UXGA: return "uxga";
    default: return String((int)size);
  }
}

bool parseFrameSize(const String& value, framesize_t& out) {
  String v = value;
  v.toLowerCase();

  if (v == "qqvga") out = FRAMESIZE_QQVGA;
  else if (v == "qvga") out = FRAMESIZE_QVGA;
  else if (v == "vga") out = FRAMESIZE_VGA;
  else if (v == "svga") out = FRAMESIZE_SVGA;
  else if (v == "xga") out = FRAMESIZE_XGA;
  else if (v == "hd") out = FRAMESIZE_HD;
  else if (v == "sxga") out = FRAMESIZE_SXGA;
  else if (v == "uxga") out = FRAMESIZE_UXGA;
  else return false;

  return true;
}

int clampInt(int value, int minValue, int maxValue) {
  if (value < minValue) return minValue;
  if (value > maxValue) return maxValue;
  return value;
}

void sendPlain(int code, const String& body) {
  server.send(code, "text/plain", body);
}

void handleRoot() {
  String ip = WiFi.localIP().toString();
  String body;

  body += "ESP32-CAM snapshot node\n";
  body += "Capture: http://" + ip + "/capture\n";
  body += "Status:  http://" + ip + "/status\n";
  body += "Set:     http://" + ip + "/set?framesize=hd&quality=14&brightness=0&contrast=0\n";

  sendPlain(200, body);
}

void handleStatus() {
  sensor_t* s = esp_camera_sensor_get();

  String body = "{";
  body += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  body += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  body += "\"psram\":" + String(psramFound() ? "true" : "false") + ",";
  body += "\"framesize\":\"" + frameSizeName((framesize_t)s->status.framesize) + "\",";
  body += "\"quality\":" + String(s->status.quality) + ",";
  body += "\"brightness\":" + String(s->status.brightness) + ",";
  body += "\"contrast\":" + String(s->status.contrast) + ",";
  body += "\"saturation\":" + String(s->status.saturation) + ",";
  body += "\"awb\":" + String(s->status.awb) + ",";
  body += "\"aec\":" + String(s->status.aec) + ",";
  body += "\"agc\":" + String(s->status.agc);
  body += "}";

  server.send(200, "application/json", body);
}

void handleCapture() {
  camera_fb_t* fb = esp_camera_fb_get();

  if (!fb) {
    sendPlain(503, "camera capture failed");
    return;
  }

  WiFiClient client = server.client();

  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.println("Cache-Control: no-store, no-cache, must-revalidate, max-age=0");
  client.println("Pragma: no-cache");
  client.print("Content-Length: ");
  client.println(fb->len);
  client.println("Connection: close");
  client.println();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

void handleSet() {
  sensor_t* s = esp_camera_sensor_get();
  bool changed = false;
  String result = "updated:";

  if (server.hasArg("framesize")) {
    framesize_t size;
    if (!parseFrameSize(server.arg("framesize"), size)) {
      sendPlain(400, "invalid framesize");
      return;
    }

    if (s->set_framesize(s, size) == 0) {
      changed = true;
      result += " framesize=" + frameSizeName(size);
    }
  }

  if (server.hasArg("quality")) {
    int quality = clampInt(server.arg("quality").toInt(), 8, 25);
    if (s->set_quality(s, quality) == 0) {
      changed = true;
      result += " quality=" + String(quality);
    }
  }

  if (server.hasArg("brightness")) {
    int value = clampInt(server.arg("brightness").toInt(), -2, 2);
    if (s->set_brightness(s, value) == 0) {
      changed = true;
      result += " brightness=" + String(value);
    }
  }

  if (server.hasArg("contrast")) {
    int value = clampInt(server.arg("contrast").toInt(), -2, 2);
    if (s->set_contrast(s, value) == 0) {
      changed = true;
      result += " contrast=" + String(value);
    }
  }

  if (server.hasArg("saturation")) {
    int value = clampInt(server.arg("saturation").toInt(), -2, 2);
    if (s->set_saturation(s, value) == 0) {
      changed = true;
      result += " saturation=" + String(value);
    }
  }

  if (server.hasArg("awb")) {
    int value = clampInt(server.arg("awb").toInt(), 0, 1);
    if (s->set_whitebal(s, value) == 0) {
      changed = true;
      result += " awb=" + String(value);
    }
  }

  if (server.hasArg("aec")) {
    int value = clampInt(server.arg("aec").toInt(), 0, 1);
    if (s->set_exposure_ctrl(s, value) == 0) {
      changed = true;
      result += " aec=" + String(value);
    }
  }

  if (server.hasArg("agc")) {
    int value = clampInt(server.arg("agc").toInt(), 0, 1);
    if (s->set_gain_ctrl(s, value) == 0) {
      changed = true;
      result += " agc=" + String(value);
    }
  }

  if (server.hasArg("hmirror")) {
    int value = clampInt(server.arg("hmirror").toInt(), 0, 1);
    if (s->set_hmirror(s, value) == 0) {
      changed = true;
      result += " hmirror=" + String(value);
    }
  }

  if (server.hasArg("vflip")) {
    int value = clampInt(server.arg("vflip").toInt(), 0, 1);
    if (s->set_vflip(s, value) == 0) {
      changed = true;
      result += " vflip=" + String(value);
    }
  }

  if (server.hasArg("lenc")) {
    int value = clampInt(server.arg("lenc").toInt(), 0, 1);
    if (s->set_lenc(s, value) == 0) {
      changed = true;
      result += " lenc=" + String(value);
    }
  }

  if (!changed) {
    result += " nothing";
  }

  sendPlain(200, result);
}

void handleRestart() {
  sendPlain(200, "restarting");
  delay(250);
  ESP.restart();
}

void setupCameraSensorDefaults() {
  sensor_t* s = esp_camera_sensor_get();

  s->set_framesize(s, DEFAULT_FRAME_SIZE);
  s->set_quality(s, DEFAULT_JPEG_QUALITY);
  s->set_brightness(s, 0);
  s->set_contrast(s, 0);
  s->set_saturation(s, 0);
  s->set_whitebal(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_gain_ctrl(s, 1);
  s->set_lenc(s, 1);
}

bool initCamera() {
  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = XCLK_FREQ_HZ;
  config.frame_size = DEFAULT_FRAME_SIZE;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.jpeg_quality = DEFAULT_JPEG_QUALITY;
  config.fb_count = 1;

  if (!psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 18;
  }

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  setupCameraSensorDefaults();
  return true;
}

void setupOta() {
  ArduinoOTA.setHostname("esp32cam-occupancy");

  ArduinoOTA.onStart([]() {
    Serial.println("OTA start");
  });

  ArduinoOTA.onEnd([]() {
    Serial.println("OTA end");
  });

  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("OTA error: %u\n", error);
  });

  ArduinoOTA.begin();
}

void setupRoutes() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/set", HTTP_GET, handleSet);
  server.on("/restart", HTTP_GET, handleRestart);

  server.onNotFound([]() {
    sendPlain(404, "not found");
  });
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi connected: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(200);

  connectWifi();

  if (!initCamera()) {
    Serial.println("Camera failed. Restarting in 5 seconds.");
    delay(5000);
    ESP.restart();
  }

  setupOta();
  setupRoutes();
  server.begin();

  Serial.println("ESP32-CAM occupancy snapshot node ready");
  Serial.print("Capture URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/capture");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }

  ArduinoOTA.handle();
  server.handleClient();
  delay(1);
}
