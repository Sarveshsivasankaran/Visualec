#include <Arduino.h>
#line 1 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

// -------- User-configurable hardware and network settings --------
const char* WIFI_SSID = "Xx";
const char* WIFI_PASSWORD = "sarvesh@2643";
const char* DEVICE_NAME = "visualec-esp32";
constexpr bool RELAY_ACTIVE_LOW = true;
constexpr uint8_t RELAY_COUNT = 3;
// Must match the physical wiring and backend relay table.
// Relay 1 -> GPIO 4, Relay 2 -> GPIO 5, Relay 3 -> GPIO 6.
const uint8_t RELAY_PINS[RELAY_COUNT] = {4, 5, 6};
constexpr uint8_t ZONE_COUNT = 3;
// Values are zero-based relay indexes: Zone 1 -> Relay 1, etc.
const uint8_t ZONE_RELAY_MAP[ZONE_COUNT] = {0, 1, 2};
constexpr unsigned long WIFI_RETRY_MS = 5000;
// -----------------------------------------------------------------

WebServer server(80);
Preferences preferences;
bool relayStates[RELAY_COUNT] = {false, false, false};
bool emergencyStopped = false;
unsigned long lastWifiAttempt = 0;
String lastCommandId = "";
String lastCommandResponse = "";

#line 28 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void writeRelay(uint8_t index, bool on);
#line 33 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void setSafeState();
#line 37 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void addCors();
#line 43 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void sendJson(int code, const String& body);
#line 56 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
String zoneJson(uint8_t zoneIndex);
#line 67 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
bool duplicateCommand();
#line 78 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void commandRelay(uint8_t index, const String& operation);
#line 97 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void commandZone(uint8_t zoneIndex, const String& operation);
#line 130 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void handleRelayRoute();
#line 143 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void handleZoneRoute();
#line 167 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void handleNotFound();
#line 179 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void allRelays(bool on);
#line 185 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void setupRoutes();
#line 215 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void connectWifi();
#line 226 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void setup();
#line 243 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void loop();
#line 28 "D:\\Program files\\Visualec\\firmware\\visualec_esp32_s3\\visualec_esp32_s3.ino"
void writeRelay(uint8_t index, bool on) {
  relayStates[index] = on;
  digitalWrite(RELAY_PINS[index], RELAY_ACTIVE_LOW ? !on : on);
}

void setSafeState() {
  for (uint8_t i = 0; i < RELAY_COUNT; i++) writeRelay(i, false);
}

void addCors() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type,X-Command-ID");
}

void sendJson(int code, const String& body) {
  addCors();
  server.send(code, "application/json", body);
}

String relayJson(uint8_t index, bool success = true) {
  return "{\"success\":" + String(success ? "true" : "false") +
         ",\"relay_id\":" + String(index + 1) +
         ",\"gpio_pin\":" + String(RELAY_PINS[index]) +
         ",\"state\":\"" + String(relayStates[index] ? "on" : "off") +
         "\",\"device\":\"" + DEVICE_NAME + "\"}";
}

String zoneJson(uint8_t zoneIndex) {
  uint8_t relayIndex = ZONE_RELAY_MAP[zoneIndex];
  return String("{\"success\":true") +
         String(",\"zone_id\":") + String(zoneIndex + 1) +
         ",\"active\":" + String(relayStates[relayIndex] ? "true" : "false") +
         ",\"relay_id\":" + String(relayIndex + 1) +
         ",\"gpio_pin\":" + String(RELAY_PINS[relayIndex]) +
         ",\"relay_state\":\"" + String(relayStates[relayIndex] ? "on" : "off") +
         "\",\"device\":\"" + DEVICE_NAME + "\"}";
}

bool duplicateCommand() {
  if (!server.hasHeader("X-Command-ID")) return false;
  String id = server.header("X-Command-ID");
  if (id.length() && id == lastCommandId) {
    sendJson(200, lastCommandResponse);
    return true;
  }
  lastCommandId = id;
  return false;
}

