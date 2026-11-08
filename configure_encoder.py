"""Set half-turn calibration only; leaves working RFID/sensor/account setup intact."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from mirror_runtime import MirrorRuntime
BASE=Path(__file__).resolve().parent

def configure(base, detents, right_delta):
    path=Path(base)/'config.json'
    cfg=json.loads((path if path.exists() else Path(base)/'config.example.json').read_text())
    cfg['encoder']={'detents_per_revolution':detents,'right_delta':right_delta}
    MirrorRuntime(cfg)
    if path.exists():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path,path.with_name('config.json.'+stamp+'.bak'))
    temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(cfg,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)
    return cfg

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detents-per-revolution',required=True,type=int)
    parser.add_argument('--right-delta',default=-1,type=int,choices=(-1,1))
    args=parser.parse_args()
    configure(BASE,args.detents_per_revolution,args.right_delta)
    print(f'Half-turn = {args.detents_per_revolution//2} detents. Right: Personal. Left: Work. Restart the backend.')

if __name__=='__main__':main()
