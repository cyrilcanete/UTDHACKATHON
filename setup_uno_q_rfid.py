"""Install the App Lab scan bridge and migrate only this project's RFID settings."""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from mirror_runtime import profiles_for

BASE = Path(__file__).resolve().parent


def configured_profiles(cfg):
    profiles = profiles_for(cfg)
    owner = next((p for p in profiles if p["id"] == cfg.get("owner_profile_id", "cyril")), None)
    sarah = next((p for p in profiles if p["id"] in ("partner", "sarah") and p is not owner), None)
    if owner is None or sarah is None:
        raise ValueError("Expected the existing owner and partner/sarah profiles; config was not changed")
    assignments = ((owner, "Cyril", "F0E2E55C"), (sarah, "Sarah", "874BBA62"))
    for target, name, uid in assignments:
        for profile in profiles:
            profile["rfid_uids"] = [card for card in profile["rfid_uids"] if card != uid]
        target["name"] = name
        target["rfid_uids"].append(uid)
    return profiles


def configure(base, app_dir):
    base, app_dir = Path(base).resolve(), Path(app_dir).resolve()
    if not (app_dir / "app.yaml").is_file() or not (app_dir / "sketch" / "sketch.ino").is_file():
        raise ValueError("The tested App Lab RFID_Test app was not found; pass --app-path to its folder")
    config_path = base / "config.json"
    original = config_path if config_path.exists() else base / "config.example.json"
    cfg = json.loads(original.read_text(encoding="utf-8"))
    cfg["profiles"] = configured_profiles(cfg)
    cfg["rfid"] = {"source": "uno_q", "event_path": str(app_dir / ".mirror-rfid" / "scans.ndjson")}
    # Validate before touching either the installed callback or the config.
    profiles_for(cfg)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = app_dir.parent / (app_dir.name + "-before-mirror-" + stamp)
    backup.mkdir(mode=0o700)
    (backup / "python").mkdir(mode=0o700)
    for name in ("main.py", "rfid_bridge.py", "mirror_runtime.py"):
        source = app_dir / "python" / name
        if source.exists():
            shutil.copy2(source, backup / "python" / name)
    if config_path.exists():
        shutil.copy2(config_path, config_path.with_name("config.json." + stamp + ".bak"))
    (app_dir / "python").mkdir(exist_ok=True)
    for source, target in ((base / "hardware" / "uno_q_rfid" / "python" / "main.py", app_dir / "python" / "main.py"),
                           (base / "rfid_bridge.py", app_dir / "python" / "rfid_bridge.py"),
                           (base / "mirror_runtime.py", app_dir / "python" / "mirror_runtime.py")):
        shutil.copy2(source, target)
    # The working MCU sketch, its dependencies and private account data stay in place.
    temp = config_path.with_suffix(".json.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)
        handle.write("\n")
    os.replace(temp, config_path)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-path", type=Path, default=Path.home() / "ArduinoApps" / "rfid_test")
    args = parser.parse_args()
    try:
        backup = configure(BASE, args.app_path)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
    print("Configured: white -> Cyril; blue -> Sarah. Both scans open Personal mode.")
    print("Reader callback backup:", backup)
    print("Restart RFID_Test with App Lab Stop/Run, then restart the dashboard.")
    print("A fresh scan after dashboard startup is required. No hardware test has been performed by setup.")


if __name__ == "__main__":
    main()
