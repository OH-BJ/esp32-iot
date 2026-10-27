/*
 * Seeed XIAO ESP32S3 - 클라우드 IoT 클라이언트
 *  - 2초마다 센서값을 HTTPS POST로 백엔드(Render)에 전송
 *  - 응답으로 받은 LED 상태를 내장 LED(GPIO21)에 반영
 *  - 서버를 거치므로 PC/폰과 같은 WiFi가 아니어도 제어 가능
 *
 * 보드: "XIAO_ESP32S3" (esp32 by Espressif 보드 패키지)
 * 라이브러리: ArduinoJson (Benoit Blanchon) v7
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===== 사용자 설정 =====
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* API_BASE      = "https://esp32-iot-api-bici.onrender.com";  // Render 배포 주소
const char* DEVICE_KEY    = "YOUR_DEVICE_KEY";                      // 백엔드 DEVICE_API_KEY 와 동일
const char* DEVICE_ID     = "xiao-s3-01";
const unsigned long INTERVAL_MS = 2000;
// ======================

const int LED_PIN    = 21;   // XIAO ESP32S3 내장 주황 LED (LOW = 켜짐)
const int ANALOG_PIN = A0;   // GPIO1 - 가변저항/조도센서 등 연결

WiFiClientSecure client;
unsigned long lastSend = 0;

void setLed(bool on) {
  digitalWrite(LED_PIN, on ? LOW : HIGH);  // active-low
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("WiFi 연결 중: %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\n연결됨: " + WiFi.localIP().toString() : "\n연결 실패");
}

void sendData() {
  float temp  = temperatureRead();       // ESP32S3 칩 내부 온도
  int analog  = analogRead(ANALOG_PIN);  // 0~4095
  int rssi    = WiFi.RSSI();

  JsonDocument doc;
  doc["device_id"]   = DEVICE_ID;
  doc["temperature"] = temp;
  doc["analog"]      = analog;
  doc["rssi"]        = rssi;
  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.setTimeout(15000);
  http.begin(client, String(API_BASE) + "/api/device/data");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);

  if (code == 200) {
    JsonDocument res;
    if (!deserializeJson(res, http.getString())) {
      bool led = res["led"] | false;
      setLed(led);
      Serial.printf("[OK] temp=%.1f analog=%d rssi=%d -> LED %s\n", temp, analog, rssi, led ? "ON" : "OFF");
    }
  } else {
    Serial.printf("[ERR] HTTP %d %s\n", code, http.errorToString(code).c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  setLed(false);
  analogReadResolution(12);
  client.setInsecure();  // 테스트용: 인증서 검증 생략 (HTTPS 암호화는 유지)
  connectWiFi();
}

void loop() {
  connectWiFi();
  if (WiFi.status() == WL_CONNECTED && millis() - lastSend >= INTERVAL_MS) {
    lastSend = millis();
    sendData();
  }
}
