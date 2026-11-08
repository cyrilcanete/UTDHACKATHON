"""Exercise knob analysis through the actual serial, UNO Q and HTTP entry points."""
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.request import Request, urlopen

import app
from mirror_runtime import SerialLines
from nemotron_agent import MODEL, NAMES
from rfid_bridge import ScanPublisher, ScanReader


TAP = {'type': 'encoder', 'action': 'analyze'}
HOLD = {'type': 'encoder', 'action': 'press'}


class EncoderAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((app.BASE / 'config.example.json').read_text())
        self.cfg['nemotron'].update(enabled=True, allow_demo=True, personal_enabled=True)
        key = patch.dict(os.environ, {'NVIDIA_API_KEY': 'test-key-only'})
        key.start()
        self.addCleanup(key.stop)
        # Any inference from a hardware callback would block input handling.
        network = patch('nemotron_agent.urlopen', side_effect=AssertionError('Input handler attempted inference'))
        network.start()
        self.addCleanup(network.stop)
        app.initialize(self.cfg)

    def feed(self, payload):
        SerialLines(app.RUNTIME).feed((json.dumps(payload) + '\n').encode())

    def test_tap_on_welcome_cannot_start_a_session_or_analysis(self):
        self.feed(TAP)
        state = app.public_state(self.cfg)
        self.assertEqual(state['mirror']['mode'], 'welcome')
        self.assertIsNone(state['mirror']['active_profile'])
        self.assertNotIn('inbox', state)
        self.assertFalse(app.WORK.analysis.states)
        self.assertFalse(app.PERSONAL.analysis.states)
        self.assertEqual(app.RUNTIME.invalid_lines, 0)

    def test_serial_tap_queues_work_and_long_hold_keeps_old_privacy_action(self):
        self.feed({'type': 'rfid', 'uid': 'F0E2E55C'})
        self.feed({'type': 'encoder', 'delta': 10})
        original_times = dict(app.RUNTIME.times)
        self.feed(TAP)
        state = app.public_state(self.cfg)
        self.assertEqual(state['mirror']['mode'], 'work')
        self.assertEqual(state['mirror']['active_profile'], 'cyril')
        self.assertEqual(state['mirror']['work']['assistant']['ai_state']['state'], 'queued')
        token = app.WORK.analysis.states['cyril']['token']
        self.feed(TAP)
        self.assertEqual(app.WORK.analysis.states['cyril']['token'], token)
        self.assertEqual(app.RUNTIME.times, original_times, 'A button must not refresh sensor freshness')
        self.assertEqual(app.RUNTIME.invalid_lines, 0)
        self.feed(HOLD)
        state = app.public_state(self.cfg)
        self.assertEqual(state['mirror']['mode'], 'welcome')
        self.assertIsNone(state['mirror']['active_profile'])
        self.assertIsNone(state['mirror']['analysis_feedback'])
        self.assertNotIn('personal_assistant', state)
        with patch('work_assistant.run') as inference:
            app.WORK.step(app.RUNTIME)
        inference.assert_not_called()

    def test_uno_q_journal_tap_queues_the_selected_sarah_personal_workflow(self):
        self.cfg['sensors']['source'] = 'uno_q'
        app.initialize(self.cfg)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'events.ndjson'
            reader = ScanReader(app.RUNTIME, path)
            publisher = ScanPublisher(path)
            publisher.publish('874BBA62', 4)
            publisher.publish_event(TAP)
            reader.poll()
            state = app.public_state(self.cfg)
            self.assertEqual(state['mirror']['active_profile'], 'partner')
            self.assertEqual(state['mirror']['mode'], 'personal')
            self.assertEqual(state['personal_assistant']['ai_state']['state'], 'queued')
            self.assertFalse(app.WORK.analysis.states)
            self.assertNotIn('cyril', app.PERSONAL.analysis.states)
            publisher.publish_event(HOLD)
            reader.poll()
            self.assertIsNone(app.RUNTIME.active)
            self.assertNotIn('inbox', app.public_state(self.cfg))

    def test_tap_with_no_selected_message_gives_feedback_and_keeps_profile(self):
        app.RUNTIME.select_profile('cyril')
        self.feed(TAP)
        state = app.public_state(self.cfg)
        self.assertEqual(state['mirror']['mode'], 'personal')
        self.assertEqual(state['mirror']['analysis_feedback']['code'], 'no_message')
        self.assertFalse(state['personal_assistant']['ai_state']['can_analyze'])
        self.assertFalse(app.PERSONAL.analysis.states)
        self.assertEqual(app.RUNTIME.invalid_lines, 0)

    def test_disabled_and_missing_key_are_feedback_not_corrupt_input(self):
        app.RUNTIME.select_profile('cyril')
        app.RUNTIME.set_mode('work')
        self.cfg['nemotron']['enabled'] = False
        self.feed(TAP)
        self.assertEqual(app.RUNTIME.snapshot()['analysis_feedback']['code'], 'disabled')
        self.cfg['nemotron']['enabled'] = True
        with patch.dict(os.environ, {}, clear=True):
            self.feed(TAP)
        self.assertEqual(app.RUNTIME.snapshot()['analysis_feedback']['code'], 'missing_key')
        self.assertFalse(app.WORK.analysis.states)
        self.assertEqual(app.RUNTIME.invalid_lines, 0)
        self.assertEqual(app.RUNTIME.snapshot()['mode'], 'work')

    def test_manual_cooldown_feedback_expires_and_cannot_cross_profiles(self):
        app.RUNTIME.select_profile('cyril')
        app.RUNTIME.set_mode('work')
        self.feed(TAP)
        result = {'note': 'Verify the room reading with another instrument.', 'tools': list(NAMES),
                  'trace': [], 'model': MODEL, 'method': 'Controlled response fixture'}
        with patch('work_assistant.run', return_value=result) as inference:
            app.WORK.step(app.RUNTIME)
        inference.assert_called_once()
        self.feed(TAP)
        state = app.public_state(self.cfg)
        self.assertEqual(state['mirror']['analysis_feedback']['code'], 'cooldown')
        self.assertEqual(state['mirror']['work']['assistant']['ai_state']['state'], 'complete')
        self.assertEqual(app.RUNTIME.invalid_lines, 0)
        with patch.object(app.RUNTIME, 'clock', return_value=app.RUNTIME.analysis_feedback_until + 1):
            self.assertIsNone(app.RUNTIME.snapshot()['analysis_feedback'])
        app.RUNTIME.select_profile('partner')
        self.assertIsNone(app.RUNTIME.snapshot()['analysis_feedback'])
        self.assertNotIn('partner', app.WORK.analysis.results)

    def test_invalid_mixed_button_event_cannot_queue_or_change_readings(self):
        app.RUNTIME.select_profile('cyril')
        app.RUNTIME.set_mode('work')
        before = app.RUNTIME.snapshot()['sensors']
        for extra in ({'delta': 1}, {'uid': '874BBA62'}, {'mode': 'personal'},
                      {'temperature_c': True}, {'temperature_c': 23.5},
                      {'humidity_pct': 46}, {'temperature_c': None}, {'motion': True}):
            with self.assertRaises(ValueError):
                app.RUNTIME.ingest(dict(TAP, **extra))
        self.assertFalse(app.WORK.analysis.states)
        self.assertEqual(app.RUNTIME.snapshot()['sensors'], before)

    def test_local_http_hardware_tap_and_hold_use_the_same_workflow(self):
        self.cfg['sensors']['source'] = 'http'
        app.initialize(self.cfg)
        app.RUNTIME.select_profile('cyril')
        app.RUNTIME.set_mode('work')
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.handler_for(self.cfg))
        server.RequestHandlerClass = app.handler_for(self.cfg, server.server_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            def send(payload):
                request = Request(base + '/api/hardware', data=json.dumps(payload).encode(),
                                  headers={'Content-Type': 'application/json', 'Origin': base})
                with urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    return json.load(response)
            state = send(TAP)
            self.assertEqual(state['mirror']['work']['assistant']['ai_state']['state'], 'queued')
            state = send(HOLD)
            self.assertEqual(state['mirror']['mode'], 'welcome')
            self.assertNotIn('inbox', state)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
