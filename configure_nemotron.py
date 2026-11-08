"""Enable or test the ESIF Nemotron workflow. API keys are entered locally, never saved to config.
Run: py configure_nemotron.py --start
The explicit --start/--test operation makes hosted requests under your NVIDIA account.
"""
import argparse
import getpass
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

BASE=Path(__file__).resolve().parent
ENDPOINT='https://integrate.api.nvidia.com/v1/chat/completions'
MODEL='nvidia/nemotron-3-nano-30b-a3b'

def configure(base=BASE, model=MODEL, personal=False):
    path=Path(base)/'config.json'
    cfg=json.loads((path if path.exists() else Path(base)/'config.example.json').read_text())
    cfg['nemotron']={'enabled':True,'allow_demo':True,'personal_enabled':personal,'endpoint':ENDPOINT,'model':model}
    if path.exists():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path,path.with_name('config.json.'+stamp+'.bak'))
    temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(cfg,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)
    return cfg

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',action='store_true',help='Test NVIDIA, then launch the mirror in this process with the entered key')
    parser.add_argument('--test',action='store_true',help='Run one bounded real tool workflow, without starting the server')
    parser.add_argument('--personal',action='store_true',help='Also enable sending selected suspicious message excerpts to NVIDIA for personal review')
    parser.add_argument('--model',default=MODEL)
    parser.add_argument('--port',type=int,default=5000)
    args=parser.parse_args()
    if not args.test and not args.start:
        parser.error('Use --test or --start. These options make requests using your NVIDIA account.')
    if not 1<=args.port<=65535: parser.error('Port must be 1–65535')
    if 'nemotron' not in args.model.lower(): parser.error('Choose a Nemotron model ID from your NVIDIA account')
    if args.start:
        import socket
        try:
            with socket.socket() as check: check.bind(('127.0.0.1',args.port))
        except OSError:
            raise SystemExit(f'Port {args.port} is in use. Stop the old mirror Python window first.') from None
    print('Uses NVIDIA for technician context and historical ESIF data.')
    print('Personal review: selected suspicious message subjects, senders and excerpts are sent to NVIDIA.' if args.personal else 'Personal review is off; no inbox is sent.')
    print('Requests use your NVIDIA account quota/billing. No API key is written to disk.')
    if not os.environ.get('NVIDIA_API_KEY'):
        if not sys.stdin.isatty(): raise SystemExit('Set NVIDIA_API_KEY locally or run this command in an interactive terminal.')
        token=getpass.getpass('Paste NVIDIA API key (hidden), then press Enter: ').strip()
        if not token: raise SystemExit('No key entered. Nothing was changed.')
        os.environ['NVIDIA_API_KEY']=token
    import app
    from nemotron_agent import run
    cfg=app.load_config()
    options={'enabled':True,'allow_demo':True,'endpoint':ENDPOINT,'model':args.model}
    app.initialize(cfg)
    app.RUNTIME.select_profile(app.RUNTIME.profiles[0]['id'])
    snapshot=app.RUNTIME.snapshot();assessment=app.WORK.assess(snapshot)
    print('Testing technician read-only tools with NVIDIA. This may take a few minutes...')
    try:
        result=run(options,snapshot,assessment)
    except HTTPError as error:
        messages={401:'API key rejected.',403:'Account/model access denied.',429:'NVIDIA quota or rate limit reached.'}
        raise SystemExit(messages.get(error.code,f'NVIDIA returned HTTP {error.code}.')+' No successful live result was produced.') from None
    except (URLError,TimeoutError,ValueError,KeyError,TypeError):
        raise SystemExit('Nemotron test failed or did not complete all tools. Check model tool support, connection and account access. No success is being claimed.') from None
    print('LIVE NEMOTRON TEST PASSED. Tools used: '+', '.join(result['tools']))
    print(result['note'])
    if args.personal:
        from personal_assistant import run_personal
        from message_review import SAMPLES, review_inbox_messages
        fixture=review_inbox_messages([{'id':'training-test','subject':'Account verification required','sender':'Training sender','body':SAMPLES[1]['text']}])[0]
        try:
            reviewed=run_personal(options,fixture,training=True)
        except Exception:
            raise SystemExit('Personal tool test failed. Configuration was not changed.') from None
        print('LIVE PERSONAL TOOL TEST PASSED: '+', '.join(reviewed['tools']))
        print(reviewed['note'])
    if args.start:
        configure(model=args.model,personal=args.personal)
        os.environ.pop('MIRROR_DEMO',None)
        os.environ['MIRROR_PORT']=str(args.port)
        print('Starting mirror. Scan a card and turn a half-turn left for Work.')
        print('Keep this terminal open. On future restarts, use this launcher or set NVIDIA_API_KEY for the service.')
        app.main()

if __name__=='__main__': main()
