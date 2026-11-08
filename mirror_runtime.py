"""Profiles, RFID selection and shared environmental data. No device needed in demo."""
import copy
import json
import math
import re
import threading
import time
from datetime import datetime, timezone


def normalize_uid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F :\-]+", value):
        raise ValueError("Card UID must contain hexadecimal bytes")
    uid = re.sub(r"[ :\-]", "", value).upper()
    if len(uid) not in (8, 14, 20):
        raise ValueError("Card UID must be 4, 7 or 10 bytes")
    return uid


def profiles_for(cfg):
    # Older config.json files get two profiles without losing the owner's settings.
    profiles = copy.deepcopy(cfg.get("profiles") or [
        {"id": "cyril", "name": cfg["name"], "tasks": cfg["tasks"], "rfid_uids": ["F0 E2 E5 5C"]},
        {"id": "partner", "name": "Sarah", "tasks": ["Review today's schedule", "Prepare the project demo"], "rfid_uids": ["87 4B BA 62"]},
    ])
    if not isinstance(profiles, list) or not all(isinstance(p, dict) for p in profiles):
        raise ValueError("profiles must be a list of profile objects")
    seen_ids, seen_uids = set(), set()
    for index, profile in enumerate(profiles):
        pid = profile.get("id", "")
        if not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", pid) or pid in seen_ids:
            raise ValueError("Each profile needs a unique id using lowercase letters, digits, _ or -")
        seen_ids.add(pid)
        if not isinstance(profile.get("name"), str) or not profile["name"].strip():
            raise ValueError("Each profile needs a name")
        if profile.get("name", "").strip().lower() == "partner":
            profile["name"] = "Sarah"
        profile.setdefault("tasks", cfg["tasks"] if index == 0 else [])
        if not isinstance(profile["tasks"], list) or not all(isinstance(x, str) for x in profile["tasks"]):
            raise ValueError("Profile tasks must be a list of strings")
        uids = profile.get("rfid_uids", [])
        if not isinstance(uids, list):
            raise ValueError("rfid_uids must be a list")
        profile["rfid_uids"] = [normalize_uid(uid) for uid in uids]
        for uid in profile["rfid_uids"]:
            if uid in seen_uids:
                raise ValueError("A card UID can belong to only one profile")
            seen_uids.add(uid)
    return profiles


def profile_config(cfg, profile_id):
    profiles = profiles_for(cfg)
    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if profile is None:
        raise ValueError("Unknown profile")
    result = dict(cfg)
    for key in ("name", "tasks", "calendar_id"):
        if key in profile:
            result[key] = profile[key]
    result["_profile_id"] = profile_id
    # Preserve the existing owner's private/token.json; other accounts are isolated.
    result["_private_subdir"] = None if profile_id == cfg.get("owner_profile_id", "cyril") else profile_id
    return result


