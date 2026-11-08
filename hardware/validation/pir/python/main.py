"""Record actual HC-SR501 D6 readings from the UNO Q microcontroller."""
import json
from datetime import datetime, timezone
from pathlib import Path

from arduino.app_utils import App, Bridge

LOG = Path(__file__).resolve().parents[1] / "test_events.jsonl"


def on_pir_test(motion: int, uptime_ms: int, changed: int):
    if motion not in (0, 1) or uptime_ms < 0:
        return
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": "pir_change" if changed else "pir_status",
        "motion": bool(motion),
        "uptime_s": uptime_ms // 1000,
        "warming_up": uptime_ms < 60000,
    }
    text = json.dumps(event)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text, flush=True)


Bridge.provide("on_pir_test", on_pir_test)
print("PIR_Test listener started. Wait for warming_up=false before the physical motion test.", flush=True)
App.run()
