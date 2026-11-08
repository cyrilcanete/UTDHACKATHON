// Optional Uno R3 reference sketch. Match pins to your wiring before uploading.
#include <SPI.h>
#include <MFRC522.h>
#include "mirror_inputs.h"
MFRC522 reader(10, 5);
void emitEncoder(int delta) {
  Serial.print(F("{\"type\":\"encoder\",\"delta\":")); Serial.print(delta); Serial.println('}');
}
void emitAnalyze() { Serial.println(F("{\"type\":\"encoder\",\"action\":\"analyze\"}")); }
void emitPress() { Serial.println(F("{\"type\":\"encoder\",\"action\":\"press\"}")); }
void emitSensors(float temperature, float humidity, bool motion) {
  Serial.print(F("{\"type\":\"sensors\",\"temperature_c\":"));
  if (isnan(temperature)) Serial.print(F("null")); else Serial.print(temperature,1);
  Serial.print(F(",\"humidity_pct\":"));
  if (isnan(humidity)) Serial.print(F("null")); else Serial.print(humidity,1);
  Serial.print(F(",\"motion\":")); Serial.print(motion ? F("true") : F("false")); Serial.println('}');
}
void setup() {
  Serial.begin(9600); setupMirrorInputs(); SPI.begin(); reader.PCD_Init();
}
void loop() {
  pollMirrorInputs();
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) return;
  Serial.print(F("{\"type\":\"rfid\",\"uid\":\""));
  for (byte i=0; i<reader.uid.size; ++i) {
    if (reader.uid.uidByte[i] < 16) Serial.print('0');
    Serial.print(reader.uid.uidByte[i], HEX);
  }
  Serial.println(F("\"}")); reader.PICC_HaltA(); reader.PCD_StopCrypto1();
}
