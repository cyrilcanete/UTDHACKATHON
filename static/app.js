'use strict';
const $ = id => document.getElementById(id);
let state = null, sequence = 0, profilesKey = '', lastSession = '', sessionStart = Date.now();
const cache = new Map();
function fitScreen() {
  const scale = Math.min(innerWidth / 1920, innerHeight / 1080);
  $('stage').style.transform = `scale(${scale})`;
  $('stage').style.left = `${(innerWidth - 1920 * scale) / 2}px`;
  $('stage').style.top = `${(innerHeight - 1080 * scale) / 2}px`;
}
addEventListener('resize', fitScreen); fitScreen();
function clearPrivate() {
  $('dashboard').hidden = true; $('welcome').hidden = false;
  for (const id of ['greeting','left-page','right-page','weather','readings','left-title','right-title']) $(id).textContent = '';
  cache.clear();
}
function card(title, text, highlights=[]) { return {title, text: String(text || 'No information available.'), highlights}; }
// Divide by actual rendered height, keeping every word. Never line-clamp or ellipsize.
function pagesFor(cards, element) {
  const key = element.id + JSON.stringify(cards);
  if (cache.has(key)) return cache.get(key);
  const pages = [];
  for (const c of cards) {
    const words = c.text.match(/\S+\s*/g) || ['No information available.'];
    let text = '';
    for (const word of words) {
      element.textContent = text + word;
      if (text && element.scrollHeight > element.clientHeight) {
        pages.push(card(c.title, text.trimEnd(), c.highlights)); text = word;
      } else text += word;
      element.textContent = text;
      while (element.scrollHeight > element.clientHeight) {
        let low = 1, high = text.length;
        while (low < high) {
          const mid = Math.ceil((low + high) / 2);
          element.textContent = text.slice(0, mid);
          if (element.scrollHeight <= element.clientHeight) low = mid; else high = mid - 1;
        }
        pages.push(card(c.title, text.slice(0, low), c.highlights));
        text = text.slice(low); element.textContent = text;
      }
    }
    if (text) pages.push(card(c.title, text.trimEnd(), c.highlights));
  }
  if (cache.size > 8) cache.clear();
  cache.set(key, pages); return pages;
}
function showPages(side, cards) {
  const element = $(side + '-page'), pages = pagesFor(cards, element);
  const index = Math.floor((Date.now() - sessionStart) / 14000) % pages.length;
  element.textContent = pages[index].text;
  const terms = (pages[index].highlights || []).filter(x => x && x.length > 2);
  if (terms.length) {
    const pattern = new RegExp('(' + terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')','gi');
    const text=pages[index].text; const fragment=document.createDocumentFragment(); let end=0;
    for (const match of text.matchAll(pattern)) {
      fragment.append(document.createTextNode(text.slice(end,match.index)));
      const mark=document.createElement('mark'); mark.textContent=match[0]; fragment.append(mark); end=match.index+match[0].length;
    }
    fragment.append(document.createTextNode(text.slice(end))); element.replaceChildren(fragment);
  }
  $(side + '-title').textContent = pages[index].title;
  $(side + '-count').textContent = `${index + 1} / ${pages.length} · advances automatically`;
}
function clock() {
  if (!state) return;
  const opts = {timeZone:state.settings.timezone};
  $('time').textContent = new Date().toLocaleTimeString('en-US',{...opts,hour:'numeric',minute:'2-digit'});
  $('date').textContent = new Date().toLocaleDateString('en-US',{...opts,weekday:'long',month:'short',day:'numeric'});
}
function render(data) {
  state = data;
  const brightness = data.mirror.brightness;
  $('stage').style.filter = `brightness(${typeof brightness === 'number' && Number.isFinite(brightness) ? Math.max(.05, Math.min(1, brightness)) : 1})`;
  const m = data.mirror, session = `${m.active_profile}:${m.mode}`;
  if (session !== lastSession) { clearPrivate(); sessionStart = Date.now(); lastSession = session; }
  if (!m.demo_controls && $('demo').open) $('demo').close();
  if (m.mode === 'welcome' || !m.screen_awake) { clearPrivate(); return; }
  $('welcome').hidden = true; $('dashboard').hidden = false;
  $('greeting').textContent = m.mode === 'work' ? `${data.settings.name}'s work desk` : `Hello, ${data.settings.name}`;
  $('mode').textContent = `${m.mode} mode`;
  $('source').textContent = data.settings.demo ? 'DEMO account data' + (m.sensors.simulated ? ' · simulated sensors' : ' · live sensor input') : 'Your mirror · live connections';
  const s = m.sensors;
  $('readings').textContent = `${s.temperature_c == null ? '—' : s.temperature_c.toFixed(1) + '°C'}  ·  ${s.humidity_pct == null ? '—' : Math.round(s.humidity_pct) + '% RH'}`;
  $('sensor-status').textContent = (s.error ? 'DHT11 connection unavailable' : '') || (s.temperature_c == null || s.humidity_pct == null ? 'DHT11 unavailable / stale' : s.simulated ? 'Simulated room conditions' : 'DHT11 · fresh room readings');
  $('connection').textContent = 'Connected · ' + (m.rfid_status || 'Card reader ready');
  clock();
  let left = [], right = [];
  if (m.mode === 'personal') {
    const w = data.weather?.data;
    $('weather').textContent = (data.weather?.error ? 'Outdoor weather unavailable' : '') || (w ? `${w.temperature}°F outdoors\n${w.condition}` : 'Outdoor weather unavailable');
    const events = data.calendar?.data || [];
    left.push(card('Your schedule', data.calendar?.error || (events.length ? events.map(e => {
      const when = e.all_day ? e.start : new Date(e.start).toLocaleString('en-US',{timeZone:data.settings.timezone,weekday:'short',hour:'numeric',minute:'2-digit'});
      return `${when}\n${e.title}${e.location ? '\n' + e.location : ''}`;
    }).join('\n\n') : 'No upcoming events.')));
    if (data.settings.tasks.length) left.push(card('Your priorities',data.settings.tasks.join('\n\n')));
    const inbox = data.inbox?.data;
    // Safety review first so the demo is visible immediately after scanning.
    for (const item of inbox?.reviews || []) {
      const phrases=item.review.signals.flatMap(x=>x.matches || []);
      const excerpt=item.review.excerpt || '';
      right.push(card('Message · pause before acting', `${excerpt.startsWith(item.subject) ? excerpt : item.subject+'\n\n'+excerpt}\n\nSafer action: ${item.review.next_step}`,phrases));
      right.push(card('Why these phrases matter', `${item.review.signals.map(x => `“${(x.matches || []).join('”, “')}” — ${x.detail}`).join('\n\n')}\n\n${inbox.review_scope}\nPhrase matches are not proof of fraud.`,phrases));
    }
    if (data.personal_assistant?.ai) {
      const ai=data.personal_assistant.ai;
      right.push(card('Nemotron · personal review', `${ai.note}\n\n${ai.tools ? 'Completed '+ai.tools.length+' read-only tools.' : ai.method}\nGenerated ${ai.generated_at || 'this session'}`));
    }
    right.push(card('Your briefing', data.briefing?.error || data.briefing?.data?.summary || 'No briefing available.'));
    right.push(card('Inbox', data.inbox?.error || `${inbox?.unread ?? '—'} unread\n\n${(inbox?.messages || []).map(x => x.subject + '\n' + x.sender).join('\n\n') || 'No unread messages.'}\n\n${inbox?.review_scope || ''}`));
    if (!(inbox?.reviews || []).length && !data.inbox?.error) right.push(card('Inbox review', 'No matching warning patterns in the checked messages. This does not establish that messages are safe.'));
  } else {
    $('weather').textContent = `Room status: ${m.work.status}`;
    const a = m.work.assistant;
    const tc = a.technician;
    const assigned = tc.assigned_orders[0];
    $('source').textContent = tc.training ? 'TRAINING CASE · historical ESIF reference' : 'Local technician task · historical ESIF reference';
    left.push(card(`${tc.technician} · assignment`, `${assigned ? assigned.id+' · '+assigned.status+'\n'+assigned.summary : 'Verify local environmental conditions'}\n\n${tc.asset.id} · ${tc.asset.name}`));
    right.push(card('Technician · next action', `${tc.assessment}\n\nNext step: ${tc.next_step}\n\n${assigned ? 'Existing order '+assigned.id+': '+assigned.last_note : 'No assigned work order is connected.'}\n\n${tc.label}`));
    right.push(card('Equipment & work history', `${tc.asset.name} · ${tc.asset.id}\n${tc.asset.sensor_link || ''}\n\n${tc.related_orders.map(o => o.id+' · '+o.status+'\n'+o.summary+'\n'+(o.last_note || '')).join('\n\n')}\n\n${tc.possible_impact}`));
    right.push(card('Troubleshooting procedure', `${tc.procedure.map((x,i)=>(i+1)+'. '+x).join('\n\n')}\n\n${tc.procedure_status}`));
    const dc = a.data_center;
    const num = (v,d=1) => typeof v === 'number' ? v.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d}) : 'Unavailable';
    if (dc?.available) {
      const at = dc.latest.timestamp.slice(0,19).replace('T',' ') + ' UTC';
      const power = dc.latest.metrics;
      $('source').textContent = `${tc.training ? 'TRAINING CASE · ' : ''}ESIF HISTORICAL\n${at}`;
      left.push(card('ESIF · recorded power', `PUE ${num(power.pue,3)}\nIT equipment ${num(power.it_power_kw)} kW\nCooling ${num(power.cooling_kw)} kW\nHVAC ${num(power.hvac_kw)} kW\nPumps ${num(power.pump_kw)} kW\n\nRecorded ${at}`));
      left.push(card('Source & coverage', `${dc.facility}\n\n${dc.record_count} hourly observations\n${dc.period_start.slice(0,10)} to ${dc.period_end.slice(0,10)}\n\nReal historical data · not live\nDOI ${dc.doi}`));
      if (a.ai) right.push(card(a.ai.method, `${a.ai.note}\n\n${a.ai.tools ? 'Completed '+a.ai.tools.length+' read-only tools.\n' : ''}Generated ${a.ai.generated_at || 'during this session'}. Local sensor context may have changed since generation.`));
      const pue = dc.statistics.pue;
      right.push(card('Data-center evidence', `Latest recorded PUE: ${num(power.pue,3)}\nPUE range across ${pue.count} recent hourly samples: ${num(pue.min,3)}–${num(pue.max,3)}\n\n${dc.missing_latest.length ? 'Missing latest fields: '+dc.missing_latest.join(', ') : 'All displayed power fields are present.'}\n\n${dc.questionable_latest.length ? 'Check questionable values: '+dc.questionable_latest.join(', ')+'. ' : ''}These values alone do not establish an equipment failure.\n\n${a.ai_status}`));
      right.push(card('Data provenance', `${dc.attribution}\n\n${dc.source_url}\n\n${dc.note}\n\n${dc.maintenance_status}`));
    } else {
      left.push(card('Data center unavailable', dc?.error || 'Real dataset unavailable.'));
      right.push(card('Source connection', 'No measurements will be invented. Restore the ESIF data file and restart the app.'));
    }
    right.push(card('Local mirror room · DHT11', `${m.work.handoff}\n\n${a.procedure.map((x,i) => `${i+1}. ${x}`).join('\n\n')}\n\n${a.incident ? a.incident.id + '\n' + a.incident.status : 'No local incident needed.'}\n${a.storage}\n\nThese local readings are separate from ESIF.`));

  }
  showPages('left',left); showPages('right',right);
}
async function refresh(path='/api/dashboard', payload) {
  const seq = ++sequence;
  try {
    const response = await fetch(path, {cache:'no-store',signal:AbortSignal.timeout(5000), ...(payload ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {})});
    if (!response.ok) throw Error(`Request failed (${response.status})`);
    const data = await response.json();
    if (seq === sequence) { render(data); $('demo-error').textContent = ''; }
  } catch(e) {
    if (seq === sequence) { state = null; clearPrivate(); $('demo-error').textContent = 'Mirror disconnected. Check the Python window.'; }
  }
}
function toggleDemo() {
  if (!state?.mirror.demo_controls) return;
  const key = JSON.stringify(state.mirror.profiles);
  if (key !== profilesKey) {
    $('profile-buttons').replaceChildren();
    state.mirror.profiles.forEach(p => { const b = document.createElement('button'); b.textContent = `Scan ${p.name}`; b.onclick = () => { $('demo').close(); refresh('/api/demo/scan',{profile_id:p.id}); }; $('profile-buttons').append(b); });
    profilesKey = key;
  }
  $('demo').open ? $('demo').close() : $('demo').showModal();
}
document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { $('demo').close(); refresh('/api/mode',{mode:b.dataset.mode}); });
document.querySelectorAll('[data-scenario]').forEach(b => b.onclick = () => { $('demo').close(); refresh('/api/demo/scenario',{scenario:b.dataset.scenario}); });
$('finish').onclick = () => { $('demo').close(); refresh('/api/welcome',{}); };
$('close-demo').onclick = () => $('demo').close();
addEventListener('keydown', e => {
  const key = e.key.toLowerCase();
  if (key === 'f') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); return; }
  if (key === 'd') { toggleDemo(); return; }
  if (key === 'escape') { refresh('/api/welcome',{}); return; }
  if (!state?.mirror.demo_controls) return;
  if (['arrowleft','arrowright','1','2','h','n','o','b','i'].includes(key)) { e.preventDefault(); if ($('demo').open) $('demo').close(); }
  if (key === '1' || key === '2') { const p = state.mirror.profiles[Number(key)-1]; if(p) refresh('/api/demo/scan',{profile_id:p.id}); }
  if (key === 'arrowright' || key === 'arrowleft') refresh('/api/mode',{mode:key === 'arrowright' ? 'personal' : 'work'});
  const scenarios = {h:'hot',n:'normal',o:'offline',b:'near',i:'away'};
  if (scenarios[key]) refresh('/api/demo/scenario',{scenario:scenarios[key]});
});
async function poll() { await refresh(); setTimeout(poll,1000); }
poll();
