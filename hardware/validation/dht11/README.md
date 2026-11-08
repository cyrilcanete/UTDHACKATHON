# DHT11_Test

Isolated test of the three-pin DHT11 module on Arduino UNO Q. The setup guide's
existing connections are S to D7, V to 3.3V and G to GND. This test changes no
wiring and reads no other sensor. Verify module voltage requirements before any
power changes; disconnect power before moving wires.

Adafruit's DHT sensor library is used for DHT11. The sketch samples every 2.5
seconds, exceeding the library's two-second minimum read interval. Failed reads
are reported explicitly, with null values in Python, rather than invented data.
MCU callbacks are saved to `test_events.jsonl` in the App Lab app folder.

Repeated actual values verify basic communication, not measurement accuracy
against a calibrated reference. Successful compilation/startup alone is not a
successful hardware test. The test temporarily uses the MCU while the RFID,
encoder and PIR apps remain saved.

Source: https://github.com/adafruit/DHT-sensor-library

The committed `result.json` summarizes the original basic read test. Raw
timestamped `test_events.jsonl` evidence remains local; running this app creates
a new local log. See [the validation overview](../README.md) for the recorded
result and integration limits.
