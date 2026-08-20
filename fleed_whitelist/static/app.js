/**
 * FleedGuard Enterprise Client Dashboard Engine
 * Advanced Whitelist Management, Anti-Dump DRM, Real-Time Telemetry & QoL Automation
 */

const API_BASE = "";

// State
let currentUser = null;
let currentScripts = [];
let currentLicenses = [];
let currentLogs = [];
let currentBypasses = [];
let selectedScriptId = null;
let selectedLicenseIds = new Set();
let liveLogInterval = null;
let isAutoRefreshOn = true;
let modalSelectedScript = null;

// Toast Notification Utility
function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  let icon = '<i class="fa-solid fa-circle-check" style="color:var(--success-color);"></i>';
  if (type === 'error') icon = '<i class="fa-solid fa-triangle-exclamation" style="color:var(--danger-color);"></i>';
  if (type === 'info') icon = '<i class="fa-solid fa-circle-info" style="color:var(--info-color);"></i>';
  toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Copy to Clipboard Utility
function copyText(text, label = "Copied to clipboard!") {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast(label, "success");
  }).catch(() => {
    showToast("Failed to copy", "error");
  });
}

// API Fetch Helper
async function apiCall(endpoint, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("fleed_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (body) options.body = JSON.stringify(body);

  try {
    const res = await fetch(endpoint, options);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || data.message || "Request failed");
    }
    return data;
  } catch (err) {
    showToast(err.message, "error");
    throw err;
  }
}

