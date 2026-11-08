"""Record actual DHT11 values from the UNO Q MCU; failed reads remain null."""
import json
from datetime import datetime, timezone
from pathlib import Path

from arduino.app_utils import App, Bridge

LOG = Path(__file__).resolve().parents[1] / "test_events.jsonl"


def on_dht11_test(ok: int, temperature_tenths: int, humidity_tenths: int, sequence: int):
    temperature = temperature_tenths / 10 if ok == 1 else None
    humidity = humidity_tenths / 10 if ok == 1 else None
    valid = ok == 1 and -40 <= temperature <= 125 and 0 <= humidity <= 100
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": "dht11_reading",
        "sequence": sequence,
        "ok": valid,
        "temperature_c": temperature if valid else None,
        "humidity_pct": humidity if valid else None,
    }
    text = json.dumps(event, allow_nan=False)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text, flush=True)


Bridge.provide("on_dht11_test", on_dht11_test)
print("DHT11_Test listener started. Awaiting actual temperature/humidity readings.", flush=True)
App.run()
