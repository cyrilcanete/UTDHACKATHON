"""Install a per-user Linux service; run with your venv Python, without sudo."""
from pathlib import Path
import subprocess
import sys

base = Path(__file__).resolve().parent
if ' ' in str(base) or ' ' in sys.executable:
    raise SystemExit('Move the project to a folder without spaces, such as ~/smart-mirror.')
folder = Path.home() / '.config/systemd/user'
folder.mkdir(parents=True, exist_ok=True)
unit = f'''[Unit]
Description=Personal smart mirror
After=network-online.target

[Service]
WorkingDirectory={base}
ExecStart={sys.executable} {base}/app.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
'''
(folder / 'smart-mirror.service').write_text(unit)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','smart-mirror.service'],check=True)
print('Service installed. Check: systemctl --user status smart-mirror')
