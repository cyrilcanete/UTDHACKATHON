#include <Arduino_RouterBridge.h>

constexpr uint8_t PIR_PIN = 6;
constexpr unsigned long WARMUP_MS = 60000;
int previousMotion = LOW;
unsigned long startedAt = 0;
unsigned long lastStatusAt = 0;

void report(int changed) {
  const unsigned long elapsed = millis() - startedAt;
  const int motion = digitalRead(PIR_PIN);
  Monitor.print(changed ? "PIR change" : "PIR status");
  Monitor.print(" | motion=");
  Monitor.print(motion == HIGH ? "detected" : "clear");
  Monitor.print(" | uptime_s=");
  Monitor.print(elapsed / 1000);
  Monitor.print(" | phase=");
  Monitor.println(elapsed < WARMUP_MS ? "warming_up" : "ready_for_test");
  Bridge.notify("on_pir_test", motion, static_cast<int>(elapsed), changed);
}

void setup() {
  Bridge.begin();
  Monitor.begin();
  pinMode(PIR_PIN, INPUT);
  previousMotion = digitalRead(PIR_PIN);
  startedAt = millis();
  Monitor.println("PIR_Test: OUT=D6; HC-SR501 supply=5V; shared GND.");
  Monitor.println("Allow 60 seconds before testing. Other modules are not read by this sketch.");
}

void loop() {
  const unsigned long now = millis();
  const int motion = digitalRead(PIR_PIN);
  if (motion != previousMotion) {
    previousMotion = motion;
    report(1);
  }
  if (now - lastStatusAt >= 3000) {
    lastStatusAt = now;
    report(0);
  }
  delay(50);
}
