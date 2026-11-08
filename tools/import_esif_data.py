"""Build a small, reproducible historical excerpt from the official ESIF CSV ZIP.
Usage: python tools/import_esif_data.py downloaded-power.zip
No interpolation, invented readings, or implied live feed. Retains the latest row per UTC hour.
"""
import csv
import hashlib
import io
import json
import math
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ('pue','it_power_kw','cooling_kw','hvac_kw','pump_kw','plug_and_light_kw')
MONTHS = dict(zip('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), range(1,13)))
SOURCE = 'https://data.nlr.gov/submissions/300'
RESOURCE = 'https://data.nlr.gov/system/files/300/1757105566-esif.influx.buildingData.PUE.combined.csv.zip'

def timestamp(value):
    # Source includes an explicit UTC offset and a human-readable timezone suffix.
    parts=value.split()
    if len(parts)>=6 and parts[1] in MONTHS and parts[5].startswith('GMT'):
        normalized=f'{parts[3]}-{MONTHS[parts[1]]:02}-{int(parts[2]):02}T{parts[4]}{parts[5][3:]}'
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('Source timestamp has no timezone')
    return parsed.astimezone(timezone.utc)

def number(value):
    try: result=float(value)
    except (ValueError,TypeError): return None
    return result if math.isfinite(result) else None

def build(archive, output):
    hours={}; count=0; first=None; latest=None
    with zipfile.ZipFile(archive) as z:
        members=[i for i in z.infolist() if i.filename.endswith('.csv') and not i.filename.startswith('__MACOSX/')]
        if len(members)!=1: raise ValueError('Expected one source CSV')
        with z.open(members[0]) as f:
            rows=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))
            if not set(('ts',*FIELDS)).issubset(rows.fieldnames): raise ValueError('Dataset columns changed')
            for row in rows:
                at=timestamp(row['ts']); count+=1
                first=min(first,at) if first else at; latest=max(latest,at) if latest else at
                metrics={k:number(row[k]) for k in FIELDS}
                if not any(v is not None for v in metrics.values()): continue
                key=at.replace(minute=0,second=0,microsecond=0).isoformat()
                record={'timestamp':at.isoformat(),'source_timestamp':row['ts'],'metrics':metrics}
                if key not in hours or record['timestamp']>hours[key]['timestamp']: hours[key]=record
                # Keep bounded memory even if source rows arrive out of order.
                if len(hours)>336:
                    for old in sorted(hours)[:-168]: del hours[old]
    selected=[hours[k] for k in sorted(hours)[-168:]]
    if not selected: raise ValueError('No measurements found')
    digest=hashlib.sha256()
    with open(archive,'rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''): digest.update(chunk)
    result={'schema_version':1,'facility':'ESIF High-Performance Computing Data Center',
        'source_url':SOURCE,'resource_url':RESOURCE,'doi':'10.7799/3015212',
        'attribution':'Struan Clark and Justin Strelka; DOE/NREL/ALLIANCE; NLR Data Catalog',
        'license_url':'https://data.nlr.gov/node/300/license','historical':True,
        'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'archive_sha256':digest.hexdigest(),
        'source_row_count':count,'source_start':first.isoformat(),'source_end':latest.isoformat(),
        'selection':'Latest source row per UTC hour, retaining the last 168 observed hours. Missing values remain null. No interpolation.',
        'records':selected}
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    print('Excerpt records:',len(selected),'Latest:',selected[-1])

if __name__=='__main__':
    build(sys.argv[1],Path(__file__).resolve().parents[1]/'data/esif_power_excerpt.json')
