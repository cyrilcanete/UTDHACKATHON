# Smart Mirror — Cyril and Sarah

This update is based on `mirror-update` commit `b8affb9`, retaining its card IDs and UNO Q bridge. It also supports the Uno R3 + Raspberry Pi 4 USB-serial arrangement. Use the transport that matches where your existing hardware code runs; don't change working wiring just to match a reference sketch.

## What the mirror does

| Input | Result |
| --- | --- |
| Startup | Black welcome screen with cursive **hello** |
| Cyril's card `F0 E2 E5 5C` | Cyril's Personal screen |
| Sarah's key `87 4B BA 62` | Sarah's Personal screen |
| Right / negative encoder delta | Work mode |
| Left / positive encoder delta | Personal mode |
| Encoder press | Welcome; active profile cleared |
| Turn while on welcome | Stays on welcome until a recognized card is scanned |

Every recognized scan returns to Personal. Sarah retains the internal ID `partner`, preserving existing tokens and caches; the visible name is Sarah. Existing `Partner` display names migrate in memory. RFID selects a profile; it is not strong authentication.

The display is a 1920×1080 canvas scaled to the actual browser viewport, with safe margins, narrow side columns and a clear central mirror area. Long content advances through pages every 14 seconds, without dropping words. The mouse cursor is hidden. The welcome font is bundled locally, with its license, so it needs no internet. Use browser full screen (F or F11); if the monitor itself crops the image even in full screen, disable its overscan / select “Just Scan” or “Screen Fit”.

## Try it on your laptop — no hardware required

1. Extract the ZIP into a **new folder**.
2. Open its `UTDHACKATHON` folder.
3. Double-click **OPEN_MIRROR_DEMO.cmd**. Keep that command window running. It opens `http://127.0.0.1:5001`.
4. You should see only **hello**. Press **1** to simulate Cyril's card, or **2** for Sarah.
5. Press **right arrow** for Work and **left arrow** for Personal.
6. Press **Escape** to simulate pushing the knob. Turn again: it stays on welcome until another card scan.
7. In Work, press **H** for hot conditions, **O** for missing sensor data, or **N** for normal readings.
8. Press **D** to open/close the laptop demo button panel. Press **F** for full screen.

The launcher deliberately forces fictional accounts and simulated sensors; it never contacts Google, Ollama or Nemotron. The clean mirror screen has no permanently visible demo buttons. On Linux, use `MIRROR_DEMO=1 python3 app.py`, then port 5000.

To copy this update into your existing Windows clone, double-click **COPY_UPDATE_TO_REPO.cmd** in the extracted folder. It defaults to `%USERPROFILE%\Downloads\UTDHACKATHON-git`, asks for another path if needed, backs up changed source files, and preserves `config.json`, `private/`, `.git/` and `.venv/`. It does not commit or push. Afterwards, review `git diff` and commit your source changes normally. Stop the old server and run the updated copy, not another extracted folder.

## HC-SR501 motion brightness

The existing PIR input now controls **displayed content brightness** automatically, including the hello screen. Motion makes it fully bright. After 60 seconds without reported motion it fades to 20% brightness. Card scans and knob input also brighten it. Motion alone never selects a person or exits welcome. Missing/stale PIR data leaves it fully bright so a disconnected sensor cannot strand it dimmed.

This is a browser brightness effect, not monitor-backlight control or monitor power saving. A PIR detects movement, not exact distance or a motionless person's presence. The countdown begins after the sensor stops reporting motion; its own hardware hold time can delay that. Keep sending the current `motion` boolean regularly, as the supplied sketches already do. No wiring changes are required if PIR data is already reaching the app.

These defaults also apply to old configs that omit the new settings. Adjust these fields inside `sensors` if desired:

```json
"motion_dimming": true,
"dim_after_seconds": 60,
"dim_brightness": 0.2
```

Leave `motion_sleep` false for dimming without the older sleep behavior. Laptop demo: **I** simulates the completed idle timeout immediately; **B** simulates movement and brightens it. Both are also in the **D** demo panel. Actual hardware always uses the configured timeout.

## Real hardware: exact event protocol

The backend accepts one JSON object per line over USB serial, or the same object through the explicitly enabled local HTTP bridge. Existing direct `mode` events remain supported.

