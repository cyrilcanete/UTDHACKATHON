"""Worker/state regressions: deterministic, with no NVIDIA or hardware access."""
import copy
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from mirror_runtime import MirrorRuntime
from nemotron_agent import ENDPOINT, MODEL, NAMES, NemotronError
from nemotron_state import AnalysisState
from technician import TRAINING
from work_assistant import WorkAssistant


RESULT = {
    'method': 'NVIDIA Nemotron', 'note': 'Compare the reading with an independent instrument.',
    'tools': list(NAMES),
    'trace': [{'tool': name, 'status': 'returned', 'step': i + 1} for i, name in enumerate(NAMES)],
    'model': MODEL, 'request_count': 3, 'elapsed_seconds': 1.5,
}


class NemotronWorkRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        self.cfg['nemotron'].update(enabled=True, allow_demo=True, endpoint='http://127.0.0.1:8000/v1/chat/completions')
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = MirrorRuntime(self.cfg, clock=lambda: 100)
        self.runtime.select_profile('cyril')
        self.runtime.set_mode('work')
        self.assistant = WorkAssistant(self.cfg, Path(self.temp.name) / 'incidents.json', Mock())

    def view(self):
        return self.assistant.assess(self.runtime.snapshot())

    def complete(self):
        with patch('work_assistant.run', return_value=RESULT):
            self.assistant.step(self.runtime)
        self.assertEqual(self.view()['ai_state']['state'], 'complete')

    def test_result_survives_identical_refresh_but_not_relevant_evidence_changes(self):
        self.complete()
        original = self.runtime.snapshot()
        refreshed = copy.deepcopy(original)
        refreshed['sensors'].update(updated='2030-01-01T00:00:00+00:00', motion=False)
        self.assertIsNotNone(self.assistant.assess(refreshed)['ai'])
        for section, field, value in (
                ('sensors', 'temperature_c', 34), ('sensors', 'humidity_pct', 20),
                ('sensors', 'source', 'serial'), ('sensors', 'simulated', False),
                ('sensors', 'status', 'unknown'), ('sensors', 'temperature_c', None)):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(original)
                changed[section][field] = value
                view = self.assistant.assess(changed)
                self.assertIsNone(view['ai'])
                self.assertEqual(view['ai_state']['state'], 'stale')
        changed = copy.deepcopy(original)
        changed['work']['limits']['temperature_alert_c'] = 25
        self.assertIsNone(self.assistant.assess(changed)['ai'])

    def test_work_order_and_historical_data_changes_invalidate_result(self):
        self.cfg['facility'] = copy.deepcopy(TRAINING)
        self.complete()
        previous = self.cfg['facility']['work_orders'][0]['last_note']
        self.cfg['facility']['work_orders'][0]['last_note'] = 'Independent measurement has now been recorded.'
        self.assertEqual(self.view()['ai_state']['state'], 'stale')
        self.assertIsNone(self.view()['ai'])
        self.cfg['facility']['work_orders'][0]['last_note'] = previous
        self.assertIsNotNone(self.view()['ai'])
        self.assistant.data_center.data['records'][-1]['metrics']['it_power_kw'] += 1
        self.assertIsNone(self.view()['ai'])
        self.assertEqual(self.view()['ai_state']['state'], 'stale')

    def test_progress_is_visible_before_commit_and_changed_evidence_rejects_result(self):
        def run_model(options, snapshot, assessment, on_progress):
            self.assertEqual(self.view()['ai_state']['state'], 'running')
            event = {'state': 'running', 'message': 'Returned local environment.',
                     'trace': RESULT['trace'][:1], 'model': MODEL, 'round': 1,
                     'reasoning_content': 'PRIVATE MODEL REASONING'}
            on_progress(event)
            state = self.view()['ai_state']
            self.assertEqual(state['trace'], RESULT['trace'][:1])
            self.assertNotIn('PRIVATE MODEL REASONING', json.dumps(state))
            on_progress(dict(event, state='complete'))
            self.assertEqual(self.view()['ai_state']['state'], 'running')
            self.assertIsNone(self.view()['ai'])
            self.runtime.demo_scenario('hot')
            self.assertEqual(self.view()['ai_state']['state'], 'running')
            return RESULT
        with patch('work_assistant.run', side_effect=run_model) as run_model:
            self.assistant.step(self.runtime)
            self.assistant.step(self.runtime)
        self.assertEqual(run_model.call_count, 1)
        self.assertIsNone(self.view()['ai'])
        self.assertEqual(self.view()['ai_state']['state'], 'stale')
        self.assertEqual(self.view()['ai_state']['trace'], [])

    def test_profile_switch_during_request_never_exposes_another_profiles_result(self):
        def run_model(options, snapshot, assessment, on_progress):
            self.assertEqual(assessment['technician']['technician'], 'Cyril')
            self.runtime.select_profile('partner')
            self.runtime.set_mode('work')
            self.assertIsNone(self.view()['ai'])
            self.assertEqual(self.view()['ai_state']['state'], 'ready')
            return dict(RESULT, note='CYRIL RESULT ONLY')
        with patch('work_assistant.run', side_effect=run_model):
            self.assistant.step(self.runtime)
        self.assertIsNone(self.view()['ai'])
        self.runtime.select_profile('cyril')
        self.runtime.set_mode('work')
        self.assertEqual(self.view()['ai']['note'], 'CYRIL RESULT ONLY')
        self.assertEqual(self.view()['ai_state']['state'], 'complete')

    def test_manual_queue_is_async_deduplicated_and_bound_to_captured_evidence(self):
        with patch('work_assistant.run', return_value=RESULT) as run_model:
            self.assistant.request_run(self.runtime.snapshot())
            self.assistant.request_run(self.runtime.snapshot())
            self.assertEqual(self.view()['ai_state']['state'], 'queued')
            run_model.assert_not_called()
            self.runtime.demo_scenario('hot')
            # A repeated click cannot replace the queued evidence with another selection.
            self.assistant.request_run(self.runtime.snapshot())
            self.assistant.step(self.runtime)
            run_model.assert_not_called()
        self.assertIsNone(self.view()['ai'])
        self.assertEqual(self.view()['ai_state']['state'], 'stale')

    def test_disabled_and_bad_configuration_never_start_a_model_request(self):
        cases = (
            ({'enabled': False}, 'disabled', 'disabled'),
            ({'allow_demo': False}, 'disabled', 'disabled'),
            ({'endpoint': 'http://remote.example/v1/chat/completions'}, 'error', 'invalid_config'),
            ({'model': 'another-model'}, 'error', 'invalid_config'),
            ({'max_rounds': 999}, 'error', 'invalid_config'),
            ({'endpoint': ENDPOINT}, 'error', 'missing_key'),
        )
        options = copy.deepcopy(self.cfg['nemotron'])
        with patch.dict(os.environ, {'NVIDIA_API_KEY': ''}), patch('work_assistant.run') as run_model:
            for changed, state, code in cases:
                with self.subTest(options=changed):
                    self.cfg['nemotron'] = dict(options, **changed)
                    self.assertEqual(self.view()['ai_state']['state'], state)
                    self.assertIsNone(self.view()['ai'])
                    with self.assertRaises(NemotronError) as error:
                        self.assistant.request_run(self.runtime.snapshot())
                    self.assertEqual(error.exception.code, code)
                    self.assistant.step(self.runtime)
            run_model.assert_not_called()

    def test_missing_dataset_blocks_automatic_and_manual_analysis(self):
        self.assistant.data_center.error = 'Missing fixture'
        self.assertEqual(self.view()['ai_state']['code'], 'evidence_unavailable')
        with patch('work_assistant.run') as run_model:
            self.assistant.step(self.runtime)
            with self.assertRaises(NemotronError) as error:
                self.assistant.request_run(self.runtime.snapshot())
            self.assertEqual(error.exception.code, 'evidence_unavailable')
            run_model.assert_not_called()

    def test_provider_failure_is_sanitized_and_automatic_retry_waits_five_minutes(self):
        now = [100]
        with patch('work_assistant.time.monotonic', side_effect=lambda: now[0]), \
                patch('work_assistant.run', side_effect=RuntimeError('SECRET KEY AND PRIVATE PROVIDER BODY')) as run_model:
            self.assistant.step(self.runtime)
            view = self.view()
            self.assertEqual(view['ai_state']['state'], 'error')
            self.assertEqual(view['ai_state']['code'], 'workflow_failed')
            self.assertIsNone(view['ai'])
            self.assertNotIn('SECRET', json.dumps(view))
            now[0] = 399
            self.assistant.step(self.runtime)
            self.assertEqual(run_model.call_count, 1)
            now[0] = 400
            self.assistant.step(self.runtime)
            self.assertEqual(run_model.call_count, 2)

    def test_work_model_does_not_run_in_personal_or_welcome_mode(self):
        with patch('work_assistant.run') as run_model:
            for mode in ('personal', 'welcome'):
                self.runtime.set_mode(mode)
                self.assistant.step(self.runtime)
            run_model.assert_not_called()


