"""Admin dashboard — self-contained HTML served by FastAPI."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Astra Admin Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }

  .header { background: #1a1a2e; color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 20px; font-weight: 600; }
  .header .subtitle { color: #8888aa; font-size: 13px; }

  .auth-bar { background: #fff; border-bottom: 1px solid #e0e0e0; padding: 12px 24px; display: flex; align-items: center; gap: 12px; }
  .auth-bar input { flex: 1; max-width: 400px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; font-family: monospace; }
  .auth-bar button { padding: 8px 20px; background: #4a90d9; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
  .auth-bar button:hover { background: #3a7bc8; }
  .auth-bar .status { font-size: 12px; color: #888; }
  .auth-bar .status.ok { color: #28a745; }
  .auth-bar .status.err { color: #dc3545; }

  .container { max-width: 1200px; margin: 0 auto; padding: 20px 24px; }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .stat-card .label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .stat-card .value.green { color: #28a745; }
  .stat-card .value.blue { color: #4a90d9; }
  .stat-card .value.orange { color: #fd7e14; }
  .stat-card .value.red { color: #dc3545; }

  .panel { background: white; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 24px; }
  .panel-header { padding: 16px 20px; border-bottom: 1px solid #eee; display: flex; align-items: center; justify-content: space-between; }
  .panel-header h2 { font-size: 16px; font-weight: 600; }
  .panel-body { padding: 16px 20px; }

  .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .toolbar select, .toolbar input { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
  .toolbar input { width: 180px; }

  .btn { padding: 6px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
  .btn-primary { background: #4a90d9; color: white; }
  .btn-primary:hover { background: #3a7bc8; }
  .btn-success { background: #28a745; color: white; }
  .btn-success:hover { background: #218838; }
  .btn-danger { background: #dc3545; color: white; }
  .btn-danger:hover { background: #c82333; }
  .btn-warning { background: #fd7e14; color: white; }
  .btn-warning:hover { background: #e8590c; }
  .btn-sm { padding: 3px 10px; font-size: 12px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 10px 12px; background: #f8f9fa; border-bottom: 2px solid #dee2e6; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #666; }
  td { padding: 10px 12px; border-bottom: 1px solid #eee; vertical-align: middle; }
  tr:hover { background: #f8f9ff; }

  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
  .badge-active { background: #d4edda; color: #155724; }
  .badge-unused { background: #e2e3e5; color: #383d41; }
  .badge-revoked { background: #f8d7da; color: #721c24; }

  .key-text { font-family: monospace; font-size: 12px; color: #555; }
  .key-full { display: none; }
  .key-cell { cursor: pointer; }
  .key-cell:hover .key-short { text-decoration: underline; }

  .actions { display: flex; gap: 4px; }

  .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 100; align-items: center; justify-content: center; }
  .modal-overlay.show { display: flex; }
  .modal { background: white; border-radius: 12px; padding: 24px; width: 420px; max-width: 90vw; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
  .modal h3 { margin-bottom: 16px; }
  .modal label { display: block; font-size: 13px; color: #555; margin-bottom: 4px; margin-top: 12px; }
  .modal input, .modal select { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
  .modal .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }

  .toast { position: fixed; bottom: 24px; right: 24px; padding: 12px 20px; border-radius: 8px; color: white; font-size: 13px; z-index: 200; opacity: 0; transition: opacity 0.3s; }
  .toast.show { opacity: 1; }
  .toast-success { background: #28a745; }
  .toast-error { background: #dc3545; }

  .empty { text-align: center; padding: 40px; color: #888; }
  .loading { text-align: center; padding: 40px; color: #888; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Astra Admin Dashboard</h1>
    <div class="subtitle">License & Usage Management</div>
  </div>
</div>

<div class="auth-bar">
  <input type="password" id="adminSecret" placeholder="Enter admin secret..." />
  <button onclick="authenticate()">Connect</button>
  <span id="authStatus" class="status"></span>
</div>

<div class="container" id="mainContent" style="display:none;">
  <!-- Stats -->
  <div class="stats-grid" id="statsGrid">
    <div class="stat-card"><div class="label">Total Keys</div><div class="value" id="statTotal">-</div></div>
    <div class="stat-card"><div class="label">Active</div><div class="value green" id="statActive">-</div></div>
    <div class="stat-card"><div class="label">Unused</div><div class="value blue" id="statUnused">-</div></div>
    <div class="stat-card"><div class="label">Revoked</div><div class="value red" id="statRevoked">-</div></div>
    <div class="stat-card"><div class="label">Total Requests</div><div class="value" id="statRequests">-</div></div>
    <div class="stat-card"><div class="label">Prompt Tokens</div><div class="value orange" id="statPrompt">-</div></div>
    <div class="stat-card"><div class="label">Completion Tokens</div><div class="value orange" id="statCompletion">-</div></div>
  </div>

  <!-- Keys Panel -->
  <div class="panel">
    <div class="panel-header">
      <h2>License Keys</h2>
      <div class="toolbar">
        <select id="filterStatus" onchange="loadKeys()">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="unused">Unused</option>
          <option value="revoked">Revoked</option>
        </select>
        <input type="text" id="filterEmail" placeholder="Search by email..." oninput="debounceLoadKeys()" />
        <button class="btn btn-success" onclick="showGenerateModal()">+ Generate Keys</button>
      </div>
    </div>
    <div class="panel-body">
      <div id="keysTable"><div class="loading">Connect with admin secret to view keys...</div></div>
    </div>
  </div>
</div>

<!-- Generate Modal -->
<div class="modal-overlay" id="generateModal">
  <div class="modal">
    <h3>Generate License Keys</h3>
    <label>Number of keys</label>
    <input type="number" id="genCount" value="1" min="1" max="100" />
    <label>Tier</label>
    <select id="genTier">
      <option value="standard">Standard</option>
      <option value="premium">Premium</option>
    </select>
    <label>Email (optional)</label>
    <input type="email" id="genEmail" placeholder="customer@example.com" />
    <div class="modal-actions">
      <button class="btn" onclick="closeModal('generateModal')">Cancel</button>
      <button class="btn btn-success" onclick="generateKeys()">Generate</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
const API_BASE = window.location.origin + '/v1/admin';
let adminSecret = '';
let debounceTimer = null;

function getHeaders() {
  return { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret };
}

async function authenticate() {
  adminSecret = document.getElementById('adminSecret').value;
  const statusEl = document.getElementById('authStatus');
  if (!adminSecret) { statusEl.textContent = 'Enter a secret'; statusEl.className = 'status err'; return; }

  try {
    const resp = await fetch(API_BASE + '/summary', { headers: getHeaders() });
    if (resp.ok) {
      statusEl.textContent = 'Connected';
      statusEl.className = 'status ok';
      document.getElementById('mainContent').style.display = 'block';
      loadSummary();
      loadKeys();
    } else {
      statusEl.textContent = resp.status === 401 ? 'Invalid secret' : 'Error ' + resp.status;
      statusEl.className = 'status err';
    }
  } catch(e) {
    statusEl.textContent = 'Connection failed';
    statusEl.className = 'status err';
  }
}

// Allow Enter key in secret input
document.getElementById('adminSecret').addEventListener('keydown', e => { if (e.key === 'Enter') authenticate(); });

async function loadSummary() {
  try {
    const resp = await fetch(API_BASE + '/summary', { headers: getHeaders() });
    const data = await resp.json();
    document.getElementById('statTotal').textContent = data.total_keys;
    document.getElementById('statActive').textContent = data.active_keys;
    document.getElementById('statUnused').textContent = data.unused_keys;
    document.getElementById('statRevoked').textContent = data.revoked_keys;
    document.getElementById('statRequests').textContent = data.total_requests.toLocaleString();
    document.getElementById('statPrompt').textContent = data.total_prompt_tokens.toLocaleString();
    document.getElementById('statCompletion').textContent = data.total_completion_tokens.toLocaleString();
  } catch(e) { console.error('Failed to load summary', e); }
}

function debounceLoadKeys() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(loadKeys, 300);
}

async function loadKeys() {
  const status = document.getElementById('filterStatus').value;
  const email = document.getElementById('filterEmail').value;
  let url = API_BASE + '/keys?';
  if (status) url += 'status=' + status + '&';
  if (email) url += 'email=' + encodeURIComponent(email) + '&';

  try {
    const resp = await fetch(url, { headers: getHeaders() });
    const keys = await resp.json();
    renderKeysTable(keys);
  } catch(e) {
    document.getElementById('keysTable').innerHTML = '<div class="empty">Failed to load keys</div>';
  }
}

function renderKeysTable(keys) {
  if (keys.length === 0) {
    document.getElementById('keysTable').innerHTML = '<div class="empty">No keys found</div>';
    return;
  }

  let html = '<table><thead><tr>';
  html += '<th>Key</th><th>Status</th><th>Tier</th><th>Email</th><th>Hardware</th>';
  html += '<th>Activated</th><th>Last Active</th><th>Requests</th><th>Tokens</th><th>Actions</th>';
  html += '</tr></thead><tbody>';

  for (const k of keys) {
    const shortKey = k.key.substring(0, 8) + '...';
    const badge = k.status === 'active' ? 'badge-active' : k.status === 'unused' ? 'badge-unused' : 'badge-revoked';
    const hw = k.hardware_id ? k.hardware_id.substring(0, 10) + '...' : '-';
    const activated = k.activated_at ? new Date(k.activated_at).toLocaleDateString() : '-';
    const lastActive = k.last_request_at ? timeAgo(k.last_request_at) : '-';
    const tokens = (k.total_prompt_tokens + k.total_completion_tokens).toLocaleString();

    html += '<tr>';
    html += '<td class="key-cell" onclick="copyKey(&quot;'+k.key+'&quot;)"><span class="key-text key-short">' + shortKey + '</span></td>';
    html += '<td><span class="badge ' + badge + '">' + k.status + '</span></td>';
    html += '<td>' + k.tier + '</td>';
    html += '<td>' + (k.email || '-') + '</td>';
    html += '<td class="key-text">' + hw + '</td>';
    html += '<td>' + activated + '</td>';
    html += '<td>' + lastActive + '</td>';
    html += '<td>' + k.total_requests + '</td>';
    html += '<td>' + tokens + '</td>';
    html += '<td class="actions">';
    if (k.status === 'active') {
      html += '<button class="btn btn-warning btn-sm" onclick="resetKey('+k.id+')">Reset</button>';
      html += '<button class="btn btn-danger btn-sm" onclick="revokeKey('+k.id+')">Revoke</button>';
    } else if (k.status === 'unused') {
      html += '<button class="btn btn-danger btn-sm" onclick="revokeKey('+k.id+')">Revoke</button>';
    } else {
      html += '<button class="btn btn-primary btn-sm" onclick="resetKey('+k.id+')">Restore</button>';
    }
    html += '</td></tr>';
  }

  html += '</tbody></table>';
  document.getElementById('keysTable').innerHTML = html;
}

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  const days = Math.floor(hrs / 24);
  return days + 'd ago';
}

async function copyKey(key) {
  try {
    await navigator.clipboard.writeText(key);
    showToast('Key copied to clipboard', 'success');
  } catch(e) {
    showToast('Copy failed', 'error');
  }
}

function showGenerateModal() {
  document.getElementById('generateModal').classList.add('show');
  document.getElementById('genCount').focus();
}

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
}

async function generateKeys() {
  const count = parseInt(document.getElementById('genCount').value) || 1;
  const tier = document.getElementById('genTier').value;
  const email = document.getElementById('genEmail').value || null;

  try {
    const resp = await fetch(API_BASE + '/keys/bulk', {
      method: 'POST', headers: getHeaders(),
      body: JSON.stringify({ count, tier, email }),
    });
    if (resp.ok) {
      const data = await resp.json();
      showToast(data.count + ' key(s) generated', 'success');
      closeModal('generateModal');
      loadSummary();
      loadKeys();

      // Copy keys to clipboard if just 1
      if (data.keys.length === 1) {
        navigator.clipboard.writeText(data.keys[0].license_key).catch(() => {});
      }
    } else {
      const err = await resp.json();
      showToast('Error: ' + (err.detail || 'Generation failed'), 'error');
    }
  } catch(e) {
    showToast('Connection error', 'error');
  }
}

async function revokeKey(id) {
  if (!confirm('Revoke this key? The user will lose access immediately.')) return;
  try {
    const resp = await fetch(API_BASE + '/keys/' + id, { method: 'DELETE', headers: getHeaders() });
    if (resp.ok) {
      showToast('Key revoked', 'success');
      loadSummary();
      loadKeys();
    } else {
      showToast('Revoke failed', 'error');
    }
  } catch(e) { showToast('Connection error', 'error'); }
}

async function resetKey(id) {
  if (!confirm('Reset this key to unused? It will be unbound from its current machine.')) return;
  try {
    const resp = await fetch(API_BASE + '/keys/' + id + '/reset', { method: 'POST', headers: getHeaders() });
    if (resp.ok) {
      showToast('Key reset to unused', 'success');
      loadSummary();
      loadKeys();
    } else {
      showToast('Reset failed', 'error');
    }
  } catch(e) { showToast('Connection error', 'error'); }
}

function showToast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast toast-' + type + ' show';
  setTimeout(() => el.classList.remove('show'), 3000);
}

// Close modals on overlay click
document.querySelectorAll('.modal-overlay').forEach(el => {
  el.addEventListener('click', e => { if (e.target === el) el.classList.remove('show'); });
});
</script>
</body>
</html>"""


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    """Serve the admin dashboard HTML page."""
    return DASHBOARD_HTML
