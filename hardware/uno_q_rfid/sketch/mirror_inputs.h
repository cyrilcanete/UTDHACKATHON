#pragma once
#include <DHT.h>
#include <stdint.h>
// Smart Mirror wiring plan: encoder D2/D3/D4, DHT11 D7, PIR D6.
constexpr byte ENCODER_CLK = 2, ENCODER_DT = 3, ENCODER_SW = 4;
constexpr byte DHT_PIN = 7, PIR_PIN = 6;
constexpr bool REVERSE_ENCODER = false; // Flip only if physical right reports +1.
DHT mirrorDht(DHT_PIN, DHT11);
uint8_t encoderPrevious;
int8_t encoderSteps = 0;
bool buttonRaw = HIGH, buttonStable = HIGH;
bool buttonReady = false, buttonActive = false, buttonLongSent = false;
bool buttonReleasePending = false;
constexpr uint32_t BUTTON_DEBOUNCE_MS = 40, BUTTON_HOLD_MS = 1000;
uint32_t buttonChanged = 0, buttonPressedAt = 0, buttonReleasedAt = 0;
unsigned long sensorsAt = 0;
void emitEncoder(int delta);
void emitAnalyze();
void emitPress();
void emitSensors(float temperature, float humidity, bool motion);

void pollMirrorButton(uint32_t now, bool raw) {
  if (raw != buttonRaw) {
    buttonRaw = raw; buttonChanged = now;
    if (raw == HIGH && buttonActive && !buttonReleasePending) {
      buttonReleasePending = true; buttonReleasedAt = now;
    }
  }
  // Unsigned 32-bit differences remain valid when Arduino millis() wraps.
  if (uint32_t(now - buttonChanged) < BUTTON_DEBOUNCE_MS) return;
  if (buttonStable != buttonRaw) {
    buttonStable = buttonRaw;
    if (buttonStable == LOW) {
      if (buttonReady) {
        buttonActive = true; buttonLongSent = false;
        buttonReleasePending = false; buttonPressedAt = buttonChanged;
      }
    } else {
      bool send = buttonActive && !buttonLongSent;
      uint32_t releasedAt = buttonReleasePending ? buttonReleasedAt : buttonChanged;
      bool held = uint32_t(releasedAt - buttonPressedAt) >= BUTTON_HOLD_MS;
      buttonActive = false; buttonReady = true; buttonReleasePending = false;
      // Release timing also handles a loop that was busy at the hold threshold.
      if (send) { if (held) emitPress(); else emitAnalyze(); }
    }
  }
  if (buttonActive && buttonRaw == LOW) {
    // A stable LOW cancels a release glitch. Until then, its first HIGH freezes
    // the hold duration so release bounce cannot turn a quick press into a hold.
    buttonReleasePending = false;
    if (!buttonLongSent && uint32_t(now - buttonPressedAt) >= BUTTON_HOLD_MS) {
      buttonLongSent = true; emitPress();
    }
  }
}

void setupMirrorInputs() {
  pinMode(ENCODER_CLK, INPUT_PULLUP); pinMode(ENCODER_DT, INPUT_PULLUP);
  pinMode(ENCODER_SW, INPUT_PULLUP); pinMode(PIR_PIN, INPUT);
  mirrorDht.begin();
  encoderPrevious = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
  buttonRaw = buttonStable = digitalRead(ENCODER_SW);
  buttonChanged = millis();
  // A button held during startup is ignored until a debounced release.
  buttonReady = buttonRaw == HIGH;
  buttonActive = buttonLongSent = buttonReleasePending = false;
}
void pollMirrorInputs() {
  // Full detents, not individual bouncing edges. Right must emit -1.
  static const int8_t transitions[16] = {0,-1,1,0, 1,0,0,-1, -1,0,0,1, 0,1,-1,0};
  uint8_t current = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
  if ((current ^ encoderPrevious) == 3) encoderSteps = 0;
  else encoderSteps += transitions[(encoderPrevious << 2) | current];
  encoderPrevious = current;
  if (encoderSteps >= 4 || encoderSteps <= -4) {
    int delta = encoderSteps > 0 ? 1 : -1;
    emitEncoder(REVERSE_ENCODER ? -delta : delta); encoderSteps = 0;
  }
  unsigned long now = millis();
  pollMirrorButton(uint32_t(now), digitalRead(ENCODER_SW));
  // DHT11 should not be sampled on every loop.
  if (now - sensorsAt >= 2200) {
    sensorsAt = now;
    float temperature = mirrorDht.readTemperature();
    float humidity = mirrorDht.readHumidity();
    emitSensors(temperature, humidity, digitalRead(PIR_PIN) == HIGH);
  }
}
