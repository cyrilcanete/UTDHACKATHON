"""MFRC522 MCU events -> the dashboard's shared scan journal. No card writes."""
import json
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


Bridge.provide("on_rfid_uid", on_rfid_uid)
print("RFID mirror listener started. Scan white for Cyril or blue for Sarah.", flush=True)
App.run()
