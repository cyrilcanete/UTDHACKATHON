# Smart Mirror — Cyril and Sarah

The Nemotron integration includes `mirror-update` commit `323a218` (personal content, simpler work screens and room warning), retaining its card IDs and UNO Q bridge. It also supports the Uno R3 + Raspberry Pi 4 USB-serial arrangement. Use the transport that matches where your existing hardware code runs; don't change working wiring just to match a reference sketch. The repository's `main` branch still contains the early dashboard; use the integration branch for these features.

## What the mirror does

| Input | Result |
| --- | --- |
| Startup | Black welcome screen with cursive **hello** |
| Cyril's card `F0 E2 E5 5C` | Cyril's Personal screen |
| Sarah's key `87 4B BA 62` | Sarah's Personal screen |
| Half-turn right (default negative deltas) | Personal mode |
| Half-turn left (default positive deltas) | Work mode |
| Quick encoder press, released before 1 second | Request Nemotron analysis of the selected mode |
| Encoder held for 1 second | Welcome; active profile cleared, as the old press did |
| Turn while on welcome | Stays on welcome until a recognized card is scanned |

Every recognized scan returns to Personal. Both Cyril and Sarah have Work mode, with separate assignments and AI results. Sarah retains the internal ID `partner`, preserving existing tokens and caches; the visible name is Sarah. Existing `Partner` display names migrate in memory. RFID selects a profile; it is not strong authentication.

The account demo preserves your supplied presentation: Sarah's ECSW/Calculus briefing and Sunday/Monday schedule, and Cyril's 1pm project briefing with Monday presentation and Tuesday appointment. Schedule stays in place instead of alternating with priorities. Room temperature and humidity appear only at the Work desks, under **In Demo data center** when using training data.

The display is a 1920×1080 canvas scaled to the actual browser viewport, with safe margins, narrow side columns and a clear central mirror area. Long content advances through pages every 14 seconds, without dropping words. When the room needs attention, a centered warning appears and the right column stays on the troubleshooting procedure. The mouse cursor is hidden. The welcome font is bundled locally, with its license, so it needs no internet. Use browser full screen (F or F11); if the monitor itself crops the image even in full screen, disable its overscan / select “Just Scan” or “Screen Fit”.

## Presentation content

Personal mode keeps the schedule fixed, removes the priorities card, and rotates the supplied briefing and inbox content. Sarah has the ECSW/Calculus briefing, Sunday Calculus study and Monday Physics exam; Cyril has the Zoom project briefing, Monday presentation and Tuesday appointment. These are fixed presentation fixtures used in account-demo mode; live account data is not overwritten. Room temperature/humidity appears only in Work mode. Work rotates today’s assignment and recorded power on the left, retains equipment/work history on the right, and fits the full troubleshooting procedure onto one slide. The Source & coverage card and additional evidence/provenance slides have been removed; historical and training labels remain.

## Room attention warning

In Work mode, an out-of-range room reading displays a gently flashing amber warning in the center and pins the complete troubleshooting checklist on the right. Automatic content rotation pauses. The warning stays bright despite PIR idle dimming; reduced-motion settings disable the pulse. If readings become unavailable during an alert, the checklist remains pinned with sensor-recovery guidance. Normal readings clear the warning and resume rotation. Personal mode and the hello screen retain their usual appearance; holding the encoder for one second ends the session.

Laptop test: press 1, Left arrow, then H. The warning and procedure remain displayed. Press O to test lost readings or N to restore normal conditions.

## Try it on your laptop — no hardware required

