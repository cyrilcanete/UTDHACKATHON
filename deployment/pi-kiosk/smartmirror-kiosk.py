#!/usr/bin/python3
"""Smart Mirror desktop startup and browser supervisor. No project edits."""
import configparser
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

MARKER = "Managed by smartmirror-startup-kit"
HOME = Path.home()
STATE = HOME / ".local/state/smartmirror-kiosk"
HELPER = HOME / ".local/lib/smartmirror-startup/smartmirror-kiosk.py"
SESSION = HOME / ".local/bin/smartmirror-kiosk-session"
UNIT = HOME / ".config/systemd/user/smartmirror-kiosk.service"
PROFILE = HOME / ".local/share/smartmirror-kiosk/profile"
DISPLAY_KEYS = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY",
                "DBUS_SESSION_BUS_ADDRESS", "XDG_SESSION_TYPE")


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def die(message):
    raise SystemExit(message)


def compositors():
    found = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            args = (proc / "cmdline").read_bytes().decode().split("\0")
            name = Path(args[0]).name
            if name in ("labwc", "wayfire", "lxsession"):
                # Field 22 is process start time; split after comm's final ')'.
                token = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
                found.append((name, int(proc.name), token, args))
        except (OSError, UnicodeError, IndexError):
            pass
    return found


def one_compositor():
    found = compositors()
    if len(found) != 1:
        die("Need exactly one running labwc, Wayfire, or LXDE session for this user. "
            "Sign in to the Pi desktop and rerun; no settings changed.")
    return found[0]


def install():
    if os.getuid() == 0 or os.environ.get("USER") != "canetebros":
        die("Run as canetebros, without sudo.")
    name, _, _, args = one_compositor()
    browser = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser:
        die("Chromium is not installed. Install the Raspberry Pi OS Chromium package first.")
    if run("systemctl", "--user", "show-environment", check=False).returncode:
        die("The user service manager is unavailable. Sign in normally as canetebros first.")
    if name == "labwc":
        target = HOME / ".config/labwc/autostart"
        defaults = Path("/etc/xdg/labwc/autostart")
        addition = f'\n# {MARKER}\n{SESSION} &\n'
    elif name == "wayfire":
        target = HOME / ".config/wayfire.ini"
        defaults = Path("/etc/wayfire/defaults.ini")
        addition = None
    else:
        session_name = "LXDE-pi"
        if "-s" in args:
            session_name = args[args.index("-s") + 1]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_name):
            die("Cannot safely determine the LXDE session name.")
        target = HOME / f".config/lxsession/{session_name}/autostart"
        defaults = Path(f"/etc/xdg/lxsession/{session_name}/autostart")
        addition = f'\n# {MARKER}\n{SESSION}\n'
    if target.is_symlink():
        die(f"Refusing to replace symlink {target}; inspect its destination first.")
    # A compositor custom config argument can select a different autostart path.
    if any(a in ("-C", "--config-dir", "-c", "--config") or
           a.startswith(("--config=", "--config-dir=")) for a in args):
        die("Compositor uses an explicit config path. Inspect that path before configuring startup.")
    source = target if target.exists() else defaults
    if not source.exists():
        die(f"Cannot find {target} or {defaults}; inspect this desktop's defaults first.")
    old = source.read_text()
    candidates = set(HOME.glob(".config/autostart/*.desktop"))
    candidates.update(Path("/etc/xdg/autostart").glob("*.desktop"))
    candidates.update([target, defaults, HOME / ".config/wayfire.ini",
                       HOME / ".config/labwc/autostart",
                       HOME / ".config/lxsession/LXDE-pi/autostart"])
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            if line.lstrip().startswith(("#", ";")):
                continue
            if "chromium" in line and ("--kiosk" in line or ":5000" in line):
                die(f"Existing kiosk command in {path}: {line}\n"
                    "Back up that file and disable only its old kiosk entry, then rerun.")
    for path in (HELPER, SESSION, UNIT):
        if path.exists() and MARKER not in path.read_text(errors="replace"):
            die(f"Unmanaged file already exists: {path}. Refusing to replace it.")
    if addition is None:
        # Preserve comments, unrelated keys, ordering, and original text.
        parser = configparser.ConfigParser(strict=True, interpolation=None)
        parser.read_string(old)
        value = parser.get("autostart", "smartmirror_kiosk", fallback=None)
        if value is not None and value != str(SESSION):
            die("Wayfire already has a different smartmirror_kiosk entry.")
        if value is None:
            match = re.search(r"(?m)^\[autostart\][ \t]*$", old)
            entry = f"\n# {MARKER}\nsmartmirror_kiosk = {SESSION}\n"
            new = old[:match.end()] + entry + old[match.end():] if match else old + "\n[autostart]" + entry
        else:
            new = old
    else:
        new = old if str(SESSION) in old else old + addition
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = HOME / "smartmirror-startup-backups" / stamp / "kiosk"
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup.parent.parent, 0o700)
    for path in (target, HELPER, SESSION, UNIT):
        if path.exists():
            destination = backup / path.relative_to(HOME)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    (backup / "manifest.json").write_text(json.dumps({
        "compositor": name, "autostart": str(target),
        "autostart_existed": target.exists(), "defaults_copied": str(source),
        "managed_paths": [str(p) for p in (HELPER, SESSION, UNIT)],
    }, indent=2) + "\n")
    for path in (HELPER, SESSION, UNIT, target):
        path.parent.mkdir(parents=True, exist_ok=True)
    HELPER.write_bytes(Path(__file__).read_bytes())
    SESSION.write_text(f'#!/bin/sh\n# {MARKER}\nexec /usr/bin/python3 "{HELPER}" session\n')
    SESSION.chmod(0o700)
    UNIT.write_text(f'''# {MARKER}
[Unit]
Description=Smart Mirror Chromium kiosk in the logged-in desktop
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/python3 {HELPER} supervise
Restart=always
RestartSec=5
RestartPreventExitStatus=78
TimeoutStopSec=15
KillMode=control-group
UMask=0077
''')
    target.write_text(new)
    run("systemctl", "--user", "daemon-reload")
    print(f"Installed for running {name}; backups: {backup}")
    print("No kiosk was enabled for boot before desktop login. Its desktop autostart starts it.")
    print("In sudo raspi-config, select desktop boot and automatic desktop login for canetebros.")
    print("Disable screen blanking there if the mirror should remain visible.")
    print("Reboot or log out and back into the desktop; do not launch the session helper from SSH.")


