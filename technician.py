"""Technician context. Training records are explicit and never attributed to ESIF."""
import copy

TRAINING = {
    'asset': {'id':'CRAC-02','name':'Server-room cooling unit','location':'Training room A',
              'serves':['Rack A1','Rack A2'], 'sensor_link':'Training assumption: apply the displayed room readings to this exercise.'},
    'work_orders': [
        {'id':'WO-203','asset_id':'CRAC-02','assigned_to':'cyril','status':'open',
         'summary':'Investigate a reported rise in rack inlet temperature.',
         'last_note':'Previous shift reported reduced airflow. Filter inspection has not been completed.'},
        {'id':'WO-204','asset_id':'CRAC-02','assigned_to':'partner','status':'open',
         'summary':'Verify a reported humidity excursion and check the environmental sensor.',
         'last_note':'Compare with an independent meter before changing humidity settings.'},
        {'id':'WO-198','asset_id':'CRAC-02','assigned_to':'facilities','status':'awaiting inspection',
         'summary':'Inspect the return-air filter and record airflow.',
         'last_note':'No inspection result or confirmed component failure is recorded.'}
    ]
}

def context(cfg, snapshot):
    pid=snapshot.get('active_profile')
    name=next((p['name'] for p in snapshot['profiles'] if p['id']==pid),'Technician')
    configured=cfg.get('facility')
    training=not configured and bool(cfg.get('demo'))
    records=copy.deepcopy(configured if configured else TRAINING if training else {
        'asset':{'id':'LOCAL-DHT11-01','name':'Mirror room sensor station','location':'Local mirror room','serves':[],
                 'sensor_link':'Local DHT11 temperature and humidity readings.'},'work_orders':[]})
    asset=records.get('asset',{})
    orders=[o for o in records.get('work_orders',[]) if o.get('asset_id')==asset.get('id')]
    # Sarah's stable ID remains partner; accept either spelling in configured records.
    aliases={pid,'sarah'} if pid=='partner' else {pid}
    assigned=[o for o in orders if o.get('assigned_to') in aliases]
    s=snapshot['sensors']; flags=snapshot['work']['alerts']
    missing=s.get('temperature_c') is None or s.get('humidity_pct') is None
    temp_high=s.get('temperature_c') is not None and s['temperature_c']>=snapshot['work']['limits']['temperature_alert_c']
    humid=s.get('humidity_pct'); limits=snapshot['work']['limits']
    humidity_issue=humid is not None and not limits['humidity_min_pct']<=humid<=limits['humidity_max_pct']
    if missing:
        assessment='Sensor data is missing or stale; the condition of the equipment is unconfirmed.'
        next_step='Restore the sensor connection and obtain a fresh reading before assessing the reported issue.'
    elif temp_high:
        assessment='Measured temperature exceeds the configured room limit. Reduced airflow is a possibility to investigate, not a confirmed fault.'
        next_step='Compare the reading with an independent thermometer, then check accessible intake and exhaust paths for obstructions.'
    elif humidity_issue:
        assessment='Measured humidity is outside the configured range. Sensor error and a room-control issue remain possible.'
        next_step='Compare humidity with an independent meter and record both readings before changing any equipment settings.'
    else:
        assessment='Current readings are within the configured limits.'
        if assigned:
            assessment+=' An open work order still needs verification before closure.'
        next_step='Recheck the reported issue and record a second reading; do not close the work order from one normal sample.' if assigned else 'Record a second reading and verify the sensor location before drawing conclusions about nearby equipment.'
    focus='humidity' if pid in ('partner','sarah') else 'temperature'
    if focus=='humidity' and not missing and not temp_high:
        next_step='Compare the DHT11 humidity with an independent meter and '+('attach both readings to the assigned work order.' if assigned else 'record both readings in the local inspection notes.')
    steps=records.get('procedures') or [
        'Confirm the equipment ID, sensor location and age of the reading.',
        'Compare temperature and humidity with an independent instrument.',
        'Review the assigned order and related filter-inspection history before repeating work.',
        'Check accessible airflow paths visually; do not open electrical or pressurized equipment.',
        'Record observations and escalate persistent out-of-range conditions to the responsible operator.'
    ]
    return {'technician':name,'profile_id':pid,'training':training,
        'label':'Training scenario · fictional equipment/work orders' if training else 'Configured local equipment and work records',
        'asset':asset,'assigned_orders':assigned,'related_orders':orders,'focus':focus,
        'assessment':assessment,'next_step':next_step,'procedure':steps,
        'procedure_status':'Project troubleshooting checklist; not a manufacturer-approved procedure.',
        'possible_impact':'If cooling is insufficient, the served racks may experience warmer inlet air; no downstream fault has been confirmed.' if training else 'Downstream impact is unconfirmed; use the configured asset records.',
        'evidence':{'readings':copy.deepcopy(s),'limits':copy.deepcopy(limits),'alerts':copy.deepcopy(flags)},
        'trace':['Read room sensors','Look up equipment','Review existing work orders','Choose verification procedure','Prepare next action']}