1. Extract the ZIP into a **new folder**.
2. Open its `UTDHACKATHON` folder.
3. Double-click **OPEN_MIRROR_DEMO.cmd**. Keep that command window running. It opens `http://127.0.0.1:5001`.
4. You should see only **hello**. Press **1** to simulate Cyril's card, or **2** for Sarah.
5. Press **right arrow** for Personal and **left arrow** for Work. Each keyboard press simulates a completed half-turn.
6. Press **Escape** to simulate the knob's long hold. Turn again: it stays on welcome until another card scan. **A** is the keyboard equivalent of a quick press when Nemotron is enabled.
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
{"type":"encoder","action":"analyze"}
{"type":"encoder","action":"press"}
{"type":"sensors","temperature_c":24.0,"humidity_pct":48.0,"motion":true}
```

`direction: "right"`, `"left"`, `"decrement"` and `"increment"` are also accepted instead of delta. Debounce the button and send one event per completed detent (click), not per quadrature edge. Send scans separately from mode events. Explicit direct `mode` events remain supported and switch immediately; firmware must emit encoder detents to use the half-turn threshold.

### Quick press and long hold

The supplied headers use your earlier wiring plan: **encoder CLK D2, DT D3, SW D4; DHT11 DATA D7; PIR OUT D6**. The RC522 remains on SS D10, RST D5 and SPI D11–D13.

The updated reference firmware debounces the switch for **40 ms**. A press released before **1,000 ms** emits `action: "analyze"` once on release. A hold reaching **1,000 ms** emits the existing `action: "press"` once and returns to welcome; releasing it does not also request analysis. A switch held during startup is ignored until it has been released. Rotation and wiring remain the same.

The backend routes a quick press through the same asynchronous queue as `/api/nemotron/run`, regardless of whether events arrive through UNO Q, serial or the local HTTP bridge. Work reviews the active technician's evidence. Personal reviews that profile's selected suspicious message; Cyril's current clean-inbox fixture has no selected message, so it reports that no analysis is needed. Repeated taps while a job is queued or running keep the same job. When analysis cannot start, the display gives a brief reason. A tap on welcome never selects a profile.

**A backend update alone cannot distinguish tap from hold.** The old sketch reports only the button going down, with no release or duration. Its legacy `press` events keep returning to welcome until the firmware is updated. For your UNO Q setup, update the App Lab Python callbacks using the setup command below, then merge the button state machine and `on_mirror_analyze` callback into your tested sketch (or use the supplied sketch after matching its pins). Restart App Lab and the backend. Keep the Pi kiosk and its existing port-5000 SSH tunnel.

### Calibrate the half-turn

The default assumes **20 detents per full revolution**, so **10 consecutive right clicks select Personal** and **10 consecutive left clicks select Work**. A reversal resets partial progress; a scan, completed switch, quick press or long hold also resets it. Turning on welcome does not select anyone. This is relative half-turn travel, not an absolute knob position.

Count your module's clicks in one full revolution. If it has a different even count, run this in the project folder, replacing 20 with that count:

```bash
python3 configure_encoder.py --detents-per-revolution 20 --right-delta -1
```

If a physical right turn emits positive deltas, use `--right-delta 1`. The helper backs up configuration and changes only encoder calibration, preserving working RFID, sensor and account settings. Restart the existing backend afterwards. Actual 180-degree travel depends on calibrating the real module; no physical calibration was performed here.

**If your badges and sensors already work, keep their setup and pin assignments.** Updating the backend is enough for existing detent events. The new tap/hold distinction also needs the firmware button change described above. The setup commands below are for a transport that still needs configuring.

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

The optional `hardware/uno_r3_mirror/uno_r3_mirror.ino` integrates RC522, encoder, DHT11 and PIR. It needs the Arduino libraries **MFRC522**, **DHT sensor library**, and **Adafruit Unified Sensor**. Pins follow the earlier wiring plan: RC522 SS10/RST5/SPI11–13, encoder CLK2/DT3/SW4, DHT7, PIR6. **Check the constants in mirror_inputs.h against the installed wiring before uploading.** It has not been compiled or physically tested on your board here. Calibrate direction with `configure_encoder.py` rather than replacing working firmware.

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
Bridge.notify("on_mirror_analyze");     // quick press, on debounced release
Bridge.notify("on_mirror_press");       // one-second hold, once per hold
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

Cyril's training inbox shows **3 unread** and **No phishing terms detected**, with no message selected for Nemotron review. Sarah's training inbox shows **2 unread** and the supplied **T-Mobile Identity Management** scenario, highlighting `t-mobile-okta-security.com` and **by EOD**. The domain is plain text, never a clickable link. The recommended action is to ignore the message, sign in through saved employee bookmarks, and report it. These are fictional demonstration messages, not a reputation check of that domain, a live-inbox audit, or a real T-Mobile security alert. The app does not visit links, download attachments, send messages, delete mail or mark messages read. Reviewed live-account excerpts are limited to 650 characters; six-to-eight-digit numbers are redacted. Subjects, senders and excerpts are displayed in Personal mode and may be cached privately. Personal Nemotron review sends these selected fields to NVIDIA only when explicitly enabled below. No match does not mean an email is safe.

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
- An optional real Nemotron analysis using the data tools described below.

Recent sample ranges, sample counts, missing-value information, and source attribution remain available to the evidence tools. The presentation keeps the historical timestamp in its header while using fewer rotating cards.

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

The integration uses NVIDIA's hosted endpoint `https://integrate.api.nvidia.com/v1/chat/completions` and model **`nvidia/nemotron-3.5-lightning-30b-a3b`**. Your existing backend host runs the Python client; NVIDIA runs the model. If the UNO Q serves `app.py` and the Pi is a kiosk through an SSH tunnel, run these commands on the **UNO Q**. If the Pi serves `app.py`, run them on the **Pi**. No model weights, CUDA, LangGraph, or new Python packages are required for this client.

