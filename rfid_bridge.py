"""Local scan journal shared by the App Lab container and UNO Q Linux dashboard."""
import json
import os
import threading
import time
from pathlib import Path

from mirror_runtime import normalize_uid


class ScanPublisher:
    """One append per scan; bounded rotation avoids an indefinitely growing file."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def publish(self, uid, uid_bytes):
        uid = normalize_uid(uid)
        if type(uid_bytes) is not int or uid_bytes not in (4, 7, 10) or len(uid) != uid_bytes * 2:
            raise ValueError("UID length does not match the card event")
        event = {"type": "rfid", "uid": uid, "mode": "personal", "received_at": time.time()}
        line = (json.dumps(event) + "\n").encode("utf-8")
        with self.lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > 262144:
                os.replace(self.path, self.path.with_suffix(".previous"))
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "ab") as handle:
                handle.write(line)
                handle.flush()
        return event


class ScanReader:
    """Read only new scans, including after reader restart/rotation; never replay history."""
    def __init__(self, runtime, path, clock=time.time):
        self.runtime, self.path, self.clock = runtime, Path(path), clock
        self.offset, self.identity, self.buffer, self.discarding = 0, None, bytearray(), False
        try:
            info = self.path.stat()
            self.identity, self.offset = (info.st_dev, info.st_ino), info.st_size
        except FileNotFoundError:
            pass

    def accept(self, line):
        event = json.loads(line.decode("utf-8"))
        if not isinstance(event, dict) or event.get("type") != "rfid":
            raise ValueError("Expected a card scan")
        received = event.get("received_at")
        if isinstance(received, bool) or not isinstance(received, (int, float)) or not 0 <= self.clock() - received <= 5:
            return  # Delayed records cannot unexpectedly select an old user's profile.
        recognized = self.runtime.ingest({"type": "rfid", "uid": event["uid"], "mode": "personal"})
        with self.runtime.lock:
            self.runtime.rfid_status = "RFID · card received" if recognized else "RFID · unassigned card"

    def poll(self):
        with self.path.open("rb") as handle:
            info = os.fstat(handle.fileno())
            identity = (info.st_dev, info.st_ino)
            if self.identity != identity or info.st_size < self.offset:
                self.offset, self.buffer, self.discarding = 0, bytearray(), False
            self.identity = identity
            handle.seek(self.offset)
            data = handle.read(65536)
            self.offset = handle.tell()
        for byte in data:
            if byte == 10:
                if self.buffer and not self.discarding:
                    try:
                        self.accept(self.buffer)
                    except (ValueError, UnicodeError, KeyError, TypeError):
                        with self.runtime.lock:
                            self.runtime.rfid_status = "RFID · invalid scan ignored"
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                self.buffer.append(byte)
                if len(self.buffer) > 4096:
                    self.buffer.clear()
                    self.discarding = True


def rfid_worker(runtime, stop):
    options = runtime.cfg.get("rfid", {})
    if options.get("source", "none") != "uno_q":
        return
    path = options.get("event_path")
    if not isinstance(path, str) or not path.strip():
        runtime.rfid_status = "RFID · setup required"
        return
    try:
        reader = ScanReader(runtime, Path(path).expanduser())
    except OSError:
        runtime.rfid_status = "RFID · reader file unavailable"
        return
    runtime.rfid_status = "RFID · waiting for a card"
    while not stop.is_set():
        try:
            reader.poll()
        except FileNotFoundError:
            with runtime.lock:
                runtime.rfid_status = "RFID · waiting for reader app"
        except OSError:
            with runtime.lock:
                runtime.rfid_status = "RFID · reader file unavailable"
        stop.wait(0.1)
