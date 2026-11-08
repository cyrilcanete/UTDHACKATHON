"""Isolated RFID test; no Smart Mirror dashboard files or settings are changed."""

import json
import re
from threading import Lock

from arduino.app_utils import App, Bridge


# Temporary scan-order labels. Restarting this app clears both assignments.
profiles = {}
profile_lock = Lock()


def on_rfid_uid(uid: str, uid_bytes: int, card_type: int):
    """Report real sketch events and label up to two distinct cards this run."""
    normalized = " ".join(str(uid).upper().split())
    if (
        uid_bytes not in (4, 7, 10)
        or not re.fullmatch(r"[0-9A-F]{2}(?: [0-9A-F]{2})*", normalized)
        or len(normalized.split()) != uid_bytes
    ):
        print(json.dumps({"event": "invalid_uid_event", "uid": normalized}), flush=True)
        return

    with profile_lock:
        newly_assigned = normalized not in profiles and len(profiles) < 2
        if newly_assigned:
            profiles[normalized] = f"profile_{len(profiles) + 1}"
        profile = profiles.get(normalized)

    print(
        json.dumps(
            {
                "event": "rfid_uid",
                "uid": normalized,
                "uid_bytes": uid_bytes,
                "card_type_code": card_type,
                "test_profile": profile,
                "newly_assigned": newly_assigned,
                "mapping_scope": "this_app_run_only",
            }
        ),
        flush=True,
    )
    if profile is None:
        print("Extra card: both test profile slots are already assigned.", flush=True)


Bridge.provide("on_rfid_uid", on_rfid_uid)
print(
    "RFID_Test Python listener started. Scan card 1, remove it, then scan card 2. "
    "The first two distinct UIDs receive temporary profile_1/profile_2 labels. "
    "Restarting clears these labels. No dashboard integration is enabled.",
    flush=True,
)
App.run()
