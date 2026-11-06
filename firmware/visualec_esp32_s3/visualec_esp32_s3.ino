#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>

// -------- User-configurable hardware and network settings --------
// Fallback credentials used only if nothing is stored in flash memory
const char* DEFAULT_WIFI_SSID = "Xx";
const char* DEFAULT_WIFI_PASSWORD = "sarvesh@2643";
const char* DEVICE_NAME = "visualec-esp32";
constexpr bool RELAY_ACTIVE_LOW = true;
constexpr uint8_t RELAY_COUNT = 3;
// Must match the physical wiring and backend relay table.
// Relay 1 -> GPIO 4, Relay 2 -> GPIO 5, Relay 3 -> GPIO 18.
const uint8_t RELAY_PINS[RELAY_COUNT] = {4, 5, 18};
constexpr uint8_t ZONE_COUNT = 3;
// Values are zero-based relay indexes: Zone 1 -> Relay 1, etc.
const uint8_t ZONE_RELAY_MAP[ZONE_COUNT] = {0, 1, 2};
constexpr unsigned long WIFI_RETRY_MS = 5000;
constexpr uint8_t BOOT_PIN = 0; // ESP32-S3 BOOT button for forced setup mode
// -----------------------------------------------------------------

WebServer server(80);
Preferences preferences;
bool inPortalMode = false;
String activeSsid = "";
String activePassword = "";
bool relayStates[RELAY_COUNT] = {false, false, false};
bool emergencyStopped = false;
unsigned long lastWifiAttempt = 0;
String lastCommandId = "";
String lastCommandResponse = "";

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

int skipJsonWhitespace(const String& json, int position) {
  while (position < json.length()) {
    char value = json[position];
    if (value != ' ' && value != '\t' && value != '\r' && value != '\n') break;
    position++;
  }
  return position;
}

bool jsonStringField(const String& json, const char* field, String& value) {
  String key = String("\"") + field + "\"";
  int position = json.indexOf(key);
  if (position < 0) return false;
  position = json.indexOf(':', position + key.length());
  if (position < 0) return false;
  position = skipJsonWhitespace(json, position + 1);
  if (position >= json.length() || json[position] != '"') return false;
  int end = json.indexOf('"', position + 1);
  if (end < 0) return false;
  value = json.substring(position + 1, end);
  return true;
}

bool jsonIntField(const String& json, const char* field, int& value) {
  String key = String("\"") + field + "\"";
  int position = json.indexOf(key);
  if (position < 0) return false;
  position = json.indexOf(':', position + key.length());
  if (position < 0) return false;
  position = skipJsonWhitespace(json, position + 1);
  int end = position;
  if (end < json.length() && json[end] == '-') end++;
  while (end < json.length() && json[end] >= '0' && json[end] <= '9') end++;
  if (end == position || (end == position + 1 && json[position] == '-')) return false;
  value = json.substring(position, end).toInt();
  return true;
}