class MirrorRuntime:
    SCENARIOS = {
        "normal": {"temperature_c": 23.5, "humidity_pct": 46.0, "motion": True},
        "hot": {"temperature_c": 35.0, "humidity_pct": 67.0, "motion": True},
        "dry": {"temperature_c": 24.0, "humidity_pct": 18.0, "motion": True},
    }

    def __init__(self, cfg, clock=time.monotonic):
        self.cfg, self.clock = cfg, clock
        self.lock = threading.RLock()
        self.profiles = profiles_for(cfg)
        self.active = None
        self.modes = {p["id"]: "personal" for p in self.profiles}
        encoder = cfg.get("encoder", {})
        self.detents_per_revolution = encoder.get("detents_per_revolution", 20)
        self.right_delta = encoder.get("right_delta", -1)
        if type(self.detents_per_revolution) is not int or not 2 <= self.detents_per_revolution <= 200 or self.detents_per_revolution % 2:
            raise ValueError("encoder.detents_per_revolution must be an even integer from 2 to 200")
        if type(self.right_delta) is not int or self.right_delta not in (-1, 1):
            raise ValueError("encoder.right_delta must be -1 or 1")
        self.encoder_progress = 0
        self.half_turn = self.detents_per_revolution // 2
        self.uid_map = {uid: p["id"] for p in self.profiles for uid in p["rfid_uids"]}
        self.options = dict(cfg.get("sensors", {}))
        self.source = self.options.get("source", "demo" if cfg["demo"] else "none")
        if self.source not in ("demo", "serial", "http", "uno_q", "none"):
            raise ValueError("sensors.source must be demo, serial, http, uno_q or none")
        self.stale_after = self._number("stale_after_seconds", 15, 1, 3600)
        self.motion_dimming = self.options.get("motion_dimming", True)
        if type(self.motion_dimming) is not bool:
            raise ValueError("motion_dimming must be true or false")
        self.dim_after = self._number("dim_after_seconds", 60, 1, 86400)
        self.dim_brightness = self._number("dim_brightness", 0.2, 0.05, 1)
        self.sleep_after = self._number("idle_seconds", 120, 1, 86400)
        self.hot_limit = self._number("temperature_alert_c", 30, -40, 125)
        self.humidity_low = self._number("humidity_min_pct", 30, 0, 100)
        self.humidity_high = self._number("humidity_max_pct", 60, 0, 100)
        if self.humidity_low >= self.humidity_high:
            raise ValueError("Humidity minimum must be below maximum")
        self.values, self.times = {}, {}
        self.last_motion = clock()
        self.updated = None
        self.event = "Scan a card or choose a demo profile." if cfg["demo"] else "Scan your registered card to select a profile."
        self.transport_error = None
        self.rfid_status = "RFID not connected"
        self.invalid_lines = 0
        self.scenario = "normal"
        if self.source == "demo":
            self.ingest(self.SCENARIOS["normal"])

    def _number(self, key, default, low, high):
        value = self.options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Invalid sensor setting: {key}")
        return value

    def select_profile(self, profile_id):
        with self.lock:
            if profile_id not in self.modes:
                raise ValueError("Unknown profile")
            self.active = profile_id
            self.encoder_progress = 0
            self.modes[profile_id] = "personal"
            self.last_motion = self.clock()
            name = next(p["name"] for p in self.profiles if p["id"] == profile_id)
            self.event = f"Profile selected: {name}"

    def set_mode(self, mode):
        if mode == "welcome":
            with self.lock:
                self.active = None
                self.encoder_progress = 0
                self.event = "Scan your card to begin."
                self.last_motion = self.clock()
            return
        if mode not in ("personal", "work"):
            raise ValueError("Mode must be personal or work")
        with self.lock:
            if self.active is None:
                return  # A knob turn cannot start a private session.
            self.modes[self.active] = mode
            self.encoder_progress = 0
            self.last_motion = self.clock()
            name = next(p["name"] for p in self.profiles if p["id"] == self.active)
            self.event = f"{mode.title()} mode · {name}"

    def scan(self, uid):
        uid = normalize_uid(uid)
        with self.lock:
            if uid not in self.uid_map:
                self.event = f"Unassigned card {uid}. Add it to a profile's rfid_uids in config.json."
                return False
            self.select_profile(self.uid_map[uid])
            return True

    def ingest(self, payload):
        """Validate the whole event before changing state; missing/null readings stay unavailable."""
        if not isinstance(payload, dict):
            raise ValueError("Hardware event must be a JSON object")
        if payload.get("type") not in (None, "rfid", "sensors", "mode", "encoder"):
            raise ValueError("Unknown hardware event type")
        mode = payload.get("mode")
        encoder_delta = None
        if payload.get("type") == "encoder":
            # Each delta is a physical detent, not a quadrature electrical edge.
            if "uid" in payload or "mode" in payload:
                raise ValueError("Send card and encoder events separately")
            supplied = [key for key in ("action", "direction", "delta") if key in payload]
            if len(supplied) != 1:
                raise ValueError("Send exactly one encoder action, direction or delta")
            if "action" in payload:
                if payload["action"] not in ("press", "push"):
                    raise ValueError("Unknown encoder action")
                mode = "welcome"
            elif "direction" in payload:
                directions = {"right": self.right_delta, "left": -self.right_delta, "decrement": -1, "increment": 1}
                value = payload["direction"]
                if not isinstance(value, str) or value not in directions:
                    raise ValueError("Unknown encoder direction")
                encoder_delta = directions[value]
            else:
                encoder_delta = payload["delta"]
                if type(encoder_delta) is not int or not 1 <= abs(encoder_delta) <= 1000:
                    raise ValueError("Encoder delta must be a nonzero integer detent count")
        if ("mode" in payload or payload.get("type") == "mode") and mode not in ("personal", "work", "welcome"):
            raise ValueError("Mode event needs mode: personal or work")
        fields = {}
        for key, low, high in (("temperature_c", -40, 125), ("humidity_pct", 0, 100)):
            if key in payload:
                value = payload[key]
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high):
                    raise ValueError(f"Invalid {key}")
                fields[key] = value
        if "motion" in payload:
            if type(payload["motion"]) is not bool:
                raise ValueError("motion must be true or false")
            fields["motion"] = payload["motion"]
        uid = normalize_uid(payload["uid"]) if "uid" in payload else None
        if not fields and uid is None and mode is None and encoder_delta is None:
            raise ValueError("Event needs uid, mode or sensor readings")
        with self.lock:
            now = self.clock()
            for key, value in fields.items():
                self.values[key], self.times[key] = value, now
            if fields.get("motion"):
                self.last_motion = now
            if fields:
                self.updated = datetime.now(timezone.utc).isoformat()
                self.transport_error = None
            if uid is not None:
                if not self.scan(uid):
                    return False
            if mode is not None:
                self.set_mode(mode)
            if encoder_delta is not None:
                self.last_motion = now
                if self.active is not None:
                    if self.encoder_progress * encoder_delta < 0:
                        self.encoder_progress = 0
                    self.encoder_progress += encoder_delta
                    if abs(self.encoder_progress) >= self.half_turn:
                        selected = "personal" if self.encoder_progress * self.right_delta > 0 else "work"
                        self.set_mode(selected)
        return True

    def demo_scenario(self, scenario):
        if self.source != "demo" or not self.cfg["demo"]:
            raise ValueError("Demo scenarios are disabled")
        if scenario not in (*self.SCENARIOS, "offline", "near", "away"):
            raise ValueError("Unknown scenario")
        with self.lock:
            self.scenario = scenario
            if scenario in ("near", "away"):
                self.ingest({"motion": scenario == "near"})
                if scenario == "away":
                    self.last_motion = self.clock() - self.dim_after
            elif scenario == "offline":
                self.times.clear()
            else:
                self.ingest(self.SCENARIOS[scenario])

    def snapshot(self):
        with self.lock:
            now = self.clock()
            simulated = self.source == "demo"
            readings = {}
            for key in ("temperature_c", "humidity_pct", "motion"):
                fresh = not self.transport_error and key in self.times and (simulated or now - self.times[key] <= self.stale_after)
                readings[key] = self.values.get(key) if fresh else None
            alerts = []
            if readings["temperature_c"] is None or readings["humidity_pct"] is None:
                alerts.append({"level": "unknown", "text": "Environmental data unavailable or stale. Check the sensor connection.", "action": "Restore fresh readings before assessing conditions."})
            if readings["temperature_c"] is not None and readings["temperature_c"] >= self.hot_limit:
                alerts.append({"level": "warning", "text": f"Temperature is at or above the configured {self.hot_limit:g}°C limit.", "action": "Check the reading and cooling/airflow; notify the responsible operator."})
            humidity = readings["humidity_pct"]
            if humidity is not None and not self.humidity_low <= humidity <= self.humidity_high:
                alerts.append({"level": "warning", "text": f"Humidity is outside the configured {self.humidity_low:g}–{self.humidity_high:g}% range.", "action": "Verify the sensor reading and check the room's humidity controls."})
            attention = any(a["level"] == "warning" for a in alerts)
            status = "attention" if attention else "unknown" if alerts else "normal"
            awake = (not self.options.get("motion_sleep", False) or readings["motion"] is None or readings["motion"] is True or now - self.last_motion < self.sleep_after)
            dimmed = self.motion_dimming and readings["motion"] is False and now - self.last_motion >= self.dim_after
            brightness = self.dim_brightness if dimmed else 1.0
            temp_text = "unavailable" if readings["temperature_c"] is None else f"{readings['temperature_c']:g}°C"
            humidity_text = "unavailable" if humidity is None else f"{humidity:g}%"
            handoff = f"{self.source.upper()} readings: temperature {temp_text}; humidity {humidity_text}. "
            handoff += " ".join(a["text"] + " " + a["action"] for a in alerts) if alerts else "Within configured thresholds. Continue monitoring."
            return {
                "active_profile": self.active,
                "profiles": [{"id": p["id"], "name": p["name"]} for p in self.profiles],
                "mode": self.modes[self.active] if self.active else "welcome", "event": self.event, "screen_awake": awake,
                "encoder": {"detents_per_revolution": self.detents_per_revolution, "half_turn_detents": self.half_turn,
                            "progress_detents": abs(self.encoder_progress), "right_mode": "personal", "left_mode": "work"},
                "brightness": brightness,
                "brightness_status": "dimmed" if dimmed else "full",
                "rfid_status": self.rfid_status,
                "sensors": {**readings, "source": self.source, "simulated": simulated, "updated": self.updated,
                            "status": status, "error": self.transport_error, "invalid_lines": self.invalid_lines},
                "work": {"status": status, "alerts": alerts, "handoff": handoff, "scenario": self.scenario,
                         "limits": {"temperature_alert_c": self.hot_limit, "humidity_min_pct": self.humidity_low, "humidity_max_pct": self.humidity_high}},
                "demo_controls": bool(self.cfg["demo"]),
            }


