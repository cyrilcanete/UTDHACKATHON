"""Local facilities triage: sensor evidence + configured assets + procedures + incident journal.
No equipment actuation, external tickets, or automatic messages. Demo incidents stay in memory.
"""
import copy
import json
import threading
import time
from nemotron_agent import run
from datetime import datetime, timezone


class WorkAssistant:
    def __init__(self, cfg, path, write):
        self.cfg, self.path, self.write = cfg, path, write
        self.lock = threading.RLock()
        self.records = []
        self.ai_result = None
        self.ai_key = None
        self.storage_error = False
        if not cfg['demo'] and path.exists():
            try:
                records = json.loads(path.read_text())
                if isinstance(records, list):
                    self.records = [r for r in records if isinstance(r, dict) and 'id' in r and 'status' in r][-100:]
            except (ValueError, OSError):
                pass

    def assess(self, snapshot):
        with self.lock:
            sensors, work = snapshot['sensors'], snapshot['work']
            configured = self.cfg.get('facility', {})
            asset = configured.get('asset', {'id': 'ROOM-01', 'name': 'Mirror room', 'depends_on': []})
            orders = configured.get('work_orders', [])
            procedures = configured.get('procedures', [
                'Verify the reading with a second measurement.',
                'Check visible airflow obstructions without opening equipment.',
                'Contact the responsible operator if the reading remains outside limits.'
            ])
            affected = asset.get('depends_on', [])
            context = 'Configured asset record' if configured else 'Example asset context; replace with your facility information'
            key = str(asset['id']) + ':' + ('environment' if work['status'] == 'attention' else 'sensor-data')
            incident = next((r for r in reversed(self.records) if r.get('key') == key and r['status'] == 'open'), None)
            changed = False
            if work['status'] != 'normal' and incident is None:
                incident = {'id': 'LOCAL-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'),
                            'key': key, 'status': 'open', 'created': datetime.now(timezone.utc).isoformat(),
                            'asset_id': asset['id'], 'evidence': copy.deepcopy(sensors),
                            'handoff': work['handoff'], 'demo': bool(self.cfg['demo'])}
                self.records.append(incident)
                self.records = self.records[-100:]
                changed = True
            if work['status'] == 'normal':
                for record in self.records:
                    if record.get('asset_id') == asset['id'] and record['status'] == 'open':
                        record['status'] = 'reading recovered; operator review needed'
                        changed = True
            storage = 'Demo journal · memory only' if self.cfg['demo'] else 'Local journal · no external ticket sent'
            if (changed or self.storage_error) and not self.cfg['demo']:
                try:
                    self.write(self.path, self.records)
                    self.storage_error = False
                except OSError:
                    self.storage_error = True
            if self.storage_error:
                storage = 'Journal save failed; incident is in memory only'
            return {'ai': copy.deepcopy(self.ai_result) if self.ai_key == self.evidence_key(snapshot) else None, 'method': 'Local rules · not an AI diagnosis', 'asset': asset, 'context': context,
                    'related_work_orders': [o for o in orders if o.get('asset_id') == asset['id']],
                    'possible_impact': ('Check dependency: ' + ', '.join(affected)) if affected else 'No downstream dependencies configured; impact is unconfirmed.',
                    'procedure': procedures if work['status'] != 'normal' else ['Readings are within configured limits. Continue monitoring.'],
                    'incident': copy.deepcopy(incident), 'storage': storage,
                    'trace': ['Read fresh sensor data', 'Look up asset and related work orders', 'Select verification procedure', 'Record local incident if attention is needed']}

    @staticmethod
    def evidence_key(snapshot):
        s = snapshot['sensors']
        return json.dumps({k: s[k] for k in ('temperature_c', 'humidity_pct', 'source', 'status')}, sort_keys=True)

    def worker(self, runtime, stop):
        options = self.cfg.get('nemotron', {})
        if self.cfg['demo'] or not options.get('enabled'):
            return
        last_key, due = None, 0
        while not stop.is_set():
            snapshot = runtime.snapshot()
            key = self.evidence_key(snapshot)
            if snapshot['mode'] == 'work' and key != last_key and time.monotonic() >= due:
                due = time.monotonic() + 300  # Bound optional remote usage.
                assessment = self.assess(snapshot)
                try:
                    result = run(options, snapshot, assessment)
                except Exception:
                    result = {'method': 'Nemotron unavailable', 'note': 'Showing local rules. Check the configured endpoint, model and API key.'}
                with self.lock:
                    self.ai_key, self.ai_result = key, result
                last_key = key
            stop.wait(2)
