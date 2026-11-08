#include <Arduino_RouterBridge.h>
#include <SPI.h>
#include <MFRC522.h>
#include "mirror_inputs.h"

void emitEncoder(int delta) { Bridge.notify("on_mirror_encoder", delta); }
void emitPress() { Bridge.notify("on_mirror_press"); }
void emitSensors(float temperature, float humidity, bool motion) {
  Bridge.notify("on_mirror_sensors", isnan(temperature) ? -999.0f : temperature, isnan(humidity) ? -999.0f : humidity, motion);
}

// UNO Q hardware SPI: D13 SCK, D11 MOSI, D12 MISO.
// RC522 power: 3.3V and GND. IRQ is not connected.
constexpr byte RFID_SS_PIN = 10;
constexpr byte RFID_RST_PIN = 5;
MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);

bool readerResponding = false;
unsigned long lastStatusAt = 0;

void probeSlowSPI() {
  // Reassert software chip select after SPI.begin() configures UNO Q pins.
  pinMode(RFID_SS_PIN, OUTPUT);
  digitalWrite(RFID_SS_PIN, HIGH);
  pinMode(RFID_RST_PIN, OUTPUT);
  digitalWrite(RFID_RST_PIN, LOW);
  delay(2);
  digitalWrite(RFID_RST_PIN, HIGH);
  delay(50);
  Monitor.println("Diagnostic: five raw VersionReg reads at 1 MHz:");
  for (byte attempt = 0; attempt < 5; ++attempt) {
    byte frame[2] = {0xEE, 0x00};
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
    digitalWrite(RFID_SS_PIN, LOW);
    SPI.transfer(frame, sizeof(frame));
    digitalWrite(RFID_SS_PIN, HIGH);
    SPI.endTransaction();
    Monitor.print("Raw VersionReg: 0x");
    if (frame[1] < 0x10) Monitor.print('0');
    Monitor.println(frame[1], HEX);
    delay(100);
  }
}

void checkReader() {
  reader.PCD_Init();
  delay(50);
  const byte version = reader.PCD_ReadRegister(MFRC522::VersionReg);
  Monitor.print("RC522 VersionReg: 0x");
  if (version < 0x10) Monitor.print('0');
  Monitor.println(version, HEX);

  readerResponding = version != 0x00 && version != 0xFF;
  if (!readerResponding) {
    Monitor.println("ERROR: RC522 communication failed. Check reader power, wiring and SPI. Retrying in 5 seconds.");
    return;
  }
  if (version != 0x90 && version != 0x91 && version != 0x92 && version != 0x88) {
    Monitor.println("WARNING: Unrecognized version. This response alone does not confirm a working reader.");
  }
  Monitor.println("RC522 responded. Present one card at a time; remove it before scanning again.");
}

void setup() {
  Bridge.begin();
  Monitor.begin();
  Monitor.println("RFID_Test starting: SS=D10, RST=D5, SPI=D11/D12/D13.");
  setupMirrorInputs();
  SPI.begin();
  probeSlowSPI();
  checkReader();
  lastStatusAt = millis();
}

void loop() {
  pollMirrorInputs();
  const unsigned long now = millis();
  if (!readerResponding) {
    if (now - lastStatusAt >= 5000) {
      lastStatusAt = now;
      checkReader();
    }
    return;
  }

  if (now - lastStatusAt >= 15000) {
    lastStatusAt = now;
    Monitor.println("Waiting for a card. A UID line is required to confirm a successful card read.");
  }
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) {
    return;
  }

  // Supports 4-, 7- and 10-byte UIDs, preserving leading zeroes.
  const char hex[] = "0123456789ABCDEF";
  char uidText[30] = {};
  size_t position = 0;
  for (byte i = 0; i < reader.uid.size && i < 10; ++i) {
    if (i != 0) uidText[position++] = ' ';
    uidText[position++] = hex[reader.uid.uidByte[i] >> 4];
    uidText[position++] = hex[reader.uid.uidByte[i] & 0x0F];
  }
  uidText[position] = '\0';
  const MFRC522::PICC_Type cardType = reader.PICC_GetType(reader.uid.sak);
  Monitor.print("Card UID: ");
  Monitor.print(uidText);
  Monitor.print(" | bytes: ");
  Monitor.print(reader.uid.size);
  Monitor.print(" | type: ");
  Monitor.println(reader.PICC_GetTypeName(cardType));

  // Release the card before notifying Linux. No card memory is written.
  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  Bridge.notify("on_rfid_uid", String(uidText),
                static_cast<int>(reader.uid.size), static_cast<int>(cardType));
  lastStatusAt = millis();
}
