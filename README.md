# Morning Mirror

Two RFID cards select two people. A rotary encoder selects Personal or Work mode for the active person. Built for an Arduino Uno R3 and Raspberry Pi 4B (2GB); all software features can be developed on a Windows PC without hardware.

## Run the demo now

From the project folder, run:

```powershell
py app.py
```

On Linux/Pi use `python3 app.py`. Open **http://127.0.0.1:5000** in a browser on that same computer. Stop an existing copy with Ctrl+C before starting the new one. The demo needs Python 3.10+ and no account credentials, model, sensor or third-party packages. If Windows reports a missing timezone database, install the included requirements in a virtual environment.

- Click **Scan Cyril's card** or **Scan Partner's card** to simulate an RFID profile selection.
- Click **Personal** or **Work**, or press **M**. Each person's chosen mode is remembered until the server restarts.
- Personal shows that person's fictional schedule, inbox, focus tasks and briefing. Try the example messages in **Message check**.
- Work shows shared room temperature, humidity, motion, threshold alerts and a handoff note. Try **Cooling issue**, **Low humidity**, **Sensor offline**, and **Normal**.
- **P** toggles personal display details; **F** toggles full screen. Shortcuts are ignored while typing in the message box.
- Demo account data and simulated sensor readings are labeled separately. No external service is contacted in demo mode, even if `ai_enabled` is true.

The mirror runs a local Python HTTP server, not Flask. Its existing address is still `127.0.0.1:5000`.

## Configure the two people and their cards

The app uses `config.json` when present, otherwise `config.example.json`. Copy the example to `config.json` only if you do not already have a config; keep your existing settings. Restart after editing.

```json
"profiles": [
  {"id": "cyril", "name": "Cyril", "rfid_uids": ["04 A1 B2 C3"], "tasks": ["Prepare the demo"]},
  {"id": "partner", "name": "Partner", "rfid_uids": ["12 34 56 78"], "tasks": ["Review the checklist"]}
]
```

These are fields inside the config object. **Replace the example UIDs with your actual card IDs.** Empty UID lists are intentional in the shipped config. Rename Partner to your girlfriend's preferred name. Card identifiers are normalized across spaces, colons, dashes and letter case. Each UID can belong to one profile; unknown cards keep the current profile and show their UID so you can register them. Card selection does not require writing personal information to the cards.

Older configs without `profiles` get the existing owner's name/tasks plus a separate Partner demo profile. To customize those or register cards, add the profiles list above. RFID and demo controls select a display profile; they are not secure authentication or a screen lock.

## Software interface for your hardware partner

The Arduino should send **one UTF-8 JSON object per line**, ending each with a newline. Use these exact keys and units:

```json
{"type":"rfid","uid":"04 A1 B2 C3"}
{"type":"sensors","temperature_c":24.5,"humidity_pct":48.0,"motion":true}
{"type":"mode","mode":"work"}
```

- **Rotary encoder:** use clockwise to select Work and counterclockwise to select Personal. Have the Arduino translate each completed encoder step into one of the explicit mode events below. These select a mode directly, so repeated events never toggle back accidentally.

```json
{"type":"mode","mode":"work"}
{"type":"mode","mode":"personal"}
```

- Mode events apply to the currently selected person. For example, scan Cyril, turn to Work, scan Partner (their own saved mode appears), then turn to Personal. A mode event also wakes the dashboard. The browser reflects hardware changes on its next poll, normally within two seconds.
- The same mode JSON works over USB serial or through the existing local HTTP bridge. In the browser, keep the Personal/Work buttons and M shortcut for software-only testing. No extra RFID card is needed for mode selection.
- Send RFID events on scans; send temperature/humidity at a sensor-appropriate interval (e.g. every 2 seconds for a DHT11), and motion updates regularly.
- A combined object with `uid`, `mode` and sensor fields is also accepted. `type` can be omitted. When both uid and mode are sent, the recognized card selects the person before that person's mode is set. An unassigned card never changes the active person's mode.
- Use numbers for temperature in Celsius and humidity in percent, and JSON `true`/`false` for motion. Use `null` for a failed temperature/humidity read. Do not send Arduino `nan` strings or numeric 0/1 for motion.
- Sensor readings are shared between people. Scanning a card never makes old sensor data fresh.
- Malformed, oversized or startup/debug lines are ignored; the next valid JSON line is processed. Partial serial reads are buffered.

### Option A: USB serial directly into this app

