'use strict';
let dashboard = null;
let hidden = sessionStorage.getItem('mirror-private') === 'true';
const el = id => document.getElementById(id);
function write(id, value) { el(id).textContent = value; }
function list(id, items, render) {
  const target = el(id); target.replaceChildren();
  for (const item of items) {
    const row = document.createElement('li'); render(row, item); target.append(row);
  }
}
function secondary(row, text) { const detail = document.createElement('small'); detail.textContent = text; row.append(detail); }
function zone() { return dashboard?.settings.timezone || 'America/Chicago'; }
function formatTime(value) { return new Date(value).toLocaleTimeString('en-US', {timeZone:zone(), hour:'numeric',minute:'2-digit'}); }
function eventTime(e) {
  if(e.all_day) return `${e.start} · All day`;
  return new Date(e.start).toLocaleDateString('en-US', {timeZone:zone(),weekday:'short',month:'short',day:'numeric'}) + ' · ' + formatTime(e.start);
}
function status(key) {
  const part = dashboard[key];
  write(`${key}-status`, `${part?.error || ''}${part?.updated ? ' Updated ' + formatTime(part.updated) : ' Waiting for data'}`);
}
function clock() {
  const now = new Date();
  write('time', now.toLocaleTimeString('en-US',{timeZone:zone(),hour:'numeric',minute:'2-digit'}));
  write('date',now.toLocaleDateString('en-US',{timeZone:zone(),weekday:'long',month:'long',day:'numeric'}));
  const events = dashboard?.calendar?.data || [];
  const active = events.find(e=> !e.all_day && new Date(e.start)<=now && new Date(e.end)>now);
  const next = events.find(e=> !e.all_day && new Date(e.start)>now);
  write('next', active ? `Now · ${active.title}` : next ? `${next.title} · in ${Math.ceil((new Date(next.start)-now)/60000)} min` : 'No upcoming timed events');
}
function privacy() {
  document.body.classList.toggle('private', hidden);
  write('privacy',hidden ? 'Show personal details' : 'Hide personal details');
  el('privacy').setAttribute('aria-pressed',String(hidden));
  sessionStorage.setItem('mirror-private',String(hidden));
}
function togglePrivacy() { hidden=!hidden; privacy(); }
el('privacy').addEventListener('click',togglePrivacy);
document.addEventListener('keydown',e=>{
  if(e.key.toLowerCase()==='p') togglePrivacy();
  if(e.key.toLowerCase()==='f') {
    const task = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    task.catch(()=>{});
  }
});
async function update() {
  try {
    const response = await fetch('/api/dashboard',{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!response.ok) throw new Error('Unavailable');
    dashboard = await response.json();
    write('greeting',`Hello, ${dashboard.settings.name}`);
    write('mode',dashboard.settings.demo ? 'DEMO · fictional data' : 'LIVE');
    write('location',dashboard.settings.location);
    const w=dashboard.weather?.data;
    if(w) {
      write('temperature',`${Math.round(w.temperature)}°F`);
      write('conditions',`${w.condition} · Feels like ${Math.round(w.feels_like)}°`);
      write('forecast',`High ${Math.round(w.high)}° / Low ${Math.round(w.low)}° · Rain ${w.rain ?? '—'}%`);
    }
    list('events',dashboard.calendar?.data?.slice(0,5)||[],(row,e)=>{row.textContent=e.title;secondary(row,eventTime(e)+(e.location ? ' · '+e.location : ''));});
    list('tasks',dashboard.settings.tasks.slice(0,3),(row,t)=>{row.textContent=t;});
    const b=dashboard.briefing?.data;
    write('summary',b?.summary || 'Briefing is not ready yet.');
    const sources=new Map([...(dashboard.calendar?.data||[]).map(e=>[e.id,e.title]),...(dashboard.inbox?.data?.messages||[]).map(m=>[m.id,m.subject])]);
    list('actions',b?.action_items||[],(row,a)=>{row.textContent=a.text;secondary(row,'Source: '+a.source_ids.map(s=>sources.get(s)||s).join(' · '));});
    const inbox=dashboard.inbox?.data;
    write('inbox-title',inbox ? `Inbox · ${inbox.unread} unread` : 'Inbox');
    list('messages',inbox?.messages?.slice(0,3)||[],(row,m)=>{row.textContent=m.subject;secondary(row,m.sender);});
    for(const key of ['weather','calendar','inbox','briefing']) status(key);
    write('connection','Display connected · '+formatTime(new Date()));
    clock();
  } catch {write('connection','Cannot reach mirror server · showing last displayed data');}
  finally {setTimeout(update,15000);}
}
privacy();clock();setInterval(clock,1000);update();
