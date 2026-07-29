// STM32 Live Monitor — Frontend Application v2
// Free-form watch groups, localStorage persistence, peripheral registers, enhanced chart

let state = {
  variables: [],
  peripherals: [],
  modules: [],
  watched: new Set(),
  paused: false,
  startTime: Date.now(),
  history: {},
  maxHistory: 200,
  previousValues: {},
  watchGroups: {},
  probeAttached: true,
};

const CHART_COLORS = [
  '#e94560', '#4ecca3', '#3498db', '#f39c12', '#9b59b6',
  '#1abc9c', '#e74c3c', '#2ecc71', '#e67e22', '#2980b9',
  '#8e44ad', '#16a085', '#d35400', '#27ae60', '#c0392b',
];

// ========== INIT ==========
async function init() {
  loadFromStorage();
  await loadVariables();
  await restoreWatchList();
  startSSE();
  updateStatusTime();
  setInterval(updateStatusTime, 1000);
  setInterval(checkProbeStatus, 5000);

  document.getElementById('btn-save-group').onclick = saveWatchGroup;
  document.getElementById('btn-load-group').onclick = showLoadGroupModal;
  document.getElementById('btn-pause').onclick = togglePause;
  document.getElementById('sel-interval').onchange = (e) => setInterval(e.target.value);
  document.getElementById('btn-ai').onclick = aiAnalyze;
  document.getElementById('btn-csv').onclick = downloadCSV;
  document.getElementById('btn-reconnect').onclick = reconnectProbe;
  document.getElementById('var-search').oninput = (e) => renderVariableTree(e.target.value);
  document.getElementById('periph-search').oninput = (e) => renderPeripheralTree(e.target.value);
  document.getElementById('overlay').onclick = closeModals;

  // Init chart
  window.chart = echarts.init(document.getElementById('chart-panel'));
  window.chart.setOption(getChartBaseOption());

  // Restore interval
  const savedInterval = localStorage.getItem('stm32mon_interval');
  if (savedInterval) {
    document.getElementById('sel-interval').value = savedInterval;
    setInterval(savedInterval);
  }
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem('stm32mon_state');
    if (raw) {
      const saved = JSON.parse(raw);
      if (saved.watched) state.watched = new Set(saved.watched);
      if (saved.watchGroups) state.watchGroups = saved.watchGroups;
      if (saved.paused) state.paused = saved.paused;
    }
  } catch (e) { /* ignore */ }
}

function saveToStorage() {
  try {
    localStorage.setItem('stm32mon_state', JSON.stringify({
      watched: Array.from(state.watched),
      watchGroups: state.watchGroups,
      paused: state.paused,
    }));
    localStorage.setItem('stm32mon_interval', document.getElementById('sel-interval').value);
  } catch (e) { /* ignore */ }
}

window.addEventListener('beforeunload', saveToStorage);

// ========== DATA LOADING ==========
async function loadVariables() {
  const resp = await fetch('/api/variables');
  const data = await resp.json();
  state.variables = data.variables || [];
  state.peripherals = data.peripherals || [];
  state.modules = data.modules || [];
  renderVariableTree();
  renderPeripheralTree();
}

async function restoreWatchList() {
  if (state.watched.size > 0) {
    await updateWatchList();
  }
}

async function updateWatchList() {
  const names = Array.from(state.watched);
  await fetch('/api/watch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ variables: names, peripherals: [] }),
  });
  document.getElementById('status-vars').textContent = `${names.length} vars`;
  saveToStorage();
}

