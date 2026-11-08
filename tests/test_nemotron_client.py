"""Protocol and setup regressions. No NVIDIA requests or real hardware required."""
import copy
import io
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

import app
from configure_nemotron import check_configuration, configure, smoke_assessment
from nemotron_agent import MODEL, NAMES, NemotronError, describe_error, request, run


def tool_call(name, call_id=None, arguments='{}'):
    return {'id': call_id or name, 'type': 'function',
            'function': {'name': name, 'arguments': arguments}}


class NemotronClientTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / 'config.example.json').read_text())
        app.initialize(self.cfg)
        app.RUNTIME.select_profile('cyril')
        app.RUNTIME.set_mode('work')
        self.snapshot = app.RUNTIME.snapshot()
        self.assessment = app.WORK.assess(self.snapshot)
        self.provenance = Mock(return_value={'available': False, 'status': 'unavailable',
                                             'checked_at': None, 'reason': 'offline_test'})

    def test_model_receives_returned_evidence_and_progress_is_actual(self):
        rounds = []
        replies = iter([
            {'tool_calls': [tool_call(name) for name in NAMES[:3]]},
            {'tool_calls': [tool_call(name) for name in NAMES[3:]]},
            {'content': 'Next step: compare the DHT11 with an independent instrument.'},
        ])
        def transport(options, messages):
            rounds.append(copy.deepcopy(messages))
            return next(replies)
        events = []
        result = run({'enabled': True}, self.snapshot, self.assessment, transport, events.append,
                     provenance_fetcher=self.provenance)
        self.assertEqual(result['model'], MODEL)
        self.assertEqual(result['request_count'], 3)
        self.assertEqual(result['tools'], sorted(NAMES))
        tool_messages = [m for m in rounds[1] if m['role'] == 'tool']
        self.assertEqual(len(tool_messages), 3)
        environment = json.loads(next(m['content'] for m in tool_messages if m['name'] == 'read_local_environment'))
        self.assertEqual(environment['sensors']['temperature_c'], self.snapshot['sensors']['temperature_c'])
        self.assertEqual(events[0]['trace'], [])
        self.assertEqual(events[-1]['state'], 'complete')
        self.assertEqual(len(events[-1]['trace']), 7)

    def test_early_answer_gets_one_correction_then_fails_without_claiming_success(self):
        transport = Mock(return_value={'content': 'No tools were used.'})
        with self.assertRaises(NemotronError) as raised:
            run({'enabled': True}, self.snapshot, self.assessment, transport, provenance_fetcher=self.provenance)
        self.assertEqual(raised.exception.code, 'incomplete_workflow')
        self.assertEqual(transport.call_count, 2)

    def test_reasoning_tags_are_never_displayed_as_a_final_answer(self):
        transport = Mock(side_effect=[
            {'tool_calls': [tool_call(name) for name in NAMES]},
            {'content': '<think>Internal planning text.</think>Next step: verify the reading.'},
        ])
        with self.assertRaises(NemotronError) as raised:
            run({'enabled': True}, self.snapshot, self.assessment, transport, provenance_fetcher=self.provenance)
        self.assertEqual(raised.exception.code, 'invalid_response')

    def test_invalid_and_reused_tool_ids_are_rejected(self):
        cases = [
            {'tool_calls': [tool_call('send_email')]},
            {'tool_calls': [tool_call(NAMES[0], arguments='{"url":"https://untrusted.invalid"}')]},
            {'tool_calls': [tool_call(NAMES[0], 'same'), tool_call(NAMES[1], 'same')]},
            {'tool_calls': [tool_call(NAMES[0], arguments={})]},
            {'tool_calls': 'not a list'},
        ]
        for reply in cases:
            with self.subTest(reply=reply), self.assertRaises(NemotronError) as raised:
                run({'enabled': True}, self.snapshot, self.assessment, Mock(return_value=reply),
                    provenance_fetcher=self.provenance)
            self.assertEqual(raised.exception.code, 'invalid_tool_call')

    def test_deadline_rejects_a_late_result(self):
        clock = [100.0]
        def delayed(options, messages):
            clock[0] = 106.0
            return {'content': 'A late result must not be accepted.'}
        with patch('nemotron_agent.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(NemotronError) as raised:
                run({'enabled': True, 'workflow_timeout_seconds': 5}, self.snapshot, self.assessment, delayed,
                    provenance_fetcher=self.provenance)
        self.assertEqual(raised.exception.code, 'timeout')

    def test_http_request_uses_remaining_budget_and_rejects_truncation(self):
        body = {'choices': [{'finish_reason': 'length', 'message': {'content': 'incomplete'}}]}
        response = io.BytesIO(json.dumps(body).encode())
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'test-secret'}), \
                patch('nemotron_agent.time.monotonic', return_value=100), \
                patch('nemotron_agent.urlopen', return_value=response) as send:
            with self.assertRaises(NemotronError) as raised:
                request({'_deadline': 103}, [])
        self.assertEqual(raised.exception.code, 'output_limit')
        self.assertEqual(send.call_args.kwargs['timeout'], 3)

    def test_malformed_provider_response_has_safe_error(self):
        for body in ({'choices': []}, {'choices': [{'message': None}]}, {'error': 'secret provider body'}):
            with self.subTest(body=body), patch.dict(os.environ, {'NVIDIA_API_KEY': 'test-secret'}), \
                    patch('nemotron_agent.urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
                with self.assertRaises(NemotronError) as raised:
                    request({}, [])
                self.assertEqual(raised.exception.code, 'invalid_response')
                self.assertNotIn('secret', str(raised.exception))

    def test_nvidia_credential_is_not_forwarded_to_a_custom_host(self):
        response = io.BytesIO(b'{"choices":[{"message":{"content":"done"}}]}')
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'test-secret'}), \
                patch('nemotron_agent.urlopen', return_value=response) as send:
            request({'endpoint': 'http://127.0.0.1:8000/v1/chat/completions'}, [])
        self.assertIsNone(send.call_args.args[0].get_header('Authorization'))

    def test_api_post_does_not_follow_a_redirect(self):
        visited = []
        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):
                visited.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/redirect-target')
                self.end_headers()
            def do_GET(self):
                visited.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"redirected"}}]}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            with self.assertRaises(HTTPError) as raised:
                request({'endpoint': endpoint}, [])
            self.assertEqual(describe_error(raised.exception)['code'], 'endpoint_redirect')
            self.assertEqual(visited, ['/v1/chat/completions'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_provider_errors_do_not_echo_urls_or_response_bodies(self):
        for status, code in ((401, 'invalid_key'), (403, 'access_denied'), (429, 'rate_limited'), (503, 'provider_unavailable')):
            failure = describe_error(HTTPError('https://example.invalid/secret', status, 'private token', {}, None))
            self.assertEqual(failure['code'], code)
            self.assertNotIn('private', failure['message'])
            self.assertNotIn('example.invalid', failure['message'])
        self.assertEqual(describe_error(URLError(TimeoutError()))['code'], 'timeout')

    def test_offline_diagnostics_do_not_print_key_or_call_provider(self):
        original = copy.deepcopy(self.cfg)
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'DO-NOT-PRINT'}), patch('nemotron_agent.urlopen') as send:
            diagnostics = check_configuration(self.cfg)
        self.assertFalse(diagnostics['live_api_verified'])
        self.assertNotIn('DO-NOT-PRINT', json.dumps(diagnostics))
        self.assertEqual(self.cfg, original)
        send.assert_not_called()

    def test_synthetic_setup_preserves_real_hardware_and_custom_limits(self):
        with TemporaryDirectory() as folder:
            cfg = copy.deepcopy(self.cfg)
            cfg.update(demo=False)
            cfg['sensors'].update(source='uno_q', temperature_alert_c=32)
            cfg['rfid'] = {'source': 'file', 'event_path': '/tmp/existing-card-events'}
            cfg['nemotron']['workflow_timeout_seconds'] = 90
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(cfg))
            result = configure(folder, personal=True, synthetic=True)
            self.assertTrue(result['demo'])
            for field in ('sensors', 'rfid', 'profiles'):
                self.assertEqual(result[field], cfg[field])
            self.assertEqual(result['nemotron']['workflow_timeout_seconds'], 90)
            self.assertEqual(result['nemotron']['model'], MODEL)
            self.assertTrue(list(Path(folder).glob('config.json.*.bak')))

    def test_api_smoke_fixture_never_reads_accounts_or_writes_real_incidents(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['demo'] = False
        cfg['sensors']['source'] = 'uno_q'
        cfg['profiles'][0]['name'] = 'PRIVATE-OPERATOR-NAME'
        cfg['facility'] = {'asset': {'id': 'PRIVATE-ASSET'}, 'work_orders': []}
        private_path = MagicMock()
        private_path.__truediv__.return_value.exists.side_effect = AssertionError('private account accessed')
        private_path.__truediv__.return_value.read_text.side_effect = AssertionError('private account read')
        with patch('app.profile_private', return_value=private_path), \
                patch('app.private_write', side_effect=AssertionError('private journal written')):
            snapshot, assessment = smoke_assessment(cfg)
        self.assertTrue(snapshot['sensors']['simulated'])
        self.assertTrue(assessment['technician']['training'])
        self.assertNotIn('PRIVATE-ASSET', json.dumps(assessment))
        self.assertNotIn('PRIVATE-OPERATOR-NAME', json.dumps(assessment))
        self.assertEqual(cfg['sensors']['source'], 'uno_q')


if __name__ == '__main__':
    unittest.main()