On the computer/Pi physically connected to the Uno, use its Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-hardware.txt
.venv/bin/python -m serial.tools.list_ports
```

On Windows the equivalent Python is `.venv\Scripts\python.exe`. Set your actual device and baud rate in `config.json`:

```json
"sensors": {
  "source": "serial",
  "port": "/dev/ttyACM0",
  "baudrate": 9600,
  "stale_after_seconds": 15,
  "temperature_alert_c": 30,
  "humidity_min_pct": 30,
  "humidity_max_pct": 60,
  "motion_sleep": false,
  "idle_seconds": 120
}
```

Examples of other ports are `/dev/ttyUSB0`, `/dev/serial/by-id/...`, or `COM3` on Windows. Match the sketch's `Serial.begin(...)`. Close the IDE Serial Monitor and other serial readers before starting the mirror. If Linux reports permission denied, ensure the mirror user has access to the device (commonly membership in `dialout`, followed by a new login). Run `.venv/bin/python app.py` so the optional dependency is available. The reader retries after unplug/replug errors.

Keep `demo: true` while mixing fictional accounts with **real** sensor input. The Work panel will label its readings SERIAL. Switch to `demo: false` when using real account data; the software scan buttons will then disappear.

### Option B: an existing local hardware bridge

If your partner already has code reading the hardware, set `sensors.source` to `"http"`. That code can POST the same JSON to **http://127.0.0.1:5000/api/hardware** with `Content-Type: application/json`. The bridge and mirror backend must run on the same computer; this is not a network-exposed endpoint. The HTTP bridge is disabled unless explicitly selected.

### Motion and lost connections

Set `motion_sleep: true` to blank the dashboard after `idle_seconds` without motion. A motion event, recognized card scan, mode selection or **Wake display** restores it. This is a black browser overlay; it does not cut monitor power. Missing/stale motion readings leave the display awake. Missing, invalid or stale temperature/humidity readings show **unavailable**, never a healthy default. A disconnected serial reader exposes an error and retries. Alert limits are configurable demo settings for a shared room; this prototype is not an actual data-center monitoring deployment.

## Google accounts remain separate

The owner identified by `owner_profile_id` (default `cyril`) preserves the existing `private/token.json` and `private/cache.json`. Other profiles use `private/profiles/PROFILE_ID/token.json` and their own cache; they never fall back to the owner's token. Keep the owner id unchanged when renaming/reordering display profiles.

Install `requirements.txt` in a virtual environment. Using your Google Desktop-app OAuth project with Gmail API and Calendar API enabled, put its downloaded client JSON at `private/credentials.json`. Add both intended accounts as test users when required by your OAuth project's testing settings. Stop the mirror and run each authorization on the computer whose browser will complete the sign-in:

```bash
.venv/bin/python google_auth.py --profile cyril
.venv/bin/python google_auth.py --profile partner
```

Choose the correct person's account each time, then set `demo: false`. Scopes stay read-only. A profile can optionally specify a different `calendar_id`. Credentials, tokens, private caches and your local config remain excluded from Git. Work API responses omit personal calendar, inbox, briefing and tasks.

## Message checking and AI

Message check runs locally without a model: it highlights urgency, requests for codes/credentials, payments and external links, and suggests independent verification. The page labels this **rule-based**. It can miss fraud and does not verify senders. Example messages are fictional, with non-working `.invalid` links. Message text is processed in memory; this feature does not save it, open links, or send/modify emails.

The existing AI briefing still uses the configured Ollama server and model. When `demo` is false and `ai_enabled` is true, manually checking a message also requests an optional AI explanation from that server; that text is sent to the configured server. An unavailable model leaves the rule-based result usable. Work handoff notes are generated directly from sensor readings/thresholds and are labeled accordingly. No paid API or new AI provider is enabled.

Run the model on your PC rather than the 2GB Pi. If Ollama is already running on your Windows PC at localhost:11434, you can keep it local and forward it to the Pi using PowerShell (replace the login and IP):

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 11434:127.0.0.1:11434 YOUR_PI_USERNAME@YOUR_PI_IP
```

Keep the terminal and PC awake. The Pi can then retain `ollama_url: "http://127.0.0.1:11434"`. Account connection, physical devices, model generation and your event's sponsor eligibility require their own verification; this change does not claim a working tool-using sponsor agent.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Backend tests cover both people, per-profile workers/storage, mode memory, card mapping, malformed/fragmented serial input, sensor freshness, motion timeout/wake, HTTP origin/input validation, demo isolation, account-data omission in Work mode and message-check behavior.

A browser smoke test is in `tests/browser_smoke.cjs`. With Playwright and its Chromium browser installed, start the demo in another terminal, then run `node tests/browser_smoke.cjs`. Optionally set `MIRROR_TEST_ARTIFACTS` to a directory for screenshots. It exercises profile switching, modes, message examples, simulated incidents, recovery, privacy, typing shortcuts and mobile layouts.

If you already run `smartmirror.service` or `smart-mirror.service`, ensure that service uses this checkout and its Python environment, then restart the existing service. The included `install_service.py` can instead install a per-user `smart-mirror.service`; run it with the venv Python and without sudo. Use only one service/server on port 5000.