void commandRelay(uint8_t index, const String& operation) {
  if (duplicateCommand()) return;
  if (index >= RELAY_COUNT) {
    sendJson(404, "{\"success\":false,\"error\":\"invalid relay id\"}");
    return;
  }
  if (emergencyStopped && operation != "off") {
    sendJson(423, "{\"success\":false,\"error\":\"emergency stop active\"}");
    return;
  }
  if (operation == "on") writeRelay(index, true);
  else if (operation == "off") writeRelay(index, false);
  else if (operation == "toggle") writeRelay(index, !relayStates[index]);
  else { sendJson(400, "{\"success\":false,\"error\":\"invalid operation\"}"); return; }
  lastCommandResponse = relayJson(index);
  Serial.println(lastCommandResponse);
  sendJson(200, lastCommandResponse);
}

void commandZone(uint8_t zoneIndex, const String& operation) {
  if (duplicateCommand()) return;
  if (zoneIndex >= ZONE_COUNT) {
    sendJson(404, "{\"success\":false,\"error\":\"invalid zone id\"}");
    return;
  }

  uint8_t relayIndex = ZONE_RELAY_MAP[zoneIndex];
  if (relayIndex >= RELAY_COUNT) {
    sendJson(500, "{\"success\":false,\"error\":\"invalid zone relay mapping\"}");
    return;
  }

  bool active;
  if (operation == "active") active = true;
  else if (operation == "inactive") active = false;
  else {
    sendJson(400, "{\"success\":false,\"error\":\"operation must be active or inactive\"}");
    return;
  }

  if (emergencyStopped && active) {
    sendJson(423, "{\"success\":false,\"error\":\"emergency stop active\"}");
    return;
  }

  // This is the physical control signal. Active-LOW modules receive LOW for ON.
  writeRelay(relayIndex, active);
  lastCommandResponse = zoneJson(zoneIndex);
  Serial.println(lastCommandResponse);
  sendJson(200, lastCommandResponse);
}

void handleRelayRoute() {
  if (server.method() == HTTP_OPTIONS) { addCors(); server.send(204); return; }
  if (server.method() != HTTP_POST) { sendJson(405, "{\"success\":false,\"error\":\"method not allowed\"}"); return; }
  String uri = server.uri();
  // Expected: /relay/{id}/{on|off|toggle}
  int firstSlash = uri.indexOf('/', 7);
  if (!uri.startsWith("/relay/") || firstSlash < 0) { sendJson(404, "{\"success\":false,\"error\":\"route not found\"}"); return; }
  int relayId = uri.substring(7, firstSlash).toInt();
  String operation = uri.substring(firstSlash + 1);
  if (relayId < 1) { sendJson(400, "{\"success\":false,\"error\":\"invalid relay id\"}"); return; }
  commandRelay(relayId - 1, operation);
}

void handleZoneRoute() {
  if (server.method() == HTTP_OPTIONS) { addCors(); server.send(204); return; }
  if (server.method() != HTTP_POST) {
    sendJson(405, "{\"success\":false,\"error\":\"method not allowed\"}");
    return;
  }

  String uri = server.uri();
  // Expected: /zone/{id}/{active|inactive}
  int firstSlash = uri.indexOf('/', 6);
  if (!uri.startsWith("/zone/") || firstSlash < 0) {
    sendJson(404, "{\"success\":false,\"error\":\"route not found\"}");
    return;
  }

  int zoneId = uri.substring(6, firstSlash).toInt();
  String operation = uri.substring(firstSlash + 1);
  if (zoneId < 1) {
    sendJson(400, "{\"success\":false,\"error\":\"invalid zone id\"}");
    return;
  }
  commandZone(zoneId - 1, operation);
}

