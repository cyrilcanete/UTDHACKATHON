import copy
import io
import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import datetime
from data_center import DataCenter, DATA
from nemotron_agent import request, run, NAMES
from configure_nemotron import configure, ENDPOINT, MODEL
from tools.import_esif_data import timestamp, build
import app

class DataCenterTests(unittest.TestCase):
    def test_bundled_actual_source_has_attribution_and_historical_dates(self):
        data=DataCenter().snapshot()
        self.assertTrue(data['available']);self.assertTrue(data['historical'])
        self.assertEqual(data['doi'],'10.7799/3015212')
        self.assertEqual(data['latest']['timestamp'],'2025-08-29T04:35:08+00:00')
        self.assertAlmostEqual(data['latest']['metrics']['it_power_kw'],2163.753217351079)
        self.assertEqual(data['record_count'],168)
        self.assertIn('not a live',data['note'])
        values=[r['metrics']['pue'] for r in data['recent'] if r['metrics']['pue'] is not None]
        self.assertEqual(data['statistics']['pue']['count'],len(values))
        self.assertAlmostEqual(data['statistics']['pue']['mean'],sum(values)/len(values))

    def test_invalid_source_has_no_invented_fallback(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'data.json'
            self.assertFalse(DataCenter(path).snapshot()['available'])
            data=json.loads(DATA.read_text());data['records'][-1]['metrics']['pue']=float('nan')
            path.write_text(json.dumps(data));self.assertFalse(DataCenter(path).snapshot()['available'])
            data=json.loads(DATA.read_text());data['records'].reverse()
            path.write_text(json.dumps(data));self.assertFalse(DataCenter(path).snapshot()['available'])

    def test_historical_values_never_replace_local_sensor_input(self):
        cfg=app.load_config();app.initialize(cfg);app.RUNTIME.select_profile('cyril');app.RUNTIME.set_mode('work')
        app.RUNTIME.ingest({'temperature_c':35,'humidity_pct':67})
        state=app.public_state(cfg)
        self.assertEqual(state['mirror']['sensors']['temperature_c'],35)
        dc=state['mirror']['work']['assistant']['data_center']
        self.assertEqual(dc['latest']['timestamp'],'2025-08-29T04:35:08+00:00')
        self.assertNotIn('temperature_c',dc['latest']['metrics'])
        self.assertNotIn('inbox',state)

    def test_importer_preserves_offsets_selects_rows_and_keeps_missing_values(self):
        self.assertEqual(timestamp('Thu Aug 28 2025 22:35:08 GMT-0600 (Mountain Daylight Time)').isoformat(),'2025-08-29T04:35:08+00:00')
        with TemporaryDirectory() as folder:
            archive=Path(folder)/'test.zip';out=Path(folder)/'out.json'
            text='ts,pue,it_power_kw,cooling_kw,hvac_kw,pump_kw,plug_and_light_kw\n2025-01-01T00:01:00+00:00,1.1,100,2,3,4,1\n2025-01-01T00:59:00+00:00,1.2,120,,3,4,1\n2025-01-01T01:30:00+00:00,1.3,130,2,3,4,1\n'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('power.csv',text)
            with patch('sys.stdout',new=io.StringIO()):build(archive,out)
            data=json.loads(out.read_text())
            self.assertEqual(data['source_row_count'],3);self.assertEqual(len(data['records']),2)
            self.assertEqual(data['records'][0]['metrics']['it_power_kw'],120)
            self.assertIsNone(data['records'][0]['metrics']['cooling_kw'])

    def test_nvidia_request_uses_official_endpoint_model_tools_and_env_key(self):
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'done'}}]}).encode())
        with patch.dict(os.environ,{'NVIDIA_API_KEY':'test-only-token'}),patch('nemotron_agent.urlopen',return_value=response) as call:
            self.assertEqual(request({},[{'role':'user','content':'test'}]),{'content':'done'})
        req=call.call_args.args[0];payload=json.loads(req.data)
        self.assertEqual(req.full_url,ENDPOINT);self.assertEqual(payload['model'],MODEL)
        self.assertEqual(req.get_header('Authorization'),'Bearer test-only-token')
        self.assertEqual({x['function']['name'] for x in payload['tools']},set(NAMES))
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertNotIn('test-only-token',req.data.decode())
        with patch.dict(os.environ,{},clear=True),patch('nemotron_agent.urlopen') as call:
            with self.assertRaises(ValueError):request({},[])
            call.assert_not_called()

    def test_configure_keeps_profiles_and_does_not_store_secret(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'; cfg=app.load_config();cfg['custom']='keep'
            path.write_text(json.dumps(cfg))
            with patch.dict(os.environ,{'NVIDIA_API_KEY':'DO-NOT-SAVE'}):result=configure(folder)
            self.assertEqual(result['profiles'],cfg['profiles']);self.assertEqual(result['custom'],'keep')
            self.assertNotIn('DO-NOT-SAVE',path.read_text())
            self.assertTrue(result['nemotron']['allow_demo'])
            self.assertTrue(list(Path(folder).glob('config.json.*.bak')))

    def test_unavailable_dataset_blocks_model_workflow(self):
        with self.assertRaises(ValueError):run({'enabled':True},{},{'data_center':{'available':False}})

if __name__=='__main__':unittest.main()
