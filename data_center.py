"""Real, attributed ESIF measurements. Historical source data never replaces the local DHT11."""
import copy
import json
import math
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data/esif_power_excerpt.json'
FIELDS = ('pue','it_power_kw','cooling_kw','hvac_kw','pump_kw','plug_and_light_kw')

class DataCenter:
    def __init__(self, path=DATA):
        self.error=None; self.data=None
        try:
            data=json.loads(Path(path).read_text())
            if data.get('schema_version')!=1 or data.get('historical') is not True:
                raise ValueError('Unsupported dataset')
            records=data['records']
            if not isinstance(records,list) or not 1<=len(records)<=1000:
                raise ValueError('Invalid record count')
            previous=None
            for record in records:
                at=datetime.fromisoformat(record['timestamp'])
                if at.tzinfo is None or (previous and at<=previous): raise ValueError('Timestamps must increase and include a timezone')
                previous=at
                for k in FIELDS:
                    v=record['metrics'].get(k)
                    if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):
                        raise ValueError('Non-finite measurement')
            self.data=data
        except (OSError,ValueError,KeyError,TypeError):
            self.error='ESIF dataset unavailable or invalid. Restore data/esif_power_excerpt.json or run the importer.'

    def snapshot(self):
        if self.error:
            return {'available':False,'historical':True,'error':self.error,'source_url':'https://data.nlr.gov/submissions/300'}
        d=self.data; latest=d['records'][-1]; recent=d['records'][-24:]
        statistics={}
        for k in FIELDS:
            values=[r['metrics'].get(k) for r in recent if r['metrics'].get(k) is not None]
            statistics[k]={'count':len(values),'min':min(values) if values else None,'max':max(values) if values else None,
                           'mean':sum(values)/len(values) if values else None}
        missing=[k for k in FIELDS if latest['metrics'].get(k) is None]
        questionable=[k for k,v in latest['metrics'].items() if v is not None and (v<0 or (k=='pue' and v<1))]
        return copy.deepcopy({'available':True,'historical':True,'facility':d['facility'],
            'source_url':d['source_url'],'doi':d['doi'],'attribution':d['attribution'],
            'retrieved_at':d['retrieved_at'],'selection':d['selection'],
            'latest':latest,'recent':recent,'statistics':statistics,
            'period_start':d['records'][0]['timestamp'],'period_end':latest['timestamp'],
            'record_count':len(d['records']),'missing_latest':missing,'questionable_latest':questionable,
            'maintenance_status':'No maintenance tickets, rack inventory or verified fault labels are supplied by this public dataset.',
            'note':'Real historical measurements, not a live facility connection. Local DHT11 readings describe the mirror room only.'})