// ========== VARIABLE TREE ==========
function renderVariableTree(query = '') {
  const q = query.toLowerCase();
  const filtered = q
    ? state.variables.filter(v => v.name.toLowerCase().includes(q))
    : state.variables;

  const groups = {};
  for (const v of filtered) {
    const m = v.module || 'Other';
    if (!groups[m]) groups[m] = [];
    groups[m].push(v);
  }

  const tree = document.getElementById('var-tree');
  let html = '';
  const sortedMods = Object.keys(groups).sort();

  for (const mod of sortedMods) {
    const vars = groups[mod];
    html += `<div class="module-group">`;
    html += `<div class="module-header" onclick="this.nextElementSibling.classList.toggle('collapsed')">
      <span>${mod}</span><span class="count">${vars.length}</span>
    </div>`;
    html += `<div class="module-vars">`;
    for (const v of vars) {
      const watched = state.watched.has(v.name);
      const isArray = v.size > 8 && v.type.startsWith('u8[');
      const sizeHint = v.size <= 4 ? '' : ` [${v.size}B]`;

      // Show expand button for arrays to pick individual bytes
      let expandBtn = '';
      if (isArray) {
        const expanded = state.expandedArrays && state.expandedArrays[v.name];
        expandBtn = ` <span class="expand-btn" onclick="event.stopPropagation();toggleArrayExpand('${v.name}')" title="Expand byte offsets">${expanded ? '▼' : '▶'}</span>`;
      }
      html += `<div class="var-item ${watched ? 'watched' : ''}">
        <input type="checkbox" ${watched ? 'checked' : ''} onclick="event.stopPropagation(); toggleVar('${v.name}')">
        <span onclick="toggleVar('${v.name}')">${v.name}${sizeHint}</span>${expandBtn}
        <span class="type-tag">${v.type}</span>
      </div>`;

      // Show byte-level children when expanded
      if (isArray && state.expandedArrays && state.expandedArrays[v.name]) {
        const maxShow = Math.min(v.size, 32); // show first 32 bytes max
        for (let i = 0; i < maxShow; i++) {
          const childName = `${v.name}[${i}]`;
          const childWatched = state.watched.has(childName);
          html += `<div class="var-item child-item ${childWatched ? 'watched' : ''}" onclick="toggleVar('${childName}')">
            <input type="checkbox" ${childWatched ? 'checked' : ''} onclick="event.stopPropagation(); toggleVar('${childName}')">
            <span>  [${i}]</span>
            <span class="type-tag">u8</span>
          </div>`;
        }
        if (v.size > 32) {
          html += `<div class="var-item child-item" style="color:#888;font-size:0.7em;padding-left:28px;">
            ... +${v.size - 32} more bytes (use manual offset via search or direct input)
          </div>`;
        }
      }
    }
    html += `</div></div>`;
  }

  tree.innerHTML = html || '<div class="empty-hint">No matching variables</div>';
}

function toggleArrayExpand(name) {
  if (!state.expandedArrays) state.expandedArrays = {};
  state.expandedArrays[name] = !state.expandedArrays[name];
  renderVariableTree(document.getElementById('var-search').value);
}

function toggleVar(name) {
  if (state.watched.has(name)) {
    state.watched.delete(name);
    delete state.history[name];
    delete state.previousValues[name];
  } else {
    state.watched.add(name);
    if (!state.history[name]) state.history[name] = [];
  }
  updateWatchList();
  renderVariableTree(document.getElementById('var-search').value);
}

// ========== PERIPHERAL TREE ==========
function renderPeripheralTree(query = '') {
  const q = query.toLowerCase();
  const filtered = q
    ? state.peripherals.filter(p => p.name.toLowerCase().includes(q))
    : state.peripherals;

  const tree = document.getElementById('periph-tree');
  let html = '';

  for (const p of filtered) {
    const baseHex = '0x' + p.base_address.toString(16).toUpperCase();
    html += `<div class="module-group">`;
    html += `<div class="module-header" onclick="this.nextElementSibling.classList.toggle('collapsed')">
      <span>${p.name}</span><span class="count">${baseHex}</span>
    </div>`;
    html += `<div class="module-vars">`;
    for (const reg of (p.registers || [])) {
      html += `<div class="var-item" onclick="togglePeriphReg('${p.name}','${reg.name}')">
        <span>${reg.name}</span>
        <span class="type-tag">@${reg.offset}</span>
      </div>`;
    }
    html += `</div></div>`;
  }

  tree.innerHTML = html || '<div class="empty-hint">No SVD file loaded</div>';
}

function togglePeriphReg(periphName, regName) {
  // TODO: add peripheral register watch support
  console.log('Periph reg:', periphName, regName);
}

// ========== WATCH GROUPS (free-form) ==========
async function saveWatchGroup() {
  const name = prompt('Enter watch group name:');
  if (!name) return;
  state.watchGroups[name] = Array.from(state.watched);
  saveToStorage();
  showToast(`Group "${name}" saved (${state.watched.size} variables)`);
}

function showLoadGroupModal() {
  const list = document.getElementById('group-list');
  const names = Object.keys(state.watchGroups);
  if (names.length === 0) {
    list.innerHTML = '<div class="empty-hint" style="padding:16px;text-align:center;color:#888;">No saved groups yet.<br>Check variables on the left, then click 💾 Save.</div>';
  } else {
    list.innerHTML = names.map(name => {
      const count = state.watchGroups[name].length;
      return `<div class="preset-item" style="display:flex;justify-content:space-between;align-items:center;">
        <span onclick="applyWatchGroup('${name}')" style="cursor:pointer;flex:1;">
          <strong>${name}</strong>
          <span style="color:#888;font-size:0.85em;margin-left:8px;">(${count} vars)</span>
        </span>
        <button onclick="deleteWatchGroup('${name}')" style="background:transparent;border:none;color:#e94560;cursor:pointer;font-size:1em;" title="Delete">🗑️</button>
      </div>`;
    }).join('');
  }
  openModal('group-modal');
}