class NemotronStateTests(unittest.TestCase):
    def test_manual_click_cooldown_deduplication_and_automatic_budget(self):
        state = AnalysisState()
        self.assertTrue(state.queue('cyril', 'a', MODEL, now=100))
        self.assertFalse(state.queue('cyril', 'b', MODEL, now=101))
        token = state.begin('cyril', 'a', MODEL, now=100)
        self.assertIsNotNone(token)
        self.assertFalse(state.queue('cyril', 'b', MODEL, now=102))
        state.finish('cyril', token, 'a', RESULT, 'a')
        with self.assertRaises(NemotronError) as error:
            state.queue('cyril', 'a', MODEL, now=109)
        self.assertEqual(error.exception.code, 'cooldown')
        self.assertTrue(state.queue('cyril', 'a', MODEL, now=110))
        token = state.begin('cyril', 'a', MODEL, now=110)
        self.assertIsNotNone(token)  # An intentional re-run bypasses the automatic interval.
        state.finish('cyril', token, 'a', RESULT, 'a')
        self.assertIsNone(state.begin('cyril', 'a', MODEL, now=500))
        self.assertIsNone(state.begin('cyril', 'b', MODEL, now=409))
        self.assertIsNotNone(state.begin('cyril', 'b', MODEL, now=410))

    def test_late_progress_or_completion_cannot_overwrite_another_run(self):
        state = AnalysisState()
        first = state.begin('cyril', 'a', MODEL, now=100)
        state.finish('cyril', first, 'a', RESULT, 'a')
        state.queue('cyril', 'b', MODEL, now=110)
        second = state.begin('cyril', 'b', MODEL, now=110)
        state.progress('cyril', first, {'message': 'OLD MESSAGE', 'trace': RESULT['trace']})
        state.finish('cyril', first, 'a', dict(RESULT, note='OLD NOTE'), 'a')
        view = state.view('cyril', 'b', MODEL)
        self.assertEqual(view['ai_state']['state'], 'running')
        self.assertNotIn('OLD', json.dumps(view))
        state.finish('cyril', second, 'b', RESULT, 'b')
        self.assertEqual(state.view('cyril', 'b', MODEL)['ai_state']['state'], 'complete')
        self.assertIsNone(state.view('partner', 'b', MODEL)['ai'])


if __name__ == '__main__':
    unittest.main()
