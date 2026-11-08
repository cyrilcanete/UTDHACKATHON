"""Small, in-memory job state for the two optional Nemotron workers."""
import copy
import threading
import time
from datetime import datetime, timezone
from nemotron_agent import NemotronError


class AnalysisState:
    def __init__(self):
        self.lock = threading.RLock()
        self.results, self.states, self.due, self.completed = {}, {}, {}, {}
        self.manual_due = {}
        self.serial = 0

    def _new(self, pid, key, model, state, message):
        self.serial += 1
        self.states[pid] = {'key': key, 'token': self.serial, 'state': state,
                            'message': message, 'model': model, 'trace': []}
        return self.serial

    def queue(self, pid, key, model, now=None):
        with self.lock:
            old = self.states.get(pid, {})
            if old.get('state') in ('queued', 'running'):
                return False
            now = time.monotonic() if now is None else now
            if now < self.manual_due.get(pid, 0):
                raise NemotronError('cooldown', 'Please wait 10 seconds between manual analysis requests.')
            self.manual_due[pid] = now + 10
            self._new(pid, key, model, 'queued', 'Analysis queued for the current evidence.')
            return True

    def begin(self, pid, key, model, now):
        with self.lock:
            old = self.states.get(pid, {})
            if old.get('state') == 'running':
                return None
            manual = old.get('state') == 'queued'
            if manual and old.get('key') != key:
                old.update(state='stale', message='Evidence changed before analysis started. Analyze again.', trace=[])
                return None
            if not manual and (now < self.due.get(pid, 0) or self.completed.get(pid) == key):
                return None
            self.due[pid] = now + 300  # Automatic retries and changed evidence stay bounded.
            return self._new(pid, key, model, 'running', 'Connecting to Nemotron.')

    def progress(self, pid, token, event):
        with self.lock:
            current = self.states.get(pid, {})
            if current.get('token') != token:
                return
            # Completion is published only after the worker checks the current evidence.
            for name in ('message', 'trace', 'model', 'round', 'elapsed_seconds'):
                if name in event:
                    current[name] = copy.deepcopy(event[name])
            current['state'] = 'running'

    def finish(self, pid, token, key, result, current_key):
        with self.lock:
            current = self.states.get(pid, {})
            if current.get('token') != token:
                return
            result = copy.deepcopy(result)
            result['generated_at'] = datetime.now(timezone.utc).isoformat()
            self.results[pid] = {'key': key, 'result': result}
            if key == current_key:
                self.completed[pid] = key
            current.update(state='complete' if key == current_key else 'stale',
                           message='Analysis complete.' if key == current_key else 'Evidence changed during analysis. Analyze again.',
                           trace=copy.deepcopy(result.get('trace', [])) if key == current_key else [],
                           model=result.get('model', current.get('model')))
            for name in ('request_count', 'elapsed_seconds'):
                if name in result:
                    current[name] = result[name]

    def fail(self, pid, token, key, error, current_key):
        with self.lock:
            current = self.states.get(pid, {})
            if current.get('token') != token:
                return
            if key != current_key:
                current.update(state='stale', message='Evidence changed during analysis. Analyze again.', trace=[])
            else:
                current.update(state='error', **error)

    def view(self, pid, key, model, disabled=None, problem=None):
        with self.lock:
            state = {'state': 'ready', 'message': 'Ready to analyze the current evidence.', 'trace': [], 'model': model}
            if disabled:
                state.update(state='disabled', message=disabled)
                return {'ai': None, 'ai_state': state}
            if problem:
                state.update(state='error', **problem)
                return {'ai': None, 'ai_state': state}
            saved = self.results.get(pid)
            current = self.states.get(pid, {})
            if current.get('key') != key and current.get('state') in ('queued', 'running'):
                state.update(state=current['state'], message='Evidence changed. Waiting for the active analysis to finish before another run.')
                return {'ai': None, 'ai_state': state}
            if current.get('key') == key:
                state.update({k: copy.deepcopy(v) for k, v in current.items() if k not in ('key', 'token')})
                if current.get('state') in ('queued', 'running', 'error', 'stale'):
                    return {'ai': None, 'ai_state': state}
            if saved and saved['key'] == key:
                result = copy.deepcopy(saved['result'])
                state.update(state='complete', message='Analysis complete.', trace=copy.deepcopy(result.get('trace', [])), model=result.get('model', model))
                return {'ai': result, 'ai_state': state}
            if current or saved:
                state.update(state='stale', message='Evidence changed. Analyze again for a current result.', trace=[])
            return {'ai': None, 'ai_state': state}
