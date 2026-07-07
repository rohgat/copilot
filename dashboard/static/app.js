// ── State ──────────────────────────────────────────────────────────────────
let ws = null;
let activeMeetingId = null;
let selectedCalendarEvent = null;
let transcriptLines = 0;
let triggerCount = 0;

// ── WebSocket ──────────────────────────────────────────────────────────────
function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'transcript') onTranscript(msg);
    if (msg.type === 'trigger') onTrigger(msg);
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
}

function onTranscript(msg) {
  const feed = document.getElementById('transcript-feed');
  const empty = document.getElementById('transcript-empty');
  if (empty) empty.remove();

  const ts = new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const line = document.createElement('div');
  line.className = 't-line';
  line.innerHTML = `
    <span class="t-speaker">${esc(msg.speaker)}</span>
    <span class="t-text">${esc(msg.text)}</span>
    <span class="t-ts">${ts}</span>
  `;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;
  transcriptLines++;
}

function onTrigger(msg) {
  triggerCount++;
  document.getElementById('trigger-count').textContent = `(${triggerCount})`;

  const feed = document.getElementById('notif-feed');
  const ts = new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const conf = (msg.confidence * 100).toFixed(0) + '%';

  const contextHtml = msg.context && msg.context.length
    ? `<div class="nc-context"><strong style="font-size:10px;font-family:var(--mono);color:var(--teal);text-transform:uppercase;letter-spacing:.06em">Context</strong><br>${msg.context.map(c => `• ${esc(c.slice(0, 150))}`).join('<br>')}</div>`
    : '';

  const suggHtml = msg.suggestion
    ? `<div class="nc-suggestion">${esc(msg.suggestion)}</div>`
    : '';

  const card = document.createElement('div');
  card.className = 'notif-card';
  card.innerHTML = `
    <div class="nc-header">
      <span class="nc-speaker">${esc(msg.speaker)}</span>
      <span class="nc-conf">${ts} · ${conf}</span>
    </div>
    <div class="nc-question">"${esc(msg.question)}"</div>
    ${contextHtml}
    ${suggHtml}
    <div class="nc-actions">
      <button class="nc-btn star" onclick="starTrigger(this, '${esc(msg.question)}')">⭐ Important</button>
      <button class="nc-btn flag" onclick="flagTrigger(this, '${esc(msg.question)}', true)">✕ Not relevant</button>
    </div>
  `;
  feed.insertBefore(card, feed.firstChild);

  // Also switch to live tab if not already there
  switchTab('live');
}

// ── Meeting control ────────────────────────────────────────────────────────
async function startMeeting(calEvent) {
  const event = calEvent || selectedCalendarEvent;
  let title = 'Untitled Meeting';
  let attendees = [];
  let calId = null;
  let platform = 'gmeet';

  if (event) {
    title = event.title;
    attendees = event.attendees || [];
    calId = event.id;
    platform = event.platform || 'gmeet';
  } else {
    const input = prompt('Meeting title?');
    if (!input) return;
    title = input;
  }

  try {
    const resp = await api('POST', '/api/meetings/start', {
      title, platform, attendees, calendar_event_id: calId, joined_late: false
    });
    activeMeetingId = resp.meeting_id;
    document.getElementById('meeting-title-live').textContent = title;
    updateStartStopButtons(true);
    triggerCount = 0;
    document.getElementById('trigger-count').textContent = '';
    toast('Listening started');
    switchTab('live');
    refreshCalendar();
  } catch (e) {
    toast('Failed to start: ' + e.message, true);
  }
}

async function stopMeeting() {
  if (!confirm('Stop meeting and generate summary?')) return;
  try {
    const resp = await api('POST', '/api/meetings/stop');
    activeMeetingId = null;
    updateStartStopButtons(false);
    if (resp.summary) {
      toast('Summary sent to WhatsApp + Notion');
      loadHistory();
    }
  } catch (e) {
    toast('Error: ' + e.message, true);
  }
}

async function requestCatchup() {
  try {
    const resp = await api('POST', '/api/meetings/catchup');
    toast('Catch-up sent to WhatsApp');
    // Show in notif feed
    const feed = document.getElementById('notif-feed');
    const card = document.createElement('div');
    card.className = 'notif-card';
    card.style.borderLeftColor = 'var(--blue)';
    card.innerHTML = `
      <div class="nc-header"><span class="nc-speaker" style="color:var(--blue)">Catch-up Summary</span></div>
      <div class="nc-question" style="white-space:pre-wrap">${esc(resp.catchup)}</div>
    `;
    feed.insertBefore(card, feed.firstChild);
  } catch (e) {
    toast('Error: ' + e.message, true);
  }
}

function updateStartStopButtons(active) {
  document.getElementById('btn-start').style.display = active ? 'none' : '';
  document.getElementById('btn-stop').style.display = active ? '' : 'none';
  document.getElementById('btn-catchup').style.display = active ? '' : 'none';
}