void handleNotFound() {
  if (server.uri().startsWith("/relay/")) {
    handleRelayRoute();
    return;
  }
  if (server.uri().startsWith("/zone/")) {
    handleZoneRoute();
    return;
  }
  sendJson(404, "{\"success\":false,\"error\":\"route not found\"}");
}

void allRelays(bool on) {
  if (emergencyStopped && on) { sendJson(423, "{\"success\":false,\"error\":\"emergency stop active\"}"); return; }
  for (uint8_t i = 0; i < RELAY_COUNT; i++) writeRelay(i, on);
  sendJson(200, "{\"success\":true,\"state\":\"" + String(on ? "on" : "off") + "\",\"device\":\"" + DEVICE_NAME + "\"}");
}

void setupRoutes() {
  const char* headers[] = {"X-Command-ID"};
  server.collectHeaders(headers, 1);
  server.on("/health", HTTP_GET, []() {
    sendJson(200, "{\"success\":true,\"device\":\"" + String(DEVICE_NAME) + "\",\"wifi_rssi\":" + String(WiFi.RSSI()) + ",\"emergency\":" + String(emergencyStopped ? "true" : "false") + "}");
  });
  server.on("/relays", HTTP_GET, []() {
    String body = "{\"success\":true,\"relays\":[";
    for (uint8_t i = 0; i < RELAY_COUNT; i++) { if (i) body += ','; body += "{\"id\":" + String(i + 1) + ",\"gpio_pin\":" + String(RELAY_PINS[i]) + ",\"state\":\"" + String(relayStates[i] ? "on" : "off") + "\"}"; }
    sendJson(200, body + "]}");
  });
  server.on("/zones", HTTP_GET, []() {
    String body = "{\"success\":true,\"zones\":[";
    for (uint8_t i = 0; i < ZONE_COUNT; i++) {
      if (i) body += ',';
      uint8_t relayIndex = ZONE_RELAY_MAP[i];
      body += "{\"id\":" + String(i + 1) +
              ",\"active\":" + String(relayStates[relayIndex] ? "true" : "false") +
              ",\"relay_id\":" + String(relayIndex + 1) +
              ",\"gpio_pin\":" + String(RELAY_PINS[relayIndex]) + "}";
    }
    sendJson(200, body + "]}");
  });
  server.on("/relays/all-off", HTTP_POST, []() { allRelays(false); });
  server.on("/relays/all-on", HTTP_POST, []() { allRelays(true); });
  server.on("/emergency-stop", HTTP_POST, []() { emergencyStopped = true; setSafeState(); preferences.putBool("emergency", true); sendJson(200, "{\"success\":true,\"emergency\":true}"); });
  server.on("/emergency-reset", HTTP_POST, []() { emergencyStopped = false; preferences.putBool("emergency", false); sendJson(200, "{\"success\":true,\"emergency\":false}"); });
  server.onNotFound(handleNotFound);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(DEVICE_NAME);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  for (uint8_t i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) { delay(500); Serial.print('.'); }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) Serial.println("IP: " + WiFi.localIP().toString());
  else Serial.println("Wi-Fi unavailable; relays remain safe OFF");
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < RELAY_COUNT; i++) {
    // Preload the OFF level before enabling output to avoid a boot pulse.
    digitalWrite(RELAY_PINS[i], RELAY_ACTIVE_LOW ? HIGH : LOW);
    pinMode(RELAY_PINS[i], OUTPUT);
    Serial.printf("Relay %u configured on GPIO %u (%s)\n", i + 1, RELAY_PINS[i], RELAY_ACTIVE_LOW ? "active-LOW" : "active-HIGH");
  }
  setSafeState();
  preferences.begin("Visualec", false);
  emergencyStopped = preferences.getBool("emergency", false);
  connectWifi();
  setupRoutes();
  server.begin();
  Serial.println("Visualec ESP32 REST server ready");
}

void loop() {
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiAttempt >= WIFI_RETRY_MS) {
    lastWifiAttempt = millis();
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
  delay(2);
}

