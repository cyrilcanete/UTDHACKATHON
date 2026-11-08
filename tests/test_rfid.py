import importlib.util
import json
import sys
import time
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import app
from mirror_runtime import MirrorRuntime, profiles_for
from rfid_bridge import ScanPublisher, ScanReader
from setup_uno_q_rfid import configure


class CardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / "config.example.json").read_text())
        self.runtime = MirrorRuntime(self.cfg)
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "scans.ndjson"
        self.publisher = ScanPublisher(self.path)
        self.reader = ScanReader(self.runtime, self.path)

    def test_actual_cards_select_cyril_and_sarah_and_open_personal(self):
        self.publisher.publish("87:4b:ba:62", 4)
        self.reader.poll()
        self.assertEqual(self.runtime.snapshot()["active_profile"], "partner")
        self.assertEqual(self.runtime.profiles[1]["name"], "Sarah")
        self.runtime.set_mode("work")
        self.publisher.publish("F0 E2 E5 5C", 4)
        self.reader.poll()
        self.assertEqual(self.runtime.snapshot()["active_profile"], "cyril")
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")
        self.publisher.publish("87 4B BA 62", 4)
        self.reader.poll()
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")
        self.assertTrue(self.runtime.snapshot()["sensors"]["simulated"])

    def test_unknown_card_cannot_select_a_profile_or_change_its_mode(self):
        self.runtime.set_mode("work")
        self.publisher.publish("FF FF FF FF", 4)
        self.reader.poll()
        state = self.runtime.snapshot()
        self.assertEqual((state["active_profile"], state["mode"]), ("cyril", "work"))
        self.assertIn("unassigned", state["rfid_status"])

    def test_restarting_dashboard_does_not_replay_old_card_scans(self):
        self.publisher.publish("874BBA62", 4)
        fresh_reader = ScanReader(self.runtime, self.path)
        fresh_reader.poll()
        self.assertEqual(self.runtime.active, "cyril")
        self.publisher.publish("874BBA62", 4)
        fresh_reader.poll()
        self.assertEqual(self.runtime.active, "partner")

    def test_rotation_and_fragmented_lines_do_not_lose_the_next_scan(self):
        self.path.write_bytes(b"x" * 262145)
        reader = ScanReader(self.runtime, self.path)
        self.publisher.publish("874BBA62", 4)
        reader.poll()
        self.assertEqual(self.runtime.active, "partner")
        record = json.dumps({"type": "rfid", "uid": "F0E2E55C", "received_at": time.time()}).encode()
        with self.path.open("ab") as handle:
            handle.write(record[:20])
        reader.poll()
        self.assertEqual(self.runtime.active, "partner")
        with self.path.open("ab") as handle:
            handle.write(record[20:] + b"\n")
        reader.poll()
        self.assertEqual(self.runtime.active, "cyril")

    def test_invalid_oversized_and_delayed_records_recover(self):
        with self.path.open("wb") as handle:
            handle.write(b"bad JSON\n" + b"x" * 5000 + b"\n")
            for timestamp in (time.time() - 60, time.time() + 60, True, float("nan")):
                handle.write((json.dumps({"type": "rfid", "uid": "874BBA62", "received_at": timestamp}) + "\n").encode())
        self.reader.poll()
        self.assertEqual(self.runtime.active, "cyril")
        self.publisher.publish("874BBA62", 4)
        self.reader.poll()
        self.assertEqual(self.runtime.active, "partner")

    def test_card_event_never_makes_old_sensor_data_fresh(self):
        self.cfg["sensors"]["source"] = "http"
        now = [0]
        runtime = MirrorRuntime(self.cfg, clock=lambda: now[0])
        runtime.ingest({"temperature_c": 23, "humidity_pct": 45})
        reader = ScanReader(runtime, self.path)
        now[0] = 30
        self.publisher.publish("874BBA62", 4)
        reader.poll()
        self.assertEqual(runtime.active, "partner")
        self.assertIsNone(runtime.snapshot()["sensors"]["temperature_c"])

    def test_callback_protocol_reaches_public_dashboard_state(self):
        callbacks = {}
        utilities = types.ModuleType("arduino.app_utils")
        utilities.Bridge = types.SimpleNamespace(provide=lambda name, callback: callbacks.update({name: callback}))
        utilities.App = types.SimpleNamespace(run=Mock())
        spec = importlib.util.spec_from_file_location("test_reader_app", app.BASE / "hardware" / "uno_q_rfid" / "python" / "main.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"arduino": types.ModuleType("arduino"), "arduino.app_utils": utilities}):
            spec.loader.exec_module(module)
        module.publisher = self.publisher
        app.initialize(self.cfg)
        reader = ScanReader(app.RUNTIME, self.path)
        callbacks["on_rfid_uid"]("87 4B BA 62", 4, 1)
        reader.poll()
        state = app.public_state(self.cfg)
        self.assertEqual(state["settings"]["name"], "Sarah")
        self.assertEqual(state["mirror"]["mode"], "personal")
        callbacks["on_rfid_uid"]("F0 E2 E5 5C", 4, 1)
        reader.poll()
        self.assertEqual(app.public_state(self.cfg)["settings"]["name"], "Cyril")

    def test_invalid_callback_lengths_do_not_publish(self):
        for uid, size in (("874BBA62", 7), ("not a uid", 4), ("874BBA62", True)):
            with self.assertRaises(ValueError):
                self.publisher.publish(uid, size)
        self.assertFalse(self.path.exists())


class SetupTests(unittest.TestCase):
    def test_setup_preserves_accounts_settings_sketch_and_previous_callback(self):
        with TemporaryDirectory() as folder:
            base, installed = Path(folder) / "dashboard", Path(folder) / "ArduinoApps" / "rfid_test"
            base.mkdir()
            for relative in ("hardware/uno_q_rfid/python",):
                (base / relative).mkdir(parents=True)
            for relative in ("rfid_bridge.py", "mirror_runtime.py", "hardware/uno_q_rfid/python/main.py"):
                (base / relative).write_text("new code", encoding="utf-8")
            cfg = json.loads((app.BASE / "config.example.json").read_text())
            cfg["calendar_id"] = "preserve-this-calendar"
            cfg["profiles"][1]["tasks"] = ["Sarah's existing task"]
            cfg["profiles"][1]["rfid_uids"] = []
            original = json.dumps(cfg)
            (base / "config.json").write_text(original)
            (base / "private").mkdir()
            (base / "private" / "token.json").write_text("leave unchanged")
            (installed / "python").mkdir(parents=True)
            (installed / "sketch").mkdir()
            (installed / "python" / "main.py").write_text("previous callback")
            (installed / "app.yaml").write_text("name: RFID_Test\n")
            (installed / "sketch" / "sketch.ino").write_text("tested MCU sketch")
            backup = configure(base, installed)
            updated = json.loads((base / "config.json").read_text())
            self.assertEqual(updated["calendar_id"], cfg["calendar_id"])
            self.assertEqual(updated["sensors"], cfg["sensors"])
            self.assertEqual(updated["profiles"][1]["id"], "partner")
            self.assertEqual(updated["profiles"][1]["tasks"], ["Sarah's existing task"])
            self.assertEqual(profiles_for(updated)[1]["rfid_uids"], ["874BBA62"])
            self.assertEqual(updated["rfid"]["event_path"], str(installed / ".mirror-rfid" / "scans.ndjson"))
            self.assertEqual((installed / "sketch" / "sketch.ino").read_text(), "tested MCU sketch")
            self.assertEqual((backup / "python" / "main.py").read_text(), "previous callback")
            self.assertEqual((base / "private" / "token.json").read_text(), "leave unchanged")
            self.assertEqual(next(base.glob("config.json.*.bak")).read_text(), original)


if __name__ == "__main__":
    unittest.main()
