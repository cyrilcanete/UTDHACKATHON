'use strict';
const $ = id => document.getElementById(id);
let state = null, sequence = 0, profilesKey = '', lastSession = '', sessionStart = Date.now();
let attentionHeld = false, lastAiResult = '', analyzePending = false, analyzeError = '';
const cache = new Map();
function fitScreen() {
  const scale = Math.min(innerWidth / 1920, innerHeight / 1080);
  $('stage').style.transform = `scale(${scale})`;
  $('stage').style.left = `${(innerWidth - 1920 * scale) / 2}px`;
  $('stage').style.top = `${(innerHeight - 1080 * scale) / 2}px`;
}
addEventListener('resize', fitScreen); fitScreen();
function clearPrivate() {
  attentionHeld = false; lastAiResult = ''; analyzeError = '';
  $('room-warning').hidden = true; $('warning-detail').textContent = '';
  $('dashboard').classList.remove('attention');
  $('nemotron-panel').hidden = true; $('nemotron-trace').replaceChildren();
  for (const id of ['nemotron-status','nemotron-detail','nemotron-hint']) $(id).textContent = '';
  $('analyze').disabled = true; $('demo-ai-status').textContent = 'Scan a card to select a mode.';
  $('dashboard').hidden = true; $('welcome').hidden = false;
  for (const id of ['greeting','left-page','right-page','weather','readings','left-title','right-title']) $(id).textContent = '';
  cache.clear();
}
function card(title, text, highlights=[]) { return {title, text: String(text || 'No information available.'), highlights}; }
function currentAssistant(data=state) {
  return data?.mirror.mode === 'work' ? data.mirror.work?.assistant : data?.personal_assistant;
}
function canAnalyze(data=state) {
  const mode=data?.mirror.mode, availability=currentAssistant(data)?.ai_state;
  return !analyzePending && data?.mirror.screen_awake && data?.mirror.active_profile &&
    availability?.can_analyze !== false && ['personal','work'].includes(mode) &&
    ['ready','complete','error','stale'].includes(availability?.state);
}
const toolLabels = {
  read_datacenter_metrics:'Historical power readings', read_datacenter_history:'Historical trends',
  read_local_environment:'Local room readings', lookup_data_provenance:'Source and date checks',
  lookup_equipment:'Equipment records', lookup_work_orders:'Existing work orders',
  lookup_procedure:'Troubleshooting checklist', get_selected_message:'Selected message',
  inspect_warning_signs:'Message warning signs', lookup_verification_guidance:'Verification guidance',
  recommend_safer_action:'Safer next action'
};
function renderAssistant(data) {
  const assistant=currentAssistant(data), aiState=assistant?.ai_state || {state:'disabled'};
  const labels={disabled:'Local guidance · AI off',ready:'Nemotron · ready',queued:'Nemotron · queued',
    running:'Nemotron · working',complete:'Nemotron · live review',error:'Local guidance · AI unavailable',stale:'Local guidance · AI out of date'};
  const defaults={disabled:'Live AI is off. Showing local guidance.',ready:'Ready to review the current evidence.',
    queued:'Analysis is waiting to start.',running:'Reviewing evidence with tools.',complete:'AI suggestions are ready for your review.',
    error:'Analysis did not complete. Local guidance remains available.',stale:'The evidence changed. Run a new analysis.'};
  const status=aiState.state in labels ? aiState.state : 'disabled';
  if (['queued','running'].includes(status)) analyzeError='';
  const feedback=data.mirror.analysis_feedback;
  const physicalFeedback=feedback && !['queued','busy'].includes(feedback.code) && typeof feedback.message === 'string' ? feedback.message : '';
  const requestFeedback=analyzeError || physicalFeedback;
  $('nemotron-panel').hidden=false;
  $('nemotron-status').textContent=requestFeedback && status !== 'disabled' ? 'Analysis was not started' : analyzePending ? 'Nemotron · requesting analysis' : labels[status];
  const message=requestFeedback || aiState.message || defaults[status];
  $('nemotron-detail').textContent=message;
  // These are actual tool events only. Model reasoning and fabricated progress are never displayed.
  const trace=Array.isArray(aiState.trace) ? aiState.trace : [];
  const items=trace.slice(-3).map(item=>{
    const li=document.createElement('li');
    const label=toolLabels[item.tool] || String(item.tool || 'Tool').replaceAll('_',' ');
    const status=['returned','complete','completed'].includes(item.status) ? 'done' :
      ['calling','running','started'].includes(item.status) ? 'running' : item.status === 'error' ? 'failed' : 'requested';
    li.textContent=`${label} · ${status}`; return li;
  });
  $('nemotron-trace').replaceChildren(...items);
  const done=trace.filter(item=>['returned','complete','completed'].includes(item.status)).length;
  $('nemotron-hint').textContent=[done ? `${done} tool result${done === 1 ? '' : 's'}` : '',canAnalyze(data) ? `Quick press or A: analyze${status === 'complete' ? ' again' : ''}` : ''].filter(Boolean).join(' · ');
  $('analyze').disabled=!canAnalyze(data);
  $('demo-ai-status').textContent=`${$('nemotron-status').textContent}. ${message}${aiState.model ? '\nModel: '+aiState.model : ''}`;
}
function completedAi(assistant) {
  // Older error objects also had an "ai" field: only current, completed tool runs earn an AI card.
  const ai=assistant?.ai;
  return assistant?.ai_state?.state === 'complete' && typeof ai?.note === 'string' && Array.isArray(ai.tools) && ai.tools.length ? ai : null;
}
function aiCard(ai) {
  return card('Nemotron · live review', `${ai.note}\n\n${ai.tools.length} tools returned evidence. Verify AI suggestions.\nGenerated ${ai.generated_at || 'this session'}`);
}
// Divide by actual rendered height, keeping every word. Never line-clamp or ellipsize.
function pagesFor(cards, element) {
  const key = `${element.id}:${element.clientWidth}:${element.clientHeight}:${getComputedStyle(element).fontSize}:` + JSON.stringify(cards);
  if (cache.has(key)) return cache.get(key);
  const pages = [];
  for (const c of cards) {
    // A procedure is always one fitted slide, including during normal rotation.
    if (c.procedure) { pages.push(c); continue; }
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
function showPages(side, cards, pinned=false) {
  const element = $(side + '-page'), pages = pagesFor(cards, element);
  const index = pinned ? 0 : Math.floor((Date.now() - sessionStart) / 14000) % pages.length;
  if (pages[index].procedure) { showProcedure(pages[index].procedure,false); return; }
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
  $(side + '-count').textContent = pinned ? 'Held · room needs attention' : `${index + 1} / ${pages.length} · advances automatically`;
}
function fitPage(element) {
  let size=25; element.style.fontSize=size+'px';
  while(element.scrollHeight>element.clientHeight && size>16) { size--; element.style.fontSize=size+'px'; }
  const scroll=element.scrollHeight>element.clientHeight;
  element.style.overflowY=scroll ? 'auto' : '';
  return scroll;
}
function showSchedule(schedule) {
  $('left-title').textContent=schedule.title;
  $('left-page').textContent=schedule.text;
  fitPage($('left-page'));
  $('left-count').textContent='';
}
function showProcedure(tc, paused=true) {
  const element=$('right-page');
  element.textContent=`Next step: ${tc.next_step}\n\n${tc.procedure.map((step,i)=>(i+1)+'. '+step).join('\n\n')}\n\n${tc.procedure_status}`;
  // Keep the whole checklist in view instead of freezing on a paginated fragment.
  const scroll=fitPage(element);
  $('right-title').textContent='Troubleshooting procedure';
  $('right-count').textContent=paused ? (scroll ? 'Procedure held · scroll for remaining steps' : 'Held until fresh readings are normal') : 'Troubleshooting procedure · advances automatically';
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
  document.querySelectorAll('[data-scenario]').forEach(button=>button.disabled=!m.demo_controls || !m.sensors.simulated);
  $('demo-sensor-status').hidden=Boolean(m.sensors.simulated);
  if (!m.demo_controls && $('demo').open) $('demo').close();
  if (m.mode === 'welcome' || !m.screen_awake) { clearPrivate(); return; }
  $('welcome').hidden = true; $('dashboard').hidden = false;
  const attention=m.mode === 'work' && (m.work.status === 'attention' || (attentionHeld && m.work.status === 'unknown'));
  if (attention !== attentionHeld) { sessionStart=Date.now(); cache.clear(); }
  attentionHeld=attention;
  $('dashboard').classList.toggle('attention',attention);
  $('room-warning').hidden=!attention;
  $('warning-heading').textContent=m.work.status === 'unknown' ? 'Room status unconfirmed' : 'Room needs attention';
  $('warning-detail').textContent=attention ? m.work.alerts.map(alert=>alert.text).join('\n') : '';
  if (attention) $('stage').style.filter='brightness(1)';
  $('left-page').style.fontSize=''; $('left-page').style.overflowY='';
  $('right-page').style.fontSize=''; $('right-page').style.overflowY='';
  const ai=completedAi(currentAssistant(data));
  const aiKey=ai ? JSON.stringify([ai.generated_at,ai.note]) : '';
  if (aiKey && aiKey !== lastAiResult) { sessionStart=Date.now(); cache.clear(); analyzeError=''; }
  lastAiResult=aiKey;
  renderAssistant(data);
  $('greeting').textContent = m.mode === 'work' ? `${data.settings.name}'s work desk` : `Hello, ${data.settings.name}`;
  $('mode').textContent = `${m.mode} mode`;
  $('source').textContent = data.settings.demo ? 'DEMO account data' + (m.sensors.simulated ? ' · simulated sensors' : ' · live sensor input') : 'Your mirror · live connections';
  $('room-readings').hidden=m.mode !== 'work';
  $('room-label').textContent=data.settings.demo ? 'In Demo data center' : 'In this room';
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
    left.push(card('Schedule', data.calendar?.error || (events.length ? events.map(e => {
      if (e.display_text) return e.display_text;
      const when = e.all_day ? e.start : new Date(e.start).toLocaleString('en-US',{timeZone:data.settings.timezone,weekday:'short',hour:'numeric',minute:'2-digit'});
      return `${when}\n${e.title}${e.location ? '\n' + e.location : ''}`;
    }).join('\n\n') : 'No upcoming events.')));
    right.push(card('Briefing', data.briefing?.error || data.briefing?.data?.summary || 'No briefing available.'));
    const inbox=data.inbox?.data, reviewItems=inbox?.reviews || [];
    if (reviewItems.length) {
      for (const item of reviewItems) {
        const phrases=item.review.signals.flatMap(x=>x.matches || []);
        const details=item.review.signals.map(x=>'• '+x.detail).join('\n\n');
        right.push(card(`Inbox · ${inbox.unread} unread`, `${item.subject}\n\n${details}\n\nSafer Action\n${item.review.next_step}`,phrases));
      }
    } else right.push(card(`Inbox · ${inbox?.unread ?? '—'} unread`,data.inbox?.error || 'No phishing terms detected'));
    if (ai) right.unshift(aiCard(ai));
  } else {
    $('weather').textContent = `Room status: ${m.work.status}`;
    const a = m.work.assistant;
    const tc = a.technician;
    const assigned = tc.assigned_orders[0];
    $('source').textContent = tc.training ? 'TRAINING CASE · historical ESIF reference' : 'Local technician task · historical ESIF reference';
    left.push(card('Assignment for today', `${assigned ? assigned.id+' · '+assigned.status+'\n'+assigned.summary : 'Verify local environmental conditions'}\n\n${tc.asset.id} · ${tc.asset.name}`));
    right.push(card('Equipment & work history', `${tc.asset.name} · ${tc.asset.id}\n${tc.asset.sensor_link || ''}\n\n${tc.related_orders.map(o => o.id+' · '+o.status+'\n'+o.summary+'\n'+(o.last_note || '')).join('\n\n')}\n\n${tc.possible_impact}`));
    right.push({...card('Troubleshooting procedure',''),procedure:{next_step:tc.next_step,procedure:tc.procedure,procedure_status:tc.procedure_status}});
    const dc = a.data_center;
    const num = (v,d=1) => typeof v === 'number' ? v.toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d}) : 'Unavailable';
    if (dc?.available) {
      const at = dc.latest.timestamp.slice(0,19).replace('T',' ') + ' UTC';
      const power = dc.latest.metrics;
      $('source').textContent = `${tc.training ? 'TRAINING CASE · ' : ''}ESIF HISTORICAL\n${at}`;
      left.push(card('ESIF · recorded power', `PUE ${num(power.pue,3)}\nIT equipment ${num(power.it_power_kw)} kW\nCooling ${num(power.cooling_kw)} kW\nHVAC ${num(power.hvac_kw)} kW\nPumps ${num(power.pump_kw)} kW\n\nRecorded ${at}`));
    } else {
      left.push(card('Data center unavailable', dc?.error || 'Real dataset unavailable.'));
      right.push(card('Source connection', 'No measurements will be invented. Restore the ESIF data file and restart the app.'));
    }
    if (ai) right.unshift(aiCard(ai));
  }
  if (attention) {
    // The procedure remains fixed on the right; a new AI answer can be read on the left.
    showPages('left',ai ? [aiCard(ai)] : left.slice(0,1),!ai);
    showProcedure(m.work.assistant.technician);
  } else {
    if (m.mode === 'personal') showSchedule(left[0]); else showPages('left',left);
    showPages('right',right);
  }
}
async function analyze() {
  if (!canAnalyze()) return;
  const session=lastSession;
  analyzePending=true; analyzeError=''; renderAssistant(state);
  try {
    const response=await fetch('/api/nemotron/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store',signal:AbortSignal.timeout(5000)});
    const data=await response.json();
    if (session !== lastSession) return;
    if (!response.ok) throw Error(typeof data.error === 'string' ? data.error : 'Analysis could not start. Try again.');
    if (data.mirror) render(data); else await refresh();
  } catch(error) {
    if (session === lastSession) analyzeError=error.name === 'TimeoutError' ? 'Analysis request timed out. Check the connection and try again.' : error.message || 'Analysis could not start. Try again.';
  } finally {
    analyzePending=false;
    if (state && state.mirror.mode !== 'welcome' && state.mirror.screen_awake) renderAssistant(state);
  }
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
document.querySelectorAll('[data-scenario]').forEach(b => b.onclick = () => {
  if (!state?.mirror.demo_controls || !state?.mirror.sensors.simulated) return;
  $('demo').close(); refresh('/api/demo/scenario',{scenario:b.dataset.scenario});
});
$('finish').onclick = () => { $('demo').close(); refresh('/api/welcome',{}); };
$('close-demo').onclick = () => $('demo').close();
$('analyze').onclick = () => { $('demo').close(); analyze(); };
addEventListener('keydown', e => {
  const key = e.key.toLowerCase();
  if (key === 'f') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); return; }
  if (key === 'd') { toggleDemo(); return; }
  if (key === 'escape') { refresh('/api/welcome',{}); return; }
  if (key === 'a') { if (!e.repeat) { e.preventDefault(); if ($('demo').open) $('demo').close(); analyze(); } return; }
  if (!state?.mirror.demo_controls) return;
  if (['h','n','o','b','i'].includes(key) && !state.mirror.sensors.simulated) return;
  if (['arrowleft','arrowright','1','2','h','n','o','b','i'].includes(key)) { e.preventDefault(); if ($('demo').open) $('demo').close(); }
  if (key === '1' || key === '2') { const p = state.mirror.profiles[Number(key)-1]; if(p) refresh('/api/demo/scan',{profile_id:p.id}); }
  if (key === 'arrowright' || key === 'arrowleft') refresh('/api/mode',{mode:key === 'arrowright' ? 'personal' : 'work'});
  const scenarios = {h:'hot',n:'normal',o:'offline',b:'near',i:'away'};
  if (scenarios[key]) refresh('/api/demo/scenario',{scenario:scenarios[key]});
});
async function poll() { await refresh(); setTimeout(poll,1000); }
poll();