```json
{"type":"rfid","uid":"F0 E2 E5 5C"}
{"type":"encoder","delta":-1}
{"type":"encoder","delta":1}
{"type":"encoder","action":"press"}
{"type":"sensors","temperature_c":24.0,"humidity_pct":48.0,"motion":true}
```

`direction: "right"` / `"decrement"` and `"left"` / `"increment"` are also accepted instead of delta. Debounce the button and send one event per completed detent. Explicit `{"type":"mode","mode":"welcome"}` is also accepted for older bridge code. Send scans separately from mode events.

Send DHT11 temperature in **Celsius**, humidity in **percent**, and motion as JSON true/false. Send `null` for failed readings; never send `nan`, fake normal values or boolean numbers. The reference sketches sample about every 2.2 seconds. Values older than 15 seconds (configurable) become unavailable. Card/encoder events never refresh sensor timestamps. Weather is separately labelled outdoors in Fahrenheit.

### Uno R3 connected to the Pi by USB

On the Pi, in the updated project folder:

```bash
.venv/bin/python -m pip install -r requirements-hardware.txt
.venv/bin/python -m serial.tools.list_ports
```

Use the **actual device listed**, for example:

```bash
.venv/bin/python configure_hardware.py --source serial --port /dev/ttyACM0 --baud 9600
.venv/bin/python app.py
```

The configuration helper backs up existing config, preserves account/card settings and selects real sensor input. Account data remains demo data unless you add `--live-accounts`. Do **not** use OPEN_MIRROR_DEMO.cmd when testing real sensors. Close Arduino Serial Monitor so only the mirror reads the serial port.

The optional `hardware/uno_r3_mirror/uno_r3_mirror.ino` integrates RC522, encoder, DHT11 and PIR. It needs the Arduino libraries **MFRC522**, **DHT sensor library**, and **Adafruit Unified Sensor**. Reference pins: RC522 SS10/RST5/SPI11–13, encoder CLK2/DT3/SW6, DHT4, PIR7. **Match the constants in mirror_inputs.h to your verified wiring before uploading.** It has not been compiled or physically tested on your board here. If physical right reports a positive delta, flip `REVERSE_ENCODER`; the dashboard consistently maps negative to Work.

### Existing UNO Q App Lab + Pi display arrangement

The prior branch uses UNO Q RouterBridge and a shared event journal. This update preserves that route and extends it for sensors/encoder. On the UNO Q, stop the dashboard and App Lab app, then run:

```bash
.venv/bin/python setup_uno_q_rfid.py --app-path "$HOME/ArduinoApps/rfid_test"
.venv/bin/python configure_hardware.py --source uno_q
```

Use your actual App Lab app path. Setup backs up/replaces Python callbacks and keeps your MCU sketch intact. To integrate with your already-verified sensor sketch, emit these callbacks:

```cpp
Bridge.notify("on_mirror_encoder", -1); // right
Bridge.notify("on_mirror_encoder", 1);  // left
Bridge.notify("on_mirror_press");       // debounced press
Bridge.notify("on_mirror_sensors", temperatureC, humidityPercent, motion);
```

The existing `on_rfid_uid` callback is unchanged. For a failed DHT value, the supplied UNO Q sketch sends `-999.0f`, which the Python callback converts to null. The updated reference sketch and dependencies are in `hardware/uno_q_rfid/sketch/`; review its pin constants before replacing a tested sketch. Restart App Lab and the dashboard. Both must run for input to reach the display. Existing SSH forwarding to dashboard port 5000 can remain in use. The callbacks skip historical events at startup, so scan again after restarting.

### Existing HTTP hardware reader

Select `python3 configure_hardware.py --source http`. POST the event JSON to `http://127.0.0.1:5000/api/hardware` with `Content-Type: application/json`, from the same host as the backend. This endpoint is disabled for other sources. No new public network listener is opened.

## Personal: explain suspicious inbox messages

With live Google accounts connected, every inbox refresh (about five minutes) also performs this **read-only** Gmail search:

```text
in:inbox newer_than:30d {free "last chance" "act now" urgent "verification code" "gift card"}
```

It reviews up to 10 search matches, including read messages. It explains matched phrases, pressure, requests for credentials/codes, money and links, then suggests independent verification through a known official channel. A keyword is a review signal, not proof of phishing. “Free” by itself is common in legitimate promotions. The search is limited, not a full inbox/security audit.