async function applyWatchGroup(name) {
  const vars = state.watchGroups[name] || [];
  state.watched = new Set(vars.filter(n => state.variables.some(v => v.name === n)));
  await updateWatchList();
  renderVariableTree(document.getElementById('var-search').value);
  closeModals();
  showToast(`Loaded "${name}" (${state.watched.size} variables)`);
}

function deleteWatchGroup(name) {
  if (confirm(`Delete group "${name}"?`)) {
    delete state.watchGroups[name];
    saveToStorage();
    showLoadGroupModal(); // refresh
  }
}

// ========== SSE ==========
let es = null;
function startSSE() {
  if (es) { es.close(); es = null; }
  es = new EventSource('/api/stream');
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleSnapshot(data);
    } catch (err) { /* skip malformed */ }
  };
  es.onerror = () => {
    document.getElementById('status-dot').className = 'dot offline';
    document.getElementById('status-text').textContent = 'Disconnected';
  };
  es.onopen = () => {
    document.getElementById('status-dot').className = 'dot online';
    document.getElementById('status-text').textContent = 'Online';
  };
}

function handleSnapshot(snapshot) {
  if (state.paused) return;

  const ts = snapshot.timestamp * 1000;
  const vars = snapshot.variables || {};
  const rows = [];
  const chartSeriesMap = {};

  for (const [name, value] of Object.entries(vars)) {
    const varDef = state.variables.find(v => v.name === name) || {};
    const type = varDef.type || 'u32';
    const size = varDef.size || 4;

    let displayValue, hex;
    if (typeof value === 'string') {
      // Hex dump for arrays (size > 8)
      displayValue = value;
      hex = value;
    } else if (typeof value === 'number') {
      displayValue = value;
      hex = '0x' + (value >>> 0).toString(16).toUpperCase().padStart(8, '0');
    } else {
      displayValue = String(value);
      hex = String(value);
    }

    let trend = '';
    if (typeof value === 'number' && state.previousValues[name] !== undefined) {
      trend = value > state.previousValues[name] ? '▲' : value < state.previousValues[name] ? '▼' : '';
    }
    state.previousValues[name] = value;

    if (!state.history[name]) state.history[name] = [];
    if (typeof value === 'number') {
      state.history[name].push({ ts, value });
      if (state.history[name].length > state.maxHistory) {
        state.history[name] = state.history[name].slice(-state.maxHistory);
      }
    }

    rows.push({ name, type, value: displayValue, hex, trend });

    if (typeof value === 'number') {
      chartSeriesMap[name] = state.history[name].map(h => [h.ts, h.value]);
    }
  }

  renderWatchTable(rows);
  renderChart(chartSeriesMap);
}

