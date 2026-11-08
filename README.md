# Smart Mirror — Cyril and Sarah

This update is based on your merged `mirror-update` commit `b2f1229`, retaining its card IDs and UNO Q bridge. It also supports the Uno R3 + Raspberry Pi 4 USB-serial arrangement. Use the transport that matches where your existing hardware code runs; don't change working wiring just to match a reference sketch.

## What the mirror does

| Input | Result |
| --- | --- |
| Startup | Black welcome screen with cursive **hello** |
| Cyril's card `F0 E2 E5 5C` | Cyril's Personal screen |
| Sarah's key `87 4B BA 62` | Sarah's Personal screen |
| Half-turn right (default negative deltas) | Personal mode |
| Half-turn left (default positive deltas) | Work mode |
| Encoder press | Welcome; active profile cleared |
| Turn while on welcome | Stays on welcome until a recognized card is scanned |

Every recognized scan returns to Personal. Both Cyril and Sarah have Work mode, with separate assignments and AI results. Sarah retains the internal ID `partner`, preserving existing tokens and caches; the visible name is Sarah. Existing `Partner` display names migrate in memory. RFID selects a profile; it is not strong authentication.

The display is a 1920×1080 canvas scaled to the actual browser viewport, with safe margins, narrow side columns and a clear central mirror area. Long content advances through pages every 14 seconds, without dropping words. The mouse cursor is hidden. The welcome font is bundled locally, with its license, so it needs no internet. Use browser full screen (F or F11); if the monitor itself crops the image even in full screen, disable its overscan / select “Just Scan” or “Screen Fit”.

## Try it on your laptop — no hardware required

1. Extract the ZIP into a **new folder**.
2. Open its `UTDHACKATHON` folder.
3. Double-click **OPEN_MIRROR_DEMO.cmd**. Keep that command window running. It opens `http://127.0.0.1:5001`.
4. You should see only **hello**. Press **1** to simulate Cyril's card, or **2** for Sarah.
5. Press **right arrow** for Personal and **left arrow** for Work. Each keyboard press simulates a completed half-turn.
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

`direction: "right"`, `"left"`, `"decrement"` and `"increment"` are also accepted instead of delta. Debounce the button and send one event per completed detent (click), not per quadrature edge. Send scans separately from mode events. Explicit direct `mode` events remain supported and switch immediately; firmware must emit encoder detents to use the half-turn threshold.

### Calibrate the half-turn

The default assumes **20 detents per full revolution**, so **10 consecutive right clicks select Personal** and **10 consecutive left clicks select Work**. A reversal resets partial progress; a scan, completed switch or push also resets it. Turning on welcome does not select anyone. This is relative half-turn travel, not an absolute knob position.

Count your module's clicks in one full revolution. If it has a different even count, run this in the project folder, replacing 20 with that count:

```bash
python3 configure_encoder.py --detents-per-revolution 20 --right-delta -1
```

If a physical right turn emits positive deltas, use `--right-delta 1`. The helper backs up configuration and changes only encoder calibration, preserving working RFID, sensor and account settings. Restart the existing backend afterwards. Actual 180-degree travel depends on calibrating the real module; no physical calibration was performed here.

**If your badges and sensors already work, keep their setup and firmware.** Updating the backend is enough when your firmware already emits one encoder delta per detent. The setup commands below are for a transport that still needs configuring.

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

The optional `hardware/uno_r3_mirror/uno_r3_mirror.ino` integrates RC522, encoder, DHT11 and PIR. It needs the Arduino libraries **MFRC522**, **DHT sensor library**, and **Adafruit Unified Sensor**. Reference pins: RC522 SS10/RST5/SPI11–13, encoder CLK2/DT3/SW6, DHT4, PIR7. **Match the constants in mirror_inputs.h to your verified wiring before uploading.** It has not been compiled or physically tested on your board here. Calibrate direction with `configure_encoder.py` rather than replacing working firmware.

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