Example: **“Last chance! Act now to claim your free prize. Pay a processing fee and send your verification code.”** The demo explains the pressure, payment and code-sharing signals. It does not visit links, download attachments, send messages, delete mail or mark messages read. Message bodies stay backend-side; subject/sender and short matched phrases are displayed and may be cached privately. No match does not mean an email is safe.

Reference guidance: [FTC phishing advice](https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams). The UI labels local rules honestly; this is not a trained fraud classifier.

## Work: from sensor readings to an operator handoff

Work mode combines fresh environmental readings, configured equipment context, related work orders and verification steps. Out-of-range or missing readings create a **local incident record** with evidence and an ID. Repeat polling does not create duplicate incidents. Recovery is recorded as needing operator review, not proof a repair occurred. Demo records stay in memory; live records are stored in `private/incidents.json`. Nothing is sent to a ticket system or another person. Old records are bounded to 100.

Add a `facility` object to your existing config to replace the explicitly labelled example room context:

```json
"facility": {
  "asset": {"id": "ROOM-01", "name": "Project room", "depends_on": ["Nearby equipment"]},
  "work_orders": [{"id": "WO-001", "asset_id": "ROOM-01", "summary": "Inspect room ventilation", "status": "open"}],
  "procedures": ["Verify with a second reading.", "Check visible airflow obstructions.", "Notify the responsible operator if conditions persist."]
}
```

These are **your configured records**, not a claimed live CBRE/equipment-system integration. A DHT11 cannot diagnose a failed component or prove a cascading failure.

### Optional Nemotron workflow

`nemotron_agent.py` implements a bounded NIM-compatible tool loop using `read_environment`, `lookup_asset`, `lookup_work_orders` and `lookup_procedure`. A completed result requires all four tools. Unknown tools/arguments and incomplete workflows are rejected; failures leave the local rules visible. The agent has no inbox, messaging or equipment-control tools. Requests run in the background, only in live Work mode with changed sensor evidence, at most once per five minutes.

It is **disabled by default**, makes no paid calls in this delivery and has only been tested with mocked model responses. To use your provisioned endpoint later, set `nemotron.enabled: true`, `nemotron.endpoint` to its complete chat/completions URL, and `nemotron.model` to its actual Nemotron model ID. Set `NVIDIA_API_KEY` in the server environment if your endpoint needs it; never commit keys. Check your provider's access/billing before enabling. Do not claim a live NVIDIA demonstration until you have verified it with your endpoint. [NVIDIA tool calling documentation](https://docs.nvidia.com/nim/large-language-models/1.15.0/function-calling.html).

## Separate Google accounts and existing AI briefing

Keep your existing `config.json` and `private/`. The owner (`owner_profile_id: "cyril"`) keeps `private/token.json`; Sarah keeps `private/profiles/partner/token.json`. No fallback to the other person's account is allowed. Welcome and Work API responses omit personal inbox/calendar/briefing/tasks.

Install `requirements.txt` in your virtual environment. With Gmail and Calendar APIs enabled in your Google Desktop-app OAuth project, put the downloaded client JSON at `private/credentials.json`. Authorize each profile using its correct account:

```bash
.venv/bin/python google_auth.py --profile cyril
.venv/bin/python google_auth.py --profile partner
```

Then set `demo: false` or use `configure_hardware.py --source ... --live-accounts`. Scopes stay read-only. Google setup and network availability are needed for real messages; demo examples work without either.

The existing `ai_enabled`, `ollama_url` and `ollama_model` settings still control the optional personal briefing. Model execution belongs on a capable PC/server, not a large model on the Pi. AI is separate from the local phishing rules and disabled by default.

## Tests and restart

```bash
python3 -m unittest discover -s tests -v
```

With Playwright and Chromium installed: `node tests/browser_smoke.cjs`. The test starts its own demo backend on port 5091, exercises the session flow and checks 1920×1080, 1920×1000 and 1366×768 viewports, cursor/font, missing sensors, and long-text pagination. `CHROMIUM_EXECUTABLE_PATH` can select an installed browser.

Restart your existing mirror service after updating its checkout. The supplied `install_service.py` optionally installs a per-user service; use only one server on port 5000. This update does not install a second service or change your existing boot/tunnel setup automatically.
