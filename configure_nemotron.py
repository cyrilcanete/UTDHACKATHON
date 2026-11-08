"""Check, test, or start Nemotron. API keys are entered locally, never saved to config.
Run: python3 configure_nemotron.py --check
Then: python3 configure_nemotron.py --start --personal --synthetic
Only --start/--test make hosted requests under your NVIDIA account.
"""
import argparse
import getpass
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from nemotron_agent import ENDPOINT, MODEL, describe_error, validate_options

BASE=Path(__file__).resolve().parent

def configure(base=BASE, model=MODEL, personal=False, synthetic=False):
    path=Path(base)/'config.json'
    cfg=json.loads((path if path.exists() else Path(base)/'config.example.json').read_text())
    options=dict(cfg.get('nemotron',{}))
    options.update(enabled=True,allow_demo=True,personal_enabled=personal,endpoint=ENDPOINT,model=model)
    validate_options(options,require_key=False)
    cfg['nemotron']=options
    if synthetic:
        # Account/demo data and real sensor transport are independent settings.
        source=cfg.get('sensors',{}).get('source','demo' if cfg['demo'] else 'none')
        cfg.setdefault('sensors',{}).setdefault('source',source)
        cfg['demo']=True
    if path.exists():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        shutil.copy2(path,path.with_name('config.json.'+stamp+'.bak'))
    temp=path.with_suffix('.json.tmp');temp.write_text(json.dumps(cfg,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)
    return cfg


def check_configuration(cfg, base=BASE):
    """Offline diagnostics: no provider request, secret output, or config changes."""
    options=cfg.get('nemotron',{})
    endpoint,model=validate_options(options,require_key=False)
    return {
        'project':str(base),
        'model':model,
        'endpoint':endpoint,
        'work_enabled':bool(options.get('enabled')),
        'personal_enabled':bool(options.get('personal_enabled')),
        'allow_demo':bool(options.get('allow_demo')),
        'account_data':'synthetic' if cfg.get('demo') else 'live accounts',
        'sensor_source':cfg.get('sensors',{}).get('source','demo' if cfg.get('demo') else 'none'),
        'api_key':'present in this process (not verified)' if os.environ.get('NVIDIA_API_KEY','').strip() else 'missing from this process',
        'live_api_verified':False,
    }


def smoke_assessment(cfg):
    """Exercise actual tools with labelled fixtures, without touching private journals or inboxes."""
    import app
    fixture=dict(cfg,demo=True,name='Training technician',tasks=[],
                 profiles=[{'id':'cyril','name':'Training technician','rfid_uids':[],'tasks':[]}],
                 sensors={'source':'demo'},rfid={'source':'none'})
    fixture.pop('facility',None)
    app.initialize(fixture)
    app.RUNTIME.select_profile(app.RUNTIME.profiles[0]['id'])
    app.RUNTIME.set_mode('work')
    snapshot=app.RUNTIME.snapshot()
    return snapshot,app.WORK.assess(snapshot)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check',action='store_true',help='Show current setup without network calls or changes')
    action.add_argument('--start',action='store_true',help='Test NVIDIA, then launch the mirror in this process with the entered key')
    action.add_argument('--test',action='store_true',help='Run a bounded real API workflow on synthetic fixtures, without changing settings')
    parser.add_argument('--personal',action='store_true',help='Also enable sending selected suspicious message excerpts to NVIDIA for personal review')
    parser.add_argument('--synthetic',action='store_true',help='Use fictional account/message data for the sponsor demo; keep the configured hardware transport')
    parser.add_argument('--model',default=None,help='Override the default NVIDIA model; confirm tool support and access in your account')
    parser.add_argument('--port',type=int,default=5000)
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('Port must be 1–65535')
    import app
    cfg=app.load_config()
    if args.check:
        try: print(json.dumps(check_configuration(cfg),indent=2))
        except ValueError as error: raise SystemExit(describe_error(error)['message']) from None
        print('Offline check only. Run --test to verify hosted model access. A running service may use a different environment.')
        return
    model=args.model or MODEL
    if 'nemotron' not in model.lower(): parser.error('Choose a Nemotron model ID from your NVIDIA account')
    if args.start:
        import socket
        try:
            with socket.socket() as check: check.bind(('127.0.0.1',args.port))
        except OSError:
            raise SystemExit(f'Port {args.port} is in use. Stop the old mirror Python window first.') from None
    print('Model: '+model)
    print('The API smoke test uses synthetic room/technician data and labelled historical ESIF reference data.')
    if args.personal:
        print('Personal smoke test: synthetic messages only.')
        if args.start:
            print('Mirror personal review: synthetic messages.' if args.synthetic or cfg.get('demo') else 'Mirror personal review: selected real message subjects, senders and excerpts will be sent to NVIDIA.')
    else: print('Personal review is off; no inbox is sent.')
    print('Requests use your existing NVIDIA account access. No billing is activated and no API key is written to disk.')
    if not os.environ.get('NVIDIA_API_KEY'):
        if not sys.stdin.isatty(): raise SystemExit('Set NVIDIA_API_KEY locally or run this command in an interactive terminal.')
        token=getpass.getpass('Paste NVIDIA API key (hidden), then press Enter: ').strip()
        if not token: raise SystemExit('No key entered. Nothing was changed.')
        os.environ['NVIDIA_API_KEY']=token
    from nemotron_agent import run
    options=dict(cfg.get('nemotron',{}),enabled=True,allow_demo=True,endpoint=ENDPOINT,model=model)
    snapshot,assessment=smoke_assessment(cfg)
    print('Testing technician read-only tools with NVIDIA...')
    seen=set()
    def show_progress(event):
        for step in event['trace']:
            if step['tool'] not in seen:
                print('  Tool returned: '+step['tool'],flush=True)
                seen.add(step['tool'])
    try:
        result=run(options,snapshot,assessment,on_progress=show_progress)
    except Exception as error:
        failure=describe_error(error)
        raise SystemExit(failure['code']+': '+failure['message']+' No configuration was changed.') from None
    print('LIVE NEMOTRON TEST PASSED. Tools used: '+', '.join(result['tools']))
    provenance = result.get('provenance_check', {})
    if provenance.get('available'):
        print('LIVE SOURCE METADATA CHECK PASSED: DataCite DOI '+provenance['doi'])
    else:
        print('DataCite source metadata check unavailable: '+provenance.get('reason', 'not_checked'))
    print('ESIF measurements remain historical: '+result['observation_timestamp'])
    print(result['note'])
    if args.personal:
        from personal_assistant import run_personal
        from message_review import SAMPLES, review_inbox_messages
        fixture=review_inbox_messages([{'id':'training-test','subject':'Account verification required','sender':'Training sender','body':SAMPLES[1]['text']}])[0]
        try:
            reviewed=run_personal(options,fixture,training=True,on_progress=show_progress)
        except Exception as error:
            failure=describe_error(error)
            raise SystemExit(failure['code']+': '+failure['message']+' Configuration was not changed.') from None
        print('LIVE PERSONAL TOOL TEST PASSED: '+', '.join(reviewed['tools']))
        print(reviewed['note'])
    if args.start:
        configure(model=model,personal=args.personal,synthetic=args.synthetic)
        os.environ.pop('MIRROR_DEMO',None)
        os.environ['MIRROR_PORT']=str(args.port)
        print('Starting mirror. Scan a card and turn a half-turn left for Work.')
        print('Keep this terminal open. On future restarts, use this launcher or set NVIDIA_API_KEY for the service.')
        app.main()

if __name__=='__main__': main()