function renderWatchTable(rows) {
  const tbody = document.getElementById('watch-tbody');
  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-hint">Check variables on the left to start monitoring</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td title="${r.name}">${r.name}</td>
      <td><span class="type-tag">${r.type}</span></td>
      <td class="val-cell">${r.value}</td>
      <td class="hex-cell">${r.hex}</td>
      <td class="${r.trend === '▲' ? 'trend-up' : r.trend === '▼' ? 'trend-down' : ''}">${r.trend}</td>
      <td><span style="cursor:pointer;color:#888;" onclick="removeVar('${r.name}')" title="Remove">✕</span></td>
    </tr>
  `).join('');
}

function removeVar(name) {
  state.watched.delete(name);
  delete state.history[name];
  delete state.previousValues[name];
  updateWatchList();
  renderVariableTree(document.getElementById('var-search').value);
}

// ========== CHART ==========
function getChartBaseOption() {
  return {
    title: { text: 'Trend', left: 12, top: 8, textStyle: { color: '#a0a0c0', fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { right: 12, top: 6, textStyle: { color: '#a0a0c0', fontSize: 11 } },
    grid: { top: 40, right: 20, bottom: 40, left: 60 },
    xAxis: { type: 'time', axisLabel: { color: '#888', fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: '#888', fontSize: 10, formatter: autoFormat }, splitLine: { lineStyle: { color: '#1a2a40' } } },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }, { type: 'slider', start: 0, end: 100, height: 20, bottom: 4, borderColor: '#333', backgroundColor: '#1a1a2e', fillerColor: 'rgba(233,69,96,0.2)' }],
    series: [],
    backgroundColor: '#16213e',
  };
}

function autoFormat(val) {
  if (Math.abs(val) >= 1e6) return (val / 1e6).toFixed(1) + 'M';
  if (Math.abs(val) >= 1e3) return (val / 1e3).toFixed(1) + 'K';
  return val.toString();
}

function renderChart(chartSeriesMap) {
  const series = [];
  let i = 0;
  for (const [name, data] of Object.entries(chartSeriesMap)) {
    if (!data || data.length === 0) continue;
    series.push({
      name,
      type: 'line',
      showSymbol: false,
      data,
      lineStyle: { width: 1.5, color: CHART_COLORS[i % CHART_COLORS.length] },
      itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
      smooth: true,
    });
    i++;
  }

  window.chart.setOption({
    series,
    legend: { data: Object.keys(chartSeriesMap) },
  }, true);
}

// ========== ACTIONS ==========
function togglePause() {
  state.paused = !state.paused;
  const btn = document.getElementById('btn-pause');
  btn.textContent = state.paused ? '▶️ Resume' : '⏯️ Pause';
  btn.classList.toggle('active', state.paused);
  document.getElementById('status-paused').textContent = state.paused ? ' [PAUSED]' : '';
  fetch('/api/pause', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused: state.paused }),
  });
  saveToStorage();
}

function setInterval(ms) {
  document.getElementById('status-rate').textContent = `${(1000/ms).toFixed(1)} Hz`;
  fetch('/api/poll-rate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_ms: parseInt(ms) }),
  });
  localStorage.setItem('stm32mon_interval', String(ms));
}

async function aiAnalyze() {
  const resp = await fetch('/api/detach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  const data = await resp.json();
  if (data.ok) {
    state.probeAttached = false;
    document.getElementById('btn-reconnect').style.display = 'inline-block';
    document.getElementById('btn-ai').style.display = 'none';
    updateProbeUI(false);
    showToast(`✅ Snapshot exported to ${data.exported}\nProbe released. Use /read-var now.`);
  }
}

async function reconnectProbe() {
  const resp = await fetch('/api/attach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  const data = await resp.json();
  if (data.ok) {
    state.probeAttached = true;
    document.getElementById('btn-reconnect').style.display = 'none';
    document.getElementById('btn-ai').style.display = 'inline-block';
    updateProbeUI(true);
    startSSE();
    showToast('Probe reconnected. Monitoring resumed.');
  } else {
    showToast('Failed to reconnect: ' + (data.error || 'unknown'));
  }
}

async function checkProbeStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    if (data.probe_attached !== state.probeAttached) {
      state.probeAttached = data.probe_attached;
      updateProbeUI(state.probeAttached);
      if (!state.probeAttached) {
        document.getElementById('btn-reconnect').style.display = 'inline-block';
        document.getElementById('btn-ai').style.display = 'none';
      }
    }
  } catch (e) { /* server may be down */ }
}

function updateProbeUI(attached) {
  document.getElementById('status-dot').className = attached ? 'dot online' : 'dot offline';
  document.getElementById('status-text').textContent = attached ? 'Online' : 'Probe released';
}

function downloadCSV() {
  // Export history data with timestamps
  const timeIndex = {};
  for (const [name, hist] of Object.entries(state.history)) {
    for (const point of hist) {
      if (!timeIndex[point.ts]) timeIndex[point.ts] = {};
      timeIndex[point.ts][name] = point.value;
    }
  }

  const timestamps = Object.keys(timeIndex).sort();
  const allNames = Array.from(new Set(
    Object.values(timeIndex).flatMap(row => Object.keys(row))
  )).sort();

  const header = ['timestamp', ...allNames];
  const rows = [header.join(',')];

  for (const ts of timestamps) {
    const date = new Date(parseInt(ts));
    const timeStr = date.toLocaleTimeString() + '.' + String(date.getMilliseconds()).padStart(3, '0');
    const vals = [timeStr];
    for (const name of allNames) {
      vals.push(timeIndex[ts][name] !== undefined ? String(timeIndex[ts][name]) : '');
    }
    rows.push(vals.join(','));
  }

  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `stm32-monitor-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast(`CSV exported: ${rows.length - 1} time points × ${allNames.length} variables`);
}

// ========== MODALS ==========
function openModal(id) {
  document.getElementById(id).classList.add('show');
  document.getElementById('overlay').classList.add('show');
}

function closeModals() {
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('show'));
  document.getElementById('overlay').classList.remove('show');
}

// ========== TOAST ==========
function showToast(msg) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.style.cssText = 'position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:#0f3460;color:#e0e0e0;padding:10px 24px;border-radius:8px;z-index:100;font-size:0.85em;white-space:pre-line;text-align:center;border:1px solid #1a508b;';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => { toast.style.opacity = '0'; }, 3000);
}

// ========== STATUS ==========
function updateStatusTime() {
  const elapsed = Math.floor((Date.now() - state.startTime) / 1000);
  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;
  document.getElementById('status-time').textContent = `${m}:${String(s).padStart(2, '0')}`;
}

window.addEventListener('resize', () => window.chart?.resize());
init();
