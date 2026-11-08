import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import app
from message_review import SAMPLES, review_message
from mirror_runtime import MirrorRuntime, SerialLines, profile_config, profiles_for


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / "config.example.json").read_text())
        self.cfg["profiles"][0]["rfid_uids"] = ["04:A1:B2:C3"]
        self.cfg["profiles"][1]["rfid_uids"] = ["12 34 56 78"]
        self.now = 100.0
        self.runtime = MirrorRuntime(self.cfg, clock=lambda: self.now)
        self.runtime.select_profile("cyril")

    def test_each_card_selects_person_and_resets_to_personal(self):
        self.runtime.set_mode("work")
        self.runtime.scan("12-34-56-78")
        self.assertEqual(self.runtime.snapshot()["active_profile"], "partner")
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")
        self.runtime.scan("04 a1 b2 c3")
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")
        self.assertFalse(self.runtime.scan("FFFFFFFF"))
        self.assertEqual(self.runtime.snapshot()["active_profile"], "cyril")
        self.assertIn("Unassigned", self.runtime.snapshot()["event"])

    def test_duplicate_cards_and_path_profile_ids_are_rejected(self):
        self.cfg["profiles"][1]["rfid_uids"] = ["04 A1 B2 C3"]
        with self.assertRaises(ValueError):
            profiles_for(self.cfg)
        self.cfg["profiles"][1]["rfid_uids"] = []
        self.cfg["profiles"][1]["id"] = "../cyril"
        with self.assertRaises(ValueError):
            profiles_for(self.cfg)

    def test_encoder_modes_follow_active_person_and_repeated_events_are_idempotent(self):
        self.runtime.ingest({"type": "mode", "mode": "work"})
        self.runtime.ingest({"type": "mode", "mode": "work"})
        self.assertEqual(self.runtime.snapshot()["mode"], "work")
        self.runtime.scan("12345678")
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")
        self.runtime.ingest({"type": "mode", "mode": "work"})
        self.runtime.ingest({"type": "mode", "mode": "personal"})
        self.runtime.scan("04A1B2C3")
        self.assertEqual(self.runtime.snapshot()["mode"], "personal")

    def test_combined_card_and_mode_targets_selected_person(self):
        self.runtime.ingest({"uid": "12345678", "mode": "work"})
        self.assertEqual(self.runtime.snapshot()["active_profile"], "partner")
        self.assertEqual(self.runtime.snapshot()["mode"], "work")
        self.assertFalse(self.runtime.ingest({"uid": "FFFFFFFF", "mode": "personal"}))
        self.assertEqual(self.runtime.snapshot()["mode"], "work")

    def test_invalid_mode_packets_do_not_change_profile_or_readings(self):
        for event in ({"type": "mode"}, {"mode": "toggle"}, {"uid": "12345678", "mode": None, "temperature_c": 99}):
            with self.assertRaises(ValueError):
                self.runtime.ingest(event)
        self.assertEqual(self.runtime.snapshot()["active_profile"], "cyril")
        self.assertEqual(self.runtime.snapshot()["sensors"]["temperature_c"], 23.5)

    def test_mode_serial_packets_preserve_sensor_freshness(self):
        self.cfg["sensors"]["source"] = "http"
        runtime = MirrorRuntime(self.cfg, clock=lambda: self.now)
        runtime.select_profile("cyril")
        runtime.ingest({"temperature_c": 23, "humidity_pct": 45})
        self.now += 20
        lines = SerialLines(runtime)
        lines.feed(b'{"type":"mode","mode":"wo')
        lines.feed(b'rk"}\n')
        self.assertEqual(runtime.snapshot()["mode"], "work")
        self.assertIsNone(runtime.snapshot()["sensors"]["temperature_c"])

    def test_legacy_config_retains_owner_and_adds_partner(self):
        self.cfg.pop("profiles")
        self.cfg["name"] = "Existing owner"
        profiles = profiles_for(self.cfg)
        self.assertEqual(profiles[0]["name"], "Existing owner")
        self.assertEqual(len(profiles), 2)

    def test_temperature_humidity_and_missing_data_alerts(self):
        self.runtime.demo_scenario("hot")
        snapshot = self.runtime.snapshot()
        self.assertEqual(snapshot["work"]["status"], "attention")
        self.assertEqual(len(snapshot["work"]["alerts"]), 2)
        self.runtime.demo_scenario("offline")
        self.assertEqual(self.runtime.snapshot()["work"]["status"], "unknown")
        self.assertIsNone(self.runtime.snapshot()["sensors"]["temperature_c"])
        self.runtime.demo_scenario("normal")
        self.assertEqual(self.runtime.snapshot()["work"]["status"], "normal")

    def test_rfid_never_refreshes_old_environmental_readings(self):
        self.cfg["sensors"]["source"] = "http"
        runtime = MirrorRuntime(self.cfg, clock=lambda: self.now)
        runtime.select_profile("cyril")
        runtime.ingest({"temperature_c": 23, "humidity_pct": 45, "motion": True})
        self.now += 20
        runtime.ingest({"uid": "12345678"})
        self.assertIsNone(runtime.snapshot()["sensors"]["temperature_c"])
        self.assertEqual(runtime.snapshot()["work"]["status"], "unknown")

    def test_partial_packets_do_not_refresh_other_fields(self):
        self.cfg["sensors"]["source"] = "http"
        runtime = MirrorRuntime(self.cfg, clock=lambda: self.now)
        runtime.select_profile("cyril")
        runtime.ingest({"temperature_c": 23, "humidity_pct": 45})
        self.now += 20
        runtime.ingest({"motion": True})
        self.assertIsNone(runtime.snapshot()["sensors"]["temperature_c"])
        self.assertTrue(runtime.snapshot()["sensors"]["motion"])

    def test_invalid_packet_is_atomic_and_null_invalidates_a_reading(self):
        for payload in ({"temperature_c": 25, "humidity_pct": 101}, {"temperature_c": float("nan")}, {"motion": "false"}, {"temperature_c": True}):
            with self.assertRaises(ValueError):
                self.runtime.ingest(payload)
        self.assertEqual(self.runtime.snapshot()["sensors"]["temperature_c"], 23.5)
        self.runtime.ingest({"temperature_c": None})
        self.assertIsNone(self.runtime.snapshot()["sensors"]["temperature_c"])

    def test_line_framing_recovers_from_noise_splits_and_oversize(self):
        lines = SerialLines(self.runtime)
        lines.feed(b'Booting...\n{"type":"rfid","uid":"1234')
        lines.feed(b'5678"}\r\n')
        self.assertEqual(self.runtime.snapshot()["active_profile"], "partner")
        lines.feed(b'x' * 5000 + b'\n{"temperature_c":28,"humidity_pct":49}\n')
        self.assertEqual(self.runtime.snapshot()["sensors"]["temperature_c"], 28)
        self.assertEqual(self.runtime.invalid_lines, 2)

    def test_motion_timeout_card_wake_and_sensor_failure_fail_awake(self):
        self.cfg["sensors"].update(source="http", motion_sleep=True, idle_seconds=5, stale_after_seconds=20)
        runtime = MirrorRuntime(self.cfg, clock=lambda: self.now)
        runtime.select_profile("cyril")
        runtime.ingest({"motion": False})
        self.now += 6
        self.assertFalse(runtime.snapshot()["screen_awake"])
        runtime.scan("12345678")
        self.assertTrue(runtime.snapshot()["screen_awake"])
        self.now += 21
        self.assertTrue(runtime.snapshot()["screen_awake"])
        runtime.transport_error = "Disconnected"
        self.assertTrue(runtime.snapshot()["screen_awake"])


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / "config.example.json").read_text())
        app.initialize(self.cfg)

    def test_profiles_have_separate_widgets_and_private_storage(self):
        app.STATE["inbox"]["data"]["messages"] = [{"id":"mail:test", "subject":"OWNER ONLY", "body":""}]
        app.RUNTIME.select_profile("partner")
        state = app.public_state(self.cfg)
        self.assertEqual(state["settings"]["name"], "Sarah")
        self.assertNotIn("OWNER ONLY", json.dumps(state))
        owner = app.profile_private(profile_config(self.cfg, "cyril"))
        partner = app.profile_private(profile_config(self.cfg, "partner"))
        self.assertEqual(owner, app.PRIVATE)
        self.assertNotEqual(owner, partner)
        self.cfg["profiles"].reverse()
        self.assertEqual(app.profile_private(profile_config(self.cfg, "cyril")), owner)
        self.assertEqual(app.profile_private(profile_config(self.cfg, "partner")), partner)

    def test_work_response_omits_calendar_inbox_tasks_and_briefing(self):
        app.RUNTIME.select_profile("cyril")
        app.RUNTIME.set_mode("work")
        state = app.public_state(self.cfg)
        for key in ("calendar", "inbox", "briefing"):
            self.assertNotIn(key, state)
        self.assertEqual(state["settings"]["tasks"], [])

    def test_cached_personal_data_stays_separate_after_restart(self):
        with TemporaryDirectory() as folder, patch.object(app, "PRIVATE", Path(folder)):
            for profile_id in ("cyril", "partner"):
                effective = profile_config(self.cfg, profile_id)
                cached = {"calendar": {"data": [{"title": profile_id + " ONLY"}]}}
                app.private_write(app.profile_private(effective) / "cache.json", cached)
            self.cfg["demo"] = False
            app.initialize(self.cfg)
            app.RUNTIME.select_profile("partner")
            state = json.dumps(app.public_state(self.cfg))
            self.assertIn("partner ONLY", state)
            self.assertNotIn("cyril ONLY", state)

    def test_each_worker_updates_only_its_profile(self):
        self.cfg["demo"] = False
        stop = threading.Event()
        def fetch(_):
            stop.set()
            return {"profile": "partner"}
        with patch.object(app, "weather", side_effect=fetch), patch.object(app, "calendar", return_value=[]), patch.object(app, "inbox", return_value={"messages": []}), patch.object(app, "private_write"):
            app.worker(self.cfg, stop, "partner")
        self.assertEqual(app.PROFILE_STATES["partner"]["weather"]["data"]["profile"], "partner")
        self.assertEqual(app.STATE["weather"]["data"]["temperature"], 72)

    def test_message_checks_explain_flags_without_certifying_safety(self):
        suspicious = review_message(SAMPLES[0]["text"])
        ordinary = review_message(SAMPLES[2]["text"])
        self.assertGreaterEqual(len(suspicious["signals"]), 3)
        self.assertEqual(ordinary["signals"], [])
        self.assertIn("cannot establish", ordinary["summary"])
        for text in ("", "x" * 4001, None):
            with self.assertRaises(ValueError):
                review_message(text)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / "config.example.json").read_text())
        app.initialize(self.cfg)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.handler_for(self.cfg))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def post(self, path, payload, extra=None):
        headers = {"Host": "localhost:5000", "Content-Type": "application/json", **(extra or {})}
        with urlopen(Request(self.root + path, data=json.dumps(payload).encode(), headers=headers), timeout=5) as response:
            return json.load(response)

    def test_demo_scan_modes_and_scenarios(self):
        state = self.post("/api/demo/scan", {"profile_id": "partner"})
        self.assertEqual(state["settings"]["name"], "Sarah")
        state = self.post("/api/mode", {"mode": "work"})
        self.assertNotIn("inbox", state)
        state = self.post("/api/demo/scenario", {"scenario": "hot"})
        self.assertEqual(state["mirror"]["work"]["status"], "attention")

    def test_demo_never_calls_ai_and_bridge_requires_opt_in(self):
        self.cfg["ai_enabled"] = True
        with patch.object(app, "read_json", side_effect=AssertionError("Demo used network")):
            self.assertIn("Rule-based", self.post("/api/message-review", {"text": SAMPLES[0]["text"]})["method"])
        with self.assertRaises(HTTPError) as error:
            self.post("/api/hardware", {"motion": True})
        self.assertEqual(error.exception.code, 403)

    def test_cross_origin_and_invalid_requests_are_rejected(self):
        cases = [("/api/mode", {"mode": "work"}, {"Origin": "https://evil.example"}, 403),
                 ("/api/mode", {"mode": "invalid"}, {}, 400),
                 ("/api/demo/scan", {"profile_id": []}, {}, 400),
                 ("/api/message-review", {"text": "x" * 9000}, {}, 413)]
        for path, payload, headers, code in cases:
            with self.assertRaises(HTTPError) as error:
                self.post(path, payload, headers)
            self.assertEqual(error.exception.code, code)

    def test_optional_ai_explanation_and_failure_preserve_local_review(self):
        self.cfg.update(demo=False, ai_enabled=True)
        with patch.object(app, "read_json", return_value={"response": "Verify the request independently."}):
            result = self.post("/api/message-review", {"text": SAMPLES[0]["text"]})
            self.assertIn("independently", result["ai_note"])
        with patch.object(app, "read_json", side_effect=TimeoutError()):
            result = self.post("/api/message-review", {"text": SAMPLES[0]["text"]})
            self.assertIn("unavailable", result["ai_error"])
            self.assertGreaterEqual(len(result["signals"]), 3)

    def test_live_blocks_demo_and_http_bridge_updates_card_and_sensors(self):
        self.cfg["demo"] = False
        self.cfg["sensors"]["source"] = "http"
        self.cfg["profiles"][1]["rfid_uids"] = ["12345678"]
        app.initialize(self.cfg)
        with self.assertRaises(HTTPError) as error:
            self.post("/api/demo/scan", {"profile_id": "partner"})
        self.assertEqual(error.exception.code, 403)
        state = self.post("/api/hardware", {"uid": "12345678", "temperature_c": 24, "humidity_pct": 45})
        self.assertEqual(state["mirror"]["active_profile"], "partner")
        self.assertEqual(state["mirror"]["sensors"]["temperature_c"], 24)
        state = self.post("/api/hardware", {"type": "mode", "mode": "work"})
        self.assertEqual(state["mirror"]["mode"], "work")
        self.assertEqual(state["mirror"]["active_profile"], "partner")


if __name__ == "__main__":
    unittest.main()
