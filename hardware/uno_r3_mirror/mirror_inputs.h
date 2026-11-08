#pragma once
#include <DHT.h>
// Reference wiring only: match these constants to your already-tested wiring.
constexpr byte ENCODER_CLK = 2, ENCODER_DT = 3, ENCODER_SW = 6;
constexpr byte DHT_PIN = 4, PIR_PIN = 7;
constexpr bool REVERSE_ENCODER = false; // Flip only if physical right reports +1.
DHT mirrorDht(DHT_PIN, DHT11);
uint8_t encoderPrevious;
int8_t encoderSteps = 0;
bool buttonRaw = HIGH, buttonStable = HIGH;
unsigned long buttonChanged = 0, sensorsAt = 0;
void emitEncoder(int delta);
void emitPress();
void emitSensors(float temperature, float humidity, bool motion);
void setupMirrorInputs() {
  pinMode(ENCODER_CLK, INPUT_PULLUP); pinMode(ENCODER_DT, INPUT_PULLUP);
  pinMode(ENCODER_SW, INPUT_PULLUP); pinMode(PIR_PIN, INPUT);
  mirrorDht.begin();
  encoderPrevious = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
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
  bool raw = digitalRead(ENCODER_SW);
  if (raw != buttonRaw) { buttonRaw = raw; buttonChanged = now; }
  if (now - buttonChanged >= 40 && buttonStable != buttonRaw) {
    buttonStable = buttonRaw;
    if (buttonStable == LOW) emitPress();
  }
  // DHT11 should not be sampled on every loop.
  if (now - sensorsAt >= 2200) {
    sensorsAt = now;
    float temperature = mirrorDht.readTemperature();
    float humidity = mirrorDht.readHumidity();
    emitSensors(temperature, humidity, digitalRead(PIR_PIN) == HIGH);
  }
}
