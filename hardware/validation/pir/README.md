# PIR_Test

Isolated HC-SR501 input test for Arduino UNO Q. Wiring from the setup guide:
OUT to D6, VCC to 5V, GND to the shared ground. No wiring changes are needed to
run the test. Do not move power wires while the board is powered.

The sketch reads D6 and reports changes and a status every three seconds. Wait
at least 60 seconds after startup before evaluating it. Then first establish a
clear/no-motion state, move across the sensor's view, and wait for it to clear.
The module's delay adjustment and retrigger setting determine how long HIGH
remains asserted; it need not fall immediately when movement stops.

Actual MCU callbacks are logged to `test_events.jsonl`. Compilation, startup and
heartbeat reports alone do not verify motion detection. This app temporarily
uses the microcontroller instead of Encoder_Test/RFID_Test. Their saved apps and
the mirror dashboard are not edited by the test.

## Observed basic test — November 8, 2026 (America/Chicago)

After warm-up, the recorded input stayed LOW during a quiet interval. Following
the user's motion test, D6 reported HIGH and then LOW again. The user confirmed
motion detection and clarified that they were still in the field of view during
repeated triggers. Basic sensor input passed. Dashboard sleep/wake integration
has not yet been tested. See the committed `result.json` summary. The original
timestamped event log remains local; running this app creates a new local log.
