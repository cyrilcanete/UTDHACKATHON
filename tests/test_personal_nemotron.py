"""Personal isolation and real HTTP queue behavior, with no hosted requests."""
import copy
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app
from mirror_runtime import profile_config
from nemotron_agent import MODEL, NemotronError
from personal_assistant import PERSONAL_NAMES


class PersonalNemotronTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((app.BASE/'config.example.json').read_text())
        self.cfg['nemotron'].update(enabled=True,allow_demo=True,personal_enabled=True)
        self.key=patch.dict(os.environ,{'NVIDIA_API_KEY':'test-key-only'})
        self.key.start();self.addCleanup(self.key.stop)
        app.initialize(self.cfg)
        app.RUNTIME.select_profile('partner')
        self.personal=lambda pid:app.personal_snapshot(profile_config(self.cfg,pid),pid)
        self.result={'note':'Next step: use a saved employee bookmark to verify the request.',
                     'method':'Nemotron tool workflow · verify AI suggestions',
                     'tools':list(PERSONAL_NAMES),'model':MODEL,
                     'trace':[{'tool':name,'status':'returned','step':i+1} for i,name in enumerate(PERSONAL_NAMES)]}

    def state(self,pid='partner'):
        return app.PERSONAL.snapshot(pid,self.personal(pid)['inbox'])

    def test_personal_progress_and_completed_answer(self):
        def model(options,item,training,on_progress):
            self.assertTrue(training)
            self.assertEqual(item['sender'],'T-Mobile Identity Management')
            on_progress({'state':'running','message':'Received selected message.',
                         'trace':self.result['trace'][:1],'model':MODEL})
            self.assertEqual(self.state()['ai_state']['state'],'running')
            self.assertEqual(len(self.state()['ai_state']['trace']),1)
            self.assertIsNone(self.state()['ai'])
            return self.result
        with patch('personal_assistant.run_personal',side_effect=model):
            app.PERSONAL.step(app.RUNTIME,self.personal)
        self.assertEqual(self.state()['ai_state']['state'],'complete')
        self.assertEqual(self.state()['ai']['tools'],list(PERSONAL_NAMES))

    def test_profile_switch_during_analysis_keeps_result_with_original_profile(self):
        def model(*args,**kwargs):
            app.RUNTIME.select_profile('cyril')
            return self.result
        with patch('personal_assistant.run_personal',side_effect=model):
            app.PERSONAL.step(app.RUNTIME,self.personal)
        self.assertIsNone(app.public_state(self.cfg)['personal_assistant']['ai'])
        app.RUNTIME.select_profile('partner')
        self.assertEqual(app.public_state(self.cfg)['personal_assistant']['ai']['note'],self.result['note'])
        app.RUNTIME.set_mode('welcome')
        self.assertNotIn('personal_assistant',app.public_state(self.cfg))

    def test_changed_message_during_analysis_hides_outdated_result(self):
        def model(*args,**kwargs):
            app.PROFILE_STATES['partner']['inbox']['data']['reviews'][0]['review']['excerpt']='A different selected message.'
            return self.result
        with patch('personal_assistant.run_personal',side_effect=model):
            app.PERSONAL.step(app.RUNTIME,self.personal)
        self.assertIsNone(self.state()['ai'])
        self.assertEqual(self.state()['ai_state']['state'],'stale')

    def test_inbox_refresh_time_alone_does_not_repeat_inference(self):
        with patch('personal_assistant.run_personal',return_value=self.result) as run:
            app.PERSONAL.step(app.RUNTIME,self.personal)
            app.PROFILE_STATES['partner']['inbox']['updated']='new refresh timestamp'
            app.PERSONAL.step(app.RUNTIME,self.personal)
        self.assertEqual(run.call_count,1)
        self.assertEqual(self.state()['ai_state']['state'],'complete')

    def test_cyril_no_selected_message_makes_no_request(self):
        app.RUNTIME.select_profile('cyril')
        with patch('personal_assistant.run_personal') as run:
            app.PERSONAL.step(app.RUNTIME,self.personal)
        run.assert_not_called()
        self.assertFalse(self.state('cyril')['ai_state']['can_analyze'])
        with self.assertRaises(NemotronError) as raised:
            app.PERSONAL.request_run('cyril',self.personal('cyril')['inbox'])
        self.assertEqual(raised.exception.code,'no_message')

    def test_missing_key_and_disabled_personal_do_not_request_network(self):
        with patch.dict(os.environ,{},clear=True),patch('personal_assistant.run_personal') as run:
            app.PERSONAL.step(app.RUNTIME,self.personal)
            self.assertEqual(self.state()['ai_state']['code'],'missing_key')
        run.assert_not_called()
        self.cfg['nemotron']['personal_enabled']=False
        with self.assertRaises(NemotronError) as raised:
            app.PERSONAL.request_run('partner',self.personal('partner')['inbox'])
        self.assertEqual(raised.exception.code,'disabled')


class NemotronEndpointTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((app.BASE/'config.example.json').read_text())
        self.cfg['nemotron'].update(enabled=True,allow_demo=True,personal_enabled=True)
        self.key=patch.dict(os.environ,{'NVIDIA_API_KEY':'test-key-only'})
        self.key.start();self.addCleanup(self.key.stop)
        app.initialize(self.cfg)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.handler_for(self.cfg))
        self.server.RequestHandlerClass=app.handler_for(self.cfg,self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def post(self,payload=None,origin=None):
        headers={'Content-Type':'application/json','Origin':origin or self.base}
        req=Request(self.base+'/api/nemotron/run',data=json.dumps(payload or {}).encode(),headers=headers)
        try:
            with urlopen(req,timeout=3) as response:return response.status,json.load(response)
        except HTTPError as error:
            return error.code,json.load(error)

    def test_manual_post_queues_work_without_inference_on_http_thread(self):
        app.RUNTIME.select_profile('cyril');app.RUNTIME.set_mode('work')
        with patch('nemotron_agent.urlopen',side_effect=AssertionError('HTTP handler made an inference call')):
            status,body=self.post()
        self.assertEqual(status,202)
        self.assertEqual(body['mirror']['work']['assistant']['ai_state']['state'],'queued')
        self.assertIsNone(body['mirror']['work']['assistant']['ai'])
        self.assertNotIn('inbox',body)
        self.assertEqual(self.post()[0],202)  # Duplicate active request stays one queued job.

    def test_manual_post_enforces_profile_origin_and_opt_in(self):
        status,body=self.post();self.assertEqual(status,409);self.assertEqual(body['code'],'no_profile')
        app.RUNTIME.select_profile('partner')
        self.assertEqual(self.post(origin='https://untrusted.invalid')[0],403)
        self.assertEqual(self.post({'profile_id':'cyril'})[0],400)
        self.cfg['nemotron']['personal_enabled']=False
        status,body=self.post();self.assertEqual(status,403);self.assertEqual(body['code'],'disabled')
        self.assertNotIn('test-key-only',json.dumps(body))

    def test_manual_personal_post_uses_active_sarah_evidence(self):
        app.RUNTIME.select_profile('partner')
        status,body=self.post()
        self.assertEqual(status,202)
        self.assertEqual(body['personal_assistant']['ai_state']['state'],'queued')
        self.assertEqual(body['mirror']['active_profile'],'partner')


if __name__=='__main__':unittest.main()
