"""Select an existing hardware transport while preserving account/card configuration."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from mirror_runtime import MirrorRuntime, profiles_for

BASE = Path(__file__).resolve().parent

def configure(base, source, port=None, baud=9600, live_accounts=False):
    path = Path(base) / 'config.json'
    cfg = json.loads((path if path.exists() else Path(base) / 'config.example.json').read_text())
    sensors = cfg.setdefault('sensors', {})
    sensors['source'] = source
    if source == 'serial':
        if not port:
            raise ValueError('Pass --port with the actual device from serial.tools.list_ports')
        sensors.update(port=port, baudrate=baud)
    if source == 'uno_q' and not cfg.get('rfid', {}).get('event_path'):
        raise ValueError('Run setup_uno_q_rfid.py with your App Lab app path first')
    cfg['profiles'] = profiles_for(cfg)
    if live_accounts:
        cfg['demo'] = False
    MirrorRuntime(cfg)  # Validate before changing anything.
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path,path.with_name('config.json.'+stamp+'.bak'))
    temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(cfg,indent=2)+'\n'); temp.chmod(0o600); temp.replace(path)
    return cfg

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=['serial','http','uno_q'],required=True)
    parser.add_argument('--port')
    parser.add_argument('--baud',type=int,default=9600)
    parser.add_argument('--live-accounts',action='store_true',help='Use connected Gmail/Calendar accounts instead of fictional examples')
    args=parser.parse_args()
    cfg=configure(BASE,args.source,args.port,args.baud,args.live_accounts)
    print('Hardware transport configured:',args.source)
    print('Accounts:', 'fictional demo data' if cfg['demo'] else 'live Google connections')
    print('Restart app.py normally. OPEN_MIRROR_DEMO.cmd always simulates sensors.')

if __name__=='__main__': main()