// ----------------- Auth & Profile -----------------
async function checkAuth() {
  try {
    const user = await apiCall("/api/auth/me");
    currentUser = user;
    if (window.location.pathname === "/" || window.location.pathname === "/index.html") {
      window.location.href = "/dashboard";
    }
    return user;
  } catch (e) {
    currentUser = null;
    if (window.location.pathname.startsWith("/dashboard")) {
      window.location.href = "/";
    }
    return null;
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById("loginUsername").value;
  const password = document.getElementById("loginPassword").value;
  const two_factor_code = document.getElementById("login2FACode")?.value || null;

  try {
    const data = await apiCall("/api/auth/login", "POST", { username, password, two_factor_code });
    if (data.requires_2fa) {
      document.getElementById("login2FAGroup").style.display = "block";
      showToast("Please enter your 6-digit 2FA code or backup code", "info");
      return;
    }
    if (data.token) {
      localStorage.setItem("fleed_token", data.token);
      showToast("Login successful!", "success");
      setTimeout(() => window.location.href = "/dashboard", 500);
    }
  } catch (err) {}
}

async function handleRegister(e) {
  e.preventDefault();
  const username = document.getElementById("regUsername").value;
  const email = document.getElementById("regEmail").value;
  const password = document.getElementById("regPassword").value;

  try {
    const data = await apiCall("/api/auth/register", "POST", { username, email, password });
    if (data.token) {
      localStorage.setItem("fleed_token", data.token);
      showToast("Account created successfully!", "success");
      setTimeout(() => window.location.href = "/dashboard", 500);
    }
  } catch (err) {}
}

async function handleLogout() {
  try {
    await apiCall("/api/auth/logout", "POST");
  } catch (e) {}
  localStorage.removeItem("fleed_token");
  window.location.href = "/";
}

// ----------------- 2FA Setup Flow -----------------
async function open2FAModal() {
  try {
    const data = await apiCall("/api/auth/2fa/setup", "POST");
    document.getElementById("qrImage").src = data.qr_code;
    document.getElementById("secretKeyText").innerText = data.secret;
    
    const codesGrid = document.getElementById("backupCodesGrid");
    codesGrid.innerHTML = data.backup_codes.map(c => `<div class="backup-code-item">${c}</div>`).join("");

    document.getElementById("modal2FA").classList.add("active");
  } catch (err) {}
}

async function confirmEnable2FA() {
  const code = document.getElementById("verify2FACode").value;
  if (!code || code.length < 6) {
    return showToast("Enter a valid 6-digit code", "error");
  }

  try {
    await apiCall("/api/auth/2fa/verify", "POST", { code });
    showToast("2FA successfully enabled!", "success");
    closeModal("modal2FA");
    loadProfileStats();
  } catch (err) {}
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

// ----------------- Dashboard Navigation -----------------
function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-view").forEach(view => view.style.display = "none");

  const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
  const activeView = document.getElementById(`view-${tabName}`);
  if (activeBtn) activeBtn.classList.add("active");
  if (activeView) activeView.style.display = "block";

  if (tabName === "overview") loadOverviewStats();
  if (tabName === "scripts") loadScripts();
  if (tabName === "licenses") loadLicensesView();
  if (tabName === "logs") loadLiveLogs();
  if (tabName === "bypasses") loadBypassLogs();
  if (tabName === "settings") loadProfileStats();
}

// ----------------- Overview & Stats -----------------
async function loadOverviewStats() {
  try {
    const stats = await apiCall("/api/stats");
    document.getElementById("statScripts").innerText = stats.total_scripts;
    document.getElementById("statActiveLicenses").innerText = stats.active_licenses;
    document.getElementById("statExecutions").innerText = stats.total_executions;
    document.getElementById("statBlockedAttacks").innerText = stats.blocked_attacks;
  } catch (e) {}
}

async function loadProfileStats() {
  if (!currentUser) return;
  const uEl = document.getElementById("profileUsername");
  if (uEl) uEl.innerText = currentUser.username || "Developer";

  const initEl = document.getElementById("userInitial");
  if (initEl && currentUser.username) {
    initEl.innerText = currentUser.username.charAt(0).toUpperCase();
  }

  const eEl = document.getElementById("profileEmail");
  if (eEl) eEl.innerText = currentUser.email || "—";

  const kEl = document.getElementById("profileApiKey");
  if (kEl) kEl.value = currentUser.api_key || "";
  
  const statusBadge = document.getElementById("2FAStatusBadge");
  if (statusBadge) {
    if (currentUser.two_factor_enabled) {
      statusBadge.className = "badge badge-success";
      statusBadge.innerHTML = '<i class="fa-solid fa-shield-check"></i> 2FA Enabled';
      const btn = document.getElementById("btnSetup2FA");
      if (btn) btn.style.display = "none";
    } else {
      statusBadge.className = "badge badge-danger";
      statusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> 2FA Disabled';
      const btn = document.getElementById("btnSetup2FA");
      if (btn) btn.style.display = "inline-flex";
    }
  }
}

function toggleApiKeyVisibility() {
  const input = document.getElementById("profileApiKey");
  const icon = document.getElementById("apiKeyEyeIcon");
  if (!input || !icon) return;
  if (input.type === "password") {
    input.type = "text";
    icon.className = "fa-solid fa-eye-slash";
  } else {
    input.type = "password";
    icon.className = "fa-solid fa-eye";
  }
}

async function regenerateApiKey() {
  if (!confirm("Are you sure you want to regenerate your Master API key? Any bots using the old key will need to be re-linked.")) return;
  try {
    const res = await apiCall("/api/auth/regenerate_api_key", "POST");
    if (res.api_key) {
      currentUser.api_key = res.api_key;
      const kEl = document.getElementById("profileApiKey");
      if (kEl) kEl.value = res.api_key;
      showToast("API Key regenerated successfully!", "success");
    }
  } catch (err) {}
}

// ----------------- Scripts Hub Management -----------------
async function loadScripts() {
  try {
    const scripts = await apiCall("/api/scripts");
    currentScripts = scripts;
    renderScripts(scripts);
  } catch (err) {}
}

function renderScripts(scripts) {
  const listEl = document.getElementById("scriptsList");
  if (!listEl) return;

  if (scripts.length === 0) {
    listEl.innerHTML = `<div class="card" style="text-align:center; padding: 40px;">
      <p style="color:var(--text-zinc-400); margin-bottom: 16px;">No script hubs created yet.</p>
      <button class="btn btn-primary" onclick="openCreateScriptModal()">+ Create Your First Hub</button>
    </div>`;
    return;
  }

  const currentOrigin = window.location.origin;
  listEl.innerHTML = scripts.map(s => {
    let modeBadge = '<span class="badge badge-zinc"><i class="fa-solid fa-file-code"></i> Unobfuscated</span>';
    if (s.is_obfuscated_mode === 2) {
      modeBadge = '<span class="badge badge-gold" style="background:rgba(250,204,21,0.18); border-color:var(--border-gold);"><i class="fa-solid fa-shield-halved"></i> O_bfuscate 1.1 VM</span>';
    } else if (s.is_obfuscated_mode === 1) {
      modeBadge = '<span class="badge badge-gold"><i class="fa-solid fa-lock"></i> Stream Encrypted</span>';
    }

    const keyGatedLoadstring = `getgenv().FleedKey = "YOUR_KEY"\nloadstring(game:HttpGet("${currentOrigin}/v1/loader/${s.slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;
    const cleanLoadstringOneLiner = `loadstring(game:HttpGet("${currentOrigin}/v1/loader/${s.slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;

    return `
      <div class="card" style="margin-bottom: 16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 14px; flex-wrap:wrap; gap:10px;">
          <div>
            <h3 style="color:var(--text-white); font-size:18px; margin-bottom:4px; display:flex; align-items:center; gap:8px;">
              ${escapeHtml(s.name)} 
              ${modeBadge}
              ${s.killswitch_active ? '<span class="badge badge-danger"><i class="fa-solid fa-bolt"></i> KILLSWITCH ACTIVE</span>' : '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> LIVE</span>'}
            </h3>
            <p style="color:var(--text-zinc-400); font-size:13px;">
              Slug: <code style="color:var(--gold-light);">${s.slug}</code> | Version: v${s.version} | Bound Licenses: ${s.active_licenses || 0}
            </p>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" onclick="openLoadstringModal('${s.slug}', '${escapeHtml(s.name)}')"><i class="fa-solid fa-terminal"></i> Get Loadstrings</button>
            <button class="btn btn-secondary btn-sm" onclick="openEditScriptModal(${s.id})"><i class="fa-solid fa-pen-to-square"></i> Edit Source</button>
            <button class="btn ${s.killswitch_active ? 'btn-primary' : 'btn-danger'} btn-sm" onclick="toggleKillswitch(${s.id}, ${s.killswitch_active})">
              <i class="fa-solid fa-bolt"></i> ${s.killswitch_active ? 'Disable Killswitch' : 'Trigger Killswitch'}
            </button>
            <button class="btn btn-danger btn-sm" onclick="deleteScript(${s.id})"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>

        <div style="background:var(--bg-input); padding: 12px 16px; border-radius: 10px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
          <div style="overflow:hidden; text-overflow:ellipsis;">
            <span style="font-size:11px; color:var(--text-zinc-500); display:block; margin-bottom:2px; font-weight:600; text-transform:uppercase;">Key-Gated Execution Loadstring:</span>
            <code style="font-family:var(--font-mono); font-size:12px; color:var(--gold-light); word-break:break-all;">
              ${cleanLoadstringOneLiner}
            </code>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="copyText('${keyGatedLoadstring.replace(/'/g, "\\'")}', 'Standard loadstring template copied!')">
              <i class="fa-solid fa-copy"></i> Copy Template
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function filterScriptsList(query) {
  const q = (query || "").toLowerCase().trim();
  const filtered = currentScripts.filter(s => 
    s.name.toLowerCase().includes(q) || s.slug.toLowerCase().includes(q)
  );
  renderScripts(filtered);
}

function updateScriptSizeCounter() {
  const text = document.getElementById("scriptSource")?.value || "";
  const bytes = new Blob([text]).size;
  const counter = document.getElementById("scriptSizeCounter");
  if (counter) {
    if (bytes > 1024 * 1024) {
      counter.innerText = (bytes / (1024 * 1024)).toFixed(2) + " MB";
    } else if (bytes > 1024) {
      counter.innerText = (bytes / 1024).toFixed(1) + " KB";
    } else {
      counter.innerText = bytes + " bytes";
    }
  }
}

function openCreateScriptModal() {
  document.getElementById("scriptModalTitle").innerHTML = '<i class="fa-solid fa-code" style="color:var(--gold-primary); margin-right:8px;"></i>Create Script Hub';
  document.getElementById("scriptEditId").value = "";
  document.getElementById("scriptName").value = "";
  document.getElementById("scriptSlug").value = "";
  document.getElementById("scriptVersion").value = "1.0.0";
  document.getElementById("scriptSource").value = "-- Paste your Lua / Luau script here\nprint(\"Hello from FleedGuard Protected Script!\")\n";
  document.getElementById("scriptMode").value = "2";
  document.getElementById("scriptWebhook").value = "";
  updateScriptSizeCounter();
  document.getElementById("modalScript").classList.add("active");
}

async function openEditScriptModal(id) {
  const script = currentScripts.find(s => s.id === id);
  if (!script) return;

  document.getElementById("scriptModalTitle").innerHTML = `<i class="fa-solid fa-pen-to-square" style="color:var(--gold-primary); margin-right:8px;"></i>Edit Hub: ${escapeHtml(script.name)}`;
  document.getElementById("scriptEditId").value = script.id;
  document.getElementById("scriptName").value = script.name;
  document.getElementById("scriptSlug").value = script.slug;
  document.getElementById("scriptVersion").value = script.version;
  document.getElementById("scriptSource").value = script.raw_source;
  document.getElementById("scriptMode").value = script.is_obfuscated_mode ? String(script.is_obfuscated_mode) : "0";
  document.getElementById("scriptWebhook").value = script.discord_webhook || "";
  updateScriptSizeCounter();
  document.getElementById("modalScript").classList.add("active");
}

async function saveScript(e) {
  e.preventDefault();
  const id = document.getElementById("scriptEditId").value;
  const name = document.getElementById("scriptName").value;
  const slug = document.getElementById("scriptSlug").value;
  const version = document.getElementById("scriptVersion").value;
  const raw_source = document.getElementById("scriptSource").value;
  const is_obfuscated_mode = parseInt(document.getElementById("scriptMode").value);
  const discord_webhook = document.getElementById("scriptWebhook").value;

  try {
    if (id) {
      await apiCall(`/api/scripts/${id}`, "PATCH", { name, version, raw_source, is_obfuscated_mode, discord_webhook });
      showToast("Script updated successfully!");
    } else {
      await apiCall("/api/scripts", "POST", { name, slug, version, raw_source, is_obfuscated_mode, discord_webhook });
      showToast("Script hub created successfully!");
    }
    closeModal("modalScript");
    loadScripts();
  } catch (err) {}
}

async function toggleKillswitch(id, currentStatus) {
  const newStatus = currentStatus ? 0 : 1;
  const reason = newStatus ? prompt("Enter Killswitch Reason (optional):", "Emergency maintenance in progress") : "";
  try {
    await apiCall(`/api/scripts/${id}`, "PATCH", { killswitch_active: newStatus, killswitch_reason: reason });
    showToast(newStatus ? "Killswitch ACTIVATED! Executions blocked." : "Killswitch deactivated.", newStatus ? "error" : "success");
    loadScripts();
  } catch (err) {}
}

async function deleteScript(id) {
  if (!confirm("Are you sure you want to delete this script and all associated licenses?")) return;
  try {
    await apiCall(`/api/scripts/${id}`, "DELETE");
    showToast("Script deleted.");
    loadScripts();
  } catch (err) {}
}

// ----------------- Loadstring Modal QoL -----------------
function openLoadstringModal(slug, name) {
  modalSelectedScript = { slug, name };
  document.getElementById("loadstringKeyInput").value = "";
  renderModalLoadstring();
  document.getElementById("modalLoadstring").classList.add("active");
}

function renderModalLoadstring() {
  if (!modalSelectedScript) return;
  const origin = window.location.origin;
  const style = document.getElementById("loadstringStyleSelect").value;
  const key = document.getElementById("loadstringKeyInput").value.trim() || "FLEED-XXXX-XXXX-XXXX";

  let code = "";
  if (style === "standard") {
    code = `getgenv().FleedKey = "${key}"\nloadstring(game:HttpGet("${origin}/v1/loader/${modalSelectedScript.slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;
  } else if (style === "direct") {
    code = `loadstring(game:HttpGet("${origin}/v1/loader/${modalSelectedScript.slug}?key=${key}"))()`;
  } else {
    code = `getgenv().FleedKey="${key}";loadstring(game:HttpGet("${origin}/v1/loader/${modalSelectedScript.slug}?key=${key}"))()`;
  }

  document.getElementById("modalLoadstringCode").innerText = code;
}

function copyModalLoadstring() {
  const text = document.getElementById("modalLoadstringCode").innerText;
  copyText(text, "Loadstring copied!");
}

// ----------------- Licenses Management & Bulk Actions -----------------
async function loadLicensesView() {
  const select = document.getElementById("licenseScriptSelect");
  if (!select) return;

  if (currentScripts.length === 0) {
    currentScripts = await apiCall("/api/scripts");
  }

  select.innerHTML = currentScripts.map(s => `<option value="${s.id}" ${s.id === selectedScriptId ? 'selected' : ''}>${escapeHtml(s.name)} (${s.slug})</option>`).join("");
  if (currentScripts.length > 0) {
    if (!selectedScriptId) selectedScriptId = currentScripts[0].id;
    select.value = selectedScriptId;
    loadLicensesForScript(selectedScriptId);
  }
}

async function loadLicensesForScript(scriptId) {
  if (!scriptId) return;
  selectedScriptId = parseInt(scriptId);
  selectedLicenseIds.clear();
  updateBulkActionBar();

  try {
    const licenses = await apiCall(`/api/scripts/${scriptId}/licenses`);
    currentLicenses = licenses;
    renderLicenses(licenses);
  } catch (err) {}
}

function renderLicenses(licenses) {
  const tableBody = document.getElementById("licensesTableBody");
  if (!tableBody) return;

  if (licenses.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 30px; color:var(--text-zinc-500);"><i class="fa-solid fa-key" style="margin-right:6px;"></i>No license keys generated for this hub.</td></tr>`;
    return;
  }

  const script = currentScripts.find(s => s.id === selectedScriptId);
  const slug = script ? script.slug : "";
  const origin = window.location.origin;

  tableBody.innerHTML = licenses.map(l => {
    const isChecked = selectedLicenseIds.has(l.id);
    const personalLoadstring = `getgenv().FleedKey = "${l.license_key}"\nloadstring(game:HttpGet("${origin}/v1/loader/${slug}?key=${l.license_key}"))()`;

    return `
      <tr class="${isChecked ? 'row-selected' : ''}">
        <td>
          <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleSelectLicense(${l.id}, this.checked)">
        </td>
        <td>
          <span class="key-badge" onclick="copyText('${l.license_key}', 'Key copied!')" title="Click to copy key">
            ${l.license_key} <i class="fa-solid fa-copy"></i>
          </span>
        </td>
        <td>${escapeHtml(l.note || l.discord_id ? (l.discord_id ? `<@${l.discord_id}> ` : '') + (l.note || '') : "—")}</td>
        <td>
          <span style="font-family:var(--font-mono); font-size:11px;">
            ${l.hwid ? '<i class="fa-solid fa-fingerprint" style="color:var(--gold-primary); margin-right:4px;"></i>' + l.hwid.substring(0, 14) + '...' : '<span style="color:var(--text-zinc-500)">Unbound</span>'}
          </span>
        </td>
        <td>${l.execution_count} / ${l.max_executions === -1 ? '<i class="fa-solid fa-infinity"></i>' : l.max_executions}</td>
        <td>${l.expires_at ? new Date(l.expires_at).toLocaleDateString() : '<span class="badge badge-gold"><i class="fa-solid fa-infinity"></i> Lifetime</span>'}</td>
        <td>
          <span class="badge ${l.is_banned ? 'badge-danger' : 'badge-success'}">
            <i class="${l.is_banned ? 'fa-solid fa-ban' : 'fa-solid fa-circle-check'}"></i> ${l.is_banned ? 'Banned' : 'Active'}
          </span>
        </td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="copyText('${personalLoadstring.replace(/'/g, "\\'")}', 'Personalized buyer loadstring copied!')" title="Copy buyer loadstring"><i class="fa-solid fa-terminal"></i></button>
            <button class="btn btn-secondary btn-sm" onclick="resetHWID(${l.id})" title="Reset bound device"><i class="fa-solid fa-arrows-rotate"></i></button>
            <button class="btn ${l.is_banned ? 'btn-secondary' : 'btn-danger'} btn-sm" onclick="toggleBanLicense(${l.id}, ${l.is_banned})" title="${l.is_banned ? 'Unban key' : 'Ban key'}">
              ${l.is_banned ? '<i class="fa-solid fa-unlock"></i>' : '<i class="fa-solid fa-ban"></i>'}
            </button>
            <button class="btn btn-danger btn-sm" onclick="deleteLicense(${l.id})" title="Delete key"><i class="fa-solid fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function filterLicensesTable() {
  const query = (document.getElementById("searchLicenseInput")?.value || "").toLowerCase().trim();
  const statusFilter = document.getElementById("filterStatusSelect")?.value || "all";

  let filtered = currentLicenses.filter(l => {
    const matchesSearch = !query || 
      l.license_key.toLowerCase().includes(query) ||
      (l.note && l.note.toLowerCase().includes(query)) ||
      (l.hwid && l.hwid.toLowerCase().includes(query)) ||
      (l.discord_id && l.discord_id.includes(query));

    if (!matchesSearch) return false;

    if (statusFilter === "active") return l.is_banned === 0;
    if (statusFilter === "banned") return l.is_banned === 1;
    if (statusFilter === "bound") return Boolean(l.hwid);
    if (statusFilter === "unbound") return !l.hwid;

    return true;
  });

  renderLicenses(filtered);
}

// Checkbox selection & bulk actions
function toggleSelectLicense(id, isChecked) {
  if (isChecked) selectedLicenseIds.add(id);
  else selectedLicenseIds.delete(id);
  updateBulkActionBar();
}

function toggleSelectAll(isChecked) {
  if (isChecked) {
    currentLicenses.forEach(l => selectedLicenseIds.add(l.id));
  } else {
    selectedLicenseIds.clear();
  }
  renderLicenses(currentLicenses);
  updateBulkActionBar();
}

function updateBulkActionBar() {
  const bar = document.getElementById("bulkActionBar");
  const countEl = document.getElementById("bulkSelectedCount");
  if (!bar || !countEl) return;

  const count = selectedLicenseIds.size;
  if (count > 0) {
    bar.style.display = "flex";
    countEl.innerText = `${count} key${count > 1 ? 's' : ''} selected`;
  } else {
    bar.style.display = "none";
  }
}

async function bulkAction(action) {
  if (selectedLicenseIds.size === 0) return;
  const ids = Array.from(selectedLicenseIds);

  if (action === "copy") {
    const keys = currentLicenses.filter(l => selectedLicenseIds.has(l.id)).map(l => l.license_key).join("\n");
    copyText(keys, `Copied ${ids.length} keys to clipboard!`);
    return;
  }

  if (action === "delete" && !confirm(`Are you sure you want to delete ${ids.length} selected license keys?`)) {
    return;
  }

  try {
    if (action === "resethwid") {
      await Promise.all(ids.map(id => apiCall(`/api/licenses/${id}/resethwid`, "POST")));
      showToast(`Reset HWID for ${ids.length} keys!`);
    } else if (action === "ban") {
      await Promise.all(ids.map(id => apiCall(`/api/licenses/${id}`, "PATCH", { is_banned: 1 })));
      showToast(`Banned ${ids.length} keys!`);
    } else if (action === "unban") {
      await Promise.all(ids.map(id => apiCall(`/api/licenses/${id}`, "PATCH", { is_banned: 0 })));
      showToast(`Unbanned ${ids.length} keys!`);
    } else if (action === "delete") {
      await Promise.all(ids.map(id => apiCall(`/api/licenses/${id}`, "DELETE")));
      showToast(`Deleted ${ids.length} keys!`);
    }

    selectedLicenseIds.clear();
    updateBulkActionBar();
    loadLicensesForScript(selectedScriptId);
  } catch (err) {}
}

// Export utilities
function exportKeys(format) {
  if (currentLicenses.length === 0) return showToast("No keys to export", "info");

  let content = "";
  let filename = `fleed_keys_${selectedScriptId}_${new Date().toISOString().slice(0,10)}`;
  let mimeType = "text/plain";

  if (format === "txt") {
    content = currentLicenses.map(l => l.license_key).join("\n");
    filename += ".txt";
  } else if (format === "json") {
    content = JSON.stringify(currentLicenses, null, 2);
    filename += ".json";
    mimeType = "application/json";
  } else if (format === "csv") {
    const headers = ["License Key", "Note", "HWID", "Executions", "Max Executions", "Expires At", "Is Banned"];
    const rows = currentLicenses.map(l => [
      l.license_key,
      `"${(l.note || '').replace(/"/g, '""')}"`,
      l.hwid || "",
      l.execution_count,
      l.max_executions,
      l.expires_at || "Lifetime",
      l.is_banned ? "Banned" : "Active"
    ]);
    content = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
    filename += ".csv";
    mimeType = "text/csv";
  }

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Exported ${currentLicenses.length} keys as ${format.toUpperCase()}`);
}

function copyAllKeys() {
  if (currentLicenses.length === 0) return showToast("No keys to copy", "info");
  const keys = currentLicenses.map(l => l.license_key).join("\n");
  copyText(keys, `Copied all ${currentLicenses.length} keys!`);
}

function openBulkGenModal() {
  document.getElementById("modalBulkGen").classList.add("active");
}

function openSingleGenModal() {
  document.getElementById("singleKeyString").value = `FLEED-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}`;
  document.getElementById("modalSingleGen").classList.add("active");
}

async function handleBulkGenerate(e) {
  e.preventDefault();
  const script_id = selectedScriptId;
  const count = parseInt(document.getElementById("genCount").value);
  const duration_days = parseInt(document.getElementById("genDuration").value) || null;
  const max_executions = parseInt(document.getElementById("genMaxExecs").value);
  const note = document.getElementById("genNote").value;

  try {
    const data = await apiCall("/api/licenses/bulk", "POST", {
      script_id, count, duration_days, max_executions, note
    });
    showToast(`Generated ${data.count} keys!`, "success");
    closeModal("modalBulkGen");
    loadLicensesForScript(script_id);
  } catch (err) {}
}

async function handleSingleGenerate(e) {
  e.preventDefault();
  const script = currentScripts.find(s => s.id === selectedScriptId);
  if (!script) return;

  const license_key = document.getElementById("singleKeyString").value.trim();
  const note = document.getElementById("singleKeyNote").value.trim();
  const duration_days = parseInt(document.getElementById("singleKeyDuration").value) || null;

  let expires_at = null;
  if (duration_days) {
    const d = new Date();
    d.setDate(d.getDate() + duration_days);
    expires_at = d.toISOString();
  }

  try {
    await apiCall("/api/licenses/create", "POST", {
      slug: script.slug,
      license_key,
      note,
      expires_at
    });
    showToast("License key created successfully!");
    closeModal("modalSingleGen");
    loadLicensesForScript(selectedScriptId);
  } catch (err) {}
}

async function resetHWID(licenseId) {
  try {
    await apiCall(`/api/licenses/${licenseId}/resethwid`, "POST");
    showToast("HWID reset successfully!");
    loadLicensesForScript(selectedScriptId);
  } catch (err) {}
}

async function toggleBanLicense(licenseId, isBanned) {
  const newBan = isBanned ? 0 : 1;
  const reason = newBan ? prompt("Enter ban reason:", "License violation") : "";
  try {
    await apiCall(`/api/licenses/${licenseId}`, "PATCH", { is_banned: newBan, ban_reason: reason });
    showToast(newBan ? "License banned!" : "License unbanned!", newBan ? "error" : "success");
    loadLicensesForScript(selectedScriptId);
  } catch (err) {}
}

async function deleteLicense(licenseId) {
  if (!confirm("Are you sure you want to permanently delete this license key?")) return;
  try {
    await apiCall(`/api/licenses/${licenseId}`, "DELETE");
    showToast("License deleted.");
    loadLicensesForScript(selectedScriptId);
  } catch (err) {}
}

// ----------------- Live Audit Logs & Threat Feed -----------------
async function loadLiveLogs() {
  const statusFilter = document.getElementById("logStatusFilter")?.value || "";
  try {
    const url = statusFilter ? `/api/logs?limit=60&status_filter=${statusFilter}` : `/api/logs?limit=60`;
    const logs = await apiCall(url);
    currentLogs = logs;
    renderLogs(logs);
  } catch (err) {}
}

function renderLogs(logs) {
  const tableBody = document.getElementById("logsTableBody");
  if (!tableBody) return;

  if (logs.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 30px; color:var(--text-zinc-500);"><i class="fa-solid fa-circle-info" style="margin-right:6px;"></i>No security events matching filter.</td></tr>`;
    return;
  }

  tableBody.innerHTML = logs.map(log => renderLogRow(log)).join("");
}

function filterLogsTable(query) {
  const q = (query || "").toLowerCase().trim();
  if (!q) {
    renderLogs(currentLogs);
    return;
  }

  const filtered = currentLogs.filter(log => 
    (log.roblox_username && log.roblox_username.toLowerCase().includes(q)) ||
    (log.license_key && log.license_key.toLowerCase().includes(q)) ||
    (log.ip_address && log.ip_address.includes(q)) ||
    (log.game_name && log.game_name.toLowerCase().includes(q)) ||
    (log.executor_name && log.executor_name.toLowerCase().includes(q)) ||
    (log.script_name && log.script_name.toLowerCase().includes(q))
  );
  renderLogs(filtered);
}

function toggleAutoRefresh() {
  isAutoRefreshOn = !isAutoRefreshOn;
  const stateEl = document.getElementById("autoRefreshState");
  const btn = document.getElementById("toggleAutoRefreshBtn");
  if (stateEl && btn) {
    if (isAutoRefreshOn) {
      stateEl.innerText = "ON";
      btn.innerHTML = '<i class="fa-solid fa-pause"></i> Auto-Refresh: <span id="autoRefreshState">ON</span>';
    } else {
      stateEl.innerText = "PAUSED";
      btn.innerHTML = '<i class="fa-solid fa-play"></i> Auto-Refresh: <span id="autoRefreshState">PAUSED</span>';
    }
  }
}

async function loadBypassLogs() {
  try {
    const logs = await apiCall("/api/logs?limit=60&status_filter=blocked");
    currentBypasses = logs;
    const tableBody = document.getElementById("bypassTableBody");
    if (!tableBody) return;

    if (logs.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 30px; color:var(--text-zinc-500);"><i class="fa-solid fa-shield-check" style="color:var(--success-color); margin-right:6px;"></i>No threat activity detected. System is completely secure.</td></tr>`;
      return;
    }

    tableBody.innerHTML = logs.map(log => {
      const avatarUrl = (log.roblox_user_id && log.roblox_user_id > 0)
        ? `/api/roblox/avatar/${log.roblox_user_id}`
        : `/api/roblox/avatar/1`;

      let threatBadge = `<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> ${log.status}</span>`;
      if (log.status === 'TAMPER_DETECTED') {
        threatBadge = `<span class="badge badge-danger"><i class="fa-solid fa-shield-virus"></i> HOOK/TAMPER DETECTED</span>`;
      } else if (log.status === 'HWID_MISMATCH') {
        threatBadge = `<span class="badge badge-danger" style="background:rgba(234,179,8,0.15); color:var(--gold-primary); border-color:rgba(234,179,8,0.4);"><i class="fa-solid fa-fingerprint"></i> HWID MISMATCH</span>`;
      } else if (log.status === 'BYPASS_ATTEMPT') {
        threatBadge = `<span class="badge badge-danger"><i class="fa-solid fa-skull-crossbones"></i> SCRAPER / DUMP TRAP</span>`;
      } else if (log.status === 'INVALID_KEY') {
        threatBadge = `<span class="badge badge-danger"><i class="fa-solid fa-key"></i> INVALID KEY</span>`;
      }

      return `
        <tr style="background: rgba(239, 68, 68, 0.03);">
          <td style="white-space:nowrap; font-size:12px; color:var(--text-zinc-400); font-family:var(--font-mono);">
            ${new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </td>
          <td>${threatBadge}</td>
          <td>
            <div style="display:flex; align-items:center; gap:10px;">
              <img src="${avatarUrl}" alt="Roblox Avatar" style="width:34px; height:34px; border-radius:50%; border:1px solid rgba(239,68,68,0.4); background:var(--bg-elevated); object-fit:cover;" loading="lazy">
              <div>
                <a href="${log.roblox_user_id ? `https://www.roblox.com/users/${log.roblox_user_id}/profile` : '#'}" target="_blank" style="color:var(--text-white); font-weight:600; text-decoration:none; display:flex; align-items:center; gap:4px; font-size:13px;">
                  ${escapeHtml(log.roblox_username || "Unknown")} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px; opacity:0.6;"></i>
                </a>
                <span style="font-size:11px; color:var(--text-zinc-500); font-family:var(--font-mono);">ID: ${log.roblox_user_id || '—'}</span>
              </div>
            </div>
          </td>
          <td>
            ${log.place_id && log.place_id > 0 ? `
              <div>
                <a href="https://www.roblox.com/games/${log.place_id}" target="_blank" style="color:var(--text-white); font-weight:500; font-size:13px; text-decoration:none; display:flex; align-items:center; gap:4px;">
                  ${escapeHtml(log.game_name || "Roblox Experience")} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px; opacity:0.6;"></i>
                </a>
                <span style="font-size:11px; color:var(--text-zinc-500); font-family:var(--font-mono);">Place: ${log.place_id}</span>
              </div>
            ` : `<span style="color:var(--text-zinc-500); font-size:13px;">${escapeHtml(log.game_name || "—")}</span>`}
          </td>
          <td>
            ${log.license_key ? `<span class="key-badge" style="font-size:11px; border-color:rgba(239,68,68,0.3); color:var(--danger-color);" onclick="copyText('${log.license_key}')">${log.license_key.substring(0, 14)}... <i class="fa-solid fa-copy"></i></span>` : '<span style="color:var(--text-zinc-500);">N/A</span>'}
          </td>
          <td>
            <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
              <span class="badge badge-zinc" style="font-size:10px; text-transform:uppercase;">${escapeHtml(log.executor_name || "Unknown Executor")}</span>
            </div>
            <span style="color:var(--text-zinc-400); font-size:12px;">${escapeHtml(log.details || "Bypass blocked by security armor")}</span>
          </td>
          <td>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-zinc-300);">
              <i class="fa-solid fa-fingerprint" style="color:var(--gold-primary); font-size:10px; margin-right:4px;"></i>${log.hwid ? log.hwid.substring(0, 12) + '...' : '—'}
            </div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-zinc-500); margin-top:2px;">
              <i class="fa-solid fa-network-wired" style="font-size:10px; margin-right:4px;"></i>${log.ip_address ? escapeHtml(log.ip_address) : '—'}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {}
}

function renderLogRow(log) {
  const avatarUrl = (log.roblox_user_id && log.roblox_user_id > 0)
    ? `/api/roblox/avatar/${log.roblox_user_id}`
    : `/api/roblox/avatar/1`;

  let rbxPlayerHtml = `<span style="color:var(--text-zinc-500);">—</span>`;
  if (log.roblox_username && log.roblox_username !== "Unknown") {
    const profileUrl = log.roblox_user_id ? `https://www.roblox.com/users/${log.roblox_user_id}/profile` : `https://www.roblox.com/search/users?keyword=${encodeURIComponent(log.roblox_username)}`;
    rbxPlayerHtml = `
      <div style="display:flex; align-items:center; gap:10px;">
        <img src="${avatarUrl}" alt="Avatar" style="width:34px; height:34px; border-radius:50%; border:1px solid var(--border-subtle); background:var(--bg-elevated); object-fit:cover;" loading="lazy">
        <div>
          <a href="${profileUrl}" target="_blank" style="color:var(--gold-light); font-weight:600; text-decoration:none; display:flex; align-items:center; gap:4px; font-size:13px;">
            ${escapeHtml(log.roblox_username)} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px; opacity:0.6;"></i>
          </a>
          <span style="font-size:11px; color:var(--text-zinc-500); font-family:var(--font-mono);">ID: ${log.roblox_user_id || '—'}</span>
        </div>
      </div>
    `;
  }

  let gamePlaceHtml = `<span style="color:var(--text-zinc-500);">—</span>`;
  if (log.place_id && log.place_id > 0) {
    const placeUrl = `https://www.roblox.com/games/${log.place_id}`;
    gamePlaceHtml = `
      <div>
        <a href="${placeUrl}" target="_blank" style="color:var(--text-white); font-weight:500; font-size:13px; text-decoration:none; display:flex; align-items:center; gap:4px;">
          ${escapeHtml(log.game_name || "Roblox Game")} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px; opacity:0.6;"></i>
        </a>
        <span style="font-size:11px; color:var(--text-zinc-500); font-family:var(--font-mono);">Place: ${log.place_id}</span>
      </div>
    `;
  } else if (log.game_name) {
    gamePlaceHtml = `<span style="color:var(--text-zinc-300); font-size:13px;">${escapeHtml(log.game_name)}</span>`;
  }

  let statusBadge = `<span class="badge badge-danger">${log.status}</span>`;
  if (log.status === 'SUCCESS') {
    statusBadge = `<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> SUCCESS</span>`;
  } else if (log.status === 'HWID_MISMATCH') {
    statusBadge = `<span class="badge badge-danger" style="background:rgba(234,179,8,0.15); color:var(--gold-primary);"><i class="fa-solid fa-fingerprint"></i> HWID MISMATCH</span>`;
  } else if (log.status === 'TAMPER_DETECTED') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-shield-virus"></i> TAMPER DETECTED</span>`;
  } else if (log.status === 'INVALID_KEY') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-key"></i> INVALID KEY</span>`;
  } else if (log.status === 'BYPASS_ATTEMPT') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-skull-crossbones"></i> BYPASS TRAP</span>`;
  } else if (log.status === 'EXPIRED') {
    statusBadge = `<span class="badge badge-zinc"><i class="fa-solid fa-clock"></i> EXPIRED</span>`;
  } else if (log.status === 'BANNED') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> BANNED</span>`;
  }

  return `
    <tr>
      <td style="white-space:nowrap; font-size:12px; color:var(--text-zinc-400); font-family:var(--font-mono);">
        ${new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </td>
      <td><strong style="color:var(--text-white);">${escapeHtml(log.script_name || "Unknown")}</strong></td>
      <td>${rbxPlayerHtml}</td>
      <td>${gamePlaceHtml}</td>
      <td>
        ${log.license_key ? `<span class="key-badge" style="font-size:11px;" onclick="copyText('${log.license_key}')">${log.license_key.substring(0, 14)}... <i class="fa-solid fa-copy"></i></span>` : '<span style="color:var(--text-zinc-500);">N/A</span>'}
      </td>
      <td>${statusBadge}</td>
      <td>
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
          <span class="badge badge-gold" style="font-size:11px;">${escapeHtml(log.executor_name || "Universal")}</span>
        </div>
        <span style="color:var(--text-zinc-400); font-size:12px;">${escapeHtml(log.details || "—")}</span>
      </td>
      <td>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-zinc-300);">
          <i class="fa-solid fa-fingerprint" style="color:var(--gold-primary); font-size:10px; margin-right:4px;"></i>${log.hwid ? log.hwid.substring(0, 12) + '...' : '—'}
        </div>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-zinc-500); margin-top:2px;">
          <i class="fa-solid fa-network-wired" style="font-size:10px; margin-right:4px;"></i>${log.ip_address ? escapeHtml(log.ip_address) : '—'}
        </div>
      </td>
      <td>
        ${log.license_id ? `
          <button class="btn btn-secondary btn-sm" onclick="resetHWID(${log.license_id})" title="Reset user HWID"><i class="fa-solid fa-arrows-rotate"></i></button>
        ` : '—'}
      </td>
    </tr>
  `;
}

// Helper: Escape HTML
function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// Global initialization
document.addEventListener("DOMContentLoaded", async () => {
  const isDashboard = window.location.pathname.startsWith("/dashboard");
  const user = await checkAuth();

  if (isDashboard && user) {
    switchTab("overview");
    loadOverviewStats();
    loadProfileStats();

    // Auto-refresh polling loop
    if (!liveLogInterval) {
      liveLogInterval = setInterval(() => {
        if (!isAutoRefreshOn) return;
        const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");
        if (activeTab === "logs") loadLiveLogs();
        if (activeTab === "bypasses") loadBypassLogs();
        if (activeTab === "overview") loadOverviewStats();
      }, 5000);
    }
  }
});