**Availability checked November 8, 2026:** the [Lightning catalog page](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b) lists its free endpoint as available. The earlier [`nemotron-3-nano-30b-a3b` page](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b) now lists its free endpoint as deprecated. Access still depends on your account and quota. The launcher selects Lightning by default; an explicit `--model` can select another tool-capable Nemotron model your NVIDIA account offers. It never switches providers or activates billing.

1. Open the [Lightning model page](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b), sign in, and use **Generate API Key** (or the **View Code** flow shown in the sponsor PDF).
2. In the updated project folder, check the setup without a network request or any changes:

```bash
.venv/bin/python configure_nemotron.py --check
```

3. Test the actual hosted model using labelled synthetic technician/message fixtures and the historical ESIF excerpt. This does not modify configuration, read account caches, or write real incident records:

```bash
.venv/bin/python configure_nemotron.py --test --personal
```

4. Stop the existing backend process (Ctrl+C in its terminal, or stop the service that actually runs it). Then start the sponsor demonstration on the same port used by your kiosk/tunnel:

```bash
.venv/bin/python configure_nemotron.py --start --personal --synthetic --port 5000
```

The key prompt hides what you type. Paste the key **only into that local prompt**, then press Enter. If `NVIDIA_API_KEY` is already set in that process, it is reused. The key stays in process memory; it is not saved to configuration or source code. An interactive launcher exits when the terminal closes. A systemd service must receive its own `NVIDIA_API_KEY` environment setting to use the API after a restart; a key entered in a different terminal does not configure the service.

The launcher prints each tool as its result returns, followed by **LIVE NEMOTRON TEST PASSED** and, with `--personal`, **LIVE PERSONAL TOOL TEST PASSED**. Only successful tests lead to configuration changes and startup. It backs up existing `config.json`, preserves RFID, sensor transport, calibration, thresholds, private files, and other settings, then enables the selected workflows.

`--synthetic` makes account/messages fictional for the T-Mobile sponsor demonstration, while preserving the configured hardware source. A DHT11 connected through `uno_q`, `serial`, or `http` still supplies real local room readings. Fictional work records remain labelled training; historical ESIF power data remains labelled historical. This flag does not create real customer data or claim a connection to live data-center equipment.

On Windows, double-click **START_MIRROR_NEMOTRON.cmd** for the same synthetic-account demonstration at **http://127.0.0.1:5001**, or substitute `py` for `.venv/bin/python` in the commands. The ordinary **OPEN_MIRROR_DEMO.cmd** explicitly disables NVIDIA calls and simulates the sensors; use the Nemotron launcher for an API demonstration.

Omit `--personal` for Work-only integration. Outside the sponsor demonstration, omitting `--synthetic` preserves the existing account-data setting. With live accounts and explicit `--personal`, selected suspicious-message subjects, senders, and excerpts are sent to NVIDIA. The 2026 T-Mobile track requires synthetic messages/scenarios, so use `--synthetic` when demonstrating that track.

### Run and inspect a workflow

Scan Cyril's or Sarah's card and turn half a turn left for Work or right for Personal. The side panel shows whether Nemotron is off, ready, running, complete, stale, or unavailable. Tool activity comes from actual returned tool calls; it is not a scripted success animation. The display shows the chosen model and a human-readable progress trace, without model reasoning text.

**Quick-press the encoder** to request analysis of the active mode. On a laptop, press **A**, or choose **Analyze with Nemotron** in the **D** control panel. The request queues background work and does not freeze the dashboard. The server rejects requests when the integration is disabled, no profile is selected, or Personal review has not been enabled. Repeated clicks while a run is in progress do not create additional runs. Hold the encoder for one second (or press **Escape**) to return to welcome.

Fresh completed answers move to the front of the display. During a work warning, the right pane remains on the troubleshooting checklist and the AI answer uses the left pane. When measurements change, an old recommendation is hidden until a matching analysis is available. API-key, access, rate-limit, connection, incomplete-tool, and timeout errors remain distinct, while the local readings and procedures continue to work.

