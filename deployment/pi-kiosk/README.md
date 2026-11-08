# Raspberry Pi display startup helper

This is the project's existing installation-specific Chromium kiosk helper for
the Raspberry Pi login **`canetebros`**. It was written for the mirror's display
setup and is retained without changing its username or startup behavior. It
requires Python 3, Chromium, a working user systemd manager, and exactly one
running labwc, Wayfire or LXDE desktop session for that user.

The browser opens **http://127.0.0.1:5000/** on the Pi. The dashboard must already
be running there or be reachable through the existing SSH local port forward
from the Pi to the computer hosting the dashboard (UNO Q in this setup). The
dashboard server and any tunnel must stay running. This helper installs neither
the dashboard service nor the SSH tunnel.

## Install for the existing Pi account

Copy both files to the Pi, sign in to its desktop as `canetebros`, then run from
that directory, without sudo:

```bash
bash install-pi-kiosk.sh
```

The installer checks the current compositor and existing kiosk entries, backs up
the files it changes under `~/smartmirror-startup-backups/`, installs a user
service and helper, and adds the desktop autostart entry. It preserves unrelated
desktop settings and refuses conflicting unmanaged entries. Follow its printed
instructions, then log out and back in or reboot into the desktop. If automatic
desktop login is wanted, configure that separately through Raspberry Pi OS.

The desktop autostart captures the actual display session before starting
`smartmirror-kiosk.service`. Do not run its `session` command from an SSH shell.
The supervisor waits for the dashboard page and `/api/dashboard` to respond,
opens Chromium in kiosk mode with a separate browser profile, and restarts the
browser when necessary. It stops the browser after repeated dashboard failures
and waits for recovery. It does not turn off the monitor or configure screen
blanking.

This package contains the startup source, not evidence that it was installed or
tested on every Pi desktop. For another username or a different dashboard URL,
review and adapt the helper first; its current installation guard intentionally
rejects another login.