Cyril's training inbox contains a **free-prize claim**; Sarah's contains an **account verification request**. The display shows the actual message excerpt, underlines warning phrases, explains the pressure/payment/code-sharing signals, and gives a specific next action through the official app or known contact. It does not visit links, download attachments, send messages, delete mail or mark messages read. Reviewed excerpts are limited to 650 characters; six-to-eight-digit numbers are redacted. Subjects, senders and excerpts are displayed in Personal mode and may be cached privately. Personal Nemotron review sends these selected fields to NVIDIA only when explicitly enabled below. No match does not mean an email is safe.

Reference guidance: [FTC phishing advice](https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams). The UI labels local rules honestly; this is not a trained fraud classifier.

## Work: technician workflow for Cyril and Sarah

The account-demo presentation includes a concrete, labelled training case for cooling unit **CRAC-02**. Cyril receives **WO-203**, investigating rising temperature; Sarah receives **WO-204**, validating humidity and the sensor. Both can review the related **WO-198** filter/airflow inspection. The workflow combines current room readings, equipment context, prior notes, a troubleshooting checklist and a specific next action. Missing readings block diagnosis; a possible cause is never presented as a confirmed failure.

The checklist asks the technician to verify sensor location and freshness, compare an independent instrument, review related work, inspect accessible airflow paths and record/escalate findings. It is a project checklist, not a manufacturer-approved service procedure. No external work order is created or closed.

These equipment/work-order records are **fictional training records**, separate from the real historical ESIF measurements. With `demo: false`, the default is the actual local DHT11 station and an empty work-order list. Authorized facility records can be supplied through the `facility` configuration (`asset`, `work_orders`, `procedures`); the public ESIF source supplies none of those records.

## Work: real ESIF data-center measurements

