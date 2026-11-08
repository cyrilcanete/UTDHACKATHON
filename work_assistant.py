"""Local facilities triage: sensor evidence + configured assets + procedures + incident journal.
No equipment actuation, external tickets, or automatic messages. Demo incidents stay in memory.
"""
import copy
import json
import hashlib
import threading
import time
from nemotron_agent import run, validate_options, describe_error, NemotronError, MODEL
from nemotron_state import AnalysisState
from data_center import DataCenter
from technician import context as technician_context
from datetime import datetime, timezone


class WorkAssistant:
    def __init__(self, cfg, path, write):
        self.cfg, self.path, self.write = cfg, path, write
        self.lock = threading.RLock()
        self.records = []
        self.data_center = DataCenter()
        self.analysis = AnalysisState()
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
            context = 'Configured local asset record' if configured else 'Local mirror room measured by your DHT11; separate from ESIF data'
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
            assessment = {'technician': technician_context(self.cfg, snapshot), 'data_center': self.data_center.snapshot(), 'method': 'Local rules · not an AI diagnosis', 'asset': asset, 'context': context,
                    'related_work_orders': [o for o in orders if o.get('asset_id') == asset['id']],
                    'possible_impact': ('Check dependency: ' + ', '.join(affected)) if affected else 'No downstream dependencies configured; impact is unconfirmed.',
                    'procedure': procedures if work['status'] != 'normal' else ['Readings are within configured limits. Continue monitoring.'],
                    'incident': copy.deepcopy(incident), 'storage': storage,
                    'trace': ['Read fresh sensor data', 'Look up asset and related work orders', 'Select verification procedure', 'Record local incident if attention is needed']}

            state = self.analysis.view(snapshot['active_profile'], self.evidence_key(snapshot, assessment),
                                       self.cfg.get('nemotron', {}).get('model', MODEL),
                                       disabled=self.disabled_reason(), problem=self.problem(assessment))
            assessment.update(state)
            assessment['ai_status'] = state['ai_state']['message']
            return assessment

    def disabled_reason(self):
        options = self.cfg.get('nemotron', {})
        if not options.get('enabled'):
            return 'Nemotron is off. Enable it in the local configuration.'
        if self.cfg['demo'] and not options.get('allow_demo', False):
            return 'Nemotron calls for training data are off. Enable allow_demo to use them.'
        return None

    def problem(self, assessment):
        if self.disabled_reason():
            return None
        try:
            validate_options(self.cfg.get('nemotron', {}))
        except Exception as error:
            return describe_error(error)
        if not assessment['data_center'].get('available'):
            return {'code': 'evidence_unavailable', 'message': 'The historical data-center evidence is unavailable. Check the local dataset.'}
        return None

    def evidence_key(self, snapshot, assessment=None):
        assessment = assessment or {'technician': technician_context(self.cfg, snapshot), 'data_center': self.data_center.snapshot()}
        sensors = snapshot['sensors']
        tc = assessment['technician']
        evidence = {
            'sensors': {k: sensors.get(k) for k in ('temperature_c', 'humidity_pct', 'source', 'status', 'simulated')},
            'limits': snapshot['work']['limits'],
            'technician': {k: tc.get(k) for k in ('technician', 'asset', 'training', 'label', 'assigned_orders', 'related_orders', 'procedure', 'procedure_status', 'next_step', 'assessment')},
            'data_center': assessment['data_center'],
            'model': self.cfg.get('nemotron', {}).get('model', MODEL),
        }
        return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()

    def request_run(self, snapshot):
        if self.disabled_reason():
            raise NemotronError('disabled', self.disabled_reason())
        assessment = self.assess(snapshot)
        problem = self.problem(assessment)
        if problem:
            raise NemotronError(problem['code'], problem['message'])
        return self.analysis.queue(snapshot['active_profile'], self.evidence_key(snapshot, assessment),
                                   self.cfg.get('nemotron', {}).get('model', MODEL))

    def step(self, runtime):
        if self.disabled_reason():
            return
        snapshot = runtime.snapshot()
        if snapshot['mode'] != 'work' or not snapshot['active_profile']:
            return
        pid = snapshot['active_profile']
        assessment = self.assess(snapshot)
        if self.problem(assessment):
            return
        key = self.evidence_key(snapshot, assessment)
        token = self.analysis.begin(pid, key, self.cfg.get('nemotron', {}).get('model', MODEL), time.monotonic())
        if token is None:
            return
        try:
            result = run(self.cfg.get('nemotron', {}), snapshot, assessment,
                         on_progress=lambda event: self.analysis.progress(pid, token, event))
            # Recompute the original technician's evidence even if another profile is now active.
            current = dict(runtime.snapshot(), active_profile=pid)
            self.analysis.finish(pid, token, key, result, self.evidence_key(current))
        except Exception as error:
            current = dict(runtime.snapshot(), active_profile=pid)
            self.analysis.fail(pid, token, key, describe_error(error), self.evidence_key(current))

    def worker(self, runtime, stop):
        if self.disabled_reason():
            return
        while not stop.is_set():
            self.step(runtime)
            stop.wait(2)
