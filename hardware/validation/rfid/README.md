# RC522 isolated RFID diagnostic

This Arduino UNO Q App Lab app reads card UIDs and reports them to its own Python
listener. The first two distinct UIDs receive temporary `profile_1` and
`profile_2` labels in scan order. Restarting clears those labels. A third UID is
reported with no test profile. It does not select dashboard profiles, write card
memory or change the dashboard configuration.

## Wiring and dependencies

| RC522 pin | UNO Q connection |
| --- | --- |
| SDA / SS | D10 |
| SCK | D13 |
| MOSI | D11 |
| MISO | D12 |
| RST | D5 |
| 3.3V | 3.3V |
| GND | GND |
| IRQ | Unconnected |

The RC522's SDA label is SPI chip select here. Disconnect board power before
changing wires. The sketch profile requests `arduino:zephyr` and MFRC522 1.4.12.
It uses Arduino_RouterBridge for Monitor and MCU-to-Python messages; Python uses
App Lab's provided `arduino.app_utils`, with no additional pip dependency.

## Test procedure

1. Stop the current App Lab MCU app, then run this separate `RFID_Test` app.
2. Inspect actual compile/upload results and Serial Monitor. A reported version
   of `0x00` or `0xFF` is a communication failure. A plausible version response
   alone is not a successful card read.
3. Present one card, remove it, then present a second card. Confirm each actual
   `Card UID:` line and matching Python `rfid_uid` event.
4. Restore the intended integration app after the diagnostic.

The Python callback validates 4-, 7- or 10-byte UID events and prints the temporary
label and card type. UIDs can be copied and are not secure login credentials.

## Historical result and integration boundary

An earlier November 7, 2026 (America/Chicago) run compiled and started, but
reported `RC522 VersionReg: 0x00`; the user reported the reader power LED was off.
No card UID was recorded in that diagnostic run. This source package does not
claim a successful new diagnostic or end-to-end hardware test.

The repository separately contains later dashboard integration code in
[`../../uno_q_rfid/`](../../uno_q_rfid/) and the dashboard's explicit card-to-person
configuration. Its MCU sketch and dependency profile match this diagnostic's
sketch, but its **Python callback is different**: it publishes scans to the
shared journal consumed by the dashboard. This diagnostic only prints events.
Use the repository's `setup_uno_q_rfid.py` procedure for that integration; do not
copy this diagnostic callback over the working integration listener.
