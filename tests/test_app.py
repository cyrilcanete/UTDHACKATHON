import base64
import importlib.util
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class Tests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((app.BASE/'config.example.json').read_text())
        app.initialize(self.cfg)

    def test_demo_never_calls_services(self):
        from unittest.mock import patch
        with patch.object(app,'weather',side_effect=AssertionError('network used')):
            app.worker(self.cfg,threading.Event())
        self.assertEqual(app.public_state(self.cfg)['inbox']['data']['unread'],2)

    def test_bodies_never_leave_backend(self):
        app.STATE['inbox']['data']['messages'][0]['body']='SECRET BODY'
        self.assertNotIn('SECRET BODY',json.dumps(app.public_state(self.cfg)))
        self.assertEqual(app.STATE['inbox']['data']['messages'][0]['body'],'SECRET BODY')

    def test_plain_preferred_and_reply_trimmed(self):
        def part(kind,text):
            return {'mimeType':kind,'body':{'data':base64.urlsafe_b64encode(text.encode()).decode()}}
        payload={'parts':[part('text/html','<b>Duplicate</b>'),part('text/plain','Bring notes\nOn Monday Alex wrote:\nOld message')]}
        self.assertEqual(app.plain_body(payload),'Bring notes')

    def test_sources_required(self):
        for ids in ([],['invented']):
            with self.assertRaises(ValueError):
                app.validate_briefing({'summary':'Hi','action_items':[{'text':'Do it','source_ids':ids}]},{'mail:1'})
        result=app.validate_briefing({'summary':'Hi','action_items':[{'text':'Read','source_ids':['mail:1']}]},{'mail:1'})
        self.assertEqual(len(result['action_items']),1)

    def test_live_ai_disabled_hides_cached_summary(self):
        self.cfg['demo']=False
        self.assertIn('off',app.public_state(self.cfg)['briefing']['data']['summary'])

    def test_failures_keep_last_data_and_label_stale(self):
        from unittest.mock import patch
        self.cfg['demo']=False
        stop=threading.Event()
        def fail(_):
            stop.set()
            raise TimeoutError()
        with patch.object(app,'weather',side_effect=fail), patch.object(app,'calendar',side_effect=fail), patch.object(app,'inbox',side_effect=fail), patch.object(app,'private_write'):
            app.worker(self.cfg,stop)
        self.assertEqual(app.STATE['weather']['data']['temperature'],72)
        self.assertIn('unavailable',app.STATE['weather']['error'])
        self.assertIn('reconnect',app.STATE['inbox']['error'])

    def test_briefing_uses_validated_ollama_result(self):
        from unittest.mock import patch
        self.cfg['ai_enabled']=True
        with patch.object(app,'read_json',return_value={'response':json.dumps({'summary':'Bring notes.','action_items':[{'text':'Bring notes','source_ids':['mail:demo']}]})}) as call:
            result=app.briefing(self.cfg,app.STATE)
        self.assertEqual(result['summary'],'Bring notes.')
        self.assertFalse(call.call_args.args[1]['stream'])

    def test_routes_and_private_files(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),app.handler_for(self.cfg))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        root=f'http://127.0.0.1:{server.server_port}'
        try:
            for path in ('/','/app.js','/style.css','/api/dashboard'):
                with urlopen(Request(root+path,headers={'Host':'localhost:5000'})) as response:
                    self.assertEqual(response.status,200)
                    self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            for path,host,status in [('/private/token.json','localhost:5000',404),('/','evil.example',403)]:
                with self.assertRaises(HTTPError) as ctx:
                    urlopen(Request(root+path,headers={'Host':host}))
                self.assertEqual(ctx.exception.code,status)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