// ── Calendar ───────────────────────────────────────────────────────────────
async function refreshCalendar() {
  const list = document.getElementById('meetings-list');
  try {
    const events = await api('GET', '/api/meetings/today');
    if (!events.length) {
      list.innerHTML = '<div class="no-meetings">No meetings today</div>';
      return;
    }
    list.innerHTML = events.map(e => {
      const start = new Date(e.start);
      const end = new Date(e.end);
      const timeStr = start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' – ' +
                      end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const isActive = activeMeetingId && e.id === selectedCalendarEvent?.id;
      return `
        <div class="meeting-card ${isActive ? 'active' : ''}" onclick="selectEvent(${JSON.stringify(e).replace(/"/g, '&quot;')})">
          <div class="mc-time">${timeStr}</div>
          <div class="mc-title">${esc(e.title)}</div>
          <div class="mc-meta">${e.attendees.slice(0, 3).join(', ')}</div>
          <div class="mc-actions">
            <button class="mc-btn" onclick="event.stopPropagation();joinMeeting(${JSON.stringify(e).replace(/"/g, '&quot;')})">
              Start Copilot
            </button>
            ${e.meet_link ? `<a class="mc-btn" href="${esc(e.meet_link)}" target="_blank" onclick="event.stopPropagation()">Open Meet</a>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="no-meetings">Calendar unavailable</div>';
  }
}

function selectEvent(event) {
  selectedCalendarEvent = event;
}

function joinMeeting(event) {
  selectedCalendarEvent = event;
  startMeeting(event);
}

// ── History ────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = document.getElementById('history-list');
  try {
    const meetings = await api('GET', '/api/meetings/history');
    if (!meetings.length) {
      list.innerHTML = '<div style="color:var(--t3);font-size:12px">No meetings recorded yet</div>';
      return;
    }
    list.innerHTML = meetings.map(m => {
      const date = m.start ? new Date(m.start) : null;
      const dateStr = date ? date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) : '';
      const timeStr = date ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
      return `
        <div class="hist-card">
          <div class="hc-header">
            <span class="hc-date">${dateStr} ${timeStr}</span>
            <span class="hc-title">${esc(m.title)}</span>
          </div>
          <div class="hc-meta">${m.attendees.slice(0,5).join(', ')} · ${m.transcript_lines} lines</div>
          <div class="hc-actions">
            <span style="font-size:11px;color:var(--t3)">ID: ${m.id}</span>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div style="color:var(--t3);font-size:12px">Could not load history</div>';
  }
}

// ── File upload ────────────────────────────────────────────────────────────
function handleFileDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag-over');
  uploadFiles(e.dataTransfer.files);
}

async function uploadFiles(files) {
  if (!files || !files.length) return;
  const meetingId = activeMeetingId || selectedCalendarEvent?.id || null;
  const fileList = document.getElementById('file-list');

  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    if (meetingId) fd.append('meeting_id', meetingId);

    try {
      const resp = await fetch('/api/files/upload', { method: 'POST', body: fd });
      const data = await resp.json();
      const item = document.createElement('div');
      item.className = 'file-item';
      item.textContent = file.name;
      fileList.appendChild(item);
      toast(`Indexed: ${file.name}`);
    } catch (e) {
      toast(`Upload failed: ${file.name}`, true);
    }
  }
}

// ── Feedback ───────────────────────────────────────────────────────────────
async function starTrigger(btn, text) {
  btn.disabled = true;
  btn.textContent = '⭐ Starred';
  await api('POST', '/feedback/star', { bullets: [text], weight: 1.0 });
}

async function flagTrigger(btn, text, isFalsePositive) {
  btn.disabled = true;
  btn.textContent = '✓ Flagged';
  await api('POST', '/feedback/flag', { text, false_positive: isFalsePositive });
}

// ── UI helpers ─────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', t.textContent.toLowerCase() === name);
  });
  document.querySelectorAll('.panel').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${name}`);
  });
  if (name === 'history') loadHistory();
}

function toast(msg, error = false) {
  const el = document.createElement('div');
  el.className = 'toast';
  if (error) el.style.borderColor = 'var(--rose)';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

// ── Status polling ─────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await api('GET', '/api/meetings/status');
    const dot = document.getElementById('status-dot');
    const txt = document.getElementById('status-text');
    dot.className = 'status-dot ' + s.status;
    txt.textContent = s.status.charAt(0).toUpperCase() + s.status.slice(1);
    if (s.active && !activeMeetingId) {
      activeMeetingId = s.meeting_id;
      updateStartStopButtons(true);
    }
  } catch (_) {}

  try {
    const wa = await api('GET', '/api/whatsapp/status');
    const badge = document.getElementById('wa-badge');
    badge.textContent = 'WhatsApp ' + (wa.status === 'connected' ? '●' : '○');
    badge.className = 'wa-badge' + (wa.status === 'connected' ? '' : ' offline');
  } catch (_) {}
}

// ── Init ───────────────────────────────────────────────────────────────────
connectWS();
refreshCalendar();
setInterval(pollStatus, 5000);
setInterval(refreshCalendar, 60000);
pollStatus();
