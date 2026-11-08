# Encoder_Test

Isolated KY-040 test for UNO Q: CLK D2, DT D3, SW D4, 3.3V and GND.
RFID, PIR and DHT11 wiring can stay connected; this sketch does not read them.
Only one App Lab MCU sketch can run at a time. Restore RFID_Test when this test
is finished; its saved files are not changed by this package.

The MCU polls the quadrature signals and debounces the button. After each short
movement burst, it reports signed quarter-step counts and the actual pin levels.
A status event every three seconds verifies that telemetry is reaching Python;
it does not establish that the knob or button works.

Test one clockwise click, then one counterclockwise click, then press/release the
knob. Count and direction depend on the encoder's detent pattern and must be
calibrated from real events before mapping them to dashboard modes.

Python writes actual callbacks to `test_events.jsonl` in the App Lab app folder.
Successful compilation/startup alone is not a successful hardware test.

## Observed input test — November 7, 2026 (America/Chicago)

Physical rotation produced changes in both directions. The user confirmed that
one clockwise click decreases `quarter_total` by 4, and one counterclockwise
click increases it by 4. Serial Monitor also recorded button pressed/released
events. Two invalid transitions appeared in the log and were ignored by the
decoder; this test establishes basic input operation, not accuracy at every
turning speed. See `calibration.json`. Mapping completed clicks to the mirror's
mode controls remains a separate integration step. The original timestamped
event log remains local; running this app creates a new local log.
