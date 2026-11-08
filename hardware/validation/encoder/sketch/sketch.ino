#include <Arduino_RouterBridge.h>

constexpr uint8_t CLK_PIN = 2;
constexpr uint8_t DT_PIN = 3;
constexpr uint8_t SW_PIN = 4;

// Valid quadrature transitions cancel contact bounce; direction is calibrated
// against one observed clockwise turn rather than assumed from module orientation.
const int8_t QUADRATURE[16] = {
   0, -1,  1,  0,
   1,  0,  0, -1,
  -1,  0,  0,  1,
   0,  1, -1,  0
};

uint8_t previousAB;
int quarterTotal = 0;
int invalidTransitions = 0;
bool movementPending = false;
unsigned long lastEdgeAt = 0;
unsigned long lastStatusAt = 0;
int lastRawButton = HIGH;
int stableButton = HIGH;
unsigned long buttonChangedAt = 0;

uint8_t readAB() {
  return (digitalRead(CLK_PIN) << 1) | digitalRead(DT_PIN);
}

void report(int kind) {
  const int ab = readAB();
  Monitor.print(kind == 1 ? "Encoder movement" : kind == 2 ? "Encoder button" : "Encoder status");
  Monitor.print(" | quarter_total=");
  Monitor.print(quarterTotal);
  Monitor.print(" | CLK=");
  Monitor.print((ab >> 1) & 1);
  Monitor.print(" | DT=");
  Monitor.print(ab & 1);
  Monitor.print(" | button=");
  Monitor.print(stableButton == LOW ? "pressed" : "released");
  Monitor.print(" | invalid=");
  Monitor.println(invalidTransitions);
  Bridge.notify("on_encoder_test", kind, quarterTotal, stableButton, ab, invalidTransitions);
}

void setup() {
  Bridge.begin();
  Monitor.begin();
  pinMode(CLK_PIN, INPUT_PULLUP);
  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SW_PIN, INPUT_PULLUP);
  previousAB = readAB();
  stableButton = lastRawButton = digitalRead(SW_PIN);
  Monitor.println("Encoder_Test: CLK=D2, DT=D3, SW=D4, power=3.3V.");
  Monitor.println("Waiting for physical rotation and button presses. Other modules are not read by this test.");
}

void loop() {
  const unsigned long now = millis();
  const uint8_t ab = readAB();
  if (ab != previousAB) {
    const int8_t change = QUADRATURE[(previousAB << 2) | ab];
    if (change == 0) ++invalidTransitions;
    quarterTotal += change;
    previousAB = ab;
    lastEdgeAt = now;
    movementPending = true;
  }

  const int rawButton = digitalRead(SW_PIN);
  if (rawButton != lastRawButton) {
    lastRawButton = rawButton;
    buttonChangedAt = now;
  }
  if (now - buttonChangedAt >= 30 && stableButton != rawButton) {
    stableButton = rawButton;
    report(2);
  }

  if (movementPending && now - lastEdgeAt >= 40) {
    movementPending = false;
    report(1);
  }
  if (now - lastStatusAt >= 3000) {
    lastStatusAt = now;
    report(0);
  }
  delay(1);
}
