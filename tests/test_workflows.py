import copy
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import app
from mirror_runtime import MirrorRuntime, SerialLines
from personal_assistant import PersonalAssistant, run_personal, PERSONAL_NAMES
from technician import context
from configure_encoder import configure

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.cfg=app.load_config();app.initialize(self.cfg)

    def test_half_turn_both_profiles_and_reversal_reset(self):
        for pid in ('cyril','partner'):
            rt=MirrorRuntime(self.cfg);rt.select_profile(pid)
            for _ in range(9):rt.ingest({'type':'encoder','direction':'left'})
            self.assertEqual(rt.snapshot()['mode'],'personal')
            rt.ingest({'type':'encoder','direction':'left'})
            self.assertEqual(rt.snapshot()['mode'],'work')
            for _ in range(9):rt.ingest({'type':'encoder','direction':'right'})
            self.assertEqual(rt.snapshot()['mode'],'work')
            rt.ingest({'type':'encoder','direction':'right'})
            self.assertEqual(rt.snapshot()['mode'],'personal')
            rt.ingest({'type':'encoder','delta':9})
            rt.ingest({'type':'encoder','delta':-1})
            self.assertEqual(rt.snapshot()['encoder']['progress_detents'],1)
            rt.ingest({'type':'encoder','action':'press'})
            rt.ingest({'type':'encoder','delta':10})
            self.assertEqual(rt.snapshot()['mode'],'welcome')
            rt.select_profile(pid)
            self.assertEqual(rt.snapshot()['encoder']['progress_detents'],0)

    def test_calibration_and_serial_detents(self):
        cfg=copy.deepcopy(self.cfg);cfg['encoder']={'detents_per_revolution':30,'right_delta':1}
        rt=MirrorRuntime(cfg);rt.select_profile('partner');lines=SerialLines(rt)
        for _ in range(14):lines.feed(b'{"type":"encoder","delta":-1}\n')
        self.assertEqual(rt.snapshot()['mode'],'personal')
        lines.feed(b'{"type":"encoder","delta":-1}\n');self.assertEqual(rt.snapshot()['mode'],'work')
        rt.ingest({'type':'encoder','delta':15});self.assertEqual(rt.snapshot()['mode'],'personal')
        for count in (0,1,21,True,201):
            cfg['encoder']['detents_per_revolution']=count
            with self.assertRaises(ValueError):MirrorRuntime(cfg)

    def test_sarah_has_distinct_complete_work_context(self):
        for pid,order in [('cyril','WO-203'),('partner','WO-204')]:
            app.RUNTIME.select_profile(pid);app.RUNTIME.set_mode('work')
            state=app.public_state(self.cfg);tc=state['mirror']['work']['assistant']['technician']
            self.assertEqual(tc['assigned_orders'][0]['id'],order)
            self.assertEqual(tc['asset']['id'],'CRAC-02')
            self.assertIn('WO-198',[o['id'] for o in tc['related_orders']])
            self.assertTrue(tc['procedure']);self.assertTrue(tc['next_step']);self.assertTrue(tc['training'])
            self.assertNotIn('inbox',state)

    def test_live_unconfigured_equipment_never_gets_fictional_work_orders(self):
        cfg=copy.deepcopy(self.cfg);cfg['demo']=False
        rt=MirrorRuntime(cfg);rt.select_profile('partner')
        tc=context(cfg,rt.snapshot())
        self.assertFalse(tc['training']);self.assertEqual(tc['related_orders'],[])
        self.assertEqual(tc['asset']['id'],'LOCAL-DHT11-01')

    def test_personal_model_requests_tools_and_receives_only_selected_profile(self):
        app.RUNTIME.select_profile('partner')
        inbox=app.public_state(self.cfg)['inbox'];item=inbox['data']['reviews'][0]
        replies=[]
        for name in PERSONAL_NAMES:
            replies.append({'tool_calls':[{'id':name,'type':'function','function':{'name':name,'arguments':'{}'}}]})
        replies.append({'content':'The verification-code request is a concern. Next step: open your official account app and do not share the code.'})
        transport=Mock(side_effect=replies)
        result=run_personal({'enabled':True},item,True,transport)
        self.assertEqual(result['tools'],sorted(PERSONAL_NAMES))
        self.assertEqual([r['tool'] for r in result['trace']],list(PERSONAL_NAMES))
        conversation=json.dumps(transport.call_args.args[1])
        self.assertIn('T-Mobile Identity Management',conversation)
        self.assertNotIn('Last chance: claim your free prize',conversation)
        self.assertEqual(transport.call_count,5)

    def test_personal_results_are_profile_and_evidence_isolated(self):
        pa=PersonalAssistant(self.cfg)
        a={'data':{'reviews':[{'id':'a'}]}};b={'data':{'reviews':[{'id':'b'}]}}
        pa.results['cyril']={'key':pa.fingerprint(a),'result':{'note':'CYRIL ONLY','method':'test'}}
        self.assertIsNone(pa.snapshot('partner',a)['ai'])
        self.assertIsNone(pa.snapshot('cyril',b)['ai'])
        self.assertEqual(pa.snapshot('cyril',a)['ai']['note'],'CYRIL ONLY')
        app.RUNTIME.set_mode('welcome');self.assertNotIn('personal_assistant',app.public_state(self.cfg))

    def test_personal_network_requires_separate_opt_in(self):
        cfg=copy.deepcopy(self.cfg);cfg['nemotron'].update(enabled=True,allow_demo=True,personal_enabled=False)
        with patch('personal_assistant.run_personal',side_effect=AssertionError('Network used')):
            PersonalAssistant(cfg).worker(app.RUNTIME,Mock(),threading.Event())

    def test_calibration_preserves_working_transport(self):
        with TemporaryDirectory() as folder:
            p=Path(folder)/'config.json';p.write_text(json.dumps(self.cfg))
            result=configure(folder,30,1)
            self.assertEqual(result['rfid'],self.cfg['rfid'])
            self.assertEqual(result['sensors'],self.cfg['sensors'])
            self.assertEqual(result['profiles'],self.cfg['profiles'])
            self.assertTrue(list(Path(folder).glob('config.json.*.bak')))

if __name__=='__main__':unittest.main()