def session():
    if not os.environ.get("XDG_RUNTIME_DIR") or not any(os.environ.get(k) for k in ("DISPLAY", "WAYLAND_DISPLAY")):
        die("Run the session helper from desktop autostart, not an SSH shell.")
    name, pid, token, _ = one_compositor()
    if name in ("labwc", "wayfire") and not os.environ.get("WAYLAND_DISPLAY"):
        die("Wayland desktop did not supply WAYLAND_DISPLAY.")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    environment = {key: os.environ[key] for key in DISPLAY_KEYS if key in os.environ}
    record = {"pid": pid, "token": token, "environment": environment}
    destination = STATE / "session.json"
    temporary = STATE / "session.json.tmp"
    temporary.write_text(json.dumps(record))
    temporary.chmod(0o600)
    temporary.replace(destination)
    # Import only actual values. Supervisor also uses the saved environment so
    # stale display variables from another desktop cannot reach Chromium.
    run("systemctl", "--user", "import-environment", *environment.keys())
    run("systemctl", "--user", "restart", "smartmirror-kiosk.service")


def session_alive(record):
    try:
        proc = Path(f"/proc/{record['pid']}")
        return proc.stat().st_uid == os.getuid() and (proc / "stat").read_text().rsplit(")", 1)[1].split()[19] == record["token"]
    except (OSError, IndexError):
        return False


def ready(opener):
    try:
        with opener.open("http://127.0.0.1:5000/", timeout=3) as response:
            if response.status != 200:
                return False
        with opener.open("http://127.0.0.1:5000/api/dashboard", timeout=3) as response:
            data = json.load(response)
            return response.status == 200 and isinstance(data, dict) and isinstance(data.get("settings"), dict)
    except (OSError, ValueError):
        return False


def stop_browser(browser):
    if browser is None or browser.poll() is not None:
        return
    try:
        os.killpg(browser.pid, signal.SIGTERM)
        browser.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(browser.pid, signal.SIGKILL)
        browser.wait()
    except ProcessLookupError:
        pass


def supervise():
    try:
        record = json.loads((STATE / "session.json").read_text())
    except (OSError, ValueError):
        return 78
    if not session_alive(record):
        return 78
    environment = dict(os.environ)
    for key in DISPLAY_KEYS:
        environment.pop(key, None)
    environment.update(record["environment"])
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser_path:
        die("Chromium unavailable")
    PROFILE.mkdir(parents=True, exist_ok=True, mode=0o700)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    browser = None
    failures = 0
    was_ready = None
    try:
        while not stopping and session_alive(record):
            healthy = ready(opener)
            if healthy != was_ready:
                print("Dashboard ready" if healthy else "Waiting for localhost dashboard", flush=True)
                was_ready = healthy
            failures = 0 if healthy else failures + 1
            if browser is not None and browser.poll() is not None:
                browser = None
            if failures >= 2 and browser is not None:
                stop_browser(browser)
                browser = None
            if healthy and browser is None and not stopping:
                platform = "wayland" if environment.get("WAYLAND_DISPLAY") else "x11"
                browser = subprocess.Popen([
                    browser_path, "--kiosk", "--no-first-run", "--no-default-browser-check",
                    "--disable-session-crashed-bubble", "--disable-background-mode",
                    f"--ozone-platform={platform}", f"--user-data-dir={PROFILE}",
                    "http://127.0.0.1:5000/"], env=environment, start_new_session=True)
            for _ in range(10):
                if stopping or not session_alive(record):
                    break
                time.sleep(0.5)
    finally:
        stop_browser(browser)
    return 78 if not session_alive(record) else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["install"]:
        install()
    elif sys.argv[1:] == ["session"]:
        session()
    elif sys.argv[1:] == ["supervise"]:
        sys.exit(supervise())
    else:
        die("Usage: smartmirror-kiosk.py install|session|supervise")