The equipment example has been replaced in the display with an attributed excerpt from **ESIF High-Performance Computing Data Center** power measurements, published in the [NLR Data Catalog](https://data.nlr.gov/submissions/300), DOI **10.7799/3015212**. The source archive was actually downloaded and processed for this update.

**These are historical measurements, not a live connection.** The latest source observation is **2025-08-29 04:35:08 UTC** (August 28 at the facility's recorded local offset). The screen always labels historical data and displays the observation timestamp. It does not turn the download date or today's clock into a measurement date.

The excerpt includes 168 observations: the latest available row per UTC hour from the last 168 observed hours. It preserves original values and nulls, without interpolation. Work mode displays:

- PUE (Power Usage Effectiveness), as published in the dataset.
- IT equipment power, cooling power, HVAC power and pump power, in kW.
- Recent sample ranges, sample counts, missing values and source attribution.
- An optional real Nemotron analysis using the data tools described below.

For example, the latest record contains IT power **2163.753217351079 kW** and PUE **1.074413627331888**. These are observed source values, not fabricated demo numbers. They are not a claim about current operations or a diagnosed fault.

The DHT11 still measures **your local mirror room**. Its readings, local alerts and local incident journal remain separate from ESIF. The training case explicitly states its assumed use of the room readings. The public dataset supplies no rack inventory, work orders or failure labels; training records are never attributed to ESIF. No messages or external tickets are sent.

### Source provenance and rebuilding

`data/esif_power_excerpt.json` includes the source URL, resource URL, DOI, authors, retrieval timestamp, input archive SHA-256, full source time span, row count and selection method. The import processed **4,569,543 source rows**. The full dataset license is preserved in `data/ESIF_LICENSE.txt`; credit DOE/NREL/ALLIANCE and the dataset authors when presenting the data. They do not endorse this project.

To rebuild from the official archive, download **ESIF DC Power Metrics Timeseries Data (Zipped CSV)** from the source page (about 97 MB), then run:

```powershell
py tools/import_esif_data.py "C:\path\to\esif.influx.buildingData.PUE.combined.csv.zip"
```

The importer uses bounded memory and the Python standard library. The app loads only the small excerpt. Restart the app after rebuilding. If the source file is missing or invalid, the screen reports unavailable; it never silently substitutes example measurements. This package does not have access to a private/live data-center monitoring API. A live deployment needs that facility's authorized feed.

### Connect real NVIDIA Nemotron locally

The integration uses NVIDIA's hosted endpoint `https://integrate.api.nvidia.com/v1/chat/completions` and model `nvidia/nemotron-3-nano-30b-a3b`. The Pi runs the Python client; NVIDIA runs the model. This avoids trying to load a large model into Pi memory.

1. Sign in at the [official NVIDIA model page](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b) and obtain an API key for your account. Check the quota/billing terms shown there; availability is account-dependent.
2. Stop the old mirror Python window with Ctrl+C.
3. Inside the updated project folder on Windows, double-click **START_MIRROR_NEMOTRON.cmd**.
4. Paste your key at the hidden local prompt and press Enter. No characters should appear. Do not paste the key into chat or commit it.
5. The launcher tests both real tool workflows. Only after successful results does it enable both integrations in a backed-up local `config.json` and launch the mirror at **http://127.0.0.1:5001**. Open/refresh that page, scan a card (or press 1/2 in account-demo mode), and turn a half-turn left for Work.

On the Pi/backend host, run the equivalent from the project's environment:

```bash
.venv/bin/python configure_nemotron.py --start --personal --port 5000
```

For a test only, use `py configure_nemotron.py --test`. A successful test prints **LIVE NEMOTRON TEST PASSED** and the tools used. A failed key, quota issue or incomplete workflow is reported honestly. The key is held in this process's environment, not saved to disk. To restart later, use the launcher again or configure `NVIDIA_API_KEY` securely for your existing service.

The setup preserves card assignments, sensor transport, private account files and other settings. Work analysis sends historical ESIF data and the labelled local technician context to NVIDIA. **The Windows launcher and `--personal` also enable sending selected suspicious-message subjects, senders and excerpts to NVIDIA.** Omit `--personal` to enable Work only. Existing configurations do not silently opt in to personal review. Account-demo mode uses fictional messages; live Google mode uses the selected person's real messages. The ordinary **OPEN_MIRROR_DEMO.cmd** explicitly disables NVIDIA calls, even if local configuration enables them.

### What Nemotron actually does

In Work mode, the model requests seven read-only tools:

1. `read_datacenter_metrics`: latest actual ESIF values, timestamp and missing-value flags.
2. `read_datacenter_history`: recent observations and sample statistics for comparison.
3. `read_local_environment`: separately labelled room readings from your DHT11.
4. `lookup_data_provenance`: attribution, historical coverage and limitations.
5. `lookup_equipment`: asset identity, location and relationship to the readings.
6. `lookup_work_orders`: assigned and related orders, with existing notes and status.
7. `lookup_procedure`: troubleshooting steps and verification requirements.

A completed Work answer requires all seven tools. The prompt asks the model to combine readings, asset information, work history and procedure, then choose a specific next step. Historical and training labels remain explicit.

In Personal mode, the model requests four tools: `get_selected_message`, `inspect_warning_signs`, `lookup_verification_guidance` and `recommend_safer_action`. It receives their actual results and chooses a safe next action. All four are required before a final answer is accepted. A trace records returned tools; local rule-based results are never labelled Nemotron output.

Unknown tools/arguments and incomplete tool loops fail back to the deterministic display. Tool access is read-only and bounded; no tool controls hardware, follows message links, sends messages or changes tickets. Email text is treated as untrusted content. AI results stay scoped to the selected profile; Personal results also require the same inbox fingerprint.

Calls run in the background in the active mode, at most once per five minutes per profile/workflow when evidence changes. Failed calls can retry after that interval. Generated answers show their generation time; local readings can change afterwards. The historical ESIF timestamp is always kept separate. Model output is labelled as AI guidance for review.

**Validation limit:** automated tests cover the protocol, tool results, parsing and error paths using mocked NVIDIA responses. No NVIDIA account key was available in this development session, so this package does not claim a successful hosted inference call. The local launcher provides that verification step using your account.

[NVIDIA API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-nano-30b-a3b-infer).

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
