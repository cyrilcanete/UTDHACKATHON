import base64
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import app
from mirror_runtime import MirrorRuntime, SerialLines
from message_review import review_message, PHISHING_QUERY
from work_assistant import WorkAssistant
from nemotron_agent import run, NAMES
from rfid_bridge import ScanPublisher, ScanReader


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = app.load_config()
        app.initialize(self.cfg)

    def test_boot_press_turn_and_rescan_privacy_flow(self):
        for event in ({'type':'encoder','delta':-1}, {'type':'encoder','direction':'left'}):
            app.RUNTIME.ingest(event)
            state = app.public_state(self.cfg)
            self.assertEqual(state['mirror']['mode'], 'welcome')
            self.assertNotIn('inbox', state)
            self.assertEqual(state['settings']['tasks'], [])
        app.RUNTIME.scan('F0E2E55C')
        self.assertEqual(app.public_state(self.cfg)['settings']['name'], 'Cyril')
        for event, mode in [({'delta':10}, 'work'), ({'delta':-10}, 'personal'),
                            ({'delta':10}, 'work'), ({'delta':-10}, 'personal'),
                            ({'action':'press'}, 'welcome')]:
            app.RUNTIME.ingest(dict(event, type='encoder'))
            self.assertEqual(app.RUNTIME.snapshot()['mode'], mode)
        self.assertNotIn('inbox', app.public_state(self.cfg))
        self.assertIsNone(app.RUNTIME.active)
        app.RUNTIME.scan('874BBA62')
        self.assertEqual(app.public_state(self.cfg)['settings']['name'], 'Sarah')
        app.RUNTIME.set_mode('work')
        app.RUNTIME.scan('874BBA62')
        self.assertEqual(app.RUNTIME.snapshot()['mode'], 'personal')

    def test_bad_encoder_events_never_mutate_readings(self):
        for event in ({'delta':True}, {'delta':0}, {'delta':'-1'}, {'direction':'right','delta':1}, {'direction':[]}, {'action':'unknown'}, {}):
            with self.assertRaises(ValueError):
                app.RUNTIME.ingest(dict(event,type='encoder',temperature_c=100))
            self.assertEqual(app.RUNTIME.snapshot()['sensors']['temperature_c'],23.5)

    def test_phrases_use_word_boundaries_and_explain_promotion_uncertainty(self):
        review = review_message('Last chance! Act now for a free prize. Send your verification code.')
        matches = [m for s in review['signals'] for m in s['matches']]
        for term in ('free','last chance','act now'):
            self.assertIn(term,matches)
        self.assertEqual(review_message('The freezer works')['signals'], [])
        self.assertIn('legitimate', review_message('Free workshop')['signals'][0]['detail'])

    def test_real_inbox_search_is_read_only_and_works_without_ai(self):
        service = Mock()
        service.users().labels().get().execute.return_value = {'messagesUnread':3}
        service.users().messages().list().execute.side_effect = [{'messages':[]},{'messages':[{'id':'a'}]}]
        service.users().messages().get().execute.return_value = {'id':'a','payload':{
            'mimeType':'text/plain','headers':[{'name':'Subject','value':'Last chance'}],
            'body':{'data':base64.urlsafe_b64encode(b'Act now for your free prize').decode()}}}
        with patch.object(app,'google_service',return_value=service):
            result=app.inbox(dict(self.cfg,ai_enabled=False))
        self.assertEqual(result['reviews'][0]['review']['risk'],'multiple warning signs')
        calls = service.users().messages().list.call_args_list
        self.assertEqual(calls[-1].kwargs['q'],PHISHING_QUERY)
        self.assertFalse(service.users().messages().modify.called)
        self.assertFalse(service.users().messages().send.called)
        self.assertNotIn('body',result['reviews'][0])

    def test_uno_q_sensor_and_encoder_journal_without_card_replay(self):
        cfg=copy.deepcopy(self.cfg);cfg['sensors']['source']='uno_q'
        runtime=MirrorRuntime(cfg)
        with TemporaryDirectory() as folder:
            path=Path(folder)/'scans.ndjson'; reader=ScanReader(runtime,path); publisher=ScanPublisher(path)
            publisher.publish_event({'type':'sensors','temperature_c':26,'humidity_pct':42,'motion':True})
            publisher.publish('F0E2E55C',4)
            publisher.publish_event({'type':'encoder','delta':10})
            reader.poll()
            self.assertEqual(runtime.snapshot()['mode'],'work')
            self.assertEqual(runtime.snapshot()['sensors']['temperature_c'],26)
            publisher.publish_event({'type':'encoder','action':'press'});reader.poll()
            self.assertEqual(runtime.snapshot()['mode'],'welcome')

    def test_incidents_deduplicate_persist_and_recover_without_claiming_repair(self):
        app.RUNTIME.demo_scenario('hot'); snapshot=app.RUNTIME.snapshot()
        with TemporaryDirectory() as folder:
            path=Path(folder)/'incidents.json'
            def write(p,v): p.write_text(json.dumps(v))
            work=WorkAssistant(dict(self.cfg,demo=False),path,write)
            first=work.assess(snapshot)['incident']['id']
            self.assertEqual(work.assess(snapshot)['incident']['id'],first)
            restored=WorkAssistant(dict(self.cfg,demo=False),path,write)
            self.assertEqual(restored.assess(snapshot)['incident']['id'],first)
            app.RUNTIME.demo_scenario('normal'); restored.assess(app.RUNTIME.snapshot())
            self.assertIn('operator review',json.loads(path.read_text())[0]['status'])

    def test_nemotron_tool_workflow_and_untrusted_tool_rejection(self):
        snap=app.RUNTIME.snapshot(); assessment=app.WORK.assess(snap)
        replies=[{'tool_calls':[{'id':n,'type':'function','function':{'name':n,'arguments':'{}'}} for n in NAMES]},
                 {'content':'Verify the sensor reading before taking action.'}]
        transport=Mock(side_effect=replies)
        provenance=Mock(return_value={'available':False,'status':'unavailable','checked_at':None,'reason':'offline_test'})
        result=run({'enabled':True},snap,assessment,transport,provenance_fetcher=provenance)
        self.assertEqual(result['tools'],sorted(NAMES))
        self.assertEqual(sum(m['role']=='tool' for m in transport.call_args.args[1]),len(NAMES))
        for reply in ({'content':'Unverified answer'}, {'tool_calls':[{'id':'bad','function':{'name':'send_email','arguments':'{}'}}]}):
            with self.assertRaises(ValueError):
                run({'enabled':True},snap,assessment,Mock(return_value=reply),provenance_fetcher=provenance)

    def test_update_copy_preserves_private_files_and_backs_up_sources(self):
        from copy_update_to_repo import apply_update
        with TemporaryDirectory() as folder:
            root=Path(folder); source=root/'update'; target=root/'repo'; backup=root/'backup'
            source.mkdir(); target.mkdir(); (target/'.git').mkdir()
            for base in (source,target):
                (base/'private').mkdir()
            (target/'config.json').write_text('KEEP CONFIG')
            (target/'private/token.json').write_text('KEEP TOKEN')
            (target/'app.py').write_text('old source')
            (source/'config.json').write_text('REPLACE?')
            (source/'private/token.json').write_text('REPLACE?')
            (source/'app.py').write_text('new source')
            self.assertEqual(apply_update(source,target,backup),1)
            self.assertEqual((target/'config.json').read_text(),'KEEP CONFIG')
            self.assertEqual((target/'private/token.json').read_text(),'KEEP TOKEN')
            self.assertEqual((backup/'app.py').read_text(),'old source')

    def test_hardware_config_migration_preserves_cards_and_accounts(self):
        from configure_hardware import configure
        with TemporaryDirectory() as folder:
            root=Path(folder); cfg=copy.deepcopy(self.cfg)
            cfg['profiles'][1]['name']='Partner'; cfg['custom_setting']='keep'
            (root/'config.json').write_text(json.dumps(cfg))
            result=configure(root,'serial','/dev/example')
            self.assertEqual(result['profiles'][1]['name'],'Sarah')
            self.assertEqual(result['profiles'][1]['rfid_uids'],['874BBA62'])
            self.assertEqual(result['custom_setting'],'keep')
            self.assertTrue(list(root.glob('config.json.*.bak')))
            self.assertEqual(result['sensors']['source'],'serial')
            self.assertTrue(result['demo'])

    def test_pir_dimming_timeout_recovery_and_session_privacy(self):
        cfg=copy.deepcopy(self.cfg); cfg['sensors']['source']='http'
        now=[0]; runtime=MirrorRuntime(cfg,clock=lambda:now[0])
        runtime.ingest({'motion':False})
        self.assertEqual(runtime.snapshot()['brightness'],1)
        now[0]=59; runtime.ingest({'motion':False})
        self.assertEqual(runtime.snapshot()['brightness'],1)
        now[0]=60; runtime.ingest({'motion':False})
        self.assertEqual(runtime.snapshot()['brightness'],.2)
        self.assertEqual(runtime.snapshot()['mode'],'welcome')
        runtime.ingest({'motion':True})
        self.assertEqual(runtime.snapshot()['brightness'],1)
        self.assertEqual(runtime.snapshot()['mode'],'welcome')
        now[0]=120; runtime.ingest({'motion':False})
        self.assertEqual(runtime.snapshot()['brightness'],.2)
        runtime.scan('F0E2E55C')
        self.assertEqual(runtime.snapshot()['brightness'],1)
        now[0]=180; runtime.ingest({'motion':False})
        self.assertEqual(runtime.snapshot()['brightness'],.2)
        now[0]=196
        self.assertEqual(runtime.snapshot()['brightness'],1)  # Stale sensor fails bright.

    def test_pir_options_and_demo_without_waiting(self):
        app.RUNTIME.demo_scenario('away')
        self.assertEqual(app.RUNTIME.snapshot()['brightness'],.2)
        app.RUNTIME.demo_scenario('near')
        self.assertEqual(app.RUNTIME.snapshot()['brightness'],1)
        self.assertEqual(app.RUNTIME.snapshot()['mode'],'welcome')
        cfg=copy.deepcopy(self.cfg);cfg['sensors']['motion_dimming']=False
        runtime=MirrorRuntime(cfg);runtime.demo_scenario('away')
        self.assertEqual(runtime.snapshot()['brightness'],1)
        for field,value in [('motion_dimming','true'),('dim_after_seconds',0),('dim_brightness',float('nan')),('dim_brightness',2)]:
            cfg=copy.deepcopy(self.cfg);cfg['sensors'][field]=value
            with self.assertRaises(ValueError): MirrorRuntime(cfg)

    def test_demo_never_starts_nemotron(self):
        import threading
        app.WORK.cfg['nemotron']={'enabled':True}
        with patch('work_assistant.run',side_effect=AssertionError('Network used')):
            app.WORK.worker(app.RUNTIME,threading.Event())

if __name__=='__main__': unittest.main()
