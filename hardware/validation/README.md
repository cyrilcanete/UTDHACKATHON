# UNO Q hardware validation apps

These are the project's isolated Arduino App Lab tests for the Arduino UNO Q.
Each folder contains a separate MCU sketch, App Lab manifest and Python listener.
They are useful for checking wiring and recording actual input before connecting
a device to the dashboard. They do not feed the dashboard or configure its modes.

| Module | Recorded basic result | Not established by this isolated record |
| --- | --- | --- |
| [DHT11](dht11/) | November 8, 2026: 432 valid readings, 0 failed reads; temperature 20.2–30.9 °C, humidity 37.3–92.0%. | Accuracy against a calibrated reference; live dashboard integration. |
| [HC-SR501 PIR](pir/) | November 8, 2026: quiet LOW input, then HIGH and LOW after a physical motion test; user confirmed detection. | Dashboard sleep/wake integration. |
| [KY-040 encoder](encoder/) | November 7, 2026: rotation in both directions and button press/release observed; clockwise −4 and counterclockwise +4 quarter steps per click. | Dashboard mode integration and operation at other turning speeds. |
| [RC522 RFID diagnostic](rfid/) | Diagnostic source retained; an earlier November 7 attempt reported failed communication. Later dashboard integration source is provided separately. | This diagnostic package contains no current successful two-card or end-to-end dashboard test record. |

Dates above use America/Chicago. The JSON result/calibration files are concise
records of the original observed tests, not fresh tests performed while packaging
this submission. Later verification of the integrated mirror is described in the
[main README](../../README.md); it does not change these historical records.
Raw timestamped event logs remain local and are not included.
Successful compilation or an app heartbeat alone does not establish working input.

## Run an isolated test

Open or import the chosen folder as an Arduino App Lab app and select the UNO Q.
Preserve the installed board platform; the sketches request `arduino:zephyr` and
use its Arduino RouterBridge support. The DHT11 and RFID profiles list their
additional libraries. Read that app's README for its pin assignments and test
procedure. Disconnect power before changing wiring.

Only one App Lab MCU sketch can run at a time. Stop the current hardware app
before running a diagnostic, then restore the intended integration app afterward.
These tests do not combine all four devices into one running sketch. DHT11, PIR
and encoder listeners create `test_events.jsonl` beside their app manifest when
run; keep those new local logs out of a public submission.

For dashboard RFID forwarding, use the integration callback and setup instructions
under [`../uno_q_rfid/`](../uno_q_rfid/) and the repository's main README. The RFID
diagnostic here uses temporary scan-order labels and must not replace that
integration callback.