String relayJson(uint8_t index, bool success = true) {
  bool outputHigh = RELAY_ACTIVE_LOW ? !relayStates[index] : relayStates[index];
  return "{\"success\":" + String(success ? "true" : "false") +
         ",\"relay_id\":" + String(index + 1) +
         ",\"gpio_pin\":" + String(RELAY_PINS[index]) +
         ",\"gpio_level\":\"" + String(outputHigh ? "HIGH" : "LOW") +
         "\",\"state\":\"" + String(relayStates[index] ? "on" : "off") +
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

void handleControlPacket() {
  if (server.method() == HTTP_OPTIONS) {
    addCors();
    server.send(204);
    return;
  }
  if (server.method() != HTTP_POST) {
    sendJson(405, "{\"success\":false,\"error\":\"method not allowed\"}");
    return;
  }

  String body = server.arg("plain");
  if (body.length() == 0 || body.length() > 2048) {
    sendJson(400, "{\"success\":false,\"error\":\"JSON body is required and must be at most 2048 bytes\"}");
    return;
  }

  int relayId = 0;
  String requestedState;
  if (!jsonIntField(body, "relay_id", relayId) || relayId < 1 || relayId > RELAY_COUNT) {
    sendJson(400, "{\"success\":false,\"error\":\"valid relay_id is required\"}");
    return;
  }
  if (!jsonStringField(body, "state", requestedState) || (requestedState != "on" && requestedState != "off")) {
    sendJson(400, "{\"success\":false,\"error\":\"state must be on or off\"}");
    return;
  }

  String commandId = server.header("X-Command-ID");
  if (commandId.length() == 0) jsonStringField(body, "command_id", commandId);
  if (commandId.length() > 0 && commandId == lastCommandId && lastCommandResponse.length() > 0) {
    sendJson(200, lastCommandResponse);
    return;
  }

  bool desired = requestedState == "on";
  if (emergencyStopped && desired) {
    sendJson(423, "{\"success\":false,\"error\":\"emergency stop active\"}");
    return;
  }

  uint8_t relayIndex = relayId - 1;
  writeRelay(relayIndex, desired);
  lastCommandId = commandId;
  lastCommandResponse = relayJson(relayIndex);

  int zoneId = 0;
  jsonIntField(body, "zone_id", zoneId);
  Serial.printf(
    "Control packet: command=%s zone=%d relay=%d state=%s GPIO=%u level=%s\n",
    commandId.c_str(), zoneId, relayId, requestedState.c_str(), RELAY_PINS[relayIndex],
    (RELAY_ACTIVE_LOW ? !desired : desired) ? "HIGH" : "LOW"
  );
  sendJson(200, lastCommandResponse);
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
  server.on("/control", HTTP_POST, handleControlPacket);
  server.on("/control", HTTP_OPTIONS, handleControlPacket);
  server.on("/relays/all-off", HTTP_POST, []() { allRelays(false); });
  server.on("/relays/all-on", HTTP_POST, []() { allRelays(true); });
  server.on("/emergency-stop", HTTP_POST, []() { emergencyStopped = true; setSafeState(); preferences.putBool("emergency", true); sendJson(200, "{\"success\":true,\"emergency\":true}"); });
  server.on("/emergency-reset", HTTP_POST, []() { emergencyStopped = false; preferences.putBool("emergency", false); sendJson(200, "{\"success\":true,\"emergency\":false}"); });
  server.onNotFound(handleNotFound);
}

void handlePortalRoot() {
  String page = "<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Visualec Setup</title>"
    "<style>* { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, sans-serif; } "
    "body { background: #0b0f19; color: #f3f4f6; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; } "
    ".card { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 28px; width: 100%; max-width: 420px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); } "
    ".hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #1f2937; padding-bottom: 14px; } "
    ".title { font-size: 20px; font-weight: 700; color: #60a5fa; } "
    ".badge { background: #1e3a5f; color: #93c5fd; font-size: 11px; padding: 4px 8px; border-radius: 9999px; font-weight: 600; text-transform: uppercase; } "
    ".desc { font-size: 13px; color: #9ca3af; margin-bottom: 20px; line-height: 1.5; } "
    ".field { margin-bottom: 16px; } "
    "label { display: block; font-size: 12px; font-weight: 600; color: #d1d5db; margin-bottom: 6px; text-transform: uppercase; } "
    "input { width: 100%; padding: 10px 12px; background: #1f2937; border: 1px solid #374151; border-radius: 8px; color: #fff; font-size: 14px; outline: none; } "
    ".btn { width: 100%; padding: 12px; background: #2563eb; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 8px; } "
    ".footer { margin-top: 20px; font-size: 11px; color: #6b7280; text-align: center; }</style></head><body>"
    "<div class='card'>"
    "<div class='hdr'><div class='title'>Visualec S3</div><span class='badge'>Wi-Fi Setup</span></div>"
    "<p class='desc'>Configure local 2.4 GHz Wi-Fi credentials for the Visualec relay controller.</p>"
    "<form action='/save' method='POST'>"
    "<div class='field'><label>Wi-Fi SSID</label><input type='text' name='ssid' required autofocus value='" + activeSsid + "'></div>"
    "<div class='field'><label>Password</label><input type='password' name='password' value='" + activePassword + "'></div>"
    "<button type='submit' class='btn'>Save & Connect</button>"
    "</form><div class='footer'>Setup Hotspot: <strong>Visualec-Setup</strong> (192.168.4.1)</div>"
    "</div></body></html>";
  server.send(200, "text/html", page);
}

void handlePortalSave() {
  if (server.method() != HTTP_POST) { server.send(405, "text/plain", "Method Not Allowed"); return; }
  String ssid = server.arg("ssid");
  String pass = server.arg("password");
  if (ssid.length() == 0) { server.send(400, "text/plain", "SSID cannot be empty"); return; }

  preferences.putString("wifi_ssid", ssid);
  preferences.putString("wifi_pass", pass);

  String savedPage = "<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'>"
    "<style>body { background:#0b0f19; color:#f3f4f6; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; } "
    ".card { background:#111827; border:1px solid #1f2937; border-radius:14px; padding:32px; text-align:center; max-width:380px; } "
    "h2 { color:#10b981; margin-top:0; } p { color:#9ca3af; font-size:14px; }</style></head><body>"
    "<div class='card'><h2>✓ Wi-Fi Saved</h2><p>Rebooting now to connect to <strong>" + ssid + "</strong>.<br>The setup hotspot is shutting down.</p></div>"
    "</body></html>";
  server.send(200, "text/html", savedPage);
  delay(1500);
  ESP.restart();
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
  activeSsid = preferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
  activePassword = preferences.getString("wifi_pass", DEFAULT_WIFI_PASSWORD);

  // Dual AP+STA mode: broadcast setup portal AND connect to configured Wi-Fi network concurrently
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP("Visualec-Setup");
  WiFi.setHostname(DEVICE_NAME);
  WiFi.begin(activeSsid.c_str(), activePassword.c_str());

  Serial.println("\n==================================================");
  Serial.println("Visualec Wi-Fi Mode: Concurrent AP + STA");
  Serial.println("Connecting Station to: '" + activeSsid + "'");
  Serial.println("Setup Hotspot Active: 'Visualec-Setup' (http://192.168.4.1/)");
  Serial.println("==================================================\n");

  // Register setup web portal routes
  server.on("/", HTTP_GET, handlePortalRoot);
  server.on("/save", HTTP_POST, handlePortalSave);
  server.on("/generate_204", HTTP_GET, []() { server.sendHeader("Location", "http://192.168.4.1/"); server.send(302); });
  server.on("/hotspot-detect.html", HTTP_GET, []() { server.sendHeader("Location", "http://192.168.4.1/"); server.send(302); });

  // Register REST API routes
  setupRoutes();
  server.begin();
  Serial.println("Visualec REST and Web Server ready on port 80");
}

void loop() {
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiAttempt >= WIFI_RETRY_MS) {
    lastWifiAttempt = millis();
    WiFi.disconnect();
    WiFi.begin(activeSsid.c_str(), activePassword.c_str());
  }
  delay(2);
}
