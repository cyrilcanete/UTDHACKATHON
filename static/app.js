'use strict';
let dashboard = null;
let privacyHidden = sessionStorage.getItem('mirror-private') === 'true';
let requestVersion = 0;
let actionBusy = false;
let pollBusy = false;
let reviewVersion = 0;
let identity = '';
let profileSignature = '';
let sampleSignature = '';
const el = id => document.getElementById(id);
function write(id, value) { el(id).textContent = value ?? ''; }
function list(id, items, render) {
  const target = el(id); target.replaceChildren();
  for (const item of items) { const row = document.createElement('li'); render(row, item); target.append(row); }
}
function secondary(row, text) { const detail = document.createElement('small'); detail.textContent = text; row.append(detail); }
function zone() { return dashboard?.settings.timezone || 'America/Chicago'; }
function formatTime(value) { return new Date(value).toLocaleTimeString('en-US', {timeZone:zone(), hour:'numeric', minute:'2-digit'}); }
function eventTime(e) {
  if (e.all_day) return `${e.start} · All day`;
  return new Date(e.start).toLocaleDateString('en-US', {timeZone:zone(),weekday:'short',month:'short',day:'numeric'}) + ' · ' + formatTime(e.start);
}
function status(key) {
  const part = dashboard[key];
  write(`${key}-status`, `${part?.error || ''}${part?.updated ? ' Updated ' + formatTime(part.updated) : ' Waiting for data'}`);
}
function clock() {
  const now = new Date();
  write('time', now.toLocaleTimeString('en-US', {timeZone:zone(),hour:'numeric',minute:'2-digit'}));
  write('date', now.toLocaleDateString('en-US', {timeZone:zone(),weekday:'long',month:'long',day:'numeric'}));
  if (dashboard?.mirror.mode === 'work') { write('next','Conditions in your shared space.'); return; }
  const events = dashboard?.calendar?.data || [];
  const active = events.find(e => !e.all_day && new Date(e.start) <= now && new Date(e.end) > now);
  const next = events.find(e => !e.all_day && new Date(e.start) > now);
  write('next', active ? `Now · ${active.title}` : next ? `${next.title} · in ${Math.ceil((new Date(next.start)-now)/60000)} min` : 'No upcoming timed events');
}
function privacy() {
  document.body.classList.toggle('private', privacyHidden);
  write('privacy', privacyHidden ? 'Show personal details' : 'Hide personal details');
  el('privacy').setAttribute('aria-pressed', String(privacyHidden));
  sessionStorage.setItem('mirror-private', String(privacyHidden));
}
function resetReview() {
  reviewVersion++;
  el('message-text').value = '';
  el('review-result').hidden = true;
  for (const id of ['review-method','review-verdict','review-summary','review-next','review-ai','review-progress']) write(id,'');
  el('review-signals').replaceChildren();
}
function renderPersonal() {
  const w = dashboard.weather?.data;
  write('temperature', w ? `${Math.round(w.temperature)}°F` : '—');
  write('conditions', w ? `${w.condition} · Feels like ${Math.round(w.feels_like)}°` : 'Weather not available yet');
  write('forecast', w ? `High ${Math.round(w.high)}° / Low ${Math.round(w.low)}° · Rain ${w.rain ?? '—'}%` : '');
  list('events', dashboard.calendar?.data?.slice(0,5)||[], (row,e) => { row.textContent=e.title; secondary(row,eventTime(e)+(e.location ? ' · '+e.location : '')); });
  if (!el('events').children.length) list('events',['No upcoming events available.'], (row,text) => { row.textContent=text; });
  list('tasks', dashboard.settings.tasks.slice(0,3), (row,t) => { row.textContent=t; });
  const b = dashboard.briefing?.data;
  write('summary', b?.summary || 'Briefing is not ready yet.');
  const sources = new Map([...(dashboard.calendar?.data||[]).map(e=>[e.id,e.title]),...(dashboard.inbox?.data?.messages||[]).map(m=>[m.id,m.subject])]);
  list('actions', b?.action_items||[], (row,a) => { row.textContent=a.text; secondary(row,'Source: '+a.source_ids.map(s=>sources.get(s)||s).join(' · ')); });
  const inbox = dashboard.inbox?.data;
  write('inbox-title', inbox ? `Inbox · ${inbox.unread} unread` : 'Inbox');
  list('messages', inbox?.messages?.slice(0,3)||[], (row,m) => { row.textContent=m.subject; secondary(row,m.sender); });
  for (const key of ['weather','calendar','inbox','briefing']) status(key);
  const signature = JSON.stringify(dashboard.message_samples);
  if (signature !== sampleSignature) {
    sampleSignature = signature;
    el('message-samples').replaceChildren();
    for (const sample of dashboard.message_samples) {
      const button = document.createElement('button'); button.type='button'; button.textContent=sample.title;
      button.addEventListener('click', () => { el('message-text').value=sample.text; el('review-result').hidden=true; });
      el('message-samples').append(button);
    }
  }
}
function clearPersonal() {
  for (const id of ['events','tasks','messages','actions','message-samples']) el(id).replaceChildren();
  for (const id of ['summary','weather-status','calendar-status','inbox-status','briefing-status','conditions','forecast','temperature']) write(id,'');
  write('inbox-title','Inbox'); sampleSignature='';
}
function renderWork() {
  const {sensors:s, work:w} = dashboard.mirror;
  const temp = s.temperature_c === null ? '—' : `${s.temperature_c.toFixed(1)}°C`;
  write('room-temperature',temp); write('metric-temperature',temp);
  write('metric-humidity', s.humidity_pct === null ? '—' : `${s.humidity_pct.toFixed(0)}%`);
  write('metric-motion', s.motion === null ? 'Unavailable' : s.motion ? 'Detected' : 'Quiet');
  write('room-source', s.simulated ? 'SIMULATED · room sensor demonstration' : `${s.source.toUpperCase()} · shared room readings`);
  write('room-status', w.status==='normal' ? 'Within configured limits' : w.status==='attention' ? 'Attention needed' : 'Fresh readings needed');
  el('room-status').className=w.status==='attention' ? 'warning' : 'muted';
  write('temperature-limit', `Alert at ${w.limits.temperature_alert_c}°C or above`);
  write('humidity-limit', `Configured range ${w.limits.humidity_min_pct}–${w.limits.humidity_max_pct}%`);
  write('work-heading', w.status==='normal' ? 'Within configured limits' : w.status==='attention' ? 'Check these conditions' : 'Readings unavailable');
  list('work-alerts', w.alerts, (row,a) => { row.textContent=a.text; row.className=a.level; secondary(row,a.action); });
  if (!w.alerts.length) list('work-alerts',['No threshold alerts from the current readings.'], (row,t) => { row.textContent=t; });
  write('sensor-updated', s.updated ? `Last readings ${formatTime(s.updated)}${s.simulated ? ' · simulation' : ''}` : 'No sensor readings received');
  write('sensor-error',s.error || ''); write('handoff',w.handoff);
  document.querySelectorAll('[data-scenario]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.scenario===w.scenario)));
}
function render() {
  const m = dashboard.mirror;
  const nextIdentity = `${m.active_profile}:${m.mode}`;
  if (identity !== nextIdentity) { resetReview(); identity=nextIdentity; }
  document.body.dataset.view=m.mode;
  write('greeting',`Hello, ${dashboard.settings.name}.`);
  write('mode',dashboard.settings.demo ? 'DEMO · FICTIONAL ACCOUNT DATA' : 'LIVE ACCOUNT DATA');
  write('location',dashboard.settings.location); write('notice',m.event);
  el('personal-mode').setAttribute('aria-pressed',String(m.mode==='personal'));
  el('work-mode').setAttribute('aria-pressed',String(m.mode==='work'));
  el('personal-panels').hidden=m.mode!=='personal'; el('weather-panel').hidden=m.mode!=='personal';
  el('work-panels').hidden=m.mode!=='work'; el('room-glance').hidden=m.mode!=='work';
  el('privacy').hidden=m.mode!=='personal';
  if (m.mode==='personal') renderPersonal(); else clearPersonal();
  renderWork(); el('sleep-screen').hidden=m.screen_awake;
  el('demo-controls').hidden=!m.demo_controls;
  el('demo-scenarios').hidden=!m.demo_controls || m.sensors.source!=='demo';
  const signature = JSON.stringify(m.profiles);
  if (signature!==profileSignature) {
    profileSignature=signature; el('demo-profiles').replaceChildren();
    for (const p of m.profiles) {
      const button=document.createElement('button'); button.type='button'; button.className='action-control'; button.dataset.profile=p.id; button.textContent=`Scan ${p.name}'s card`;
      button.addEventListener('click',()=>action('/api/demo/scan',{profile_id:p.id})); el('demo-profiles').append(button);
    }
  }
  document.querySelectorAll('[data-profile]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.profile===m.active_profile)));
  write('connection','Display connected · '+formatTime(new Date())); clock();
}
async function post(path,payload) {
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(60000)});
  const data=await response.json(); if(!response.ok) throw new Error(data.error || 'Request failed'); return data;
}
async function action(path,payload) {
  if(actionBusy) return;
  actionBusy=true; const version=++requestVersion;
  document.querySelectorAll('.action-control').forEach(b=>b.disabled=true);
  try { const data=await post(path,payload); if(version===requestVersion) { dashboard=data; render(); } }
  catch(error) { write('notice',error.message); }
  finally { actionBusy=false; document.querySelectorAll('.action-control').forEach(b=>b.disabled=false); }
}
async function update() {
  if(actionBusy || pollBusy) return;
  pollBusy=true;
  const version=++requestVersion;
  try {
    const response=await fetch('/api/dashboard',{cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!response.ok) throw new Error('Unavailable');
    const data=await response.json(); if(version===requestVersion) { dashboard=data; render(); }
  } catch { if(version===requestVersion) write('connection','Mirror server unavailable · displayed information may be stale'); }
  finally {pollBusy=false;}
}
el('personal-mode').addEventListener('click',()=>action('/api/mode',{mode:'personal'}));
el('work-mode').addEventListener('click',()=>action('/api/mode',{mode:'work'}));
el('privacy').addEventListener('click',()=>{privacyHidden=!privacyHidden;privacy();});
el('wake').addEventListener('click',()=>action('/api/wake',{}));
document.querySelectorAll('[data-scenario]').forEach(b=>b.addEventListener('click',()=>action('/api/demo/scenario',{scenario:b.dataset.scenario})));
el('review-message').addEventListener('click',async()=>{
  const text=el('message-text').value.trim();
  if(!text) {write('review-progress','Enter a message first.'); return;}
  const requestedIdentity=identity;
  const requestedVersion=++reviewVersion;
  el('review-message').disabled=true; write('review-progress','Checking…'); el('review-result').hidden=true;
  try {
    const result=await post('/api/message-review',{text});
    if(identity!==requestedIdentity || reviewVersion!==requestedVersion) return;
    write('review-method',result.method); write('review-verdict',result.verdict); write('review-summary',result.summary);
    list('review-signals',result.signals,(row,s)=>{row.textContent=s.title;secondary(row,s.detail);});
    write('review-next',result.next_step); write('review-ai',result.ai_note ? 'Optional AI explanation: '+result.ai_note : result.ai_error || '');
    el('review-result').hidden=false; write('review-progress','Review complete.');
  } catch(error) {if(identity===requestedIdentity && reviewVersion===requestedVersion) write('review-progress',error.message);}
  finally {el('review-message').disabled=false;}
});
document.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
  if(e.key.toLowerCase()==='p') {privacyHidden=!privacyHidden;privacy();}
  if(e.key.toLowerCase()==='m' && dashboard) action('/api/mode',{mode:dashboard.mirror.mode==='personal'?'work':'personal'});
  if(e.key.toLowerCase()==='f') {
    const task=document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); task.catch(()=>{});
  }
});
privacy(); clock(); setInterval(clock,1000); update(); setInterval(update,2000);