class SerialLines:
    """Bounded newline framing survives reads split by serial timeouts and noisy lines."""
    def __init__(self, runtime):
        self.runtime, self.buffer, self.discarding = runtime, bytearray(), False

    def feed(self, data):
        for byte in data:
            if byte == 10:
                if not self.discarding and self.buffer:
                    try:
                        self.runtime.ingest(json.loads(self.buffer.decode("utf-8")))
                    except (ValueError, UnicodeError):
                        with self.runtime.lock:
                            self.runtime.invalid_lines += 1
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                self.buffer.append(byte)
                if len(self.buffer) > 4096:
                    self.buffer.clear()
                    self.discarding = True
                    with self.runtime.lock:
                        self.runtime.invalid_lines += 1


def serial_worker(runtime, stop):
    if runtime.source != "serial":
        return
    try:
        import serial
    except ImportError:
        runtime.transport_error = "Install requirements-hardware.txt to read Arduino USB serial."
        return
    port = runtime.options.get("port")
    if not port:
        runtime.transport_error = "Set sensors.port to the Arduino serial device in config.json."
        return
    while not stop.is_set():
        try:
            with serial.Serial(port, int(runtime.options.get("baudrate", 9600)), timeout=1) as device:
                with runtime.lock:
                    runtime.transport_error = None
                lines = SerialLines(runtime)
                while not stop.is_set():
                    lines.feed(device.read(256))
        except (OSError, ValueError, serial.SerialException):
            with runtime.lock:
                runtime.transport_error = "Arduino unavailable. Check its USB connection, port, permissions and baud rate; retrying."
            stop.wait(3)