### What Nemotron actually does

In Work mode, the model requests seven read-only tools:

1. `read_datacenter_metrics`: latest actual ESIF values, timestamp and missing-value flags.
2. `read_datacenter_history`: recent observations and sample statistics for comparison.
3. `read_local_environment`: separately labelled room readings from your DHT11.
4. `lookup_data_provenance`: attribution, historical coverage and an on-demand check of the dataset's registered DOI through the public DataCite API.
5. `lookup_equipment`: asset identity, location and relationship to the readings.
6. `lookup_work_orders`: assigned and related orders, with existing notes and status.
7. `lookup_procedure`: troubleshooting steps and verification requirements.

A completed Work answer requires all seven tools. The prompt asks the model to combine readings, asset information, work history and procedure, then choose a specific next step. Historical and training labels remain explicit.

The provenance tool makes a real read-only `GET` to `https://api.datacite.org/dois/10.7799/3015212` when the model requests it. It sends only the fixed public DOI request, with no NVIDIA key or personal/sensor data. The response must match the DOI; the client bounds its size and timeout and refuses redirects. A successful check identifies the registered dataset and publisher. Its metadata update/check times are separate from the historical observation time. It does not validate the measurements, make them current, or connect to live facility monitoring. An unavailable registry produces an explicit unavailable result alongside the cached source information. Repeated provenance requests within a workflow reuse the same check. See the [DataCite Public API documentation](https://support.datacite.org/docs/api).

In Personal mode, the model requests four tools: `get_selected_message`, `inspect_warning_signs`, `lookup_verification_guidance` and `recommend_safer_action`. It receives their actual results and chooses a safe next action. All four are required before a final answer is accepted. A trace records returned tools; local rule-based results are never labelled Nemotron output.

Unknown tools/arguments and incomplete tool loops fail back to the deterministic display. Tool access is read-only and bounded; no tool controls hardware, follows message links, sends messages or changes tickets. Email text is treated as untrusted content. AI results stay scoped to the selected profile; Personal results also require the same inbox fingerprint.

Automatic calls run in the background in the active mode, at most once per five minutes per profile/workflow when evidence changes. Explicit quick presses or **A** requests can start a new review sooner, subject to the server's ten-second cooldown. Failed automatic calls can retry after their interval. Each workflow has a configurable 120-second overall budget, a 45-second per-request timeout, a nine-request cap, and a bounded tool-call count. A model that answers before gathering the required evidence gets one correction; incomplete or truncated results are rejected. No automatic provider fallback occurs. Generated answers show their generation time and remain scoped to the profile and captured evidence. The historical ESIF timestamp is always kept separate.

**Validation limit:** automated tests cover the protocol, tool results, parsing and error paths using mocked NVIDIA responses. No NVIDIA account key was available in this development session, so this package does not claim a successful hosted inference call. The local launcher provides that verification step using your account.

[NVIDIA API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer) · [NVIDIA hosted tool-calling configuration](https://docs.nvidia.com/nemo/labs-voice-agent/about/core-concepts/language-models/llm-backends/) · [HackUTD 2026 sponsor challenges](https://zeroday.hackutd.co/).

The NVIDIA sponsor PDF lists `build.nvidia.com`, OpenRouter, and open weights as access options. Its Brev credit instructions and LangGraph/RAG workshops are optional starting points; they do not require a GPU instance for this hosted-client design. The seven Work tools demonstrate a model requesting evidence, receiving tool results, checking provenance through an external service, and producing a technician handoff. The four Personal tools demonstrate the same loop with a synthetic message, warning signals, verification guidance, and a safer next step. This is a bounded evidence-review workflow: the required tool checklist is fixed, while the model selects tool order/grouping and interprets the results to propose a next step. These workflows are designed for the NVIDIA/NMC²/T-Mobile themes; qualification and judging remain with the event organizers.

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

`tests/test_firmware_button.py` also compiles both actual input headers with host `g++` when available and tests debounce, short/long presses, release bounce, boot-held input and timer wraparound. Its Arduino/DHT stubs make it a logic check, not a complete Arduino board build or physical hardware test. The backend tests exercise analysis events through serial framing, the UNO Q event journal and the local HTTP bridge. A real board upload and switch check are still required.

Restart your existing mirror service after updating its checkout. The supplied `install_service.py` optionally installs a per-user service; use only one server on port 5000. This update does not install a second service or change your existing boot/tunnel setup automatically.
