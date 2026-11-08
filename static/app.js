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
function card(title, text) { return {title, text: String(text || 'No information available.')}; }
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
        pages.push(card(c.title, text.trimEnd())); text = word;
      } else text += word;
      element.textContent = text;
      while (element.scrollHeight > element.clientHeight) {
        let low = 1, high = text.length;
        while (low < high) {
          const mid = Math.ceil((low + high) / 2);
          element.textContent = text.slice(0, mid);
          if (element.scrollHeight <= element.clientHeight) low = mid; else high = mid - 1;
        }
        pages.push(card(c.title, text.slice(0, low)));
        text = text.slice(low); element.textContent = text;
      }
    }
    if (text) pages.push(card(c.title, text.trimEnd()));
  }
  if (cache.size > 8) cache.clear();
  cache.set(key, pages); return pages;
}
function showPages(side, cards) {
  const element = $(side + '-page'), pages = pagesFor(cards, element);
  const index = Math.floor((Date.now() - sessionStart) / 14000) % pages.length;
  element.textContent = pages[index].text;
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
  $('greeting').textContent = `Hello, ${data.settings.name}`;
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
      right.push(card('Inbox · review before acting', `${item.subject}\nFrom: ${item.sender}\n\n${item.review.signals.map(x => `${x.matches?.length ? '“' + x.matches.join('”, “') + '” — ' : ''}${x.detail}`).join('\n\n')}\n\nNext step: ${item.review.next_step}\n\n${inbox.review_scope}\nRule-based review; not proof of fraud.`));
    }
    right.push(card('Your briefing', data.briefing?.error || data.briefing?.data?.summary || 'No briefing available.'));
    right.push(card('Inbox', data.inbox?.error || `${inbox?.unread ?? '—'} unread\n\n${(inbox?.messages || []).map(x => x.subject + '\n' + x.sender).join('\n\n') || 'No unread messages.'}\n\n${inbox?.review_scope || ''}`));
    if (!(inbox?.reviews || []).length && !data.inbox?.error) right.push(card('Inbox review', 'No matching warning patterns in the checked messages. This does not establish that messages are safe.'));
  } else {
    $('weather').textContent = `Room status: ${m.work.status}`;
    const a = m.work.assistant;
    left.push(card('Facility context', `${a.asset.name} · ${a.asset.id}\n\n${a.context}\n\n${a.possible_impact}`));
    left.push(card('Related work orders',a.related_work_orders.length ? a.related_work_orders.map(o => `${o.id}: ${o.summary} (${o.status})`).join('\n\n') : 'No related work orders configured.'));
    right.push(card('Operator handoff', `${m.work.handoff}\n\n${a.procedure.map((x,i) => `${i+1}. ${x}`).join('\n\n')}\n\n${a.incident ? a.incident.id + '\n' + a.incident.status : 'No new incident needed.'}\n${a.storage}`));
    if (a.ai) right.push(card(a.ai.method, a.ai.note));
    right.push(card('How this was assessed', `${a.trace.join('\n\n')}\n\n${a.method}\nThese readings do not identify a failed component.`));
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
  if (key === 'arrowright' || key === 'arrowleft') refresh('/api/mode',{mode:key === 'arrowright' ? 'work' : 'personal'});
  const scenarios = {h:'hot',n:'normal',o:'offline',b:'near',i:'away'};
  if (scenarios[key]) refresh('/api/demo/scenario',{scenario:scenarios[key]});
});
async function poll() { await refresh(); setTimeout(poll,1000); }
poll();
