"""Record actual UNO Q encoder events. No dashboard or other sensor changes."""
import json
from datetime import datetime, timezone
from pathlib import Path

from arduino.app_utils import App, Bridge

LOG = Path(__file__).resolve().parents[1] / "test_events.jsonl"
last_movement_total = 0


def on_encoder_test(kind: int, quarter_total: int, button: int, ab: int, invalid: int):
    global last_movement_total
    names = {0: "encoder_status", 1: "encoder_movement", 2: "encoder_button"}
    if kind not in names:
        return
    delta = quarter_total - last_movement_total if kind == 1 else 0
    if kind == 1:
        last_movement_total = quarter_total
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": names[kind],
        "quarter_total": quarter_total,
        "delta_quarters": delta,
        "clk": (ab >> 1) & 1,
        "dt": ab & 1,
        "button": "pressed" if button == 0 else "released",
        "invalid_transitions": invalid,
    }
    text = json.dumps(event)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text, flush=True)


Bridge.provide("on_encoder_test", on_encoder_test)
print("Encoder_Test listener started. Awaiting physical encoder events.", flush=True)
App.run()
