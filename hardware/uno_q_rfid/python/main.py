"""MFRC522 MCU events -> the dashboard's shared scan journal. No card writes."""
import json
import math
from pathlib import Path

from arduino.app_utils import App, Bridge
from rfid_bridge import ScanPublisher


publisher = ScanPublisher(Path(__file__).resolve().parents[1] / ".mirror-rfid" / "scans.ndjson")


def on_rfid_uid(uid: str, uid_bytes: int, card_type: int):
    try:
        event = publisher.publish(uid, uid_bytes)
        print(json.dumps({"event": "rfid_scan_written", "uid": event["uid"], "uid_bytes": uid_bytes}), flush=True)
    except (ValueError, OSError) as error:
        print(json.dumps({"event": "rfid_scan_error", "error": str(error)}), flush=True)


def on_mirror_encoder(delta: int):
    if type(delta) is not int or delta == 0:
        return
    publisher.publish_event({"type": "encoder", "delta": delta})


def on_mirror_press():
    publisher.publish_event({"type": "encoder", "action": "press"})


def on_mirror_analyze():
    publisher.publish_event({"type": "encoder", "action": "analyze"})


def on_mirror_sensors(temperature: float, humidity: float, motion: bool):
    # The firmware sends -999 when DHT11 fails; never substitute a normal reading.
    temp = float(temperature)
    humid = float(humidity)
    publisher.publish_event({"type": "sensors",
        "temperature_c": temp if math.isfinite(temp) and -40 <= temp <= 125 else None,
        "humidity_pct": humid if math.isfinite(humid) and 0 <= humid <= 100 else None,
        "motion": bool(motion)})


Bridge.provide("on_mirror_encoder", on_mirror_encoder)
Bridge.provide("on_mirror_press", on_mirror_press)
Bridge.provide("on_mirror_analyze", on_mirror_analyze)
Bridge.provide("on_mirror_sensors", on_mirror_sensors)
Bridge.provide("on_rfid_uid", on_rfid_uid)
print("RFID mirror listener started. Scan white for Cyril or blue for Sarah.", flush=True)
App.run()
