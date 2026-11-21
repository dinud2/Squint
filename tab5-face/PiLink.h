// PiLink: Wi-Fi link from the Tab5 to the Squint service on the Pi (docs/tab5-pi.md).
//
// A background task joins Wi-Fi and long-polls  GET http://<pi>:8081/tab5/commands?after=<seq>&wait=20
// Lines are handed to the UI loop through a queue: call piLink::poll(handleCommand) from loop(),
// so the face/text code only ever runs on the loop task.
//
// Wi-Fi name/password and the Pi address live in secrets.h (git-ignored), see secrets.example.h.
#pragma once

#if defined(ARDUINO)
#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "No secrets.h: copy secrets.example.h to secrets.h. PiLink is disabled."
#define SQUINT_NO_SECRETS 1
#endif

namespace piLink {

// The Tab5's Wi-Fi is the ESP32-C6 on SDIO (ESP-Hosted); these are its pins on the Tab5.
constexpr int kSdioClk = 12, kSdioCmd = 13, kSdioD0 = 11, kSdioD1 = 10, kSdioD2 = 9, kSdioD3 = 8, kC6Reset = 15;
constexpr size_t kLineLen = 192;

inline QueueHandle_t& queue() {
  static QueueHandle_t q = nullptr;
  return q;
}
inline volatile bool& online() {
  static volatile bool v = false;
  return v;
}

// Pull the "lines" array out of {"seq": 12, "lines": ["a", "b|c"]} without a JSON library.
// Lines never contain quotes or backslashes (the Pi only sends names, words and '|').
inline long parse(const String& body, long seq) {
  int s = body.indexOf("\"seq\"");
  if (s >= 0) seq = body.substring(body.indexOf(':', s) + 1).toInt();
  int a = body.indexOf('[', body.indexOf("\"lines\""));
  int end = body.indexOf(']', a);
  for (int i = a; a >= 0 && i < end;) {
    int q1 = body.indexOf('"', i);
    if (q1 < 0 || q1 > end) break;
    int q2 = body.indexOf('"', q1 + 1);
    if (q2 < 0) break;
    char line[kLineLen];
    String v = body.substring(q1 + 1, q2);
    strncpy(line, v.c_str(), kLineLen - 1);
    line[kLineLen - 1] = '\0';
    xQueueSend(queue(), line, 0);
    i = q2 + 1;
  }
  return seq;
}

// A line for the UI that comes from the Tab5 itself, not the Pi ("offline ..." / "online").
inline void local(const char* text) {
  char line[kLineLen];
  strncpy(line, text, kLineLen - 1);
  line[kLineLen - 1] = '\0';
  xQueueSend(queue(), line, 0);
}

// Say on screen why nothing is happening, instead of sleeping forever: after 15 s without
// Wi-Fi, or 3 failed requests to the Pi in a row. Cleared by the next good answer.
constexpr uint32_t kNoWifiMs = 15000;
constexpr int kFailsBeforeShowing = 3;

inline void task(void*) {
#ifndef SQUINT_NO_SECRETS
  bool shownOffline = false;
  int fails = 0;
  uint32_t wifiLostMs = millis();
  WiFi.setPins(kSdioClk, kSdioCmd, kSdioD0, kSdioD1, kSdioD2, kSdioD3, kC6Reset);
  WiFi.mode(WIFI_STA);
  vTaskDelay(pdMS_TO_TICKS(1500));  // let USB serial attach so the scan below is visible
  int n = WiFi.scanNetworks();
  Serial.printf("[pilink] scan: %d networks\n", n);
  for (int i = 0; i < n && i < 12; ++i)
    Serial.printf("[pilink]   %-32s %4d dBm%s\n", WiFi.SSID(i).c_str(), WiFi.RSSI(i),
                  WiFi.SSID(i) == SQUINT_WIFI_SSID ? "   <- ours" : "");
  WiFi.begin(SQUINT_WIFI_SSID, SQUINT_WIFI_PASS);
  long seq = -1;  // -1: first call only learns the current seq, so old lines are not replayed
  uint32_t lastReport = 0;
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      if (online()) wifiLostMs = millis();
      online() = false;
      if (!shownOffline && millis() - wifiLostMs > kNoWifiMs) {
        local("offline No Wi-Fi|Looking for " SQUINT_WIFI_SSID);
        shownOffline = true;
      }
      if (millis() - lastReport > 5000) {
        lastReport = millis();
        Serial.printf("[pilink] waiting for wifi \"%s\", status %d\n", SQUINT_WIFI_SSID, (int)WiFi.status());
      }
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }
    if (!online()) Serial.printf("[pilink] wifi ok, ip %s\n", WiFi.localIP().toString().c_str());
    online() = true;
    HTTPClient http;
    String url = String("http://") + SQUINT_PI_HOST + ":8081/tab5/commands?after=" + (seq < 0 ? 0 : seq) +
                 (seq < 0 ? "&wait=0" : "&wait=20");
    http.begin(url);
    http.setTimeout(25000);
    int code = http.GET();
    if (code == 200) {
      fails = 0;
      if (shownOffline) {
        local("online");
        shownOffline = false;
      }
      String body = http.getString();
      if (seq < 0) {
        int s = body.indexOf("\"seq\"");
        seq = s >= 0 ? body.substring(body.indexOf(':', s) + 1).toInt() : 0;
      } else {
        int s = body.indexOf("\"seq\"");
        long theirs = s >= 0 ? body.substring(body.indexOf(':', s) + 1).toInt() : seq;
        if (theirs < seq) {
          // The Pi service restarted (its count starts again at 0): fetch everything since then.
          Serial.printf("[pilink] pi restarted (seq %ld -> %ld)\n", seq, theirs);
          seq = 0;
          http.end();
          continue;
        }
        seq = parse(body, seq);
      }
    } else {
      Serial.printf("[pilink] GET failed: %d\n", code);
      if (++fails >= kFailsBeforeShowing && !shownOffline) {
        local("offline Can't reach Squint|Pi " SQUINT_PI_HOST ":8081 (secrets.h)");
        shownOffline = true;
      }
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
    http.end();
  }
#else
  vTaskDelete(nullptr);
#endif
}

// Call once from setup().
inline void begin() {
  queue() = xQueueCreate(16, kLineLen);
  xTaskCreatePinnedToCore(task, "pilink", 8192, nullptr, 1, nullptr, 0);
}

// Call from loop(): runs every line that arrived since the last call.
template <typename Fn>
inline void poll(Fn handle) {
  char line[kLineLen];
  while (queue() && xQueueReceive(queue(), line, 0) == pdTRUE) {
    Serial.printf("[pilink] %s\n", line);
    handle(line);
  }
}

}  // namespace piLink
#endif
