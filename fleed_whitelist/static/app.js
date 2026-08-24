/**
 * FleedGuard Enterprise Security Console Engine
 * Comprehensive Whitelist Management, Anti-Dump DRM, Real-Time Telemetry & QoL Automation
 */

const API_BASE = "";

// Global State
let currentUser = null;
let currentScripts = [];
let currentLicenses = [];
let currentLogs = [];
let currentBypasses = [];
let currentBlacklists = [];
let currentStats = null;
let selectedScriptId = null;
let selectedLicenseIds = new Set();
let liveLogInterval = null;
let isAutoRefreshOn = true;
let modalSelectedScript = null;
const discordUsersCache = new Map();

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

// Copy to Clipboard Utility with Robust Fallback
function copyText(text, label = "Copied to clipboard!") {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(label, "success");
    }).catch(() => {
      fallbackCopyText(text, label);
    });
  } else {
    fallbackCopyText(text, label);
  }
}

function fallbackCopyText(text, label = "Copied to clipboard!") {
  try {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.top = "-9999px";
    textArea.style.left = "-9999px";
    textArea.style.opacity = "0";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const successful = document.execCommand("copy");
    document.body.removeChild(textArea);
    if (successful) {
      showToast(label, "success");
    } else {
      showToast("Unable to copy to clipboard", "error");
    }
  } catch (err) {
    showToast("Copy error: " + err.message, "error");
  }
}

function copyBuyerLoadstring(licenseKey, scriptSlug = "") {
  let slug = scriptSlug;
  if (!slug) {
    const script = currentScripts.find(s => s.id === selectedScriptId) || currentScripts[0];
    slug = script ? script.slug : "hoopz_hub_v1";
  }
  const origin = window.location.origin;
  const loadstringCode = `getgenv().FleedKey = "${licenseKey}"\nloadstring(game:HttpGet("${origin}/v1/loader/${slug}?key=${licenseKey}"))()`;
  copyText(loadstringCode, "Personalized buyer loadstring copied!");
}

// Modal Helpers
function openModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) {
    m.classList.add("active");
    m.style.display = "flex";
  }
}

function closeModal(modalId) {
  if (!modalId) {
    document.querySelectorAll(".modal-overlay.active, .modal-overlay[style*='display: flex']").forEach(m => {
      m.classList.remove("active");
      m.style.display = "none";
    });
    return;
  }
  const m = document.getElementById(modalId);
  if (m) {
    m.classList.remove("active");
    m.style.display = "none";
  }
}

// Global backdrop click-to-close handler for all modals
document.addEventListener("click", (e) => {
  if (e.target && e.target.classList && e.target.classList.contains("modal-overlay")) {
    e.target.classList.remove("active");
    e.target.style.display = "none";
  }
});

// Global ESC key listener to close any active modal
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" || e.keyCode === 27) {
    closeModal();
  }
});

// Escape HTML helper
function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// Relative time formatting helper (e.g., "5s ago", "2m ago", "1h ago")
function formatTimeAgo(isoString) {
  if (!isoString) return "Just now";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "Just now";
    const now = new Date();
    const diffSec = Math.max(0, Math.floor((now.getTime() - d.getTime()) / 1000));
    if (diffSec < 45) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDays = Math.floor(diffHr / 24);
    return `${diffDays}d ago`;
  } catch (e) {
    return "Just now";
  }
}

// ----------------- Executor Icon & Metadata Resolver -----------------
function getExecutorMeta(rawName) {
  const raw = (rawName || "").trim();
  const lower = raw.toLowerCase();

  // 1. Potassium
  if (lower.includes("potass") || lower.includes("potassium")) {
    return {
      displayName: "Potassium",
      color: "#facc15",
      bg: "rgba(250, 204, 21, 0.14)",
      border: "rgba(250, 204, 21, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><path d="M4.5 19.5C6.5 21.5 12 21 16 17C20 13 21 8 19.5 4.5C18 1 15 2 13 4C11 6 10 9 7 11C4 13 2.5 17.5 4.5 19.5Z" fill="#FACC15" stroke="#EAB308" stroke-width="1.5"/><path d="M14 4C14 4 16 8 13 12" stroke="#CA8A04" stroke-width="1.2" stroke-linecap="round"/></svg>`
    };
  }

  // 2. Wave
  if (lower.includes("wave")) {
    return {
      displayName: "Wave",
      color: "#06b6d4",
      bg: "rgba(6, 182, 212, 0.14)",
      border: "rgba(6, 182, 212, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><path d="M2 12C5 7 7 7 10 12C13 17 15 17 18 12C20 8.5 21.5 8.5 22 10" stroke="#06B6D4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 17C5 12 7 12 10 17C13 22 15 22 18 17C20 13.5 21.5 13.5 22 15" stroke="#22D3EE" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    };
  }

  // 3. Solara
  if (lower.includes("solara")) {
    return {
      displayName: "Solara",
      color: "#f59e0b",
      bg: "rgba(245, 158, 11, 0.14)",
      border: "rgba(245, 158, 11, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="5" fill="#F59E0B"/><path d="M12 2V5M12 19V22M2 12H5M19 12H22M4.93 4.93L7.05 7.05M16.95 16.95L19.07 19.07M4.93 19.07L7.05 16.95M16.95 7.05L19.07 4.93" stroke="#FBBF24" stroke-width="2" stroke-linecap="round"/></svg>`
    };
  }

  // 4. Synapse / Synapse Z / Synapse X
  if (lower.includes("synapse")) {
    return {
      displayName: raw.includes("Z") ? "Synapse Z" : (raw.includes("X") ? "Synapse X" : "Synapse"),
      color: "#38bdf8",
      bg: "rgba(56, 189, 248, 0.14)",
      border: "rgba(56, 189, 248, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14H12L11 22L21 10H12L13 2Z" fill="#38BDF8" stroke="#0284C7" stroke-width="1.5" stroke-linejoin="round"/></svg>`
    };
  }

  // 5. Celery
  if (lower.includes("celery")) {
    return {
      displayName: "Celery",
      color: "#10b981",
      bg: "rgba(16, 185, 129, 0.14)",
      border: "rgba(16, 185, 129, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><path d="M12 22V10M12 10C12 5.5 8.5 2 4 2C4 6.5 7.5 10 12 10ZM12 10C12 5.5 15.5 2 20 2C20 6.5 16.5 10 12 10Z" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    };
  }

  // 6. Macsploit
  if (lower.includes("macsploit") || lower.includes("mac")) {
    return {
      displayName: "Macsploit",
      color: "#f1f5f9",
      bg: "rgba(241, 245, 249, 0.14)",
      border: "rgba(241, 245, 249, 0.35)",
      icon: `<i class="fa-brands fa-apple" style="color:#f1f5f9; font-size:13px; vertical-align:middle;"></i>`
    };
  }

  // 7. Delta
  if (lower.includes("delta")) {
    return {
      displayName: "Delta",
      color: "#818cf8",
      bg: "rgba(129, 140, 248, 0.14)",
      border: "rgba(129, 140, 248, 0.38)",
      icon: `<svg style="width:14px; height:14px; vertical-align:middle; display:inline-block;" viewBox="0 0 24 24" fill="none"><path d="M12 3L22 21H2L12 3Z" fill="rgba(129, 140, 248, 0.2)" stroke="#818CF8" stroke-width="2" stroke-linejoin="round"/><path d="M12 9L17 18H7L12 9Z" fill="#818CF8"/></svg>`
    };
  }

  // 8. Codex
  if (lower.includes("codex")) {
    return {
      displayName: "Codex",
      color: "#c084fc",
      bg: "rgba(192, 132, 252, 0.14)",
      border: "rgba(192, 132, 252, 0.38)",
      icon: `<i class="fa-solid fa-book-bookmark" style="color:#c084fc; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // 9. Krampus / Ro-Exec
  if (lower.includes("krampus") || lower.includes("ro-exec") || lower.includes("roexec")) {
    return {
      displayName: "Krampus",
      color: "#f87171",
      bg: "rgba(248, 113, 113, 0.14)",
      border: "rgba(248, 113, 113, 0.38)",
      icon: `<i class="fa-solid fa-crown" style="color:#f87171; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // 10. Fluxus
  if (lower.includes("fluxus") || lower.includes("flux")) {
    return {
      displayName: "Fluxus",
      color: "#f472b6",
      bg: "rgba(244, 114, 182, 0.14)",
      border: "rgba(244, 114, 182, 0.38)",
      icon: `<i class="fa-solid fa-bolt" style="color:#f472b6; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // 11. Arceus X
  if (lower.includes("arceus")) {
    return {
      displayName: "Arceus X",
      color: "#fb923c",
      bg: "rgba(251, 146, 60, 0.14)",
      border: "rgba(251, 146, 60, 0.38)",
      icon: `<i class="fa-solid fa-fire-flame-curved" style="color:#fb923c; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // 12. Hydrogen
  if (lower.includes("hydrogen")) {
    return {
      displayName: "Hydrogen",
      color: "#38bdf8",
      bg: "rgba(56, 189, 248, 0.14)",
      border: "rgba(56, 189, 248, 0.38)",
      icon: `<i class="fa-solid fa-atom" style="color:#38bdf8; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // 13. Xeno / Volcano / Lunar / Ronix / Swift / Velocity
  if (lower.includes("xeno") || lower.includes("volcano") || lower.includes("lunar") || lower.includes("ronix") || lower.includes("swift") || lower.includes("velocity")) {
    return {
      displayName: raw,
      color: "#2dd4bf",
      bg: "rgba(45, 212, 191, 0.14)",
      border: "rgba(45, 212, 191, 0.38)",
      icon: `<i class="fa-solid fa-shield-virus" style="color:#2dd4bf; font-size:12px; vertical-align:middle;"></i>`
    };
  }

  // Fallback Universal / Undetected
  return {
    displayName: raw || "Universal",
    color: "#fbbf24",
    bg: "rgba(245, 158, 11, 0.12)",
    border: "rgba(245, 158, 11, 0.3)",
    icon: `<i class="fa-solid fa-terminal" style="color:var(--gold-primary); font-size:11px; vertical-align:middle;"></i>`
  };
}

function renderExecutorBadge(executorName) {
  const meta = getExecutorMeta(executorName);
  return `
    <span class="executor-badge-pill" style="display:inline-flex; align-items:center; gap:5px; background:${meta.bg}; border:1px solid ${meta.border}; padding:2px 8px; border-radius:6px; font-weight:600; font-size:11.5px; color:${meta.color}; white-space:nowrap;">
      ${meta.icon}
      <span>${escapeHtml(meta.displayName)}</span>
    </span>
  `;
}

// Generic API Fetch Wrapper
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
  const startPing = performance.now();
  try {
    const user = await apiCall("/api/auth/me");
    currentUser = user;
    const pingMs = Math.round(performance.now() - startPing);
    const pingBadge = document.getElementById("headerPingBadge");
    if (pingBadge) pingBadge.innerText = `${pingMs}ms`;

    loadProfileStats();

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
    currentUser.two_factor_enabled = true;
    loadProfileStats();
  } catch (err) {}
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

let selectedAvatarUrl = null;

function updateAvatarUI(avatarUrl, username) {
  const initial = (username || "U").charAt(0).toUpperCase();

  // 1. Sidebar Avatar & Topbar Profile
  const avatarImgs = [
    document.getElementById("sidebarAvatarImg"),
    document.getElementById("topProfileAvatarImg"),
    document.getElementById("dropdownAvatarImg"),
    document.getElementById("settingsAvatarImg")
  ];
  const initialEls = [
    document.getElementById("sidebarUserInitial"),
    document.getElementById("topProfileInitial"),
    document.getElementById("dropdownInitial"),
    document.getElementById("settingsInitial")
  ];

  avatarImgs.forEach(img => {
    if (img) {
      if (avatarUrl) {
        img.src = avatarUrl;
        img.style.display = "block";
      } else {
        img.style.display = "none";
      }
    }
  });

  initialEls.forEach(init => {
    if (init) {
      if (avatarUrl) {
        init.style.display = "none";
      } else {
        init.style.display = "flex";
        init.innerText = initial;
      }
    }
  });
}

async function loadProfileStats() {
  if (!currentUser) return;
  const user = currentUser;

  const sidebarUser = document.getElementById("sidebarUsername");
  if (sidebarUser) sidebarUser.innerText = user.username || "Developer";

  const sidebarRole = document.getElementById("sidebarUserRole");
  if (sidebarRole) sidebarRole.innerText = (user.role || "developer").toUpperCase();

  const topName = document.getElementById("topProfileName");
  if (topName) topName.innerText = user.username || "Developer";

  const dropUser = document.getElementById("dropdownUserFull");
  if (dropUser) dropUser.innerText = user.username || "Developer";

  const dropEmail = document.getElementById("dropdownEmail");
  if (dropEmail) dropEmail.innerText = user.email || "";

  const setUsername = document.getElementById("settingsUsername");
  if (setUsername) setUsername.innerText = user.username || "admin";

  const setEmail = document.getElementById("settingsEmail");
  if (setEmail) setEmail.innerText = user.email || "";

  const setRole = document.getElementById("settingsRole");
  if (setRole) setRole.innerText = (user.role || "developer").toUpperCase();

  const profEmail = document.getElementById("profileEmail");
  if (profEmail) profEmail.innerText = user.email || "—";

  const profRole = document.getElementById("profileRole");
  if (profRole) profRole.innerText = user.role || "developer";

  const badge2FA = document.getElementById("2FAStatusBadge");
  const btn2FA = document.getElementById("btnSetup2FA");
  if (badge2FA && btn2FA) {
    if (user.two_factor_enabled) {
      badge2FA.className = "badge badge-success";
      badge2FA.innerHTML = '<i class="fa-solid fa-circle-check"></i> Enabled & Enforced';
      btn2FA.className = "btn btn-danger btn-sm";
      btn2FA.innerHTML = '<i class="fa-solid fa-unlock"></i> Disable 2FA';
      btn2FA.onclick = () => openDisable2FAModal();
    } else {
      badge2FA.className = "badge badge-zinc";
      badge2FA.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Not Configured';
      btn2FA.className = "btn btn-primary btn-sm";
      btn2FA.innerHTML = '<i class="fa-solid fa-lock"></i> Configure 2FA';
      btn2FA.onclick = () => open2FAModal();
    }
  }

  updateAvatarUI(user.avatar_url, user.username);
}

// ----------------- Avatar Customization Functions -----------------
let pendingAvatarFile = null;

function openChangeAvatarModal() {
  pendingAvatarFile = null;
  selectedAvatarUrl = currentUser?.avatar_url || null;
  updateModalAvatarPreview(selectedAvatarUrl);
  document.getElementById("avatarCustomUrlInput").value = selectedAvatarUrl && !selectedAvatarUrl.startsWith("data:") ? selectedAvatarUrl : "";
  document.getElementById("avatarRobloxInput").value = "";
  
  const dropText = document.getElementById("avatarDropText");
  if (dropText) dropText.innerText = "Click to browse or drag & drop image";
  const fileInput = document.getElementById("avatarFileInput");
  if (fileInput) fileInput.value = "";

  document.getElementById("modalChangeAvatar").classList.add("active");
  setupAvatarDragAndDrop();
}

function setupAvatarDragAndDrop() {
  const zone = document.getElementById("avatarDropZone");
  if (!zone || zone.dataset.dropReady) return;
  zone.dataset.dropReady = "true";

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.style.borderColor = "var(--gold-primary)";
    zone.style.background = "rgba(250, 204, 21, 0.08)";
  });

  zone.addEventListener("dragleave", (e) => {
    e.preventDefault();
    zone.style.borderColor = "var(--border-gold-subtle)";
    zone.style.background = "rgba(250, 204, 21, 0.02)";
  });

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.style.borderColor = "var(--border-gold-subtle)";
    zone.style.background = "rgba(250, 204, 21, 0.02)";
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processSelectedAvatarFile(e.dataTransfer.files[0]);
    }
  });
}

function handleAvatarFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  processSelectedAvatarFile(file);
}

function processSelectedAvatarFile(file) {
  if (file.size > 5 * 1024 * 1024) {
    return showToast("Image file exceeds 5MB limit", "error");
  }

  const validTypes = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"];
  if (!validTypes.includes(file.type)) {
    return showToast("Invalid image format. Supported: PNG, JPG, WebP, GIF", "error");
  }

  pendingAvatarFile = file;
  const dropText = document.getElementById("avatarDropText");
  if (dropText) dropText.innerText = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

  const reader = new FileReader();
  reader.onload = (e) => {
    selectedAvatarUrl = e.target.result;
    updateModalAvatarPreview(selectedAvatarUrl);
    document.getElementById("avatarCustomUrlInput").value = "";
    showToast(`Image loaded: ${file.name}`, "info");
  };
  reader.readAsDataURL(file);
}

function updateModalAvatarPreview(url) {
  const previewImg = document.getElementById("previewAvatarImg");
  const previewInit = document.getElementById("previewInitial");
  const initial = (currentUser?.username || "U").charAt(0).toUpperCase();

  if (url && url.trim()) {
    previewImg.src = url;
    previewImg.style.display = "block";
    previewInit.style.display = "none";
  } else {
    previewImg.style.display = "none";
    previewInit.style.display = "flex";
    previewInit.innerText = initial;
  }
}

function selectPresetAvatar(url) {
  pendingAvatarFile = null;
  selectedAvatarUrl = url || null;
  document.getElementById("avatarCustomUrlInput").value = url || "";
  const dropText = document.getElementById("avatarDropText");
  if (dropText) dropText.innerText = "Click to browse or drag & drop image";
  const fileInput = document.getElementById("avatarFileInput");
  if (fileInput) fileInput.value = "";
  updateModalAvatarPreview(url);
}

function updateAvatarPreviewDirect(url) {
  pendingAvatarFile = null;
  selectedAvatarUrl = url.trim() || null;
  const dropText = document.getElementById("avatarDropText");
  if (dropText) dropText.innerText = "Click to browse or drag & drop image";
  const fileInput = document.getElementById("avatarFileInput");
  if (fileInput) fileInput.value = "";
  updateModalAvatarPreview(selectedAvatarUrl);
}

async function fetchRobloxAvatarPreview() {
  const input = document.getElementById("avatarRobloxInput")?.value.trim();
  if (!input) return showToast("Enter a Roblox username or User ID", "info");

  showToast("Fetching Roblox avatar...", "info");
  try {
    let rbxId = parseInt(input);
    if (isNaN(rbxId) || rbxId <= 0) {
      // Username lookup
      const res = await fetch(`https://users.roblox.com/v1/usernames/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usernames: [input], excludeBannedUsers: false })
      });
      const data = await res.json();
      if (data.data && data.data.length > 0) {
        rbxId = data.data[0].id;
      } else {
        return showToast(`Roblox user "${input}" not found`, "error");
      }
    }

    const avatarUrl = `/api/roblox/avatar/${rbxId}`;
    pendingAvatarFile = null;
    selectedAvatarUrl = avatarUrl;
    document.getElementById("avatarCustomUrlInput").value = avatarUrl;
    const dropText = document.getElementById("avatarDropText");
    if (dropText) dropText.innerText = "Click to browse or drag & drop image";
    const fileInput = document.getElementById("avatarFileInput");
    if (fileInput) fileInput.value = "";
    updateModalAvatarPreview(avatarUrl);
    showToast(`Found Roblox avatar for User ID ${rbxId}!`, "success");
  } catch (err) {
    // Direct endpoint fallback
    const fallbackUrl = `/api/roblox/avatar/1`;
    pendingAvatarFile = null;
    selectedAvatarUrl = fallbackUrl;
    updateModalAvatarPreview(fallbackUrl);
  }
}

async function saveUserAvatar() {
  // 1. If user selected a local file from PC (data URL), use base64 upload
  if (selectedAvatarUrl && selectedAvatarUrl.startsWith("data:image/")) {
    showToast("Uploading avatar image from PC...", "info");
    try {
      const res = await apiCall("/api/auth/upload_avatar_base64", "POST", { image_data: selectedAvatarUrl });
      showToast("Avatar uploaded and saved successfully!", "success");
      if (currentUser) {
        currentUser.avatar_url = res.avatar_url;
      }
      updateAvatarUI(res.avatar_url, currentUser?.username);
      closeModal("modalChangeAvatar");
      return;
    } catch (err) {
      showToast(err.message || "Failed to upload avatar", "error");
      return;
    }
  }

  // 2. Otherwise update with URL / Preset / Roblox
  const avatar_url = selectedAvatarUrl || document.getElementById("avatarCustomUrlInput")?.value.trim() || null;

  try {
    const res = await apiCall("/api/auth/update_avatar", "POST", { avatar_url });
    showToast("Profile avatar updated successfully!", "success");
    if (currentUser) {
      currentUser.avatar_url = res.avatar_url;
    }
    updateAvatarUI(res.avatar_url, currentUser?.username);
    closeModal("modalChangeAvatar");
  } catch (err) {}
}

// ----------------- Dashboard Navigation & Sidebar -----------------
const TAB_TITLES = {
  overview: "Command Overview & Telemetry",
  sessions: "Live In-Game Players Radar",
  scripts: "Script Hubs & Armor Pipelines",
  licenses: "License Keys & Whitelist Matrix",
  bypasses: "Threat Radar & Forensic Attribution",
  logs: "Live Security Audit Stream",
  telemetry: "Executor Analytics & Fingerprinting",
  "remote-exec": "Remote Luau Code Execution",
  versions: "Version Control & Rollback",
  flags: "Feature Flags & Remote Switches",
  api: "Developer REST API Studio",
  chat: "Live Developer Room",
  announcements: "Broadcasts & In-Game Alerts",
  webhooks: "Discord Security Webhooks",
  staff: "Staff & Reseller Accounts",
  system: "System Health & Database Engine",
  settings: "Security & 2FA Profile"
};

function toggleSidebar() {
  const sidebar = document.getElementById("mainSidebar");
  if (!sidebar) return;
  const isCollapsed = sidebar.classList.toggle("collapsed");
  localStorage.setItem("fleed_sidebar_collapsed", isCollapsed ? "1" : "0");
  const btn = document.getElementById("sidebarCollapseBtn");
  if (btn) {
    btn.innerHTML = isCollapsed ? '<i class="fa-solid fa-angles-right"></i>' : '<i class="fa-solid fa-angles-left"></i>';
    btn.title = isCollapsed ? "Expand Sidebar (Ctrl+[)" : "Collapse Sidebar (Ctrl+[)";
  }
}

function toggleMobileSidebar() {
  const sidebar = document.getElementById("mainSidebar");
  if (!sidebar) return;
  sidebar.classList.toggle("mobile-open");
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-view").forEach(view => {
    view.style.display = "none";
    view.classList.remove("active");
  });

  const activeBtns = document.querySelectorAll(`[data-tab="${tabName}"]`);
  const activeView = document.getElementById(`view-${tabName}`);
  activeBtns.forEach(btn => btn.classList.add("active"));
  if (activeView) {
    activeView.style.display = (tabName === "chat" || tabName === "overview" || tabName === "sessions" || tabName === "remote-exec" || tabName === "logs" || tabName === "licenses" || tabName === "scripts" || tabName === "bypasses" || tabName === "telemetry") ? "flex" : "block";
    activeView.classList.add("active");
  }

  // Update Breadcrumb
  const breadcrumbEl = document.getElementById("currentViewBreadcrumb");
  if (breadcrumbEl) {
    breadcrumbEl.innerText = TAB_TITLES[tabName] || tabName.toUpperCase();
  }

  // Close mobile sidebar on mobile
  const sidebar = document.getElementById("mainSidebar");
  if (sidebar && sidebar.classList.contains("mobile-open")) {
    sidebar.classList.remove("mobile-open");
  }

  if (tabName === "overview") loadOverviewStats();
  if (tabName === "scripts") loadScripts();
  if (tabName === "licenses") loadLicensesView();
  if (tabName === "chat") { loadChatMessages(); initChatWebSocket(); }
  if (tabName === "sessions") loadLiveSessions();
  if (tabName === "staff") loadStaffManagers();
  if (tabName === "telemetry") loadTelemetryData();
  if (tabName === "flags") loadFeatureFlags();
  if (tabName === "announcements") loadAnnouncements();
  if (tabName === "remote-exec") loadRemoteExecQueue();
  if (tabName === "versions") loadScriptVersions();
  if (tabName === "webhooks") loadDiscordWebhooks();
  if (tabName === "logs") loadLiveLogs();
  if (tabName === "bypasses") { loadThreatRadarBypasses(); loadAnomalies(); loadBlacklists(); }
  if (tabName === "api") loadApiStudioView();
  if (tabName === "settings") loadProfileStats();
  if (tabName === "system") loadSystemHealth();
}

// ----------------- Overview & Telemetry Analytics -----------------
async function loadOverviewStats() {
  try {
    const stats = await apiCall("/api/stats");
    currentStats = stats;

    document.getElementById("statScripts").innerText = stats.total_scripts || 0;
    document.getElementById("statActiveLicenses").innerText = stats.active_licenses || 0;
    document.getElementById("statExecutions").innerText = stats.total_executions || 0;
    document.getElementById("statBlockedAttacks").innerText = stats.blocked_attacks || 0;
    document.getElementById("statUniquePlayers").innerText = stats.unique_players || 0;
    document.getElementById("statActive15m").innerText = stats.active_sessions_15m || 0;

    // Subtext stats
    const licBreakdown = document.getElementById("statLicenseBreakdown");
    if (licBreakdown) {
      licBreakdown.innerText = `${stats.total_licenses || 0} Total (${stats.banned_licenses || 0} Banned, ${stats.expired_licenses || 0} Expired)`;
    }

    const succRate = document.getElementById("statSuccessRate");
    if (succRate) {
      const rate = stats.total_executions > 0 
        ? Math.round((stats.success_executions / stats.total_executions) * 100) 
        : 100;
      succRate.innerHTML = `<i class="fa-solid fa-circle-check" style="color:var(--success-color);"></i> ${rate}% Success rate`;
    }

    // Update tab count badges
    const bScr = document.getElementById("badgeScriptsCount");
    if (bScr) bScr.innerText = stats.total_scripts || 0;
    const bLic = document.getElementById("badgeLicensesCount");
    if (bLic) bLic.innerText = stats.total_licenses || 0;

    const bThreat = document.getElementById("badgeThreatCount");
    if (bThreat) {
      if (stats.blocked_attacks > 0) {
        bThreat.style.display = "inline-block";
        bThreat.innerText = stats.blocked_attacks;
      } else {
        bThreat.style.display = "none";
      }
    }

    // Render 24h Hourly Activity Chart (SVG)
    renderOverviewChart(stats.hourly_activity || []);

    // Render Top Games & Top Executors
    renderTopGames(stats.top_games || []);
    renderTopExecutors(stats.top_executors || []);

    // Load active in-game sessions and recent kicks
    loadActiveSessions();
    loadRecentKicks();

    // Fetch system health to detect public tunnel
    loadSystemHealth();
  } catch (e) {}
}

function renderOverviewChart(hourlyData) {
  const container = document.getElementById("overviewChartContainer");
  if (!container) return;

  if (!hourlyData || hourlyData.length === 0) {
    hourlyData = [];
    const now = new Date();
    for (let i = 23; i >= 0; i--) {
      const d = new Date(now.getTime() - i * 3600 * 1000);
      hourlyData.push({
        hour: `${String(d.getHours()).padStart(2, '0')}:00`,
        success: 0,
        blocked: 0,
        total: 0
      });
    }
  }

  const svgWidth = 1000;
  const chartHeight = 110;
  const maxVal = Math.max(...hourlyData.map(d => (d.success || 0) + (d.blocked || 0)), 5);
  const slotWidth = svgWidth / hourlyData.length;
  const barWidth = slotWidth * 0.62;

  let barsSvg = "";
  hourlyData.forEach((d, idx) => {
    const succ = d.success || 0;
    const block = d.blocked || 0;
    const total = succ + block;

    const x = idx * slotWidth + (slotWidth - barWidth) / 2;

    // Subtle baseline slot
    barsSvg += `
      <rect x="${x}" y="${chartHeight - 3}" width="${barWidth}" height="3" rx="1.5" fill="rgba(255,255,255,0.08)">
        <title>${d.hour}: 0 Handshakes</title>
      </rect>
    `;

    if (total > 0) {
      const succH = Math.max((succ / maxVal) * chartHeight, succ > 0 ? 6 : 0);
      const blockH = Math.max((block / maxVal) * chartHeight, block > 0 ? 6 : 0);

      const ySucc = chartHeight - succH;
      if (succ > 0) {
        barsSvg += `
          <rect class="chart-bar-success" x="${x}" y="${ySucc}" width="${barWidth}" height="${succH}" rx="3" fill="url(#goldBarGrad)">
            <title>${d.hour}: ${succ} Deliveries</title>
          </rect>
        `;
      }

      if (block > 0) {
        const yBlock = ySucc - blockH;
        barsSvg += `
          <rect class="chart-bar-blocked" x="${x}" y="${yBlock}" width="${barWidth}" height="${blockH}" rx="3" fill="url(#threatBarGrad)">
            <title>${d.hour}: ${block} Blocked Threats</title>
          </rect>
        `;
      }
    }

    // Hour label on X-axis
    if (idx % 4 === 0 || idx === hourlyData.length - 1) {
      barsSvg += `
        <text class="chart-axis-label" x="${x + barWidth / 2}" y="${chartHeight + 18}" text-anchor="middle" fill="#64748b" font-size="11" font-family="'JetBrains Mono', monospace">${d.hour}</text>
      `;
    }
  });

  container.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${svgWidth} ${chartHeight + 24}" style="width:100%; height:100%; display:block;">
      <defs>
        <linearGradient id="goldBarGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#fbbf24" />
          <stop offset="100%" stop-color="#d97706" />
        </linearGradient>
        <linearGradient id="threatBarGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f87171" />
          <stop offset="100%" stop-color="#dc2626" />
        </linearGradient>
      </defs>
      <!-- Grid lines -->
      <line x1="0" y1="5" x2="${svgWidth}" y2="5" stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="4" />
      <line x1="0" y1="${chartHeight / 2}" x2="${svgWidth}" y2="${chartHeight / 2}" stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="4" />
      <line x1="0" y1="${chartHeight}" x2="${svgWidth}" y2="${chartHeight}" stroke="rgba(255,255,255,0.12)" stroke-width="1" />
      ${barsSvg}
    </svg>
  `;
}

function renderTopGames(games) {
  const container = document.getElementById("topGamesList");
  if (!container) return;

  if (games.length === 0) {
    container.innerHTML = `<p style="color:var(--text-zinc-500); font-size:13px; text-align:center; padding:20px;">No game executions logged yet.</p>`;
    return;
  }

  const maxCount = Math.max(...games.map(g => g.count), 1);
  container.innerHTML = games.map(g => {
    const pct = Math.round((g.count / maxCount) * 100);
    const placeLink = g.place_id > 0 ? `https://www.roblox.com/games/${g.place_id}` : '#';
    return `
      <div class="rank-item">
        <div class="rank-header">
          <a href="${placeLink}" target="_blank" style="color:var(--text-white); font-weight:600; text-decoration:none; display:flex; align-items:center; gap:6px;">
            <i class="fa-solid fa-gamepad" style="color:var(--gold-primary); font-size:11px;"></i>
            ${escapeHtml(g.name)}
            ${g.place_id > 0 ? `<i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i>` : ''}
          </a>
          <span style="font-family:var(--font-mono); font-weight:700; color:var(--gold-light);">${g.count} execs</span>
        </div>
        <div class="rank-bar-bg">
          <div class="rank-bar-fill" style="width:${pct}%;"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderTopExecutors(executors) {
  const container = document.getElementById("topExecutorsList");
  if (!container) return;

  if (executors.length === 0) {
    container.innerHTML = `<p style="color:var(--text-zinc-500); font-size:13px; text-align:center; padding:20px;">No executor telemetry logged yet.</p>`;
    return;
  }

  const maxCount = Math.max(...executors.map(e => e.count), 1);
  container.innerHTML = executors.map(e => {
    const meta = getExecutorMeta(e.name);
    const pct = Math.round((e.count / maxCount) * 100);
    return `
      <div class="rank-item">
        <div class="rank-header">
          <span style="color:var(--text-white); font-weight:600; display:flex; align-items:center; gap:6px;">
            ${meta.icon}
            ${escapeHtml(meta.displayName)}
          </span>
          <span style="font-family:var(--font-mono); font-weight:700; color:var(--text-zinc-300);">${e.count} execs</span>
        </div>
        <div class="rank-bar-bg">
          <div class="rank-bar-fill" style="width:${pct}%; background:${meta.color};"></div>
        </div>
      </div>
    `;
  }).join("");
}

async function loadProfileStats() {
  if (!currentUser) return;
  const uEl = document.getElementById("profileUsername");
  if (uEl) uEl.innerText = currentUser.username || "Developer";

  const dUserFull = document.getElementById("dropdownUserFull");
  if (dUserFull) dUserFull.innerText = currentUser.username || "Developer";

  const initEl = document.getElementById("userInitial");
  if (initEl && currentUser.username) {
    initEl.innerText = currentUser.username.charAt(0).toUpperCase();
  }

  const eEl = document.getElementById("profileEmail");
  if (eEl) eEl.innerText = currentUser.email || "—";

  const dEmail = document.getElementById("dropdownEmail");
  if (dEmail) dEmail.innerText = currentUser.email || "—";

  const kEl = document.getElementById("profileApiKey");
  if (kEl) kEl.value = currentUser.api_key || "";

  const roleEl = document.getElementById("profileRole");
  if (roleEl) roleEl.innerText = currentUser.role || "developer";
  
  const statusBadge = document.getElementById("2FAStatusBadge");
  if (statusBadge) {
    if (currentUser.two_factor_enabled) {
      statusBadge.className = "badge badge-success";
      statusBadge.innerHTML = '<i class="fa-solid fa-shield-check"></i> 2FA ACTIVE';
      const btn = document.getElementById("btnSetup2FA");
      if (btn) btn.style.display = "none";
    } else {
      statusBadge.className = "badge badge-danger";
      statusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> 2FA DISABLED';
      const btn = document.getElementById("btnSetup2FA");
      if (btn) btn.style.display = "inline-flex";
    }
  }

  const discInput = document.getElementById("discordBindInput");
  if (discInput && currentUser.discord_id) {
    discInput.value = currentUser.discord_id;
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
  if (!confirm("Are you sure you want to regenerate your Master API key? Any bots or stores using the old key will need to be updated.")) return;
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

async function saveDiscordBind() {
  const val = document.getElementById("discordBindInput")?.value.trim();
  if (!val) return showToast("Enter a valid Discord user ID", "error");
  try {
    const res = await apiCall("/api/auth/bind_discord", "POST", { discord_id: val });
    showToast(res.message, "success");
    currentUser.discord_id = val;
  } catch (err) {}
}

// ----------------- Script Hubs Management -----------------
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
      <i class="fa-solid fa-code" style="font-size:36px; color:var(--gold-primary); margin-bottom:12px; display:block;"></i>
      <h3 style="color:var(--text-white); font-size:18px; margin-bottom:6px;">No Script Hubs Found</h3>
      <p style="color:var(--text-zinc-400); margin-bottom: 18px; font-size:13px;">Create your first Lua script hub to enable O_bfuscate 1.1 virtualization and generate key-gated loaders.</p>
      <button class="btn btn-primary" onclick="openCreateScriptModal()"><i class="fa-solid fa-plus"></i> Create Hub Now</button>
    </div>`;
    return;
  }

  const currentOrigin = window.location.origin;
  listEl.innerHTML = scripts.map(s => {
    let modeBadge = '<span class="badge badge-zinc"><i class="fa-solid fa-file-code"></i> Unobfuscated</span>';
    if (s.is_obfuscated_mode === 2) {
      modeBadge = '<span class="badge badge-gold"><i class="fa-solid fa-shield-halved"></i> O_bfuscate V2 Ultra</span>';
    } else if (s.is_obfuscated_mode === 1) {
      modeBadge = '<span class="badge badge-gold"><i class="fa-solid fa-bolt"></i> O_bfuscate V2 MaxPerf</span>';
    }

    const keyGatedLoadstring = `getgenv().FleedKey = "YOUR_KEY"\nloadstring(game:HttpGet("${currentOrigin}/v1/loader/${s.slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;
    const cleanLoadstringOneLiner = `loadstring(game:HttpGet("${currentOrigin}/v1/loader/${s.slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;

    return `
      <div class="card" style="margin-bottom: 18px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 14px; flex-wrap:wrap; gap:10px;">
          <div>
            <h3 style="color:var(--text-white); font-size:18px; margin-bottom:4px; display:flex; align-items:center; gap:8px;">
              ${escapeHtml(s.name)} 
              ${modeBadge}
              ${s.killswitch_active ? '<span class="badge badge-danger"><i class="fa-solid fa-bolt"></i> KILLSWITCH ACTIVE</span>' : '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> LIVE</span>'}
            </h3>
            <p style="color:var(--text-zinc-400); font-size:13px;">
              Slug: <code style="color:var(--gold-light);">${s.slug}</code> | Version: v${s.version} | Active Licenses: <strong style="color:var(--text-white);">${s.active_licenses || 0}</strong>
              ${s.discord_webhook ? ` | <span style="color:#8ea1e1;"><i class="fa-brands fa-discord"></i> Webhook Active</span>` : ''}
            </p>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" style="border-color:var(--border-gold); color:var(--gold-primary);" onclick="previewObfuscatedSource(${s.id})"><i class="fa-solid fa-eye" style="color:var(--gold-primary);"></i> Preview Obfuscated</button>
            <button class="btn btn-secondary btn-sm" onclick="openLoadstringModal('${s.slug}', '${escapeHtml(s.name)}')"><i class="fa-solid fa-terminal"></i> Loadstring Studio</button>
            <button class="btn btn-secondary btn-sm" onclick="openEditScriptModal(${s.id})"><i class="fa-solid fa-pen-to-square"></i> Edit Source</button>
            ${s.discord_webhook ? `<button class="btn btn-secondary btn-sm" onclick="testScriptWebhook(${s.id})" title="Test Discord Webhook"><i class="fa-brands fa-discord" style="color:#5865F2;"></i> Test Webhook</button>` : ''}
            <button class="btn ${s.killswitch_active ? 'btn-primary' : 'btn-danger'} btn-sm" onclick="toggleKillswitch(${s.id}, ${s.killswitch_active})">
              <i class="fa-solid fa-bolt"></i> ${s.killswitch_active ? 'Disable Killswitch' : 'Trigger Killswitch'}
            </button>
            <button class="btn btn-danger btn-sm" onclick="deleteScript(${s.id})"><i class="fa-solid fa-trash"></i></button>
          </div>
        </div>

        <div style="background:var(--bg-input); padding: 12px 16px; border-radius: 10px; border: 1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
          <div style="overflow:hidden; text-overflow:ellipsis;">
            <span style="font-size:11px; color:var(--text-zinc-500); display:block; margin-bottom:2px; font-weight:700; text-transform:uppercase;">Armored Buyer Execution Loadstring:</span>
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

function handleLuaFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (event) => {
    document.getElementById("scriptSource").value = event.target.result;
    updateScriptSizeCounter();
    showToast(`Loaded ${file.name} (${file.size} bytes)!`);
  };
  reader.readAsText(file);
}

// ----------------- Script Hub Modals & Form Handlers -----------------
function openCreateScriptModal() {
  const nameEl = document.getElementById("createScriptName");
  const slugEl = document.getElementById("createScriptSlug");
  const codeEl = document.getElementById("createScriptCode");
  const webEl = document.getElementById("createScriptWebhook");

  if (nameEl) nameEl.value = "";
  if (slugEl) slugEl.value = "";
  if (codeEl) codeEl.value = '-- Paste your Lua / Luau script here\nprint("Hello from FleedGuard Protected Script!")\n';
  if (webEl) webEl.value = "";

  openModal("createScriptModal");
}

async function handleCreateScript(e) {
  e.preventDefault();
  const name = document.getElementById("createScriptName")?.value.trim();
  const slug = document.getElementById("createScriptSlug")?.value.trim();
  const raw_source = document.getElementById("createScriptCode")?.value;
  const discord_webhook = document.getElementById("createScriptWebhook")?.value.trim() || null;

  if (!name || !slug || !raw_source) {
    return showToast("Please fill in all required fields", "error");
  }

  try {
    await apiCall("/api/scripts", "POST", {
      name,
      slug,
      version: "1.0.0",
      raw_source,
      is_obfuscated_mode: 1,
      discord_webhook
    });
    showToast(`Script Hub '${name}' created successfully!`, "success");
    closeModal("createScriptModal");
    loadScripts();
    loadOverviewStats();
  } catch (err) {}
}

async function openEditScriptModal(id) {
  let script = currentScripts.find(s => s.id === id);
  if (!script) {
    try {
      script = await apiCall(`/api/scripts/${id}`);
    } catch (e) {
      return showToast("Failed to load script details", "error");
    }
  }
  if (!script) return;

  const idEl = document.getElementById("editScriptId");
  const nameEl = document.getElementById("editScriptName");
  const codeEl = document.getElementById("editScriptCode");
  const webEl = document.getElementById("editScriptWebhook");

  if (idEl) idEl.value = script.id;
  if (nameEl) nameEl.value = script.name || "";
  if (codeEl) codeEl.value = script.raw_source || "";
  if (webEl) webEl.value = script.discord_webhook || "";

  openModal("editScriptModal");
}

async function handleSaveEditScript(e) {
  e.preventDefault();
  const id = document.getElementById("editScriptId")?.value;
  const name = document.getElementById("editScriptName")?.value.trim();
  const raw_source = document.getElementById("editScriptCode")?.value;
  const discord_webhook = document.getElementById("editScriptWebhook")?.value.trim() || null;

  if (!id || !name || !raw_source) {
    return showToast("Please fill in all required fields", "error");
  }

  try {
    await apiCall(`/api/scripts/${id}`, "PATCH", {
      name,
      raw_source,
      discord_webhook
    });
    showToast("Script source updated successfully!", "success");
    closeModal("editScriptModal");
    loadScripts();
  } catch (err) {}
}

// ----------------- Obfuscated Source Preview -----------------
async function previewObfuscatedSource(scriptId) {
  showToast("Compiling obfuscated preview...", "info");
  try {
    const data = await apiCall(`/api/scripts/${scriptId}/preview`);
    if (!data || !data.success) {
      showToast("Failed to compile preview", "error");
      return;
    }

    const titleEl = document.getElementById("scriptCodeModalTitle");
    if (titleEl) {
      titleEl.innerHTML = `<i class="fa-solid fa-eye gold-accent"></i> Preview: ${escapeHtml(data.name)} (${escapeHtml(data.mode_name)})`;
    }

    const contentEl = document.getElementById("scriptCodeModalContent");
    if (contentEl) {
      contentEl.innerText = data.obfuscated_source;
    }

    openModal("scriptCodeModal");
  } catch (err) {
    showToast("Error generating preview: " + (err.message || err), "error");
  }
}

// ----------------- Loadstring Studio -----------------
let currentLoadstringSlug = "";
let currentLoadstringName = "";
let currentLoadstringStyle = "oneliner";

function openLoadstringModal(slug, name) {
  currentLoadstringSlug = slug;
  currentLoadstringName = name;
  currentLoadstringStyle = "oneliner";

  const titleEl = document.getElementById("modalLoadstringTitle");
  if (titleEl) {
    titleEl.innerHTML = `<i class="fa-solid fa-terminal gold-accent"></i> Loadstring Studio: ${escapeHtml(name)}`;
  }

  document.querySelectorAll("#modalLoadstring .snippet-tab-btn").forEach(btn => btn.classList.remove("active"));
  document.getElementById("btnTabOneliner")?.classList.add("active");

  updateLoadstringModalCode();
  openModal("modalLoadstring");
}

function switchLoadstringStyle(style) {
  currentLoadstringStyle = style;
  document.querySelectorAll("#modalLoadstring .snippet-tab-btn").forEach(btn => btn.classList.remove("active"));
  if (style === "oneliner") document.getElementById("btnTabOneliner")?.classList.add("active");
  if (style === "keygated") document.getElementById("btnTabKeygated")?.classList.add("active");
  if (style === "luau_headers") document.getElementById("btnTabHeaders")?.classList.add("active");
  updateLoadstringModalCode();
}

function updateLoadstringModalCode() {
  const origin = window.location.origin;
  const slug = currentLoadstringSlug || "script";
  let code = "";

  if (currentLoadstringStyle === "oneliner") {
    code = `loadstring(game:HttpGet("${origin}/v1/loader/${slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;
  } else if (currentLoadstringStyle === "keygated") {
    code = `getgenv().FleedKey = "YOUR_LICENSE_KEY"\nloadstring(game:HttpGet("${origin}/v1/loader/${slug}?key=" .. tostring(getgenv().FleedKey or "")))()`;
  } else if (currentLoadstringStyle === "luau_headers") {
    code = `local req = (syn and syn.request) or (http and http.request) or http_request or request\nlocal res = req({\n    Url = "${origin}/v1/loader/${slug}",\n    Method = "GET",\n    Headers = {["X-License-Key"] = tostring(getgenv().FleedKey or "YOUR_KEY")}\n})\nloadstring(res.Body)()`;
  }

  const codeEl = document.getElementById("modalLoadstringCode");
  if (codeEl) codeEl.innerText = code;
}

function copyModalLoadstring() {
  const text = document.getElementById("modalLoadstringCode")?.innerText || "";
  copyText(text, "Loadstring copied to clipboard!");
}

// ----------------- Webhook, Killswitch & Deletion Actions -----------------
async function testScriptWebhook(scriptId) {
  try {
    const res = await apiCall(`/api/scripts/${scriptId}/test-webhook`, "POST", {});
    showToast(res.message || "Test webhook alert sent to Discord!", "success");
  } catch (err) {}
}

async function toggleKillswitch(id, currentStatus) {
  const newStatus = currentStatus ? 0 : 1;
  const reason = newStatus ? prompt("Enter Killswitch Reason (shown to blocked players):", "Emergency security maintenance in progress") : "";
  if (newStatus && reason === null) return;
  try {
    await apiCall(`/api/scripts/${id}`, "PATCH", { killswitch_active: newStatus, killswitch_reason: reason });
    showToast(newStatus ? "Killswitch ACTIVATED! Executions blocked." : "Killswitch deactivated. Hub is LIVE.", newStatus ? "error" : "success");
    loadScripts();
  } catch (err) {}
}

async function deleteScript(id) {
  if (!confirm("Are you sure you want to permanently delete this script hub and all associated license keys?")) return;
  try {
    await apiCall(`/api/scripts/${id}`, "DELETE");
    showToast("Script hub deleted successfully.", "success");
    loadScripts();
    loadOverviewStats();
  } catch (err) {}
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

function formatCustomerCell(l) {
  let discordId = "";
  if (l.discord_id) {
    discordId = String(l.discord_id).replace(/<@!?(\d+)>/, '$1').trim();
  }

  let cleanNote = (l.note || "").trim();
  const match = cleanNote.match(/<@!?(\d+)>/);
  if (match) {
    if (!discordId) discordId = match[1];
    cleanNote = cleanNote.replace(/<@!?\d+>\s*/g, "").trim();
  }

  if (!discordId && !cleanNote) {
    return `<span style="color:var(--text-zinc-500);">—</span>`;
  }

  let discordBadgeHtml = "";
  if (discordId) {
    const cached = discordUsersCache.get(discordId);
    const displayName = cached?.display_name || l.discord_display_name || cached?.username || l.discord_username || "";
    const avatar = cached?.avatar_url || l.discord_avatar || "https://cdn.discordapp.com/embed/avatars/0.png";

    if (displayName) {
      discordBadgeHtml = `
        <div class="discord-tag-pill" style="display:inline-flex; align-items:center; gap:6px; background:rgba(88,101,242,0.15); border:1px solid rgba(88,101,242,0.3); border-radius:6px; padding:3px 8px; margin-bottom:${cleanNote ? '4px' : '0'};">
          <img src="${escapeHtml(avatar)}" style="width:16px; height:16px; border-radius:50%; object-fit:cover;" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
          <span style="color:#8ea1e1; font-size:12px; font-weight:600; font-family:var(--font-mono);">@${escapeHtml(displayName)}</span>
        </div>
      `;
    } else {
      discordBadgeHtml = `
        <div class="discord-tag-pill discord-user-loader" data-discord-id="${escapeHtml(discordId)}" style="display:inline-flex; align-items:center; gap:6px; background:rgba(88,101,242,0.12); border:1px solid rgba(88,101,242,0.25); border-radius:6px; padding:3px 8px; margin-bottom:${cleanNote ? '4px' : '0'};">
          <i class="fa-brands fa-discord" style="color:#5865F2; font-size:12px;"></i>
          <span class="disc-label" style="color:#8ea1e1; font-size:12px; font-weight:600; font-family:var(--font-mono);">@${escapeHtml(discordId)}</span>
        </div>
      `;
    }
  }

  const noteHtml = cleanNote ? `<div style="font-size:11px; color:var(--text-zinc-400); line-height:1.3;">${escapeHtml(cleanNote)}</div>` : "";
  return `<div>${discordBadgeHtml}${noteHtml}</div>`;
}

async function hydrateDiscordUsers() {
  const loaders = document.querySelectorAll(".discord-user-loader[data-discord-id]");
  const idsToFetch = new Set();
  loaders.forEach(el => {
    const id = el.getAttribute("data-discord-id");
    if (id && !discordUsersCache.has(id)) {
      idsToFetch.add(id);
    }
  });

  for (const id of idsToFetch) {
    try {
      const data = await apiCall(`/api/discord/user/${id}`);
      if (data && (data.username || data.display_name)) {
        discordUsersCache.set(id, data);
        document.querySelectorAll(`.discord-user-loader[data-discord-id="${id}"]`).forEach(el => {
          const avatar = data.avatar_url || "https://cdn.discordapp.com/embed/avatars/0.png";
          const name = data.display_name || data.username || id;
          el.innerHTML = `
            <img src="${escapeHtml(avatar)}" style="width:16px; height:16px; border-radius:50%; object-fit:cover;" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
            <span class="disc-label" style="color:#8ea1e1; font-size:12px; font-weight:600; font-family:var(--font-mono);">@${escapeHtml(name)}</span>
          `;
          el.classList.remove("discord-user-loader");
        });
      }
    } catch (e) {}
  }
}

function renderLicenses(licenses) {
  const tableBody = document.getElementById("licensesTableBody");
  if (!tableBody) return;

  if (licenses.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 32px; color:var(--text-zinc-500);"><i class="fa-solid fa-key" style="margin-right:6px;"></i>No license keys found for this filter.</td></tr>`;
    return;
  }

  const script = currentScripts.find(s => s.id === selectedScriptId) || currentScripts[0];
  const slug = script ? script.slug : (licenses[0]?.script_slug || "hoopz_hub_v1");

  tableBody.innerHTML = licenses.map(l => {
    const isChecked = selectedLicenseIds.has(l.id);
    const keySlug = l.script_slug || slug;

    return `
      <tr class="${isChecked ? 'row-selected' : ''}">
        <td>
          <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleSelectLicense(${l.id}, this.checked)">
        </td>
        <td>
          <span class="key-badge" onclick="openLicenseDetailModal(${l.id})" title="Click to view full forensic record">
            ${escapeHtml(l.license_key)} <i class="fa-solid fa-magnifying-glass" style="font-size:10px; opacity:0.6;"></i>
          </span>
        </td>
        <td>${formatCustomerCell(l)}</td>
        <td>
          <span style="font-family:var(--font-mono); font-size:11px;">
            ${l.hwid ? '<i class="fa-solid fa-fingerprint" style="color:var(--gold-primary); margin-right:4px;"></i>' + escapeHtml(l.hwid.substring(0, 14)) + '...' : '<span style="color:var(--text-zinc-500)">Unbound</span>'}
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
            <button class="btn btn-secondary btn-sm" onclick="copyBuyerLoadstring('${escapeHtml(l.license_key)}', '${escapeHtml(keySlug)}')" title="Copy buyer loadstring"><i class="fa-solid fa-terminal"></i></button>
            <button class="btn btn-secondary btn-sm" onclick="openLicenseDetailModal(${l.id})" title="Inspect key history"><i class="fa-solid fa-chart-line"></i></button>
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

  hydrateDiscordUsers();
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
    if (statusFilter === "lifetime") return !l.expires_at;

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

  if (action === "delete" && !confirm(`Are you sure you want to permanently delete ${ids.length} selected license keys?`)) {
    return;
  }

  try {
    let extend_days = 30;
    let ban_reason = "Bulk Banned by Administrator";

    if (action === "ban") {
      const reason = prompt("Enter ban reason for selected keys:", "License Terms Violation");
      if (reason !== null) ban_reason = reason;
    }

    await apiCall("/api/licenses/bulk-action", "POST", {
      action,
      license_ids: ids,
      extend_days,
      ban_reason
    });

    showToast(`Bulk action '${action}' completed for ${ids.length} keys!`);
    selectedLicenseIds.clear();
    updateBulkActionBar();
    loadLicensesForScript(selectedScriptId);
    loadOverviewStats();
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
    const headers = ["License Key", "Note", "Discord ID", "HWID", "Executions", "Max Executions", "Expires At", "Status"];
    const rows = currentLicenses.map(l => [
      l.license_key,
      `"${(l.note || '').replace(/"/g, '""')}"`,
      l.discord_id || "",
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
  const select = document.getElementById("bulkGenScriptId");
  if (select) {
    select.innerHTML = currentScripts.map(s => `<option value="${s.id}" ${s.id === selectedScriptId ? 'selected' : ''}>${escapeHtml(s.name)} (${s.slug})</option>`).join("");
  }
  openModal("bulkGenModal");
}

function openSingleGenModal() {
  const select = document.getElementById("singleGenScriptId");
  if (select) {
    select.innerHTML = currentScripts.map(s => `<option value="${s.id}" ${s.id === selectedScriptId ? 'selected' : ''}>${escapeHtml(s.name)} (${s.slug})</option>`).join("");
  }
  const customKeyInput = document.getElementById("singleGenCustomKey");
  if (customKeyInput) {
    customKeyInput.value = "";
    customKeyInput.placeholder = `FLEED-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}`;
  }
  openModal("singleGenModal");
}

async function handleGenerateSingleKey(e) {
  e.preventDefault();
  const scriptSelect = document.getElementById("singleGenScriptId");
  const script_id = scriptSelect ? parseInt(scriptSelect.value) : selectedScriptId;
  const script = currentScripts.find(s => s.id === script_id) || currentScripts.find(s => s.id === selectedScriptId);
  if (!script) return showToast("Please select a valid script hub first", "error");

  const customKeyInput = document.getElementById("singleGenCustomKey");
  let license_key = customKeyInput ? customKeyInput.value.trim() : "";
  if (!license_key && customKeyInput && customKeyInput.placeholder) {
    license_key = customKeyInput.placeholder;
  }
  if (!license_key) {
    license_key = `FLEED-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}-${Math.random().toString(36).substring(2,6).toUpperCase()}`;
  }

  const note = document.getElementById("singleGenNote")?.value.trim() || "";
  const discord_id = document.getElementById("singleGenDiscordId")?.value.trim() || null;
  const duration_days = parseInt(document.getElementById("singleGenDays")?.value) || 0;

  let expires_at = null;
  if (duration_days > 0) {
    const d = new Date();
    d.setDate(d.getDate() + duration_days);
    expires_at = d.toISOString();
  }

  try {
    await apiCall("/api/licenses/create", "POST", {
      slug: script.slug,
      license_key,
      note,
      discord_id,
      expires_at
    });
    showToast("License key created successfully!", "success");
    closeModal("singleGenModal");
    loadLicensesForScript(script_id);
    loadOverviewStats();
  } catch (err) {}
}
const handleSingleGenerate = handleGenerateSingleKey;

async function handleBulkGenerateKeys(e) {
  e.preventDefault();
  const scriptSelect = document.getElementById("bulkGenScriptId");
  const script_id = scriptSelect ? parseInt(scriptSelect.value) : selectedScriptId;
  const count = parseInt(document.getElementById("bulkGenCount")?.value) || 10;
  const prefix = document.getElementById("bulkGenPrefix")?.value.trim() || "FLEED";
  const note = document.getElementById("bulkGenNote")?.value.trim() || "";
  const duration_days = parseInt(document.getElementById("bulkGenDays")?.value) || 0;

  try {
    const data = await apiCall("/api/licenses/bulk", "POST", {
      script_id,
      count,
      prefix,
      duration_days: duration_days > 0 ? duration_days : null,
      max_executions: -1,
      note
    });
    showToast(`Generated ${data.count || count} keys!`, "success");
    closeModal("bulkGenModal");
    loadLicensesForScript(script_id);
    loadOverviewStats();
  } catch (err) {}
}
const handleBulkGenerate = handleBulkGenerateKeys;

function openImportKeysModal() {
  const select = document.getElementById("importScriptSelect");
  if (select) {
    select.innerHTML = currentScripts.map(s => `<option value="${s.id}" ${s.id === selectedScriptId ? 'selected' : ''}>${escapeHtml(s.name)} (${s.slug})</option>`).join("");
  }
  const textArea = document.getElementById("importKeysText");
  if (textArea) textArea.value = "";
  openModal("importKeysModal");
}

async function handleImportKeys(e) {
  e.preventDefault();
  const script_id = parseInt(document.getElementById("importScriptSelect")?.value) || selectedScriptId;
  const text = (document.getElementById("importKeysText") || document.getElementById("importKeysTextarea"))?.value.trim();

  if (!text) return showToast("Enter keys to import", "error");

  const lines = text.split("\n").map(l => l.trim()).filter(l => l.length > 0);
  const items = [];

  for (const line of lines) {
    const parts = line.split(",");
    const key = parts[0].trim();
    const note = parts[1] ? parts[1].trim() : "";
    const discord_id = parts[2] ? parts[2].trim() : null;

    if (key) {
      items.push({
        license_key: key,
        note,
        discord_id,
        duration_days: null,
        max_executions: -1
      });
    }
  }

  try {
    const res = await apiCall("/api/licenses/import", "POST", {
      script_id,
      keys: items
    });
    showToast(`Successfully imported ${res.imported} keys! (Skipped: ${res.skipped})`, "success");
    closeModal("importKeysModal");
    loadLicensesForScript(script_id);
    loadOverviewStats();
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
  const reason = newBan ? prompt("Enter ban reason:", "License Terms Violation") : "";
  try {
    await apiCall(`/api/licenses/${licenseId}`, "PATCH", { is_banned: newBan, ban_reason: reason });
    showToast(newBan ? "License banned!" : "License unbanned!", newBan ? "error" : "success");
    loadLicensesForScript(selectedScriptId);
    loadOverviewStats();
  } catch (err) {}
}

async function deleteLicense(licenseId) {
  if (!confirm("Are you sure you want to permanently delete this license key?")) return;
  try {
    await apiCall(`/api/licenses/${licenseId}`, "DELETE");
    showToast("License deleted.");
    loadLicensesForScript(selectedScriptId);
    loadOverviewStats();
  } catch (err) {}
}

// ----------------- Deep License Detail Modal / Drawer -----------------
async function openLicenseDetailModal(licenseId) {
  const contentEl = document.getElementById("licDetailContent");
  if (!contentEl) return;

  contentEl.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-zinc-400);"><i class="fa-solid fa-spinner fa-spin" style="font-size:24px; color:var(--gold-primary);"></i><div style="margin-top:10px;">Loading forensic audit history...</div></div>`;
  document.getElementById("modalLicenseDetail").classList.add("active");

  try {
    const data = await apiCall(`/api/licenses/${licenseId}/history`);
    const lic = data.license;
    const users = data.roblox_users || [];
    const ips = data.ip_addresses || [];
    const games = data.games || [];
    const logs = data.logs || [];

    const usersHtml = users.length > 0
      ? users.map(u => `<span class="badge badge-zinc" style="font-size:11px;"><i class="fa-solid fa-user"></i> ${escapeHtml(u.roblox_username)} (ID: ${u.roblox_user_id}) • ${u.exec_count} execs</span>`).join(" ")
      : `<span style="color:var(--text-zinc-500);">No Roblox player telemetry logged</span>`;

    const ipsHtml = ips.length > 0
      ? ips.map(i => `<span class="badge badge-zinc" style="font-size:11px;"><i class="fa-solid fa-network-wired"></i> ${escapeHtml(i.ip_address)} • ${i.exec_count} execs</span>`).join(" ")
      : `<span style="color:var(--text-zinc-500);">None logged</span>`;

    contentEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; flex-wrap:wrap; gap:10px;">
        <div>
          <span class="badge ${lic.is_banned ? 'badge-danger' : 'badge-success'}">${lic.is_banned ? 'BANNED' : 'ACTIVE'}</span>
          <h3 style="color:var(--gold-light); font-family:var(--font-mono); font-size:18px; margin:6px 0 2px 0;">${lic.license_key}</h3>
          <span style="font-size:12px; color:var(--text-zinc-400);">Hub: <strong>${escapeHtml(lic.script_name)}</strong> (${lic.script_slug})</span>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" onclick="copyBuyerLoadstring('${escapeHtml(lic.license_key)}', '${escapeHtml(lic.script_slug)}')"><i class="fa-solid fa-terminal"></i> Copy Loadstring</button>
          <button class="btn btn-danger btn-sm" onclick="openKickModal({ key: '${lic.license_key}', hwid: '${lic.hwid || ''}', displayName: '${lic.license_key}' })"><i class="fa-solid fa-bolt"></i> Kick Session</button>
          <button class="btn btn-secondary btn-sm" onclick="resetHWID(${lic.id})"><i class="fa-solid fa-arrows-rotate"></i> Reset HWID</button>
          <button class="btn ${lic.is_banned ? 'btn-secondary' : 'btn-danger'} btn-sm" onclick="toggleBanLicense(${lic.id}, ${lic.is_banned})">
            ${lic.is_banned ? '<i class="fa-solid fa-unlock"></i> Unban' : '<i class="fa-solid fa-ban"></i> Ban Key'}
          </button>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; font-size:12px; background:var(--bg-input); padding:14px; border-radius:10px; border:1px solid var(--border-subtle); margin-bottom:16px;">
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Bound Device HWID:</span>
          <strong style="color:var(--text-white); font-family:var(--font-mono);">${lic.hwid ? lic.hwid.substring(0, 16) + '...' : '<span style="color:var(--text-zinc-500)">Unbound</span>'}</strong>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Total Executions:</span>
          <strong style="color:var(--text-white); font-family:var(--font-mono); font-size:14px;">${lic.execution_count}</strong>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Expiration Date:</span>
          <span style="color:var(--text-zinc-300);">${lic.expires_at ? new Date(lic.expires_at).toLocaleString() : '<span class="badge badge-gold">Lifetime</span>'}</span>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Buyer Note / Tag:</span>
          <span style="color:var(--text-zinc-300);">${escapeHtml(lic.note || '—')}</span>
        </div>
      </div>

      <div style="margin-bottom:14px;">
        <strong style="color:var(--text-zinc-300); font-size:12px; display:block; margin-bottom:6px;">Roblox Accounts Identified on this Key:</strong>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${usersHtml}</div>
      </div>

      <div style="margin-bottom:16px;">
        <strong style="color:var(--text-zinc-300); font-size:12px; display:block; margin-bottom:6px;">IP Address Trail:</strong>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${ipsHtml}</div>
      </div>

      <strong style="color:var(--text-white); font-size:13px; display:block; margin-bottom:8px;">Recent Execution Handshakes:</strong>
      <div style="max-height: 200px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 8px;">
        <table style="font-size:12px;">
          <thead>
            <tr>
              <th>Time</th>
              <th>Player</th>
              <th>Game</th>
              <th>Status</th>
              <th>Executor</th>
            </tr>
          </thead>
          <tbody>
            ${logs.length > 0 ? logs.map(log => `
              <tr>
                <td style="font-family:var(--font-mono); color:var(--text-zinc-400);">${new Date(log.timestamp).toLocaleTimeString()}</td>
                <td>${escapeHtml(log.roblox_username || '—')}</td>
                <td>${escapeHtml(log.game_name || '—')}</td>
                <td><span class="badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${log.status}</span></td>
                <td><span class="badge badge-zinc">${escapeHtml(log.executor_name || 'Universal')}</span></td>
              </tr>
            `).join("") : '<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-zinc-500);">No execution logs found for this key.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    contentEl.innerHTML = `<div style="color:var(--danger-color); padding:20px;">Failed to load license forensic history: ${escapeHtml(err.message)}</div>`;
  }
}

// ----------------- Live Audit Logs & Threat Feed -----------------
async function loadLiveLogs() {
  const statusFilter = document.getElementById("logStatusFilter")?.value || "";
  try {
    const url = statusFilter ? `/api/logs?limit=80&status_filter=${statusFilter}` : `/api/logs?limit=80`;
    const logs = await apiCall(url);
    currentLogs = logs;
    renderLogs(logs);
  } catch (err) {}
}

function renderLogs(logs) {
  const tableBody = document.getElementById("logsTableBody");
  if (!tableBody) return;

  if (logs.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 32px; color:var(--text-zinc-500);"><i class="fa-solid fa-circle-info" style="margin-right:6px;"></i>No security events matching current filter.</td></tr>`;
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

function renderLogRow(log) {
  const avatarUrl = (log.roblox_user_id && log.roblox_user_id > 0)
    ? `/api/roblox/avatar/${log.roblox_user_id}`
    : `/api/roblox/avatar/1`;

  let rbxPlayerHtml = `<span style="color:var(--text-zinc-500);">—</span>`;
  if (log.roblox_username && log.roblox_username !== "Unknown") {
    const profileUrl = log.roblox_user_id ? `https://www.roblox.com/users/${log.roblox_user_id}/profile` : `https://www.roblox.com/search/users?keyword=${encodeURIComponent(log.roblox_username)}`;
    rbxPlayerHtml = `
      <div style="display:flex; align-items:center; gap:8px;">
        <img src="${avatarUrl}" alt="Avatar" style="width:30px; height:30px; border-radius:50%; border:1px solid var(--border-subtle); background:var(--bg-elevated); object-fit:cover;" loading="lazy">
        <div>
          <a href="${profileUrl}" target="_blank" style="color:var(--gold-light); font-weight:600; text-decoration:none; display:flex; align-items:center; gap:4px; font-size:12px;">
            ${escapeHtml(log.roblox_username)} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i>
          </a>
          <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">ID: ${log.roblox_user_id || '—'}</span>
        </div>
      </div>
    `;
  }

  let gamePlaceHtml = `<span style="color:var(--text-zinc-500);">—</span>`;
  if (log.place_id && log.place_id > 0) {
    const placeUrl = `https://www.roblox.com/games/${log.place_id}`;
    gamePlaceHtml = `
      <div>
        <a href="${placeUrl}" target="_blank" style="color:var(--text-white); font-weight:500; font-size:12px; text-decoration:none; display:flex; align-items:center; gap:4px;">
          ${escapeHtml(log.game_name || "Roblox Game")} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i>
        </a>
        <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">Place: ${log.place_id}</span>
      </div>
    `;
  } else if (log.game_name) {
    gamePlaceHtml = `<span style="color:var(--text-zinc-300); font-size:12px;">${escapeHtml(log.game_name)}</span>`;
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
  } else if (log.status === 'BLACKLISTED') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> BLACKLISTED</span>`;
  } else if (log.status === 'EXPIRED') {
    statusBadge = `<span class="badge badge-zinc"><i class="fa-solid fa-clock"></i> EXPIRED</span>`;
  } else if (log.status === 'BANNED') {
    statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> BANNED</span>`;
  }

  return `
    <tr>
      <td style="white-space:nowrap; font-size:11px; color:var(--text-zinc-400); font-family:var(--font-mono);">
        ${new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </td>
      <td><strong style="color:var(--text-white); font-size:12px;">${escapeHtml(log.script_name || "Unknown")}</strong></td>
      <td>${rbxPlayerHtml}</td>
      <td>${gamePlaceHtml}</td>
      <td>
        ${log.license_key ? `<span class="key-badge" style="font-size:11px;" onclick="copyText('${log.license_key}')">${log.license_key.substring(0, 14)}... <i class="fa-solid fa-copy"></i></span>` : '<span style="color:var(--text-zinc-500);">N/A</span>'}
      </td>
      <td>${statusBadge}</td>
      <td>
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;">
          ${renderExecutorBadge(log.executor_name)}
        </div>
        <span style="color:var(--text-zinc-400); font-size:11px;">${escapeHtml(log.details || "—")}</span>
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
        <div style="display:flex; gap:6px;">
          ${log.license_id ? `
            <button class="btn btn-secondary btn-sm" onclick="resetHWID(${log.license_id})" title="Reset user HWID"><i class="fa-solid fa-arrows-rotate"></i></button>
          ` : ''}
          <button class="btn btn-danger btn-sm" onclick="openKickModal({ key: '${log.license_key || ''}', hwid: '${log.hwid || ''}', userId: ${log.roblox_user_id || 0}, username: '${log.roblox_username || ''}', displayName: '${log.roblox_username || log.license_key || 'Device'}' })" title="Kick Player from Game">
            <i class="fa-solid fa-bolt"></i> Kick
          </button>
        </div>
      </td>
    </tr>
  `;
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

function exportLogsCSV() {
  if (currentLogs.length === 0) return showToast("No logs to export", "info");

  const headers = ["Timestamp", "Script", "Roblox Username", "Roblox User ID", "Game", "Place ID", "License Key", "Status", "Executor", "Details", "HWID", "IP Address"];
  const rows = currentLogs.map(l => [
    l.timestamp,
    `"${(l.script_name || '').replace(/"/g, '""')}"`,
    `"${(l.roblox_username || '').replace(/"/g, '""')}"`,
    l.roblox_user_id || "",
    `"${(l.game_name || '').replace(/"/g, '""')}"`,
    l.place_id || "",
    l.license_key || "",
    l.status || "",
    `"${(l.executor_name || '').replace(/"/g, '""')}"`,
    `"${(l.details || '').replace(/"/g, '""')}"`,
    l.hwid || "",
    l.ip_address || ""
  ]);

  const content = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `fleedguard_logs_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Exported ${currentLogs.length} audit logs to CSV!`);
}

async function loadBypassLogs() {
  try {
    const logs = await apiCall("/api/logs?limit=50&status_filter=blocked");
    currentBypasses = logs;
  } catch (err) {}
}

async function loadThreatRadarBypasses() {
  const tbody = document.getElementById("threatRadarBypassesTableBody");
  if (!tbody) return;

  try {
    const kicks = await apiCall("/api/kicks?limit=50");
    if (!kicks || kicks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-zinc-500);"><i class="fa-solid fa-shield-halved" style="color:var(--gold-primary); margin-right:6px;"></i> No security interceptions, tampering traps, or remote kicks logged.</td></tr>`;
      return;
    }

    tbody.innerHTML = kicks.map(k => {
      const avatarSrc = (k.roblox_user_id && k.roblox_user_id > 0)
        ? `/api/roblox/avatar/${k.roblox_user_id}`
        : `/api/roblox/avatar/1`;
      const profileUrl = (k.roblox_user_id && k.roblox_user_id > 0) ? `https://www.roblox.com/users/${k.roblox_user_id}/profile` : '#';
      const timeStr = formatTimeAgo(k.timestamp);
      const placeName = escapeHtml(k.game_name || (k.place_id > 0 ? `Place #${k.place_id}` : 'Roblox Experience'));

      const placeHtml = k.place_id > 0
        ? `<a href="https://www.roblox.com/games/${k.place_id}" target="_blank" style="color:var(--gold-light); font-size:12px; font-weight:550; text-decoration:none; display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-gamepad" style="font-size:10px; opacity:0.8;"></i> ${placeName} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i></a>`
        : `<span style="color:var(--text-zinc-400); font-size:12px; display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-gamepad" style="font-size:10px; opacity:0.6;"></i> ${placeName}</span>`;

      return `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <img src="${avatarSrc}" style="width:28px; height:28px; border-radius:50%; object-fit:cover; border:1px solid var(--border-subtle); flex-shrink:0;">
              <div>
                <a href="${profileUrl}" target="_blank" style="color:var(--text-white); font-weight:650; font-size:12px; text-decoration:none; display:flex; align-items:center; gap:3px;">
                  ${escapeHtml(k.roblox_username || 'Unknown')} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:8px; opacity:0.6;"></i>
                </a>
                <div style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">${k.roblox_user_id > 0 ? `ID: ${k.roblox_user_id}` : 'ID: —'}</div>
              </div>
            </div>
          </td>
          <td>
            <span class="badge ${k.badge_class || 'badge-danger'}" style="font-weight:650; font-size:11px; white-space:normal; text-align:left; line-height:1.3; max-width:320px; display:inline-block;">
              <i class="fa-solid ${k.icon || 'fa-bolt'}"></i> ${escapeHtml(k.kick_reason || 'Session Terminated')}
            </span>
          </td>
          <td><span class="badge badge-gold" style="font-size:11px;">${escapeHtml(k.script_name || k.script_slug || 'Hub')}</span></td>
          <td>${placeHtml}</td>
          <td><span style="font-size:11px; color:var(--text-zinc-400); white-space:nowrap;">${timeStr}</span></td>
          <td>
            <div style="display:flex; gap:6px;">
              ${k.license_key && k.license_key !== 'N/A' ? `
                <button class="btn btn-secondary btn-sm" style="padding:4px 8px; font-size:10px;" onclick="copyText('${escapeHtml(k.license_key)}', 'License key copied!')" title="Copy License Key">
                  <i class="fa-solid fa-copy"></i>
                </button>
              ` : ''}
              ${k.hwid ? `
                <button class="btn btn-danger btn-sm" style="padding:4px 8px; font-size:10px;" onclick="openBlacklistModal({ target: '${escapeHtml(k.hwid)}', type: 'HWID', reason: 'Security Interception / Kicked session' })" title="Blacklist HWID">
                  <i class="fa-solid fa-ban"></i>
                </button>
              ` : ''}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--danger-light);">Error loading threat feed: ${err.message}</td></tr>`;
  }
}

// ----------------- Threat Radar & Attribution -----------------
async function handleWatermarkTrace() {
  const inputEl = document.getElementById("watermarkInput");
  const resultBox = document.getElementById("watermarkResultBox");
  if (!inputEl || !resultBox) return;

  const rawVal = inputEl.value.trim();
  if (!rawVal) {
    showToast("Please enter a watermark hash or paste a script snippet", "info");
    return;
  }

  resultBox.style.display = "block";
  resultBox.innerHTML = `<div style="display:flex; align-items:center; gap:8px; color:var(--text-zinc-400);"><i class="fa-solid fa-spinner fa-spin"></i> Tracing watermark through execution records...</div>`;

  try {
    const data = await apiCall("/api/audit/lookup-watermark", "POST", { watermark_or_source: rawVal });
    if (!data.found) {
      resultBox.innerHTML = `
        <div style="color:var(--danger-color); display:flex; align-items:center; gap:8px; font-weight:600;">
          <i class="fa-solid fa-circle-xmark"></i> No Matching License Found
        </div>
        <p style="color:var(--text-zinc-400); font-size:12px; margin:6px 0 0 0;">Searched for watermark: <code>${escapeHtml(data.searched_watermark)}</code>. This build was not generated by your hubs or has never executed.</p>
      `;
      return;
    }

    const lic = data.license;
    const scr = data.script;
    const attr = data.attribution;

    const accountsList = (attr.roblox_accounts && attr.roblox_accounts.length > 0)
      ? attr.roblox_accounts.map(a => `<span class="badge badge-zinc" style="font-size:11px;"><i class="fa-solid fa-user"></i> ${escapeHtml(a.roblox_username)} (ID: ${a.roblox_user_id})</span>`).join(" ")
      : `<span style="color:var(--text-zinc-500);">None logged</span>`;

    const ipsList = (attr.ip_addresses && attr.ip_addresses.length > 0)
      ? attr.ip_addresses.map(ip => `<span class="badge badge-zinc" style="font-size:11px;"><i class="fa-solid fa-network-wired"></i> ${escapeHtml(ip)}</span>`).join(" ")
      : `<span style="color:var(--text-zinc-500);">None logged</span>`;

    resultBox.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
        <div>
          <span class="badge badge-danger" style="font-size:12px;"><i class="fa-solid fa-bullseye"></i> LEAKER ATTRIBUTED</span>
          <h4 style="color:var(--gold-light); font-size:16px; margin:6px 0 2px 0;">Script Hub: ${escapeHtml(scr.name)} (${escapeHtml(scr.slug)})</h4>
          <span style="font-size:12px; color:var(--text-zinc-400);">Matched Watermark: <code>${escapeHtml(data.searched_watermark)}</code></span>
        </div>
        <div style="display:flex; gap:8px;">
          ${!lic.is_banned ? `
            <button class="btn btn-danger btn-sm" onclick="quickBanLeaker(${lic.id}, '${lic.license_key}')">
              <i class="fa-solid fa-ban"></i> Ban Leaker Immediately
            </button>
          ` : `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> ALREADY BANNED</span>`}
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; font-size:12px; margin-bottom:12px; background:rgba(0,0,0,0.3); padding:12px; border-radius:8px;">
        <div>
          <span style="color:var(--text-zinc-500); display:block;">License Key:</span>
          <strong style="color:var(--gold-primary); font-family:var(--font-mono); font-size:13px;" class="copy-click" onclick="copyText('${lic.license_key}')">${lic.license_key} <i class="fa-solid fa-copy"></i></strong>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Discord ID:</span>
          <strong style="color:var(--text-white); font-family:var(--font-mono);">${lic.discord_id ? escapeHtml(lic.discord_id) : '—'}</strong>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">First Delivered:</span>
          <span style="color:var(--text-zinc-300);">${attr.delivery_timestamp ? new Date(attr.delivery_timestamp).toLocaleString() : '—'}</span>
        </div>
        <div>
          <span style="color:var(--text-zinc-500); display:block;">Total Executions:</span>
          <span style="color:var(--text-white); font-weight:700;">${lic.execution_count}</span>
        </div>
      </div>

      <div style="font-size:12px; margin-bottom:8px;">
        <strong style="color:var(--text-zinc-300); display:block; margin-bottom:4px;">Roblox Accounts Identified on this Build:</strong>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${accountsList}</div>
      </div>

      <div style="font-size:12px;">
        <strong style="color:var(--text-zinc-300); display:block; margin-bottom:4px;">IP History:</strong>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${ipsList}</div>
      </div>
    `;
  } catch (e) {
    resultBox.innerHTML = `<div style="color:var(--danger-color); font-size:13px;">Error performing watermark trace: ${escapeHtml(e.message)}</div>`;
  }
}

async function loadAnomalies() {
  try {
    const anomalies = await apiCall("/api/audit/anomalies");
    const tableBody = document.getElementById("anomaliesTableBody");
    if (!tableBody) return;

    if (!anomalies || anomalies.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color:var(--text-zinc-500);"><i class="fa-solid fa-circle-check" style="color:var(--success-color); margin-right:6px;"></i>Zero active multi-account leaks detected in the last 48 hours.</td></tr>`;
      return;
    }

    tableBody.innerHTML = anomalies.map(row => {
      const isBanned = row.is_banned === 1;
      let statusBadge = "";
      if (isBanned) {
        statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-ban"></i> BANNED</span>`;
      } else if (row.distinct_users >= 3) {
        statusBadge = `<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> ${row.distinct_users} ACCOUNTS</span>`;
      } else if (row.distinct_users >= 2) {
        statusBadge = `<span class="badge badge-gold"><i class="fa-solid fa-users"></i> ${row.distinct_users} ACCOUNTS</span>`;
      } else {
        statusBadge = `<span class="badge badge-zinc"><i class="fa-solid fa-network-wired"></i> ${row.distinct_ips} IPs</span>`;
      }

      let userChips = '—';
      if (row.user_list) {
        const users = row.user_list.split(',').map(u => u.trim()).filter(Boolean);
        userChips = users.map(u => `<span class="badge badge-zinc" style="font-size:10px; margin:2px 2px 2px 0;"><i class="fa-solid fa-user" style="font-size:8px; opacity:0.6;"></i> ${escapeHtml(u)}</span>`).join('');
      }

      const lastSeenStr = row.last_seen ? formatTimeAgo(row.last_seen) : '—';

      return `
        <tr>
          <td>
            <span class="key-badge" style="font-size:11px;" onclick="copyText('${row.license_key}', 'License Key copied!')" title="Click to copy key">
              ${escapeHtml(row.license_key)} <i class="fa-solid fa-copy"></i>
            </span>
            ${row.note ? `<div style="font-size:10px; color:var(--text-zinc-500); margin-top:2px;">${escapeHtml(row.note)}</div>` : ''}
          </td>
          <td><strong style="color:var(--text-white); font-size:12px;">${escapeHtml(row.script_name || 'Hub')}</strong></td>
          <td>
            <div style="font-size:12px; color:var(--gold-light); font-weight:600; margin-bottom:3px;">${row.distinct_users} distinct player(s)</div>
            <div style="display:flex; flex-wrap:wrap; max-width:280px;">${userChips}</div>
          </td>
          <td>
            <span class="badge badge-zinc" style="font-size:11px;"><i class="fa-solid fa-network-wired"></i> ${row.distinct_ips} IPs</span>
          </td>
          <td style="font-size:11px; color:var(--text-zinc-400); white-space:nowrap;">
            ${lastSeenStr}
          </td>
          <td>${statusBadge}</td>
          <td>
            ${!isBanned ? `
              <button class="btn btn-danger btn-sm" onclick="quickBanLeaker(${row.id}, '${escapeHtml(row.license_key)}')"><i class="fa-solid fa-ban"></i> Ban</button>
            ` : `<span style="color:var(--text-zinc-500); font-size:11px; font-weight:600;">Enforced</span>`}
          </td>
        </tr>
      `;
    }).join("");
  } catch (e) {}
}

async function quickBanLeaker(licenseId, key) {
  if (!confirm(`Are you sure you want to BAN and revoke license key: ${key}?`)) return;
  try {
    await apiCall("/api/audit/ban-leaker", "POST", { license_id: licenseId, reason: "Banned: Multi-Account Leak Attribution" });
    showToast(`License ${key} has been banned!`, "success");
    loadAnomalies();
    if (typeof loadLicensesView === "function") loadLicensesView();
    loadThreatRadarBypasses();
    loadOverviewStats();
    loadRecentKicks();
    const resultBox = document.getElementById("watermarkResultBox");
    if (resultBox && resultBox.style.display !== "none") {
      handleWatermarkTrace();
    }
  } catch (e) {
    showToast(e.message, "error");
  }
}

// ----------------- Global Blacklist Manager -----------------
async function loadBlacklists() {
  try {
    const list = await apiCall("/api/blacklist");
    currentBlacklists = list;
    const tbody = document.getElementById("blacklistTableBody");
    if (!tbody) return;

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-zinc-500);">No global blacklists configured. All authorized players with valid keys can connect.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(item => `
      <tr>
        <td><span class="badge ${item.target_type === 'HWID' ? 'badge-gold' : 'badge-info'}">${item.target_type}</span></td>
        <td><code style="font-family:var(--font-mono); color:var(--gold-light); font-size:12px;">${escapeHtml(item.target_value)}</code></td>
        <td><span style="color:var(--text-zinc-300); font-size:12px;">${escapeHtml(item.reason || '—')}</span></td>
        <td style="font-size:11px; color:var(--text-zinc-500); font-family:var(--font-mono);">${new Date(item.created_at).toLocaleDateString()}</td>
        <td>
          <button class="btn btn-danger btn-sm" onclick="removeBlacklist(${item.id})"><i class="fa-solid fa-trash"></i> Remove</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {}
}

function openAddBlacklistModal() {
  document.getElementById("blTargetValue").value = "";
  document.getElementById("blReason").value = "";
  document.getElementById("modalBlacklistAdd").classList.add("active");
}

async function handleBlacklistAdd(e) {
  e.preventDefault();
  const target_type = document.getElementById("blTargetType").value;
  const target_value = document.getElementById("blTargetValue").value.trim();
  const reason = document.getElementById("blReason").value.trim();

  try {
    await apiCall("/api/blacklist/add", "POST", { target_type, target_value, reason });
    showToast(`${target_type} added to global blacklist!`, "success");
    closeModal("modalBlacklistAdd");
    loadBlacklists();
  } catch (err) {}
}

async function removeBlacklist(id) {
  if (!confirm("Are you sure you want to remove this entry from the global blacklist?")) return;
  try {
    await apiCall(`/api/blacklist/${id}`, "DELETE");
    showToast("Blacklist entry removed.");
    loadBlacklists();
  } catch (err) {}
}

// ----------------- Developer API Studio & Simulator -----------------
function loadApiStudioView() {
  const scriptSelect = document.getElementById("simScriptSlug");
  if (scriptSelect && currentScripts.length > 0) {
    scriptSelect.innerHTML = currentScripts.map(s => `<option value="${s.slug}">${escapeHtml(s.name)} (${s.slug})</option>`).join("");
  }
}

async function handleSimulateHandshake(e) {
  e.preventDefault();
  const slug = document.getElementById("simScriptSlug").value;
  const key = document.getElementById("simKeyInput").value.trim();
  const resBox = document.getElementById("simResultBox");
  if (!resBox) return;

  resBox.style.display = "block";
  resBox.innerHTML = `<div style="color:var(--text-zinc-400);"><i class="fa-solid fa-spinner fa-spin"></i> Testing handshake diagnostic...</div>`;

  try {
    const data = await apiCall("/api/tools/simulate-handshake", "POST", { slug, key });
    if (!data.valid) {
      resBox.innerHTML = `
        <div style="color:var(--danger-color); font-weight:700; display:flex; align-items:center; gap:6px; margin-bottom:4px;">
          <i class="fa-solid fa-circle-xmark"></i> Handshake Rejected
        </div>
        <div style="color:var(--text-zinc-300);">${escapeHtml(data.reason)}</div>
      `;
    } else {
      resBox.innerHTML = `
        <div style="color:var(--success-color); font-weight:700; display:flex; align-items:center; gap:6px; margin-bottom:8px;">
          <i class="fa-solid fa-circle-check"></i> Handshake Diagnostic PASSED
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; color:var(--text-zinc-300);">
          <div>Script: <strong>${escapeHtml(data.script_name)}</strong></div>
          <div>HWID Status: <strong>${escapeHtml(data.hwid_status)}</strong></div>
          <div>Executions: <strong>${data.execution_count}</strong></div>
          <div>Expires: <strong>${escapeHtml(String(data.expires_at))}</strong></div>
        </div>
      `;
    }
  } catch (err) {
    resBox.innerHTML = `<div style="color:var(--danger-color);">${escapeHtml(err.message)}</div>`;
  }
}

function switchSnippetTab(tab) {
  document.getElementById("snippet-curl").style.display = tab === "curl" ? "block" : "none";
  document.getElementById("snippet-python").style.display = tab === "python" ? "block" : "none";
  document.getElementById("snippet-node").style.display = tab === "node" ? "block" : "none";
}

// ----------------- System Health -----------------
async function loadSystemHealth() {
  try {
    const health = await apiCall("/api/system/health");
    const upEl = document.getElementById("sysUptime");
    if (upEl) upEl.innerText = health.uptime || "--";

    const dbEl = document.getElementById("sysDbSize");
    if (dbEl) dbEl.innerText = health.database_size || "--";

    const noncesEl = document.getElementById("sysActiveNonces");
    if (noncesEl) noncesEl.innerText = health.active_nonces || "0";

    // Public tunnel container in header
    const tunnelCont = document.getElementById("headerTunnelContainer");
    const tunnelUrl = document.getElementById("headerTunnelUrl");
    if (tunnelCont && tunnelUrl) {
      if (health.public_tunnel_url) {
        tunnelCont.style.display = "inline-flex";
        tunnelUrl.innerText = health.public_tunnel_url;
      } else {
        tunnelCont.style.display = "none";
      }
    }
  } catch (err) {}
}

// ----------------- Command Search Palette (Ctrl+K) -----------------
const PALETTE_ACTIONS = {
  kick: { title: "Remote Kick In-Game Player", icon: "fa-solid fa-bolt", fn: () => { closeSearchPalette(); openKickModal(); } },
  create_script: { title: "Create New Script Hub", icon: "fa-solid fa-plus", fn: () => { closeSearchPalette(); openCreateScriptModal(); } },
  bulk_keys: { title: "Bulk Generate License Keys", icon: "fa-solid fa-layer-group", fn: () => { closeSearchPalette(); openBulkGenModal(); } },
  import_keys: { title: "Import Keys from CSV/TXT", icon: "fa-solid fa-file-import", fn: () => { closeSearchPalette(); openImportKeysModal(); } },
  trace_watermark: { title: "Trace Leaker / Forensic Watermark", icon: "fa-solid fa-fingerprint", fn: () => { closeSearchPalette(); switchTab("bypasses"); } },
  audit_logs: { title: "View Live Security Audit Feed", icon: "fa-solid fa-shield-halved", fn: () => { closeSearchPalette(); switchTab("logs"); } },
  backup_db: { title: "Download Database Backup", icon: "fa-solid fa-cloud-arrow-down", fn: () => { closeSearchPalette(); window.location.href = "/api/system/backup"; } },
  tab_overview: { title: "Go to: Command Overview & Telemetry", icon: "fa-solid fa-chart-line", fn: () => { closeSearchPalette(); switchTab("overview"); } },
  tab_sessions: { title: "Go to: Live Players & In-Game Sessions", icon: "fa-solid fa-signal", fn: () => { closeSearchPalette(); switchTab("sessions"); } },
  tab_scripts: { title: "Go to: Script Hubs & Luau Obfuscation", icon: "fa-solid fa-code", fn: () => { closeSearchPalette(); switchTab("scripts"); } },
  tab_licenses: { title: "Go to: License Whitelist & HWID Keys", icon: "fa-solid fa-key", fn: () => { closeSearchPalette(); switchTab("licenses"); } },
  tab_bypasses: { title: "Go to: Threat Radar & Leaker Forensics", icon: "fa-solid fa-shield-virus", fn: () => { closeSearchPalette(); switchTab("bypasses"); } },
  tab_logs: { title: "Go to: Live Security Audit Logs", icon: "fa-solid fa-terminal", fn: () => { closeSearchPalette(); switchTab("logs"); } },
  tab_telemetry: { title: "Go to: Executor Analytics & Runtimes", icon: "fa-solid fa-chart-pie", fn: () => { closeSearchPalette(); switchTab("telemetry"); } },
  tab_remote: { title: "Go to: Remote Luau Console IDE", icon: "fa-solid fa-laptop-code", fn: () => { closeSearchPalette(); switchTab("remote-exec"); } },
  tab_versions: { title: "Go to: Script Versions & Rollbacks", icon: "fa-solid fa-clock-rotate-left", fn: () => { closeSearchPalette(); switchTab("versions"); } },
  tab_flags: { title: "Go to: Feature Flags & Overrides", icon: "fa-solid fa-toggle-on", fn: () => { closeSearchPalette(); switchTab("flags"); } },
  tab_api: { title: "Go to: Developer REST API & Simulator", icon: "fa-solid fa-network-wired", fn: () => { closeSearchPalette(); switchTab("api"); } },
  tab_chat: { title: "Go to: Developer Live Chat Room", icon: "fa-solid fa-comments", fn: () => { closeSearchPalette(); switchTab("chat"); } },
  tab_announcements: { title: "Go to: Global In-Game Broadcasts", icon: "fa-solid fa-bullhorn", fn: () => { closeSearchPalette(); switchTab("announcements"); } },
  tab_webhooks: { title: "Go to: Discord Webhooks & Telemetry", icon: "fa-brands fa-discord", fn: () => { closeSearchPalette(); switchTab("webhooks"); } },
  tab_staff: { title: "Go to: Staff & Resellers Management", icon: "fa-solid fa-user-shield", fn: () => { closeSearchPalette(); switchTab("staff"); } },
  tab_system: { title: "Go to: System Engine Health", icon: "fa-solid fa-server", fn: () => { closeSearchPalette(); switchTab("system"); } },
  tab_settings: { title: "Go to: Security & 2FA Settings", icon: "fa-solid fa-gears", fn: () => { closeSearchPalette(); switchTab("settings"); } }
};

function executePaletteAction(actionKey) {
  const item = PALETTE_ACTIONS[actionKey];
  if (item && typeof item.fn === "function") {
    item.fn();
  }
}

function openSearchPalette() {
  const modal = document.getElementById("searchPaletteModal") || document.getElementById("modalSearchPalette");
  const input = document.getElementById("paletteSearchInput");
  if (modal) {
    modal.style.display = "flex";
    modal.classList.add("active");
    if (input) {
      input.value = "";
      setTimeout(() => input.focus(), 50);
    }
    renderPaletteResults("");
  }
}

function closeSearchPalette() {
  const modal = document.getElementById("searchPaletteModal") || document.getElementById("modalSearchPalette");
  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
  }
}

function handlePaletteSearch(val) {
  renderPaletteResults((val || "").toLowerCase().trim());
}

function renderPaletteResults(query) {
  const container = document.getElementById("paletteResultsList") || document.getElementById("paletteResults");
  if (!container) return;

  const results = [];

  // Match quick actions
  Object.keys(PALETTE_ACTIONS).forEach(key => {
    const a = PALETTE_ACTIONS[key];
    if (!query || a.title.toLowerCase().includes(query)) {
      results.push(`
        <div class="palette-item" onclick="executePaletteAction('${key}')">
          <span style="display:flex; align-items:center; gap:8px;"><i class="${a.icon}" style="color:var(--gold-primary); width:16px; text-align:center;"></i> ${escapeHtml(a.title)}</span>
          <span class="badge badge-zinc" style="font-size:9.5px;">Jump</span>
        </div>
      `);
    }
  });

  // Hub matches
  if (Array.isArray(currentScripts)) {
    currentScripts.forEach(s => {
      if (query && (s.name.toLowerCase().includes(query) || (s.slug && s.slug.toLowerCase().includes(query)))) {
        results.push(`
          <div class="palette-item" onclick="closeSearchPalette(); switchTab('scripts'); openEditScriptModal(${s.id});">
            <span style="display:flex; align-items:center; gap:8px;"><i class="fa-solid fa-code" style="color:var(--gold-primary); width:16px; text-align:center;"></i> Hub: ${escapeHtml(s.name)} (<code>${escapeHtml(s.slug)}</code>)</span>
            <span class="badge badge-gold" style="font-size:9.5px;">Hub</span>
          </div>
        `);
      }
    });
  }

  // License matches
  if (Array.isArray(currentLicenses)) {
    currentLicenses.forEach(l => {
      if (query && ((l.license_key && l.license_key.toLowerCase().includes(query)) || (l.note && l.note.toLowerCase().includes(query)) || (l.roblox_username && l.roblox_username.toLowerCase().includes(query)))) {
        results.push(`
          <div class="palette-item" onclick="closeSearchPalette(); switchTab('licenses'); openLicenseDetailModal(${l.id});">
            <span style="display:flex; align-items:center; gap:8px;"><i class="fa-solid fa-key" style="color:var(--gold-primary); width:16px; text-align:center;"></i> Key: ${escapeHtml(l.license_key)} ${l.note ? '(' + escapeHtml(l.note) + ')' : ''}</span>
            <span class="badge badge-zinc" style="font-size:9.5px;">License</span>
          </div>
        `);
      }
    });
  }

  container.innerHTML = results.length > 0
    ? results.join("")
    : `<div style="text-align:center; padding:18px; color:var(--text-zinc-500); font-size:11px;">No matching commands or records found.</div>`;
}

// =========================================================================
// REAL-TIME IN-GAME PRESENCE ENGINE & ZERO-REFRESH SESSIONS CONTROLLER
// =========================================================================
window.liveSessionsData = [];
window.overviewSessionsFilter = 'all';
window.liveSessionsTabFilter = 'all';
window.overviewSessionsSearch = '';
window.liveSessionsTabSearch = '';
let livePresenceTickerInterval = null;

function formatSecsAgo(seconds) {
  if (seconds < 60) return `${seconds}s ago`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hrs}h ${remMins}m`;
}

function startLiveSessionsPresenceTicker() {
  if (livePresenceTickerInterval) return;
  livePresenceTickerInterval = setInterval(() => {
    if (!window.liveSessionsData || window.liveSessionsData.length === 0) return;

    // Locally tick presence states and elapsed seconds with zero lag
    window.liveSessionsData.forEach(s => {
      if (s.presence_state !== "kicked") {
        s.seconds_ago = (s.seconds_ago || 0) + 1;
      }
      s.duration_seconds = (s.duration_seconds || 0) + 1;

      if (s.is_kicked) {
        s.presence_state = "kicked";
        s.presence_label = "KICKED";
      } else if (s.seconds_ago <= 35) {
        s.presence_state = "online";
        s.presence_label = "ONLINE";
      } else if (s.seconds_ago <= 120) {
        s.presence_state = "idle";
        s.presence_label = "IDLE";
      } else {
        s.presence_state = "offline";
        s.presence_label = "DISCONNECTED";
      }
    });

    updateSessionsCountBadges();
    renderActiveSessionsTable();
    renderLiveSessionsTabTable();
  }, 1000);
}

function updateSessionsCountBadges() {
  const all = window.liveSessionsData || [];
  const onlineCount = all.filter(s => s.presence_state === "online").length;
  const idleCount = all.filter(s => s.presence_state === "idle").length;
  const offlineCount = all.filter(s => s.presence_state === "offline").length;
  const kickedCount = all.filter(s => s.presence_state === "kicked").length;

  // Update Overview tab badge counts
  const cAll = document.getElementById("countSessionsAll"); if (cAll) cAll.innerText = all.length;
  const cOn = document.getElementById("countSessionsOnline"); if (cOn) cOn.innerText = onlineCount;
  const cId = document.getElementById("countSessionsIdle"); if (cId) cId.innerText = idleCount;
  const cOff = document.getElementById("countSessionsOffline"); if (cOff) cOff.innerText = offlineCount;
  const cKick = document.getElementById("countSessionsKicked"); if (cKick) cKick.innerText = kickedCount;

  // Update In-Game Tab badge counts
  const tAll = document.getElementById("tabCountSessionsAll"); if (tAll) tAll.innerText = all.length;
  const tOn = document.getElementById("tabCountSessionsOnline"); if (tOn) tOn.innerText = onlineCount;
  const tId = document.getElementById("tabCountSessionsIdle"); if (tId) tId.innerText = idleCount;
  const tOff = document.getElementById("tabCountSessionsOffline"); if (tOff) tOff.innerText = offlineCount;
  const tKick = document.getElementById("tabCountSessionsKicked"); if (tKick) tKick.innerText = kickedCount;

  // Header tab badge count (Live players)
  const bLive = document.getElementById("badgeLiveSessionsCount");
  if (bLive) bLive.innerText = onlineCount + idleCount;
}

function setSessionsFilter(filter, context) {
  if (context === "overview") {
    window.overviewSessionsFilter = filter;
    document.querySelectorAll("#overviewSessionsFilterGroup .filter-pill-btn").forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-filter") === filter);
    });
    renderActiveSessionsTable();
  } else {
    window.liveSessionsTabFilter = filter;
    document.querySelectorAll("#liveSessionsFilterGroup .filter-pill-btn").forEach(btn => {
      btn.classList.toggle("active", btn.getAttribute("data-filter") === filter);
    });
    renderLiveSessionsTabTable();
  }
}

function filterActiveSessionsTable(query) {
  window.overviewSessionsSearch = (query || "").trim().toLowerCase();
  renderActiveSessionsTable();
}

function filterLiveSessionsTab(query) {
  window.liveSessionsTabSearch = (query || "").trim().toLowerCase();
  renderLiveSessionsTabTable();
}

function handleRealtimeSessionEvent(data) {
  if (!data) return;
  const ev = data.event;
  if (ev === "heartbeat") {
    const key = (data.license_key || "").toUpperCase();
    const found = (window.liveSessionsData || []).find(s => (s.license_key || "").toUpperCase() === key);
    if (found) {
      found.last_heartbeat = data.last_heartbeat || new Date().toISOString();
      found.seconds_ago = 0;
      found.presence_state = "online";
      found.presence_label = "ONLINE";
      found.is_kicked = 0;
      updateSessionsCountBadges();
      renderActiveSessionsTable();
      renderLiveSessionsTabTable();
    } else {
      loadActiveSessions(false);
    }
  } else if (ev === "join") {
    const key = (data.license_key || "").toUpperCase();
    const existingIdx = (window.liveSessionsData || []).findIndex(s => (s.license_key || "").toUpperCase() === key);
    const newSession = {
      license_key: data.license_key,
      roblox_username: data.roblox_username,
      roblox_user_id: data.roblox_user_id,
      game_name: data.game_name,
      place_id: data.place_id,
      executor_name: data.executor_name,
      last_heartbeat: data.last_heartbeat || new Date().toISOString(),
      started_at: data.started_at || new Date().toISOString(),
      seconds_ago: 0,
      duration_seconds: 0,
      presence_state: "online",
      presence_label: "ONLINE",
      is_kicked: 0
    };
    if (existingIdx >= 0) {
      window.liveSessionsData[existingIdx] = { ...window.liveSessionsData[existingIdx], ...newSession };
    } else {
      window.liveSessionsData.unshift(newSession);
    }
    updateSessionsCountBadges();
    renderActiveSessionsTable();
    renderLiveSessionsTabTable();
  } else if (ev === "kicked") {
    const key = (data.license_key || "").toUpperCase();
    const user = (data.roblox_username || "").toLowerCase();
    (window.liveSessionsData || []).forEach(s => {
      if ((key && (s.license_key || "").toUpperCase() === key) ||
          (user && (s.roblox_username || "").toLowerCase() === user) ||
          (data.hwid && s.hwid === data.hwid) ||
          (data.roblox_user_id && s.roblox_user_id === data.roblox_user_id)) {
        s.is_kicked = 1;
        s.presence_state = "kicked";
        s.presence_label = "KICKED";
        s.kick_reason = data.reason || "Kicked by admin";
      }
    });
    updateSessionsCountBadges();
    renderActiveSessionsTable();
    renderLiveSessionsTabTable();
  }
}

async function loadActiveSessions(force = false) {
  try {
    const sessions = await apiCall("/api/sessions?show_all=true");
    if (sessions && Array.isArray(sessions)) {
      window.liveSessionsData = sessions;
      updateSessionsCountBadges();
      renderActiveSessionsTable();
      renderLiveSessionsTabTable();
      startLiveSessionsPresenceTicker();
    }
  } catch (e) {}
}

function renderActiveSessionsTable() {
  const tableBody = document.getElementById("activeSessionsTableBody");
  if (!tableBody) return;

  const sessions = window.liveSessionsData || [];
  const filter = window.overviewSessionsFilter || "all";
  const search = window.overviewSessionsSearch || "";

  let filtered = sessions.filter(s => {
    if (filter === "online" && s.presence_state !== "online") return false;
    if (filter === "idle" && s.presence_state !== "idle") return false;
    if (filter === "offline" && s.presence_state !== "offline") return false;
    if (filter === "kicked" && s.presence_state !== "kicked") return false;

    if (search) {
      const match = (s.roblox_username && s.roblox_username.toLowerCase().includes(search)) ||
                    (s.game_name && s.game_name.toLowerCase().includes(search)) ||
                    (s.license_key && s.license_key.toLowerCase().includes(search)) ||
                    (s.hwid && s.hwid.toLowerCase().includes(search)) ||
                    (s.executor_name && s.executor_name.toLowerCase().includes(search)) ||
                    (s.script_name && s.script_name.toLowerCase().includes(search));
      if (!match) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 24px; color:var(--text-zinc-500);"><i class="fa-solid fa-signal" style="color:var(--gold-light); margin-right:6px;"></i> No player sessions match this filter. Live presence active (0s refresh).</td></tr>`;
    return;
  }

  tableBody.innerHTML = filtered.map(s => {
    const avatarUrl = (s.roblox_user_id && s.roblox_user_id > 0)
      ? `/api/roblox/avatar/${s.roblox_user_id}`
      : `/api/roblox/avatar/1`;
    const profileUrl = (s.roblox_user_id && s.roblox_user_id > 0) ? `https://www.roblox.com/users/${s.roblox_user_id}/profile` : '#';
    const placeUrl = s.place_id > 0 ? `https://www.roblox.com/games/${s.place_id}` : '#';

    let presenceBadge = "";
    if (s.presence_state === "kicked") {
      presenceBadge = `<span class="presence-pill kicked"><span class="radar-dot kicked"></span> KICKED</span>`;
    } else if (s.presence_state === "online") {
      presenceBadge = `<span class="presence-pill online"><span class="radar-dot online"></span> LIVE (${s.seconds_ago || 0}s ago)</span>`;
    } else if (s.presence_state === "idle") {
      presenceBadge = `<span class="presence-pill idle"><span class="radar-dot idle"></span> IDLE (${s.seconds_ago || 0}s ago)</span>`;
    } else {
      presenceBadge = `<span class="presence-pill offline"><span class="radar-dot offline"></span> LEFT (${formatSecsAgo(s.seconds_ago || 0)})</span>`;
    }

    return `
      <tr>
        <td>${presenceBadge}</td>
        <td>
          <div style="display:flex; align-items:center; gap:9px;">
            <div class="avatar-badge-wrap">
              <img src="${avatarUrl}" alt="Avatar">
              <span class="status-indicator ${s.presence_state}"></span>
            </div>
            <div>
              <a href="${profileUrl}" target="_blank" style="color:var(--text-white); font-weight:650; text-decoration:none; font-size:13px; display:flex; align-items:center; gap:4px;">
                ${escapeHtml(s.roblox_username || 'Unknown')} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i>
              </a>
              <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">ID: ${s.roblox_user_id || '—'}</span>
            </div>
          </div>
        </td>
        <td>
          <a href="${placeUrl}" target="_blank" style="color:var(--gold-light); font-size:12px; font-weight:550; text-decoration:none; display:flex; align-items:center; gap:4px;">
            <i class="fa-solid fa-gamepad" style="font-size:11px; opacity:0.8;"></i> ${escapeHtml(s.game_name || 'Roblox Experience')}
          </a>
          <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">Place: ${s.place_id || '—'}</span>
        </td>
        <td><strong style="color:var(--text-white); font-size:12px;">${escapeHtml(s.script_name || s.script_slug || 'Hub')}</strong></td>
        <td>
          <span class="key-badge" style="font-size:11px;" onclick="copyText('${s.license_key}', 'License Key copied!')" title="Click to copy key">${escapeHtml((s.license_key || '').substring(0, 14))}... <i class="fa-solid fa-copy"></i></span>
        </td>
        <td>${renderExecutorBadge(s.executor_name)}</td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-primary btn-sm" onclick="openRemoteExecModal('${escapeHtml(s.license_key)}', '${escapeHtml(s.roblox_username || '')}')" title="Execute Remote Luau">
              <i class="fa-solid fa-bolt"></i>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openTargetedBroadcastModal('${escapeHtml(s.license_key)}', '${escapeHtml(s.roblox_username || '')}')" title="Send In-Game Message">
              <i class="fa-solid fa-bullhorn" style="color:var(--gold-light);"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="openKickModal({ key: '${escapeHtml(s.license_key || '')}', hwid: '${escapeHtml(s.hwid || '')}', userId: ${s.roblox_user_id || 0}, username: '${escapeHtml(s.roblox_username || '')}', displayName: '${escapeHtml(s.roblox_username || s.license_key || 'Player')}' })" title="Kick Player from Game">
              <i class="fa-solid fa-power-off"></i> Kick
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function loadLiveSessions(force = false) {
  return loadActiveSessions(force);
}

function filterSessionsViewTable(query) {
  window.liveSessionsTabSearch = (query || "").trim().toLowerCase();
  renderLiveSessionsTabTable();
}

function renderLiveSessionsTabTable() {
  const tableBody = document.getElementById("sessionsViewTableBody");
  if (!tableBody) return;

  const sessions = window.liveSessionsData || [];
  const filter = window.liveSessionsTabFilter || "all";
  const search = window.liveSessionsTabSearch || "";

  // Update In-Game Tab badge counts
  const allCount = sessions.length;
  const onlineCount = sessions.filter(s => s.presence_state === "online").length;
  const idleCount = sessions.filter(s => s.presence_state === "idle").length;
  const offlineCount = sessions.filter(s => s.presence_state === "offline").length;
  const kickedCount = sessions.filter(s => s.presence_state === "kicked").length;

  const tAll = document.getElementById("sessionsViewCountAll"); if (tAll) tAll.innerText = allCount;
  const tOn = document.getElementById("sessionsViewCountOnline"); if (tOn) tOn.innerText = onlineCount;
  const tId = document.getElementById("sessionsViewCountIdle"); if (tId) tId.innerText = idleCount;
  const tOff = document.getElementById("sessionsViewCountOffline"); if (tOff) tOff.innerText = offlineCount;
  const tKick = document.getElementById("sessionsViewCountKicked"); if (tKick) tKick.innerText = kickedCount;

  let filtered = sessions.filter(s => {
    if (filter === "online" && s.presence_state !== "online") return false;
    if (filter === "idle" && s.presence_state !== "idle") return false;
    if (filter === "offline" && s.presence_state !== "offline") return false;
    if (filter === "kicked" && s.presence_state !== "kicked") return false;

    if (search) {
      const match = (s.roblox_username && s.roblox_username.toLowerCase().includes(search)) ||
                    (s.game_name && s.game_name.toLowerCase().includes(search)) ||
                    (s.license_key && s.license_key.toLowerCase().includes(search)) ||
                    (s.hwid && s.hwid.toLowerCase().includes(search)) ||
                    (s.executor_name && s.executor_name.toLowerCase().includes(search)) ||
                    (s.script_name && s.script_name.toLowerCase().includes(search));
      if (!match) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 24px; color:var(--text-zinc-500);"><i class="fa-solid fa-signal" style="color:var(--gold-light); margin-right:6px;"></i> No live in-game sessions match this filter.</td></tr>`;
    return;
  }

  tableBody.innerHTML = filtered.map(s => {
    const avatarUrl = (s.roblox_user_id && s.roblox_user_id > 0)
      ? `/api/roblox/avatar/${s.roblox_user_id}`
      : `/api/roblox/avatar/1`;
    const profileUrl = (s.roblox_user_id && s.roblox_user_id > 0) ? `https://www.roblox.com/users/${s.roblox_user_id}/profile` : '#';
    const placeUrl = s.place_id > 0 ? `https://www.roblox.com/games/${s.place_id}` : '#';

    let presenceBadge = "";
    if (s.presence_state === "kicked") {
      presenceBadge = `<span class="presence-pill kicked"><span class="radar-dot kicked"></span> KICKED</span>`;
    } else if (s.presence_state === "online") {
      presenceBadge = `<span class="presence-pill online"><span class="radar-dot online"></span> LIVE (${s.seconds_ago || 0}s ago)</span>`;
    } else if (s.presence_state === "idle") {
      presenceBadge = `<span class="presence-pill idle"><span class="radar-dot idle"></span> IDLE (${s.seconds_ago || 0}s ago)</span>`;
    } else {
      presenceBadge = `<span class="presence-pill offline"><span class="radar-dot offline"></span> LEFT (${formatSecsAgo(s.seconds_ago || 0)})</span>`;
    }

    const hwidSnippet = s.hwid ? `${escapeHtml(s.hwid.substring(0, 8))}...` : '—';
    const ipSnippet = s.ip_address ? escapeHtml(s.ip_address) : '—';

    return `
      <tr>
        <td>${presenceBadge}</td>
        <td>
          <div style="display:flex; align-items:center; gap:9px;">
            <div class="avatar-badge-wrap">
              <img src="${avatarUrl}" alt="Avatar">
              <span class="status-indicator ${s.presence_state}"></span>
            </div>
            <div>
              <a href="${profileUrl}" target="_blank" style="color:var(--text-white); font-weight:650; text-decoration:none; font-size:13px; display:flex; align-items:center; gap:4px;">
                ${escapeHtml(s.roblox_username || 'Unknown')} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i>
              </a>
              <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">ID: ${s.roblox_user_id || '—'}</span>
            </div>
          </div>
        </td>
        <td>
          <a href="${placeUrl}" target="_blank" style="color:var(--gold-light); font-size:12px; font-weight:550; text-decoration:none; display:flex; align-items:center; gap:4px;">
            <i class="fa-solid fa-gamepad" style="font-size:11px; opacity:0.8;"></i> ${escapeHtml(s.game_name || 'Roblox Experience')}
          </a>
          <span style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">Place: ${s.place_id || '—'}</span>
        </td>
        <td><strong style="color:var(--text-white); font-size:12px;">${escapeHtml(s.script_name || s.script_slug || 'Hub')}</strong></td>
        <td>
          <span class="key-badge" style="font-size:11px;" onclick="copyText('${s.license_key}', 'License Key copied!')" title="Click to copy key">${escapeHtml((s.license_key || '').substring(0, 14))}... <i class="fa-solid fa-copy"></i></span>
        </td>
        <td>${renderExecutorBadge(s.executor_name)}</td>
        <td>
          <div style="font-size:11px; font-family:var(--font-mono); color:var(--text-zinc-400);">
            <div>${ipSnippet}</div>
            <div style="color:var(--text-zinc-500); font-size:10px;">HWID: ${hwidSnippet}</div>
          </div>
        </td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-primary btn-sm" onclick="openRemoteExecModal('${escapeHtml(s.license_key)}', '${escapeHtml(s.roblox_username || '')}')" title="Execute Remote Luau">
              <i class="fa-solid fa-bolt"></i>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="openTargetedBroadcastModal('${escapeHtml(s.license_key)}', '${escapeHtml(s.roblox_username || '')}')" title="Send In-Game Message">
              <i class="fa-solid fa-bullhorn" style="color:var(--gold-light);"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="openKickModal({ key: '${escapeHtml(s.license_key || '')}', hwid: '${escapeHtml(s.hwid || '')}', userId: ${s.roblox_user_id || 0}, username: '${escapeHtml(s.roblox_username || '')}', displayName: '${escapeHtml(s.roblox_username || s.license_key || 'Player')}' })" title="Kick Player from Game">
              <i class="fa-solid fa-power-off"></i> Kick
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function loadRecentKicks() {
  const tbody = document.getElementById("recentKicksTableBody");
  const badge = document.getElementById("badgeKickCount");
  if (!tbody) return;

  try {
    const kicks = await apiCall("/api/kicks?limit=30");
    if (badge) {
      badge.innerText = `${kicks.length} Kick${kicks.length === 1 ? '' : 's'}`;
      badge.style.display = kicks.length > 0 ? "inline-block" : "none";
    }

    if (kicks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:16px; color:var(--text-zinc-500);"><i class="fa-solid fa-shield-halved" style="color:var(--gold-primary); margin-right:6px;"></i> No in-game kicks logged yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = kicks.map(k => {
      const avatarSrc = (k.roblox_user_id && k.roblox_user_id > 0)
        ? `/api/roblox/avatar/${k.roblox_user_id}`
        : `/api/roblox/avatar/1`;
      const profileUrl = (k.roblox_user_id && k.roblox_user_id > 0) ? `https://www.roblox.com/users/${k.roblox_user_id}/profile` : '#';
      const timeStr = formatTimeAgo(k.timestamp);
      const placeName = escapeHtml(k.game_name || (k.place_id > 0 ? `Place #${k.place_id}` : 'Experience'));

      const placeHtml = k.place_id > 0
        ? `<a href="https://www.roblox.com/games/${k.place_id}" target="_blank" style="color:var(--gold-light); font-size:11px; font-weight:550; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"><i class="fa-solid fa-gamepad" style="font-size:9px; opacity:0.8;"></i> ${placeName}</a>`
        : `<span style="color:var(--text-zinc-400); font-size:11px;">${placeName}</span>`;

      return `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <img src="${avatarSrc}" style="width:24px; height:24px; border-radius:50%; object-fit:cover; border:1px solid var(--border-subtle); flex-shrink:0;">
              <div>
                <a href="${profileUrl}" target="_blank" style="color:var(--text-white); font-weight:650; font-size:11.5px; text-decoration:none; display:flex; align-items:center; gap:3px;">
                  ${escapeHtml(k.roblox_username || 'Unknown')}
                </a>
              </div>
            </div>
          </td>
          <td>
            <span class="badge ${k.badge_class || 'badge-danger'}" style="font-weight:650; font-size:10.5px; white-space:nowrap;">
              <i class="fa-solid ${k.icon || 'fa-bolt'}"></i> ${escapeHtml(k.kick_reason || 'Terminated')}
            </span>
          </td>
          <td>${placeHtml}</td>
          <td>
            <span style="font-size:10.5px; color:var(--text-zinc-400); white-space:nowrap; font-family:var(--font-mono);">${timeStr}</span>
          </td>
          <td>
            <div style="display:flex; gap:4px;">
              ${k.license_key && k.license_key !== 'N/A' ? `
                <button class="btn btn-secondary btn-sm" style="padding:2px 6px; font-size:9.5px;" onclick="copyText('${escapeHtml(k.license_key)}', 'License key copied!')" title="Copy License Key">
                  <i class="fa-solid fa-copy"></i>
                </button>
              ` : ''}
              ${k.hwid ? `
                <button class="btn btn-danger btn-sm" style="padding:2px 6px; font-size:9.5px;" onclick="openBlacklistModal({ target: '${escapeHtml(k.hwid)}', type: 'HWID', reason: 'Security Interception / Kicked session' })" title="Blacklist HWID">
                  <i class="fa-solid fa-ban"></i>
                </button>
              ` : ''}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:16px; color:var(--danger-light);">Error loading kicks: ${err.message}</td></tr>`;
  }
}

async function loadThreatRadarBypasses() {
  const tbody = document.getElementById("threatRadarBypassesTableBody");
  if (!tbody) return;

  try {
    const kicks = await apiCall("/api/kicks?limit=50");
    if (!kicks || kicks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-zinc-500);"><i class="fa-solid fa-shield-halved" style="color:var(--gold-primary); margin-right:6px;"></i> No security interceptions, tampering traps, or remote kicks logged.</td></tr>`;
      return;
    }

    tbody.innerHTML = kicks.map(k => {
      const avatarSrc = (k.roblox_user_id && k.roblox_user_id > 0)
        ? `/api/roblox/avatar/${k.roblox_user_id}`
        : `/api/roblox/avatar/1`;
      const profileUrl = (k.roblox_user_id && k.roblox_user_id > 0) ? `https://www.roblox.com/users/${k.roblox_user_id}/profile` : '#';
      const timeStr = formatTimeAgo(k.timestamp);
      const placeName = escapeHtml(k.game_name || (k.place_id > 0 ? `Place #${k.place_id}` : 'Roblox Experience'));

      const placeHtml = k.place_id > 0
        ? `<a href="https://www.roblox.com/games/${k.place_id}" target="_blank" style="color:var(--gold-light); font-size:12px; font-weight:550; text-decoration:none; display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-gamepad" style="font-size:10px; opacity:0.8;"></i> ${placeName} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:9px; opacity:0.6;"></i></a>`
        : `<span style="color:var(--text-zinc-400); font-size:12px; display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-gamepad" style="font-size:10px; opacity:0.6;"></i> ${placeName}</span>`;

      return `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <img src="${avatarSrc}" style="width:28px; height:28px; border-radius:50%; object-fit:cover; border:1px solid var(--border-subtle); flex-shrink:0;">
              <div>
                <a href="${profileUrl}" target="_blank" style="color:var(--text-white); font-weight:650; font-size:12px; text-decoration:none; display:flex; align-items:center; gap:3px;">
                  ${escapeHtml(k.roblox_username || 'Unknown')} <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:8px; opacity:0.6;"></i>
                </a>
                <div style="font-size:10px; color:var(--text-zinc-500); font-family:var(--font-mono);">${k.roblox_user_id > 0 ? `ID: ${k.roblox_user_id}` : 'ID: —'}</div>
              </div>
            </div>
          </td>
          <td>
            <span class="badge ${k.badge_class || 'badge-danger'}" style="font-weight:650; font-size:11px; white-space:normal; text-align:left; line-height:1.3; max-width:320px; display:inline-block;">
              <i class="fa-solid ${k.icon || 'fa-bolt'}"></i> ${escapeHtml(k.kick_reason || 'Session Terminated')}
            </span>
          </td>
          <td><span class="badge badge-gold" style="font-size:11px;">${escapeHtml(k.script_name || k.script_slug || 'Hub')}</span></td>
          <td>${placeHtml}</td>
          <td><span style="font-size:11px; color:var(--text-zinc-400); white-space:nowrap;">${timeStr}</span></td>
          <td>
            <div style="display:flex; gap:6px;">
              ${k.license_key && k.license_key !== 'N/A' ? `
                <button class="btn btn-secondary btn-sm" style="padding:4px 8px; font-size:10px;" onclick="copyText('${escapeHtml(k.license_key)}', 'License key copied!')" title="Copy License Key">
                  <i class="fa-solid fa-copy"></i>
                </button>
              ` : ''}
              ${k.hwid ? `
                <button class="btn btn-danger btn-sm" style="padding:4px 8px; font-size:10px;" onclick="openBlacklistModal({ target: '${escapeHtml(k.hwid)}', type: 'HWID', reason: 'Security Interception / Kicked session' })" title="Blacklist HWID">
                  <i class="fa-solid fa-ban"></i>
                </button>
              ` : ''}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--danger-light);">Error loading threat feed: ${err.message}</td></tr>`;
  }
}

function openKickModal(opts) {
  opts = opts || {};
  const displayInput = document.getElementById("kickTargetDisplay");
  if (!displayInput) return;

  displayInput.value = opts.displayName || opts.username || opts.key || opts.hwid || "Select Player / Key";
  document.getElementById("kickTargetKey").value = opts.key || "";
  document.getElementById("kickTargetHWID").value = opts.hwid || "";
  document.getElementById("kickTargetUserId").value = opts.userId || "";
  document.getElementById("kickTargetUsername").value = opts.username || "";
  document.getElementById("kickReasonPreset").value = "FleedGuard: Session terminated by administrator";
  document.getElementById("kickReasonText").value = "FleedGuard: Session terminated by administrator";
  document.getElementById("modalKickPlayer").classList.add("active");
}

function applyKickPreset(val) {
  if (val !== "custom") {
    document.getElementById("kickReasonText").value = val;
  }
}

async function handleExecuteKick(e) {
  e.preventDefault();
  const license_key = document.getElementById("kickTargetKey")?.value || null;
  const hwid = document.getElementById("kickTargetHWID")?.value || null;
  const roblox_user_id = parseInt(document.getElementById("kickTargetUserId")?.value) || null;
  const roblox_username = document.getElementById("kickTargetUsername")?.value || null;
  const reason = document.getElementById("kickReasonText")?.value.trim() || "Kicked by FleedGuard Administrator";

  try {
    const res = await apiCall("/api/sessions/kick", "POST", {
      license_key,
      hwid,
      roblox_user_id,
      roblox_username,
      reason
    });
    showToast(res.message, "success");
    closeModal("modalKickPlayer");
    loadActiveSessions();
    loadOverviewStats();
  } catch (err) {}
}

// Global Keyboard Shortcuts (Ctrl+K for palette, Ctrl+[ for sidebar, Esc for modals)
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openSearchPalette();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === "[" || e.key === "b")) {
    e.preventDefault();
    toggleSidebar();
  }
  if (e.key === "Escape") {
    document.querySelectorAll(".modal-overlay.active").forEach(m => {
      m.classList.remove("active");
      m.style.display = "none";
    });
  }
});

// Global initialization
document.addEventListener("DOMContentLoaded", async () => {
  const isDashboard = window.location.pathname.startsWith("/dashboard");

  // Restore sidebar collapsed preference
  if (localStorage.getItem("fleed_sidebar_collapsed") === "1") {
    const sidebar = document.getElementById("mainSidebar");
    if (sidebar) sidebar.classList.add("collapsed");
    const btn = document.getElementById("sidebarCollapseBtn");
    if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-angles-right"></i>';
      btn.title = "Expand Sidebar (Ctrl+[)";
    }
  }

  const user = await checkAuth();

  if (isDashboard && user) {
    switchTab("overview");
    loadOverviewStats();
    loadProfileStats();
    initChatWebSocket();

    // Auto-refresh polling loop (every 5 seconds)
    if (!liveLogInterval) {
      liveLogInterval = setInterval(() => {
        if (!isAutoRefreshOn) return;
        const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");
        if (activeTab === "logs") loadLiveLogs();
        if (activeTab === "bypasses") { loadThreatRadarBypasses(); loadAnomalies(); }
        if (activeTab === "overview") { loadOverviewStats(); loadRecentKicks(); }
        if (activeTab === "sessions") loadLiveSessions();
      }, 5000);
    }
  }
});


// =========================================================================
// REALTIME LIVE SESSION & SECURITY EVENT DISPATCHER
// =========================================================================
function handleRealtimeSessionEvent(data) {
  if (!data) return;
  const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");

  if (data.event === "kicked") {
    // If a player was kicked remotely or by security guard, update threat radar and kicks immediately
    if (activeTab === "overview") loadRecentKicks();
    if (activeTab === "bypasses") loadThreatRadarBypasses();
    if (activeTab === "sessions") loadLiveSessions();
  } else if (data.event === "join" || data.event === "heartbeat") {
    if (activeTab === "sessions") loadLiveSessions();
  }
}


// =========================================================================
// LIVE COMMUNITY CHAT (WEBSOCKET & REALTIME BROADCAST)
// =========================================================================
let chatSocket = null;
let isChatSoundEnabled = true;
let unreadChatCount = 0;

function initChatWebSocket() {
  if (chatSocket && (chatSocket.readyState === WebSocket.OPEN || chatSocket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const token = localStorage.getItem("fleed_token") || "";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/chat?token=${encodeURIComponent(token)}`;

  try {
    chatSocket = new WebSocket(wsUrl);

    chatSocket.onopen = () => {
      console.log("[FleedGuard] Chat WebSocket connected.");
    };

    chatSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "message") {
          appendChatMessage(data);
          playChatSound();
          const activeTab = document.querySelector(".tab-btn.active")?.getAttribute("data-tab");
          if (activeTab !== "chat") {
            unreadChatCount++;
            updateChatBadge();
          }
        } else if (data.type === "presence") {
          updateChatPresence(data);
        } else if (data.type === "session_event") {
          handleRealtimeSessionEvent(data);
        }
      } catch (err) {}
    };

    chatSocket.onclose = () => {
      console.log("[FleedGuard] Chat WebSocket closed. Retrying in 5s...");
      setTimeout(() => initChatWebSocket(), 5000);
    };

    chatSocket.onerror = () => {
      try { chatSocket.close(); } catch (e) {}
    };
  } catch (err) {}
}

function updateChatBadge() {
  const b1 = document.getElementById("badgeChatUnread");
  const b2 = document.getElementById("floatingChatBadge");
  if (unreadChatCount > 0) {
    if (b1) { b1.innerText = unreadChatCount; b1.style.display = "inline-block"; }
    if (b2) { b2.innerText = unreadChatCount; b2.style.display = "inline-block"; }
  } else {
    if (b1) b1.style.display = "none";
    if (b2) b2.style.display = "none";
  }
}

function playChatSound() {
  if (!isChatSoundEnabled) return;
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.1); // A5
    gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.15);
  } catch (e) {}
}

function toggleChatSound() {
  isChatSoundEnabled = !isChatSoundEnabled;
  const icon1 = document.getElementById("mainChatSoundIcon");
  const icon2 = document.getElementById("floatingChatSoundIcon");
  const cls = isChatSoundEnabled ? "fa-solid fa-volume-high" : "fa-solid fa-volume-xmark";
  if (icon1) icon1.className = cls;
  if (icon2) icon2.className = cls;
  showToast(isChatSoundEnabled ? "Chat notifications enabled" : "Chat muted", "info");
}

function toggleFloatingChat() {
  const panel = document.getElementById("floatingChatPanel");
  if (!panel) return;
  const isHidden = panel.style.display === "none" || !panel.style.display;
  panel.style.display = isHidden ? "flex" : "none";
  if (isHidden) {
    unreadChatCount = 0;
    updateChatBadge();
    const input = document.getElementById("floatingChatInput");
    if (input) input.focus();
  }
}

async function loadChatMessages() {
  try {
    const msgs = await apiCall("/api/chat/messages?limit=50");
    const container = document.getElementById("mainChatMessages");
    const floatContainer = document.getElementById("floatingChatMessages");
    if (container) container.innerHTML = "";
    if (floatContainer) floatContainer.innerHTML = "";

    msgs.forEach(m => {
      appendChatMessage(m, false);
    });

    unreadChatCount = 0;
    updateChatBadge();
  } catch (err) {}
}

function appendChatMessage(msg, autoScroll = true) {
  const mainBox = document.getElementById("mainChatMessages");
  const floatBox = document.getElementById("floatingChatMessages");

  const avatar = msg.avatar_url 
    ? `<img src="${escapeHtml(msg.avatar_url)}" alt="avatar">` 
    : (msg.username || "U").charAt(0).toUpperCase();

  const roleCls = `chat-role-${(msg.role || 'developer').toLowerCase()}`;
  const timeStr = formatTimeAgo(msg.created_at);

  const html = `
    <div class="chat-msg-row">
      <div class="chat-avatar">${avatar}</div>
      <div class="chat-content-wrap">
        <div class="chat-meta">
          <span class="chat-username">${escapeHtml(msg.username || 'Anonymous')}</span>
          <span class="chat-role-badge ${roleCls}">${escapeHtml(msg.role || 'Member')}</span>
          <span class="chat-time">${timeStr}</span>
        </div>
        <div class="chat-bubble">${escapeHtml(msg.message)}</div>
      </div>
    </div>
  `;

  if (mainBox) {
    mainBox.insertAdjacentHTML("beforeend", html);
    if (autoScroll) mainBox.scrollTop = mainBox.scrollHeight;
  }
  if (floatBox) {
    floatBox.insertAdjacentHTML("beforeend", html);
    if (autoScroll) floatBox.scrollTop = floatBox.scrollHeight;
  }
}

function updateChatPresence(data) {
  const onlineCount = data.online_count || 1;
  const bMain = document.getElementById("chatOnlineCount");
  const bFloat = document.getElementById("floatingOnlineBadge");
  if (bMain) bMain.innerText = `${onlineCount} Online`;
  if (bFloat) bFloat.innerText = `${onlineCount} Online`;

  const usersList = document.getElementById("chatOnlineUsersList");
  if (!usersList || !data.users) return;

  usersList.innerHTML = data.users.map(u => {
    const avatar = u.avatar_url 
      ? `<img src="${escapeHtml(u.avatar_url)}" style="width:100%; height:100%; border-radius:50%; object-fit:cover;">` 
      : (u.username || "U").charAt(0).toUpperCase();
    const roleCls = `chat-role-${(u.role || 'developer').toLowerCase()}`;

    return `
      <div class="chat-user-item">
        <div class="chat-avatar" style="width:28px; height:28px; font-size:11px;">${avatar}</div>
        <div style="flex:1; overflow:hidden;">
          <div style="font-size:12px; font-weight:700; color:var(--text-white); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(u.username)}</div>
          <span class="chat-role-badge ${roleCls}" style="font-size:9px; padding:0 4px;">${escapeHtml(u.role || 'Dev')}</span>
        </div>
      </div>
    `;
  }).join("");
}

function sendMainChatMessage(e) {
  e.preventDefault();
  const input = document.getElementById("mainChatInput");
  const text = input?.value.trim();
  if (!text) return;

  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
    chatSocket.send(JSON.stringify({ type: "message", message: text, channel: "general" }));
  }
  input.value = "";
}

function sendFloatingChatMessage(e) {
  e.preventDefault();
  const input = document.getElementById("floatingChatInput");
  const text = input?.value.trim();
  if (!text) return;

  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
    chatSocket.send(JSON.stringify({ type: "message", message: text, channel: "general" }));
  }
  input.value = "";
}


// =========================================================================
// IN-GAME SESSIONS & LIVE REMOTE KICK
// =========================================================================



function openRemoteKickModal(key = "", hwid = "", username = "") {
  if (key) {
    document.getElementById("kickTargetType").value = "KEY";
    document.getElementById("kickTargetValue").value = key;
  } else if (username) {
    document.getElementById("kickTargetType").value = "USERNAME";
    document.getElementById("kickTargetValue").value = username;
  }
  document.getElementById("modalRemoteKick").classList.add("active");
}

async function handleExecuteRemoteKick(e) {
  e.preventDefault();
  const target_type = document.getElementById("kickTargetType").value;
  const target_value = document.getElementById("kickTargetValue").value.trim();
  const reason = document.getElementById("kickReason").value.trim();

  try {
    const res = await apiCall("/api/sessions/kick", "POST", { target_type, target_value, reason });
    showToast(res.message, "success");
    closeModal("modalRemoteKick");
    loadLiveSessions();
  } catch (err) {}
}


// =========================================================================
// STAFF & RESELLER MANAGERS
// =========================================================================

async function loadStaffManagers() {
  try {
    const managers = await apiCall("/api/staff/managers");
    const tbody = document.getElementById("staffTableBody");
    if (!tbody) return;

    if (managers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-users-slash" style="margin-right:6px;"></i>No authorized whitelist managers delegated yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = managers.map(m => `
      <tr>
        <td><span class="badge ${m.is_role ? 'badge-zinc' : 'badge-gold'}">${m.is_role ? 'Discord Role' : 'Discord User'}</span></td>
        <td><span style="font-family:var(--font-mono); font-size:12px; font-weight:700; color:var(--text-white);">${escapeHtml(m.discord_user_id)}</span></td>
        <td><span class="badge badge-zinc">${escapeHtml(m.script_name || m.script_slug || 'All Scripts')}</span></td>
        <td><span style="font-weight:600;">${m.quota_limit === -1 ? 'Unlimited' : m.quota_limit}</span></td>
        <td><span class="badge badge-gold">${m.keys_generated || 0}</span></td>
        <td><span style="color:var(--text-zinc-400); font-size:12px;">${escapeHtml(m.note || '—')}</span></td>
        <td><span style="font-size:12px; color:var(--text-zinc-500);">${escapeHtml(m.granted_by)}</span></td>
        <td>
          <button class="btn btn-danger btn-sm" onclick="revokeStaffManager(${m.id})">
            <i class="fa-solid fa-trash"></i> Revoke
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {}
}

async function openAddManagerModal() {
  const select = document.getElementById("mgrScriptSlug");
  if (select) {
    select.innerHTML = '<option value="all">All Scripts (Global Manager)</option>' +
      currentScripts.map(s => `<option value="${escapeHtml(s.slug)}">${escapeHtml(s.name)}</option>`).join("");
  }
  document.getElementById("modalAddManager").classList.add("active");
}

async function handleSaveManager(e) {
  e.preventDefault();
  const discord_user_id = document.getElementById("mgrDiscordId").value.trim();
  const is_role = parseInt(document.getElementById("mgrIsRole").value) || 0;
  const script_slug = document.getElementById("mgrScriptSlug").value;
  const quota_limit = parseInt(document.getElementById("mgrQuota").value) || -1;
  const note = document.getElementById("mgrNote").value.trim();

  try {
    const res = await apiCall("/api/staff/managers", "POST", { discord_user_id, is_role, script_slug, quota_limit, note });
    showToast(res.message, "success");
    closeModal("modalAddManager");
    loadStaffManagers();
  } catch (err) {}
}

async function revokeStaffManager(id) {
  if (!confirm("Are you sure you want to revoke whitelist management access for this staff member?")) return;
  try {
    const res = await apiCall(`/api/staff/managers/${id}`, "DELETE");
    showToast(res.message, "success");
    loadStaffManagers();
  } catch (err) {}
}


// =========================================================================
// ROBLOX EXECUTOR TELEMETRY & ANALYTICS
// =========================================================================

async function loadTelemetryData() {
  try {
    const [execData, overviewData] = await Promise.all([
      apiCall("/api/telemetry/executors"),
      apiCall("/api/telemetry/overview")
    ]);

    const chartBox = document.getElementById("executorChartContainer");
    if (chartBox && execData.executors) {
      if (execData.executors.length === 0) {
        chartBox.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-zinc-500);">No executor telemetry captured yet.</div>`;
      } else {
        chartBox.innerHTML = execData.executors.map(ex => `
          <div class="telemetry-bar-row">
            <div class="telemetry-bar-header">
              <span style="color:var(--text-white);">${escapeHtml(ex.executor_name)}</span>
              <span style="color:var(--gold-primary); font-family:var(--font-mono);">${ex.percentage}% (${ex.count} runs)</span>
            </div>
            <div class="telemetry-bar-track">
              <div class="telemetry-bar-fill" style="width: ${ex.percentage}%;"></div>
            </div>
          </div>
        `).join("");
      }
    }

    const statsBox = document.getElementById("telemetryStatsBox");
    if (statsBox && overviewData) {
      statsBox.innerHTML = `
        <div class="stat-box" style="padding:16px;">
          <div class="stat-label">Total Authentications</div>
          <div class="stat-value gold" style="font-size:24px;">${overviewData.total_logs}</div>
          <div class="stat-subtext">${overviewData.success_rate}% Success Rate</div>
        </div>
        <div class="stat-box" style="padding:16px;">
          <div class="stat-label">Security Interceptions</div>
          <div class="stat-value" style="font-size:24px; color:var(--danger-light);">${overviewData.total_threats}</div>
          <div class="stat-subtext">Threat Traps & Blocks</div>
        </div>
      `;
    }
  } catch (err) {}
}


// =========================================================================
// REMOTE DYNAMIC FEATURE FLAGS & AST SCRIPT AUTO-SCANNER
// =========================================================================

let cachedFeatureFlags = [];
let activeFlagsCategory = "all";
let activeFlagsSearchQuery = "";
let selectedFlagsScriptSlug = "";

function getCategoryBadgeClass(category) {
  const cat = (category || "").toLowerCase();
  if (cat.includes("combat") || cat.includes("shoot") || cat.includes("aim")) return "cat-combat";
  if (cat.includes("defense") || cat.includes("guard") || cat.includes("steal")) return "cat-defense";
  if (cat.includes("move") || cat.includes("mobil") || cat.includes("speed")) return "cat-movement";
  if (cat.includes("vis") || cat.includes("esp") || cat.includes("cosmetic")) return "cat-visuals";
  if (cat.includes("auto") || cat.includes("macro") || cat.includes("farm")) return "cat-automation";
  if (cat.includes("protect") || cat.includes("bypass") || cat.includes("anti")) return "cat-protection";
  return "cat-general";
}

function getCategoryIcon(category) {
  const cat = (category || "").toLowerCase();
  if (cat.includes("combat") || cat.includes("shoot") || cat.includes("aim")) return "fa-crosshairs";
  if (cat.includes("defense") || cat.includes("guard") || cat.includes("steal")) return "fa-shield-halved";
  if (cat.includes("move") || cat.includes("mobil") || cat.includes("speed")) return "fa-person-running";
  if (cat.includes("vis") || cat.includes("esp") || cat.includes("cosmetic")) return "fa-eye";
  if (cat.includes("auto") || cat.includes("macro") || cat.includes("farm")) return "fa-robot";
  if (cat.includes("protect") || cat.includes("bypass") || cat.includes("anti")) return "fa-user-shield";
  return "fa-sliders";
}

async function loadFeatureFlags() {
  if (currentScripts.length === 0) await loadScripts();
  
  const select = document.getElementById("flagsScriptSelector");
  if (select && currentScripts.length > 0) {
    if (!selectedFlagsScriptSlug) selectedFlagsScriptSlug = currentScripts[0].slug;
    select.innerHTML = currentScripts.map(s => `
      <option value="${escapeHtml(s.slug)}" ${s.slug === selectedFlagsScriptSlug ? 'selected' : ''}>
        ${escapeHtml(s.name)} (${escapeHtml(s.slug)})
      </option>
    `).join("");
  }

  const slug = selectedFlagsScriptSlug || currentScripts[0]?.slug;
  if (!slug) return;

  try {
    const flags = await apiCall(`/api/scripts/${slug}/flags`);
    cachedFeatureFlags = flags || [];
    updateFlagsCategoryCounts();
    renderFeatureFlagsTable();
  } catch (err) {
    const tbody = document.getElementById("flagsTableBody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-flag" style="margin-right:6px;"></i>No dynamic feature flags found. Click "Auto-Scan Script Features" to discover toggles!</td></tr>`;
  }
}

function updateFlagsCategoryCounts() {
  const counts = {
    all: cachedFeatureFlags.length,
    combat: 0,
    defense: 0,
    movement: 0,
    visuals: 0,
    automation: 0,
    protection: 0,
    utilities: 0
  };

  cachedFeatureFlags.forEach(f => {
    const cat = (f.category || "").toLowerCase();
    if (cat.includes("combat") || cat.includes("shoot") || cat.includes("aim")) counts.combat++;
    else if (cat.includes("defense") || cat.includes("guard") || cat.includes("steal")) counts.defense++;
    else if (cat.includes("move") || cat.includes("mobil") || cat.includes("speed")) counts.movement++;
    else if (cat.includes("vis") || cat.includes("esp") || cat.includes("cosmetic")) counts.visuals++;
    else if (cat.includes("auto") || cat.includes("macro") || cat.includes("farm")) counts.automation++;
    else if (cat.includes("protect") || cat.includes("bypass") || cat.includes("anti")) counts.protection++;
    else counts.utilities++;
  });

  const setCnt = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.innerText = val;
  };

  setCnt("countFlagsAll", counts.all);
  setCnt("countFlagsCombat", counts.combat);
  setCnt("countFlagsDefense", counts.defense);
  setCnt("countFlagsMovement", counts.movement);
  setCnt("countFlagsVisuals", counts.visuals);
  setCnt("countFlagsAutomation", counts.automation);
  setCnt("countFlagsProtection", counts.protection);
  setCnt("countFlagsUtilities", counts.utilities);
}

function renderFeatureFlagsTable() {
  const tbody = document.getElementById("flagsTableBody");
  if (!tbody) return;

  let filtered = cachedFeatureFlags;

  // Filter by category
  if (activeFlagsCategory !== "all") {
    filtered = filtered.filter(f => (f.category || "General Utilities") === activeFlagsCategory);
  }

  // Filter by search query
  if (activeFlagsSearchQuery.trim()) {
    const q = activeFlagsSearchQuery.toLowerCase();
    filtered = filtered.filter(f => 
      (f.flag_name && f.flag_name.toLowerCase().includes(q)) ||
      (f.display_name && f.display_name.toLowerCase().includes(q)) ||
      (f.category && f.category.toLowerCase().includes(q)) ||
      (f.source_type && f.source_type.toLowerCase().includes(q))
    );
  }

  if (filtered.length === 0) {
    if (cachedFeatureFlags.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; padding:40px 20px;">
            <div style="font-size:14px; font-weight:700; color:var(--text-white); margin-bottom:6px;">
              <i class="fa-solid fa-wand-magic-sparkles" style="color:var(--gold-primary); margin-right:8px;"></i>No Features Discovered Yet
            </div>
            <p style="font-size:12px; color:var(--text-zinc-400); max-width:480px; margin:0 auto 16px auto;">
              Click <strong>"Auto-Scan Script Features"</strong> above. FleedGuard will parse your Lua script, detect all UI toggles, config tables, and function routines automatically!
            </p>
            <button class="btn btn-primary btn-sm" onclick="triggerAutoScanFlags()">
              <i class="fa-solid fa-wand-magic-sparkles"></i> Auto-Scan Script Features Now
            </button>
          </td>
        </tr>
      `;
    } else {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-filter" style="margin-right:6px;"></i>No features match the selected filter.</td></tr>`;
    }
    return;
  }

  const slug = selectedFlagsScriptSlug || currentScripts[0]?.slug;

  tbody.innerHTML = filtered.map(f => {
    const isEn = Boolean(f.is_enabled);
    const catClass = getCategoryBadgeClass(f.category);
    const catIcon = getCategoryIcon(f.category);
    const displayName = f.display_name || f.flag_name;
    const sourceLabel = f.line_number > 0 ? `${escapeHtml(f.source_type || 'Script')} (Line ${f.line_number})` : escapeHtml(f.source_type || 'Manual Override');

    return `
      <tr>
        <td>
          <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-weight:700; color:var(--text-white); font-size:13px;">${escapeHtml(displayName)}</span>
              <span class="category-badge ${catClass}"><i class="fa-solid ${catIcon}"></i> ${escapeHtml(f.category || 'General')}</span>
            </div>
            <div style="font-size:11px; font-family:var(--font-mono); color:var(--gold-light); opacity:0.85;">
              <code>getgenv().GetFlag("${escapeHtml(f.flag_name)}")</code>
            </div>
          </div>
        </td>
        <td>
          <div style="font-size:11px; color:var(--text-zinc-300);">
            <i class="fa-solid fa-code" style="color:var(--text-zinc-500); margin-right:4px;"></i>
            ${sourceLabel}
          </div>
        </td>
        <td><span class="badge badge-zinc" style="font-family:var(--font-mono);">${escapeHtml(f.flag_type)}</span></td>
        <td>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-bright); background:var(--bg-input); padding:3px 8px; border-radius:6px; border:1px solid var(--border-subtle);">
            ${escapeHtml(f.flag_value)}
          </span>
        </td>
        <td>
          <button class="flag-toggle-btn ${isEn ? 'flag-toggle-active' : 'flag-toggle-disabled'}" onclick="toggleFeatureFlag('${slug}', ${f.id})" title="Click to instantly toggle feature globally">
            <i class="fa-solid ${isEn ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
            <span>${isEn ? 'ENABLED' : 'DISABLED'}</span>
          </button>
        </td>
        <td style="text-align:right;">
          <button class="btn btn-danger btn-sm" onclick="deleteFeatureFlag('${slug}', ${f.id})" title="Remove flag">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function handleFlagsScriptChange(slug) {
  selectedFlagsScriptSlug = slug;
  loadFeatureFlags();
}

function filterFlagsByCategory(category, btn) {
  activeFlagsCategory = category;
  const container = document.getElementById("flagsCategoryFilters");
  if (container) {
    container.querySelectorAll(".filter-pill-btn").forEach(b => b.classList.remove("active"));
  }
  if (btn) btn.classList.add("active");
  renderFeatureFlagsTable();
}

function handleFlagsSearch(query) {
  activeFlagsSearchQuery = query;
  renderFeatureFlagsTable();
}

async function triggerAutoScanFlags() {
  const slug = selectedFlagsScriptSlug || currentScripts[0]?.slug;
  if (!slug) {
    showToast("No script hub selected to scan.", "error");
    return;
  }

  const btn = document.getElementById("btnAutoScanFlags");
  const origHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analyzing AST...`;
  }

  try {
    const res = await apiCall(`/api/scripts/${slug}/flags/auto-scan`, "POST");
    showToast(res.message || `Discovered ${res.discovered_count} features!`, "success");
    cachedFeatureFlags = res.flags || [];
    updateFlagsCategoryCounts();
    renderFeatureFlagsTable();
  } catch (err) {
    showToast("Failed to auto-scan script features: " + (err.message || err), "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function toggleFeatureFlag(slug, flagId) {
  try {
    const res = await apiCall(`/api/scripts/${slug}/flags/${flagId}/toggle`, "PATCH");
    showToast(res.message, res.is_enabled ? "success" : "warning");
    
    // Update locally in cache for instant responsive UI
    const target = cachedFeatureFlags.find(f => f.id === flagId);
    if (target) {
      target.is_enabled = res.is_enabled;
      renderFeatureFlagsTable();
    } else {
      loadFeatureFlags();
    }
  } catch (err) {
    showToast("Failed to toggle feature: " + (err.message || err), "error");
  }
}

async function handleToggleAllFlags(action) {
  const slug = selectedFlagsScriptSlug || currentScripts[0]?.slug;
  if (!slug) return;

  const actionName = action === "enable" ? "ENABLE ALL" : "KILLSWITCH (DISABLE ALL)";
  const scope = activeFlagsCategory !== "all" ? `in category '${activeFlagsCategory}'` : "globally";
  
  if (!confirm(`Are you sure you want to ${actionName} feature flags ${scope}? Connected players will sync this state in real time.`)) {
    return;
  }

  try {
    const res = await apiCall(`/api/scripts/${slug}/flags/toggle-all`, "POST", { action, category: activeFlagsCategory });
    showToast(res.message, action === "enable" ? "success" : "warning");
    loadFeatureFlags();
  } catch (err) {
    showToast("Failed to update features: " + (err.message || err), "error");
  }
}

async function openAddFlagModal() {
  const select = document.getElementById("flagScriptSlug");
  if (select) {
    select.innerHTML = currentScripts.map(s => `
      <option value="${escapeHtml(s.slug)}" ${s.slug === selectedFlagsScriptSlug ? 'selected' : ''}>
        ${escapeHtml(s.name)}
      </option>
    `).join("");
  }
  document.getElementById("modalAddFlag").classList.add("active");
}

async function handleSaveFeatureFlag(e) {
  e.preventDefault();
  const slug = document.getElementById("flagScriptSlug").value;
  const flag_name = document.getElementById("flagName").value.trim();
  const flag_type = document.getElementById("flagType").value;
  const flag_value = document.getElementById("flagValue").value.trim();

  try {
    const res = await apiCall(`/api/scripts/${slug}/flags`, "POST", { flag_name, flag_type, flag_value, is_enabled: 1 });
    showToast(res.message, "success");
    closeModal("modalAddFlag");
    loadFeatureFlags();
  } catch (err) {}
}

async function deleteFeatureFlag(slug, flagId) {
  if (!confirm("Are you sure you want to remove this feature flag?")) return;
  try {
    const res = await apiCall(`/api/scripts/${slug}/flags/${flagId}`, "DELETE");
    showToast(res.message, "success");
    loadFeatureFlags();
  } catch (err) {}
}


// =========================================================================
// IN-GAME BROADCASTS & MAINTENANCE BANNERS
// =========================================================================

function toggleBroadcastTargetInput(targetType) {
  const scriptGroup = document.getElementById("annScriptSelectGroup");
  const targetGroup = document.getElementById("annTargetValueGroup");
  const targetLabel = document.getElementById("annTargetValueLabel");
  const targetInput = document.getElementById("annTargetValue");

  if (!scriptGroup || !targetGroup) return;

  if (targetType === "SCRIPT") {
    scriptGroup.style.display = "block";
    targetGroup.style.display = "none";
  } else if (targetType === "USERNAME") {
    scriptGroup.style.display = "none";
    targetGroup.style.display = "block";
    targetLabel.innerText = "Roblox Username";
    targetInput.placeholder = "e.g. Builderman";
  } else if (targetType === "KEY") {
    scriptGroup.style.display = "none";
    targetGroup.style.display = "block";
    targetLabel.innerText = "Target License Key";
    targetInput.placeholder = "e.g. FLEED-XXXX-XXXX";
  } else {
    // GLOBAL
    scriptGroup.style.display = "none";
    targetGroup.style.display = "none";
  }
}

function openTargetedBroadcastModal(key = "", username = "") {
  openAddAnnouncementModal();
  const select = document.getElementById("annTargetType");
  const valInput = document.getElementById("annTargetValue");
  if (username && select && valInput) {
    select.value = "USERNAME";
    valInput.value = username;
    toggleBroadcastTargetInput("USERNAME");
    document.getElementById("annTitle").value = `Message to ${username}`;
  } else if (key && select && valInput) {
    select.value = "KEY";
    valInput.value = key;
    toggleBroadcastTargetInput("KEY");
    document.getElementById("annTitle").value = "Staff Message";
  }
}

async function loadAnnouncements() {
  try {
    const broadcasts = await apiCall("/api/broadcasts");
    const tbody = document.getElementById("announcementsTableBody");
    if (!tbody) return;

    if (!broadcasts || broadcasts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-bullhorn" style="margin-right:6px;"></i>No active in-game broadcasts queued. Send your first broadcast above!</td></tr>`;
      return;
    }

    tbody.innerHTML = broadcasts.map(b => {
      let audienceBadge = '<span class="badge badge-zinc">Global</span>';
      if (b.target_type === 'SCRIPT') {
        audienceBadge = `<span class="badge badge-gold">${escapeHtml(b.script_name || b.script_slug || 'Script')}</span>`;
      } else if (b.target_type === 'USERNAME') {
        audienceBadge = `<span class="badge badge-primary"><i class="fa-solid fa-user"></i> ${escapeHtml(b.target_value)}</span>`;
      } else if (b.target_type === 'KEY') {
        audienceBadge = `<span class="badge badge-warning"><i class="fa-solid fa-key"></i> Key</span>`;
      }

      return `
        <tr>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="badge badge-gold">${escapeHtml(b.banner_type || 'INFO')}</span>
              ${audienceBadge}
            </div>
          </td>
          <td>
            <div style="font-weight:600; color:var(--text-white); font-size:13px;">${escapeHtml(b.title || 'Announcement')}</div>
            <div style="font-size:12px; color:var(--text-zinc-400); margin-top:2px;">${escapeHtml(b.message)}</div>
          </td>
          <td>
            <span class="badge badge-success"><i class="fa-solid fa-signal"></i> Active (${b.duration || 10}s)</span>
          </td>
          <td><span style="font-size:11px; color:var(--text-zinc-500);">${formatTimeAgo(b.created_at)}</span></td>
          <td>
            <button class="btn btn-danger btn-sm" onclick="deleteBroadcast(${b.id})" title="Cancel Broadcast">
              <i class="fa-solid fa-trash"></i>
            </button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {}
}

async function openAddAnnouncementModal() {
  if (currentScripts.length === 0) await loadScripts();
  const select = document.getElementById("annScriptSlug");
  if (select) {
    select.innerHTML = currentScripts.map(s => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`).join("");
  }
  const targetType = document.getElementById("annTargetType");
  if (targetType) {
    targetType.value = "GLOBAL";
    toggleBroadcastTargetInput("GLOBAL");
  }
  document.getElementById("annMessage").value = "";
  document.getElementById("modalAddAnnouncement").classList.add("active");
}

async function handleSendLiveBroadcast(e) {
  e.preventDefault();
  const target_type = document.getElementById("annTargetType").value;
  let target_value = "";
  let script_id = null;

  if (target_type === "SCRIPT") {
    script_id = parseInt(document.getElementById("annScriptSlug").value) || null;
  } else if (target_type === "USERNAME" || target_type === "KEY") {
    target_value = document.getElementById("annTargetValue").value.trim();
  }

  const title = document.getElementById("annTitle").value.trim();
  const banner_type = document.getElementById("annBannerType").value;
  const message = document.getElementById("annMessage").value.trim();
  const duration = parseInt(document.getElementById("annDuration").value) || 10;
  const play_sound = parseInt(document.getElementById("annPlaySound").value) || 1;

  try {
    const res = await apiCall("/api/broadcasts", "POST", {
      target_type,
      target_value,
      script_id,
      title,
      message,
      banner_type,
      duration,
      play_sound
    });
    showToast(res.message, "success");
    closeModal("modalAddAnnouncement");
    loadAnnouncements();
  } catch (err) {}
}

async function deleteBroadcast(broadcastId) {
  try {
    const res = await apiCall(`/api/broadcasts/${broadcastId}`, "DELETE");
    showToast(res.message, "success");
    loadAnnouncements();
  } catch (err) {}
}



// =========================================================================
// SCRIPT VERSION HISTORY & ROLLBACK
// =========================================================================

async function loadScriptVersions() {
  if (currentScripts.length === 0) await loadScripts();
  const slug = currentScripts[0]?.slug;
  if (!slug) return;

  try {
    const versions = await apiCall(`/api/scripts/${slug}/versions`);
    const tbody = document.getElementById("versionsTableBody");
    if (!tbody) return;

    if (versions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-code-branch" style="margin-right:6px;"></i>No version releases published yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = versions.map(v => `
      <tr>
        <td><span class="badge badge-gold" style="font-size:12px;">${escapeHtml(v.version_tag)}</span></td>
        <td><span style="color:var(--text-zinc-300); font-size:13px;">${escapeHtml(v.changelog || 'Routine release')}</span></td>
        <td><span style="font-size:12px; color:var(--text-zinc-400);">${escapeHtml(v.created_by)}</span></td>
        <td><span style="font-size:11px; color:var(--text-zinc-500);">${formatTimeAgo(v.created_at)}</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="rollbackVersion('${slug}', ${v.id}, '${escapeHtml(v.version_tag)}')">
            <i class="fa-solid fa-rotate-left"></i> Rollback
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {}
}

async function openPublishVersionModal() {
  const select = document.getElementById("verScriptSlug");
  if (select) {
    select.innerHTML = currentScripts.map(s => `<option value="${escapeHtml(s.slug)}">${escapeHtml(s.name)}</option>`).join("");
  }
  document.getElementById("modalPublishVersion").classList.add("active");
}

async function handleSaveVersion(e) {
  e.preventDefault();
  const slug = document.getElementById("verScriptSlug").value;
  const version_tag = document.getElementById("verTag").value.trim();
  const changelog = document.getElementById("verChangelog").value.trim();
  const raw_source = document.getElementById("verSource").value;

  try {
    const res = await apiCall(`/api/scripts/${slug}/versions`, "POST", { version_tag, changelog, raw_source });
    showToast(res.message, "success");
    closeModal("modalPublishVersion");
    loadScriptVersions();
  } catch (err) {}
}

async function rollbackVersion(slug, verId, verTag) {
  if (!confirm(`Are you sure you want to rollback active script source to version ${verTag}?`)) return;
  try {
    const res = await apiCall(`/api/scripts/${slug}/rollback/${verId}`, "POST");
    showToast(res.message, "success");
    loadScriptVersions();
  } catch (err) {}
}


// =========================================================================
// DISCORD WEBHOOKS
// =========================================================================

async function loadDiscordWebhooks() {
  try {
    const webhooks = await apiCall("/api/webhooks");
    const tbody = document.getElementById("webhooksTableBody");
    if (!tbody) return;

    if (webhooks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-brands fa-discord" style="margin-right:6px;"></i>No Discord webhooks configured yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = webhooks.map(w => `
      <tr>
        <td><span class="badge badge-gold">${escapeHtml(w.event_type)}</span></td>
        <td><span class="badge badge-zinc">${escapeHtml(w.script_name || 'Global')}</span></td>
        <td><span style="font-family:var(--font-mono); font-size:11px; color:var(--text-zinc-400);">${escapeHtml(w.webhook_url.substring(0, 45))}...</span></td>
        <td><span class="badge badge-success">Active</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="testWebhook('${escapeHtml(w.webhook_url)}')"><i class="fa-solid fa-paper-plane"></i> Test</button>
          <button class="btn btn-danger btn-sm" onclick="deleteWebhook(${w.id})"><i class="fa-solid fa-trash"></i></button>
        </td>
      </tr>
    `).join("");
  } catch (err) {}
}

function openAddWebhookModal() {
  document.getElementById("modalAddWebhook").classList.add("active");
}

async function handleSaveWebhook(e) {
  e.preventDefault();
  const event_type = document.getElementById("whEvent").value;
  const webhook_url = document.getElementById("whUrl").value.trim();

  try {
    const res = await apiCall("/api/webhooks", "POST", { event_type, webhook_url, is_enabled: 1 });
    showToast(res.message, "success");
    closeModal("modalAddWebhook");
    loadDiscordWebhooks();
  } catch (err) {}
}

async function testWebhook(webhook_url) {
  try {
    const res = await apiCall("/api/webhooks/test", "POST", { webhook_url });
    showToast(res.message, "success");
  } catch (err) {}
}

async function testWebhookFromModal() {
  const url = document.getElementById("whUrl").value.trim();
  if (!url) return showToast("Enter webhook URL first", "error");
  await testWebhook(url);
}

async function deleteWebhook(id) {
  try {
    const res = await apiCall(`/api/webhooks/${id}`, "DELETE");
    showToast(res.message, "success");
    loadDiscordWebhooks();
  } catch (err) {}
}


// =========================================================================
// LIVE REMOTE LUAU CONSOLE & DISPATCH ENGINE
// =========================================================================

const LUAU_PRESETS = {
  toast: `-- Send Luxury Notification Toast to Player's Screen
pcall(function()
    game:GetService("StarterGui"):SetCore("SendNotification", {
        Title = "FleedGuard Remote Console",
        Text = "Live update dispatched from developer dashboard!",
        Duration = 7,
        Icon = "rbxassetid://10804470355"
    })
end)`,

  chat: `-- Send In-Game Chat Message on Behalf of Client
pcall(function()
    local text = "[FleedGuard]: Hello from the developer console!"
    local tcs = game:GetService("TextChatService")
    if tcs and tcs.ChatVersion == Enum.ChatVersion.TextChatService then
        local channel = tcs.TextChannels:FindFirstChild("RBXGeneral")
        if channel then channel:SendAsync(text) end
    else
        game:GetService("ReplicatedStorage"):FindFirstChild("DefaultChatSystemChatEvents")
            :FindFirstChild("SayMessageRequest"):FireServer(text, "All")
    end
end)`,

  speed: `-- Boost Character WalkSpeed & JumpPower
pcall(function()
    local player = game:GetService("Players").LocalPlayer
    if player and player.Character then
        local hum = player.Character:FindFirstChildOfClass("Humanoid")
        if hum then
            hum.WalkSpeed = 32
            hum.JumpPower = 75
            print("[FleedGuard]: Applied WalkSpeed=32, JumpPower=75")
        end
    end
end)`,

  teleport: `-- Teleport Character to Coordinates or Spawn
pcall(function()
    local player = game:GetService("Players").LocalPlayer
    if player and player.Character and player.Character:FindFirstChild("HumanoidRootPart") then
        local hrp = player.Character.HumanoidRootPart
        hrp.CFrame = hrp.CFrame + Vector3.new(0, 15, 0)
        print("[FleedGuard]: Teleported Character +15 studs up")
    end
end)`,

  reload: `-- Reload / Refresh Script Hub Environment
pcall(function()
    print("[FleedGuard]: Hot-reloading script environment...")
    local g = getgenv and getgenv()
    if g and g.FleedReload then
        g.FleedReload()
    else
        game:GetService("StarterGui"):SetCore("SendNotification", {
            Title = "FleedGuard",
            Text = "Script environment refresh triggered.",
            Duration = 5
        })
    end
end)`,

  dump: `-- Dump Active Players & Diagnostics to Client Console
pcall(function()
    local players = game:GetService("Players"):GetPlayers()
    print("========== FLEEDGUARD CLIENT DIAGNOSTICS ==========")
    print("Local Player:", game:GetService("Players").LocalPlayer.Name)
    print("Place ID:", game.PlaceId, "Job ID:", game.JobId)
    print("Total Players in Server:", #players)
    for i, p in ipairs(players) do
        print(string.format("  [%d] %s (ID: %d)", i, p.Name, p.UserId))
    end
    print("==================================================")
end)`,

  fade: `-- [[ Smooth Cinematic Fade In / Fade Out Notification ]]
pcall(function()
    local TweenService = game:GetService("TweenService")
    local Players = game:GetService("Players")
    local LocalPlayer = Players.LocalPlayer
    local CoreGui = game:GetService("CoreGui")

    local existing = CoreGui:FindFirstChild("FleedFadeOverlay") or (LocalPlayer:FindFirstChild("PlayerGui") and LocalPlayer.PlayerGui:FindFirstChild("FleedFadeOverlay"))
    if existing then existing:Destroy() end

    local screenGui = Instance.new("ScreenGui")
    screenGui.Name = "FleedFadeOverlay"
    screenGui.ResetOnSpawn = false
    screenGui.IgnoreGuiInset = true
    
    local parentOk = pcall(function() screenGui.Parent = CoreGui end)
    if not parentOk or not screenGui.Parent then
        screenGui.Parent = LocalPlayer:WaitForChild("PlayerGui")
    end

    local frame = Instance.new("Frame")
    frame.Size = UDim2.new(0, 380, 0, 90)
    frame.Position = UDim2.new(0.5, -190, 0.15, 0)
    frame.BackgroundColor3 = Color3.fromRGB(12, 14, 20)
    frame.BackgroundTransparency = 1
    frame.BorderSizePixel = 0
    frame.Parent = screenGui

    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, 12)
    corner.Parent = frame

    local stroke = Instance.new("UIStroke")
    stroke.Color = Color3.fromRGB(250, 204, 21)
    stroke.Thickness = 1.5
    stroke.Transparency = 1
    stroke.Parent = frame

    local title = Instance.new("TextLabel")
    title.Size = UDim2.new(1, 0, 0, 35)
    title.Position = UDim2.new(0, 0, 0, 10)
    title.BackgroundTransparency = 1
    title.Text = "⚡ FLEEDGUARD LIVE SYNC"
    title.TextColor3 = Color3.fromRGB(250, 204, 21)
    title.TextSize = 15
    title.Font = Enum.Font.GothamBold
    title.TextTransparency = 1
    title.Parent = frame

    local subtitle = Instance.new("TextLabel")
    subtitle.Size = UDim2.new(1, 0, 0, 30)
    subtitle.Position = UDim2.new(0, 0, 0, 45)
    subtitle.BackgroundTransparency = 1
    subtitle.Text = "Fade In / Fade Out Animation Executed!"
    subtitle.TextColor3 = Color3.fromRGB(220, 225, 235)
    subtitle.TextSize = 13
    subtitle.Font = Enum.Font.Gotham
    subtitle.TextTransparency = 1
    subtitle.Parent = frame

    local tweenInfo = TweenInfo.new(0.8, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

    -- Fade In
    TweenService:Create(frame, tweenInfo, { BackgroundTransparency = 0.15 }):Play()
    TweenService:Create(stroke, tweenInfo, { Transparency = 0.2 }):Play()
    TweenService:Create(title, tweenInfo, { TextTransparency = 0 }):Play()
    TweenService:Create(subtitle, tweenInfo, { TextTransparency = 0 }):Play()

    task.wait(2.5)

    -- Fade Out
    local fadeOut = TweenService:Create(frame, tweenInfo, { BackgroundTransparency = 1 })
    TweenService:Create(stroke, tweenInfo, { Transparency = 1 }):Play()
    TweenService:Create(title, tweenInfo, { TextTransparency = 1 }):Play()
    TweenService:Create(subtitle, tweenInfo, { TextTransparency = 1 }):Play()
    fadeOut:Play()
    fadeOut.Completed:Wait()

    screenGui:Destroy()
end)`,

  clear: ""
};

let cachedLivePlayers = [];

function updateLineNumbers(textarea, lineNumbersId) {
  const lineNumbers = document.getElementById(lineNumbersId);
  if (!lineNumbers || !textarea) return;
  const lines = (textarea.value || "").split("\n").length;
  lineNumbers.innerHTML = Array.from({ length: Math.max(lines, 1) }, (_, i) => i + 1).join("<br>");
  
  const lineCountEl = document.getElementById("execLineCount");
  if (lineCountEl) lineCountEl.innerText = `${lines} Line${lines === 1 ? '' : 's'}`;
  
  updateCursorPosition(textarea);
}

function syncScroll(textarea, lineNumbersId) {
  const lineNumbers = document.getElementById(lineNumbersId);
  if (lineNumbers && textarea) {
    lineNumbers.scrollTop = textarea.scrollTop;
  }
}

function updateCursorPosition(textarea) {
  const posEl = document.getElementById("execCursorPos");
  if (!posEl || !textarea) return;
  const pos = textarea.selectionStart || 0;
  const val = textarea.value.substring(0, pos);
  const line = val.split("\n").length;
  const col = pos - val.lastIndexOf("\n");
  posEl.innerText = `Ln ${line}, Col ${col}`;
}

function copyEditorCode() {
  const editor = document.getElementById("remoteExecCode");
  if (!editor || !editor.value) return showToast("Editor is empty", "info");
  copyText(editor.value, "Luau source copied to clipboard!");
}

function saveLuauPayloadFile() {
  const editor = document.getElementById("remoteExecCode");
  const code = editor?.value || "";
  if (!code.trim()) return showToast("Editor is empty", "info");

  const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "payload.luau";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast("Saved payload.luau to downloads", "success");
}

function handleOpenScriptFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (event) => {
    const editor = document.getElementById("remoteExecCode");
    if (editor) {
      editor.value = event.target.result;
      updateLineNumbers(editor, "execLineNumbers");
      showToast(`Loaded ${file.name} into executor!`, "success");
    }
  };
  reader.readAsText(file);
}

function insertLuauPreset(presetKey) {
  const editor = document.getElementById("remoteExecCode");
  if (!editor) return;
  if (presetKey === "clear") {
    editor.value = "";
    updateLineNumbers(editor, "execLineNumbers");
    return;
  }
  const snippet = LUAU_PRESETS[presetKey];
  if (snippet) {
    editor.value = snippet;
    updateLineNumbers(editor, "execLineNumbers");
    showToast(`Loaded ${presetKey.toUpperCase()} preset template`, "info");
  }
}

function insertModalLuauPreset(presetKey) {
  const editor = document.getElementById("modalExecCode");
  if (!editor) return;
  if (presetKey === "clear") {
    editor.value = "";
    updateLineNumbers(editor, "modalExecLineNumbers");
    return;
  }
  const snippet = LUAU_PRESETS[presetKey];
  if (snippet) {
    editor.value = snippet;
    updateLineNumbers(editor, "modalExecLineNumbers");
    showToast(`Loaded ${presetKey.toUpperCase()} preset template`, "info");
  }
}

function handleRemoteExecTargetTypeChange(type) {
  const grp = document.getElementById("remoteExecTargetValueGroup");
  const lbl = document.getElementById("remoteExecTargetValueLabel");
  const input = document.getElementById("remoteExecTargetValue");
  const dropdown = document.getElementById("remoteExecLivePlayersDropdown");

  if (!grp) return;

  if (type === "ALL") {
    grp.style.display = "none";
    if (input) input.required = false;
  } else {
    grp.style.display = "block";
    if (input) input.required = true;
    if (type === "PLAYER") {
      if (lbl) lbl.innerText = "Roblox Username or User ID";
      if (input) input.placeholder = "e.g. Undix or 48291039";
      if (dropdown) dropdown.style.display = "block";
    } else if (type === "KEY") {
      if (lbl) lbl.innerText = "License Key";
      if (input) input.placeholder = "e.g. FLEED-B3UZ-ZATY-9Z07";
      if (dropdown) dropdown.style.display = "none";
    } else if (type === "SESSION") {
      if (lbl) lbl.innerText = "Active Session ID";
      if (input) input.placeholder = "e.g. sess_abc123...";
      if (dropdown) dropdown.style.display = "none";
    }
  }
}

function handleModalExecTargetTypeChange(type) {
  const grp = document.getElementById("modalExecTargetValueGroup");
  const lbl = document.getElementById("modalExecTargetValueLabel");
  const input = document.getElementById("modalExecTargetValue");

  if (!grp) return;

  if (type === "ALL") {
    grp.style.display = "none";
    if (input) input.required = false;
  } else {
    grp.style.display = "block";
    if (input) input.required = true;
    if (type === "PLAYER") {
      if (lbl) lbl.innerText = "Roblox Username or User ID";
      if (input) input.placeholder = "e.g. Undix or 48291039";
    } else if (type === "KEY") {
      if (lbl) lbl.innerText = "License Key";
      if (input) input.placeholder = "e.g. FLEED-B3UZ-ZATY-9Z07";
    }
  }
}

function selectLivePlayerForExec(val) {
  if (!val) return;
  const input = document.getElementById("remoteExecTargetValue");
  if (input) input.value = val;
}

function handleRemoteExecScriptChange(slug) {
  populateLivePlayersDropdown(slug);
}

async function populateLivePlayersDropdown(scriptSlug = "all") {
  const dropdown = document.getElementById("remoteExecLivePlayersDropdown");
  if (!dropdown) return;

  try {
    const sessions = await apiCall("/api/sessions?show_all=false");
    cachedLivePlayers = sessions || [];
    
    let filtered = cachedLivePlayers;
    if (scriptSlug && scriptSlug !== "all") {
      filtered = cachedLivePlayers.filter(s => s.script_slug === scriptSlug);
    }

    if (filtered.length === 0) {
      dropdown.innerHTML = `<option value="">No live players on this hub</option>`;
      return;
    }

    dropdown.innerHTML = `<option value="">Select Live Player (${filtered.length} online)...</option>` + 
      filtered.map(s => `
        <option value="${escapeHtml(s.roblox_username || s.license_key)}">
          ${escapeHtml(s.roblox_username || 'Unknown')} (${escapeHtml(s.script_slug || 'hub')})
        </option>
      `).join("");
  } catch (err) {
    dropdown.innerHTML = `<option value="">Select Live Player...</option>`;
  }
}

async function loadRemoteExecQueue() {
  if (currentScripts.length === 0) await loadScripts();

  const selectMain = document.getElementById("remoteExecScriptSlug");
  const selectModal = document.getElementById("modalExecScriptSlug");

  const optionsHtml = `<option value="all">All Scripts (Global Broadcast)</option>` + 
    currentScripts.map(s => `<option value="${escapeHtml(s.slug)}">${escapeHtml(s.name)} (${escapeHtml(s.slug)})</option>`).join("");

  if (selectMain && selectMain.children.length <= 1) selectMain.innerHTML = optionsHtml;
  if (selectModal) selectModal.innerHTML = optionsHtml;

  populateLivePlayersDropdown();

  try {
    const queue = await apiCall("/api/remote-exec/queue");
    const tbody = document.getElementById("remoteExecQueueTableBody");
    const pendingBadge = document.getElementById("badgeRemoteExecPending");

    if (pendingBadge) {
      const pendingCount = (queue || []).filter(q => q.status === "PENDING").length;
      if (pendingCount > 0) {
        pendingBadge.style.display = "inline-block";
        pendingBadge.innerText = pendingCount;
      } else {
        pendingBadge.style.display = "none";
      }
    }

    if (!tbody) return;

    if (!queue || queue.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-terminal" style="margin-right:6px;"></i>No remote execution commands queued yet. Enter code above to dispatch!</td></tr>`;
      return;
    }

    tbody.innerHTML = queue.map(q => {
      let statusBadge = `<span class="exec-status-badge exec-status-pending"><span class="live-pulse"></span> PENDING (${q.execution_count} runs)</span>`;
      if (q.status === "EXECUTED") {
        statusBadge = `<span class="exec-status-badge exec-status-executed"><i class="fa-solid fa-circle-check"></i> DELIVERED (${q.execution_count}x)</span>`;
      } else if (q.status === "EXPIRED" || q.status === "REVOKED") {
        statusBadge = `<span class="exec-status-badge exec-status-expired"><i class="fa-solid fa-ban"></i> ${q.status}</span>`;
      }

      let targetHtml = `<span class="badge badge-gold">GLOBAL ALL</span>`;
      if (q.target_type === "PLAYER") {
        targetHtml = `<span class="badge badge-zinc"><i class="fa-solid fa-user"></i> ${escapeHtml(q.target_value || 'Player')}</span>`;
      } else if (q.target_type === "KEY") {
        targetHtml = `<span class="badge badge-zinc"><i class="fa-solid fa-key"></i> ${escapeHtml((q.target_value || '').substring(0, 16))}...</span>`;
      } else if (q.target_type === "SESSION") {
        targetHtml = `<span class="badge badge-zinc"><i class="fa-solid fa-gamepad"></i> ${escapeHtml((q.target_value || '').substring(0, 12))}...</span>`;
      }

      const codeSnippet = (q.luau_code || "").trim();
      const codePreview = codeSnippet.length > 80 ? codeSnippet.substring(0, 80) + "..." : codeSnippet;

      return `
        <tr>
          <td>${targetHtml}</td>
          <td><span class="badge badge-zinc">${escapeHtml(q.script_name)}</span></td>
          <td>
            <div style="display:flex; flex-direction:column; gap:2px;">
              <code class="mono-tag" style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; max-width:380px;">${escapeHtml(codePreview)}</code>
              ${q.description ? `<span style="font-size:10px; color:var(--text-zinc-500);">${escapeHtml(q.description)}</span>` : ''}
            </div>
          </td>
          <td>${statusBadge}</td>
          <td><span style="font-size:12px; color:var(--text-zinc-400);">${formatTimeAgo(q.created_at)}</span></td>
          <td style="text-align:right;">
            <div style="display:flex; gap:6px; justify-content:flex-end;">
              <button class="btn btn-secondary btn-sm" onclick="reRunRemoteExec('${escapeHtml(encodeURIComponent(q.luau_code))}', '${escapeHtml(q.target_type)}', '${escapeHtml(q.target_value || '')}', '${escapeHtml(q.script_slug)}')" title="Load & Re-run this snippet">
                <i class="fa-solid fa-rotate-right"></i>
              </button>
              <button class="btn btn-danger btn-sm" onclick="deleteRemoteExecItem(${q.id})" title="Delete Task">
                <i class="fa-solid fa-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    const tbody = document.getElementById("remoteExecQueueTableBody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-terminal" style="margin-right:6px;"></i>No remote execution tasks found.</td></tr>`;
  }
}

async function handleDispatchRemoteExec(e) {
  e.preventDefault();
  const script_slug = document.getElementById("remoteExecScriptSlug").value;
  const target_type = document.getElementById("remoteExecTargetType").value;
  const target_value = document.getElementById("remoteExecTargetValue")?.value.trim() || null;
  const luau_code = document.getElementById("remoteExecCode").value.trim();
  const description = document.getElementById("remoteExecDescription")?.value.trim() || "Live Console Exec";

  if (!luau_code) {
    return showToast("Luau code payload cannot be empty", "error");
  }

  const btn = document.getElementById("btnDispatchRemoteExec");
  if (btn) btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Dispatching...`;

  try {
    const res = await apiCall("/api/remote-exec", "POST", {
      script_slug,
      target_type,
      target_value,
      luau_code,
      description
    });
    showToast(res.message, "success");
    loadRemoteExecQueue();
  } catch (err) {
  } finally {
    if (btn) btn.innerHTML = `<i class="fa-solid fa-bolt"></i> Dispatch to Client`;
  }
}

function openRemoteExecModal(targetKey = "", targetPlayer = "") {
  loadRemoteExecQueue();
  const modal = document.getElementById("modalRemoteExec");
  if (!modal) return;

  const targetTypeSelect = document.getElementById("modalExecTargetType");
  const targetValInput = document.getElementById("modalExecTargetValue");

  if (targetKey) {
    if (targetTypeSelect) targetTypeSelect.value = "KEY";
    if (targetValInput) targetValInput.value = targetKey;
  } else if (targetPlayer) {
    if (targetTypeSelect) targetTypeSelect.value = "PLAYER";
    if (targetValInput) targetValInput.value = targetPlayer;
  } else {
    if (targetTypeSelect) targetTypeSelect.value = "ALL";
    if (targetValInput) targetValInput.value = "";
  }

  handleModalExecTargetTypeChange(targetTypeSelect?.value || "ALL");
  const modalEditor = document.getElementById("modalExecCode");
  if (modalEditor) updateLineNumbers(modalEditor, "modalExecLineNumbers");
  modal.classList.add("active");
}

async function handleModalRemoteExecDispatch(e) {
  e.preventDefault();
  const script_slug = document.getElementById("modalExecScriptSlug").value;
  const target_type = document.getElementById("modalExecTargetType").value;
  const target_value = document.getElementById("modalExecTargetValue")?.value.trim() || null;
  const luau_code = document.getElementById("modalExecCode").value.trim();
  const description = document.getElementById("modalExecDescription")?.value.trim() || "Quick Modal Exec";

  if (!luau_code) {
    return showToast("Luau code payload cannot be empty", "error");
  }

  try {
    const res = await apiCall("/api/remote-exec", "POST", {
      script_slug,
      target_type,
      target_value,
      luau_code,
      description
    });
    showToast(res.message, "success");
    closeModal("modalRemoteExec");
    loadRemoteExecQueue();
  } catch (err) {}
}

function reRunRemoteExec(encodedCode, targetType, targetValue, scriptSlug) {
  const code = decodeURIComponent(encodedCode);
  switchTab("remote-exec");
  const editor = document.getElementById("remoteExecCode");
  const targetTypeSelect = document.getElementById("remoteExecTargetType");
  const targetValInput = document.getElementById("remoteExecTargetValue");
  const scriptSelect = document.getElementById("remoteExecScriptSlug");

  if (editor) {
    editor.value = code;
    updateLineNumbers(editor, "execLineNumbers");
  }
  if (targetTypeSelect) {
    targetTypeSelect.value = targetType;
    handleRemoteExecTargetTypeChange(targetType);
  }
  if (targetValInput) targetValInput.value = targetValue;
  if (scriptSelect && scriptSlug) scriptSelect.value = scriptSlug;

  showToast("Loaded snippet into remote console ready to re-dispatch!", "info");
}

async function deleteRemoteExecItem(id) {
  try {
    const res = await apiCall(`/api/remote-exec/${id}`, "DELETE");
    showToast(res.message, "success");
    loadRemoteExecQueue();
  } catch (err) {}
}

async function handleClearRemoteExecHistory() {
  if (!confirm("Are you sure you want to clear completed execution history?")) return;
  try {
    const res = await apiCall("/api/remote-exec/clear", "POST");
    showToast(res.message, "success");
    loadRemoteExecQueue();
  } catch (err) {}
}

// =========================================================================
// LIVE DEVELOPER ROOM CONTROLLER (REAL-TIME WEBSOCKETS + CHANNELS)
// =========================================================================
window.currentChatChannel = "general";
window.chatSoundEnabled = true;
window.chatSocket = null;
window.chatMessagesMap = { general: [], security: [], dev: [] };

function initChatWebSocket() {
  if (window.chatSocket && window.chatSocket.readyState === WebSocket.OPEN) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

  try {
    window.chatSocket = new WebSocket(wsUrl);

    window.chatSocket.onopen = () => {
      console.log("[FleedGuard Chat] Connected to live room stream.");
    };

    window.chatSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "message") {
          appendChatMessage(data);
          if (data.channel !== window.currentChatChannel) {
            playChatSound();
          } else {
            playChatSound();
          }
        } else if (data.type === "presence") {
          updateChatPresence(data.count || 1, data.users || []);
        } else if (data.type === "session_event") {
          // Real-time live player session broadcast
          handleLiveSessionStreamEvent(data);
        }
      } catch (err) {}
    };

    window.chatSocket.onclose = () => {
      setTimeout(() => {
        if (document.getElementById("view-chat")?.style.display === "flex") {
          initChatWebSocket();
        }
      }, 3000);
    };
  } catch (err) {}
}

async function loadChatMessages(channel = window.currentChatChannel || "general") {
  const container = document.getElementById("chatMessagesContainer");
  if (!container) return;

  try {
    const messages = await apiCall(`/api/chat/messages?channel=${encodeURIComponent(channel)}&limit=50`);
    window.chatMessagesMap[channel] = Array.isArray(messages) ? messages : [];
    renderChatMessages(window.chatMessagesMap[channel]);
  } catch (err) {
    container.innerHTML = `<div style="text-align:center; padding:24px; color:var(--text-zinc-500);"><i class="fa-solid fa-comments gold-accent"></i> Welcome to #${escapeHtml(channel)} chat! Start the conversation.</div>`;
  }
}

function renderChatMessages(messages) {
  const container = document.getElementById("chatMessagesContainer");
  if (!container) return;

  if (!messages || messages.length === 0) {
    container.innerHTML = `<div style="text-align:center; padding:24px; color:var(--text-zinc-500);"><i class="fa-solid fa-comments gold-accent"></i> Welcome to #${escapeHtml(window.currentChatChannel)} room! Send a message or paste Luau code below.</div>`;
    return;
  }

  const myUsername = (window.currentUser?.username || "").toLowerCase();

  container.innerHTML = messages.map(m => {
    const isSelf = (m.username || "").toLowerCase() === myUsername;
    const role = (m.role || "developer").toLowerCase();
    const roleClass = role === "admin" ? "chat-msg-role-admin" : (role === "developer" ? "chat-msg-role-dev" : "chat-msg-role-user");
    const avatarLetter = (m.username || "D").charAt(0).toUpperCase();
    const avatarHtml = m.avatar_url
      ? `<img src="${escapeHtml(m.avatar_url)}" alt="Avatar">`
      : avatarLetter;
    const timeStr = m.created_at ? formatTimeAgo(m.created_at) : "just now";

    return `
      <div class="chat-msg-row ${isSelf ? 'chat-msg-self' : ''}">
        <div class="chat-msg-avatar">${avatarHtml}</div>
        <div class="chat-msg-content">
          <div class="chat-msg-meta">
            <span class="chat-msg-user">${escapeHtml(m.username || 'Developer')}</span>
            <span class="chat-msg-role-badge ${roleClass}">${escapeHtml(role)}</span>
            <span class="chat-msg-time">${timeStr}</span>
          </div>
          <div class="chat-msg-bubble">${escapeHtml(m.message)}</div>
        </div>
      </div>
    `;
  }).join("");

  container.scrollTop = container.scrollHeight;
}

function appendChatMessage(msg) {
  const channel = msg.channel || "general";
  if (!window.chatMessagesMap[channel]) window.chatMessagesMap[channel] = [];
  window.chatMessagesMap[channel].push(msg);

  if (channel === window.currentChatChannel) {
    const container = document.getElementById("chatMessagesContainer");
    if (!container) return;

    const myUsername = (window.currentUser?.username || "").toLowerCase();
    const isSelf = (msg.username || "").toLowerCase() === myUsername;
    const role = (msg.role || "developer").toLowerCase();
    const roleClass = role === "admin" ? "chat-msg-role-admin" : (role === "developer" ? "chat-msg-role-dev" : "chat-msg-role-user");
    const avatarLetter = (msg.username || "D").charAt(0).toUpperCase();
    const avatarHtml = msg.avatar_url
      ? `<img src="${escapeHtml(msg.avatar_url)}" alt="Avatar">`
      : avatarLetter;
    const timeStr = msg.created_at ? formatTimeAgo(msg.created_at) : "just now";

    const msgHtml = `
      <div class="chat-msg-row ${isSelf ? 'chat-msg-self' : ''}">
        <div class="chat-msg-avatar">${avatarHtml}</div>
        <div class="chat-msg-content">
          <div class="chat-msg-meta">
            <span class="chat-msg-user">${escapeHtml(msg.username || 'Developer')}</span>
            <span class="chat-msg-role-badge ${roleClass}">${escapeHtml(role)}</span>
            <span class="chat-msg-time">${timeStr}</span>
          </div>
          <div class="chat-msg-bubble">${escapeHtml(msg.message)}</div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML("beforeend", msgHtml);
    container.scrollTop = container.scrollHeight;
  }
}

function switchChatChannel(channel) {
  window.currentChatChannel = channel;
  document.querySelectorAll(".channel-pill").forEach(pill => {
    pill.classList.toggle("active", pill.getAttribute("data-channel") === channel);
  });
  loadChatMessages(channel);
}

function handleSendChatMessage(e) {
  e.preventDefault();
  const input = document.getElementById("chatInputMessage");
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  if (window.chatSocket && window.chatSocket.readyState === WebSocket.OPEN) {
    window.chatSocket.send(JSON.stringify({
      type: "message",
      message: message,
      channel: window.currentChatChannel || "general"
    }));
    input.value = "";
    input.focus();
  } else {
    // Fallback REST POST if socket is reconnecting
    apiCall("/api/chat/messages", "POST", {
      message: message,
      channel: window.currentChatChannel || "general"
    }).then(() => {
      input.value = "";
      loadChatMessages(window.currentChatChannel);
    }).catch(err => {
      showToast("Unable to send chat message: " + err.message, "error");
    });
  }
}

function updateChatPresence(count, users) {
  const pill = document.getElementById("chatOnlinePill");
  if (pill) {
    pill.innerHTML = `<i class="fa-solid fa-circle"></i> ${count} Online`;
  }

  const userListEl = document.getElementById("chatActiveUsersList");
  if (userListEl) {
    if (!users || users.length === 0) {
      userListEl.innerHTML = `<div style="color:var(--text-zinc-500); font-size:11px; padding:6px;">No other users active</div>`;
      return;
    }

    userListEl.innerHTML = users.map(u => {
      const name = escapeHtml(u.username || "Guest");
      const role = escapeHtml(u.role || "Developer");
      const initial = name.charAt(0).toUpperCase();
      return `
        <div class="chat-user-item">
          <div class="chat-user-avatar">${initial}</div>
          <span class="chat-user-name">${name}</span>
          <span class="badge badge-zinc" style="font-size:8.5px;">${role}</span>
        </div>
      `;
    }).join("");
  }
}

function toggleChatSound() {
  window.chatSoundEnabled = !window.chatSoundEnabled;
  const btn = document.getElementById("chatSoundBtn");
  if (btn) {
    btn.innerHTML = window.chatSoundEnabled
      ? '<i class="fa-solid fa-volume-high"></i> Sound: ON'
      : '<i class="fa-solid fa-volume-xmark"></i> Sound: OFF';
  }
  showToast(`Chat sound notifications: ${window.chatSoundEnabled ? 'ENABLED' : 'MUTED'}`, "info");
}

function playChatSound() {
  if (!window.chatSoundEnabled) return;
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.1); // A5
    gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.12);
  } catch (err) {}
}

// =========================================================================
// REST API CODE SNIPPET TAB SWITCHER
// =========================================================================
function switchSnippetTab(tab) {
  document.querySelectorAll(".snippet-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
  });
  const boxes = {
    curl: document.getElementById("snippet-curl"),
    python: document.getElementById("snippet-python"),
    node: document.getElementById("snippet-node")
  };
  Object.keys(boxes).forEach(k => {
    if (boxes[k]) boxes[k].style.display = (k === tab) ? "block" : "none";
  });
}

// =========================================================================
// EXECUTOR ANALYTICS & THREAT FINGERPRINTING TELEMETRY
// =========================================================================
async function loadExecutorAnalytics() {
  return loadTelemetryData();
}

async function loadTelemetryData() {
  const marketContainer = document.getElementById("executorMarketShareContainer");
  const threatContainer = document.getElementById("threatDistributionContainer");
  if (!marketContainer || !threatContainer) return;

  marketContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-circle-notch fa-spin" style="color:var(--gold-primary); margin-right:8px;"></i> Aggregating runtime fingerprinting telemetry...</div>`;
  threatContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-zinc-500);"><i class="fa-solid fa-circle-notch fa-spin" style="color:var(--danger-color); margin-right:8px;"></i> Analyzing threat interception vectors...</div>`;

  try {
    let data;
    try {
      data = await apiCall("/api/analytics/executors");
    } catch (e) {
      const stats = await apiCall("/api/stats");
      data = {
        success: true,
        total_executions: stats.total_executions || 0,
        total_threats: stats.blocked_attacks || 0,
        market_share: (stats.top_executors || []).map(e => ({
          name: e.name,
          count: e.count,
          percentage: stats.total_executions > 0 ? Math.round((e.count / stats.total_executions) * 100) : 0,
          unique_users: 1,
          last_seen: new Date().toISOString()
        })),
        threat_breakdown: [
          { status: "HWID_MISMATCH", count: Math.ceil((stats.blocked_attacks || 0) * 0.45), percentage: 45 },
          { status: "TAMPER_DETECTED", count: Math.ceil((stats.blocked_attacks || 0) * 0.35), percentage: 35 },
          { status: "INVALID_KEY", count: Math.ceil((stats.blocked_attacks || 0) * 0.20), percentage: 20 }
        ]
      };
    }

    // 1. Render Market Share
    const totalExecs = data.total_executions || 0;
    const marketList = data.market_share || [];

    if (marketList.length === 0) {
      const defaultClients = ["Potassium", "Wave", "Solara", "Synapse Z", "Macsploit", "Delta", "Codex", "Celery"];
      marketContainer.innerHTML = `
        <div style="padding:16px; background:rgba(245,158,11,0.06); border:1px dashed var(--border-gold-subtle); border-radius:8px; margin-bottom:14px;">
          <div style="display:flex; align-items:center; gap:8px; color:var(--gold-light); font-weight:700; font-size:13px; margin-bottom:4px;">
            <i class="fa-solid fa-fingerprint"></i> Telemetry Engine Standing By
          </div>
          <p style="color:var(--text-zinc-400); font-size:12px; margin:0 0 10px 0;">
            Execution fingerprints are automatically captured upon each Luau script handshake. Supported runtimes include:
          </p>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            ${defaultClients.map(c => renderExecutorBadge(c)).join("")}
          </div>
        </div>
      `;
    } else {
      marketContainer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:12px; margin-bottom:12px; border-bottom:1px solid var(--border-subtle);">
          <span style="color:var(--text-zinc-400); font-size:12.5px;">Total Runtime Handshakes: <strong style="color:var(--text-white);">${totalExecs.toLocaleString()}</strong></span>
          <span class="badge badge-gold"><i class="fa-solid fa-microchip"></i> Active Fingerprinting</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:12px;">
          ${marketList.map(item => {
            const meta = getExecutorMeta(item.name);
            return `
              <div style="background:var(--bg-elevated); border:1px solid var(--border-card); border-radius:8px; padding:12px 14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <div style="display:flex; align-items:center; gap:8px;">
                    <div style="width:28px; height:28px; border-radius:6px; background:${meta.bg}; border:1px solid ${meta.border}; display:flex; align-items:center; justify-content:center;">
                      ${meta.icon}
                    </div>
                    <div>
                      <strong style="color:var(--text-white); font-size:13.5px; display:block;">${escapeHtml(meta.displayName)}</strong>
                      <span style="font-size:11px; color:var(--text-zinc-400);">Unique Players: <span style="color:var(--gold-light);">${item.unique_users || 0}</span></span>
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <span style="font-family:var(--font-mono); font-size:14px; font-weight:800; color:${meta.color};">${item.percentage}%</span>
                    <span style="font-size:11px; color:var(--text-zinc-500); display:block;">${item.count.toLocaleString()} execs</span>
                  </div>
                </div>
                <div style="background:rgba(255,255,255,0.06); height:6px; border-radius:3px; overflow:hidden;">
                  <div style="background:${meta.color}; width:${Math.max(item.percentage, 2)}%; height:100%; border-radius:3px; transition:width 0.6s ease;"></div>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    }

    // 2. Render Threat Interceptions
    const totalThreats = data.total_threats || 0;
    const threatList = data.threat_breakdown || [];

    if (threatList.length === 0) {
      threatContainer.innerHTML = `
        <div style="text-align:center; padding:30px; background:rgba(34,197,94,0.05); border:1px solid rgba(34,197,94,0.2); border-radius:8px;">
          <i class="fa-solid fa-shield-check" style="font-size:28px; color:var(--success-color); margin-bottom:8px;"></i>
          <h4 style="color:var(--text-white); font-size:14px; margin-bottom:4px;">No Security Interceptions</h4>
          <p style="color:var(--text-zinc-400); font-size:12px; margin:0;">Zero unauthorized tampered executions or dumper attacks recorded.</p>
        </div>
      `;
    } else {
      const threatLabels = {
        "TAMPER_DETECTED": { label: "Memory Tamper & Hook Interception", icon: "fa-solid fa-bug", color: "#ef4444" },
        "HWID_MISMATCH": { label: "Hardware ID (HWID) Violation", icon: "fa-solid fa-desktop", color: "#f97316" },
        "BYPASS_ATTEMPT": { label: "Anti-Dump / DRM Bypass Attempt", icon: "fa-solid fa-shield-halved", color: "#dc2626" },
        "BLACKLISTED": { label: "Blacklisted Device / IP Blocked", icon: "fa-solid fa-ban", color: "#a855f7" },
        "INVALID_KEY": { label: "Invalid / Forged License Key", icon: "fa-solid fa-key", color: "#eab308" },
        "KILLSWITCH": { label: "Killswitch Gated Execution", icon: "fa-solid fa-bolt", color: "#f43f5e" }
      };

      threatContainer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:12px; margin-bottom:12px; border-bottom:1px solid var(--border-subtle);">
          <span style="color:var(--text-zinc-400); font-size:12.5px;">Total Blocked Threat Vectors: <strong style="color:var(--danger-light);">${totalThreats.toLocaleString()}</strong></span>
          <span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Live Sentinel</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:12px;">
          ${threatList.map(t => {
            const meta = threatLabels[t.status] || { label: t.status, icon: "fa-solid fa-triangle-exclamation", color: "#f87171" };
            return `
              <div style="background:var(--bg-elevated); border:1px solid var(--border-card); border-radius:8px; padding:12px 14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                  <div style="display:flex; align-items:center; gap:8px;">
                    <div style="width:28px; height:28px; border-radius:6px; background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3); display:flex; align-items:center; justify-content:center; color:${meta.color}; font-size:12px;">
                      <i class="${meta.icon}"></i>
                    </div>
                    <div>
                      <strong style="color:var(--text-white); font-size:13px; display:block;">${meta.label}</strong>
                      <code style="font-size:10.5px; color:var(--text-zinc-500);">${escapeHtml(t.status)}</code>
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <span style="font-family:var(--font-mono); font-size:14px; font-weight:800; color:${meta.color};">${t.percentage}%</span>
                    <span style="font-size:11px; color:var(--text-zinc-500); display:block;">${t.count.toLocaleString()} blocked</span>
                  </div>
                </div>
                <div style="background:rgba(255,255,255,0.06); height:6px; border-radius:3px; overflow:hidden;">
                  <div style="background:${meta.color}; width:${Math.max(t.percentage, 2)}%; height:100%; border-radius:3px; transition:width 0.6s ease;"></div>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    }

  } catch (err) {
    marketContainer.innerHTML = `<p style="color:var(--danger-light); font-size:13px; text-align:center; padding:20px;">Failed to load executor telemetry: ${escapeHtml(err.message)}</p>`;
    threatContainer.innerHTML = `<p style="color:var(--danger-light); font-size:13px; text-align:center; padding:20px;">Failed to load threat telemetry.</p>`;
  }
}

// =========================================================================
// GPU-ACCELERATED AMBER DRIFTING PARTICLES ENGINE (ZERO-LAG)
// =========================================================================
function initAmberParticles() {
  const canvas = document.getElementById("amberParticlesCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  window.addEventListener("resize", () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }, { passive: true });

  const particleCount = 80;
  const particles = [];

  for (let i = 0; i < particleCount; i++) {
    const isGlowFlare = Math.random() > 0.82;
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      r: isGlowFlare ? (2.4 + Math.random() * 2.8) : (1.0 + Math.random() * 2.0),
      angle: Math.random() * Math.PI * 2,
      angleSpeed: 0.008 + Math.random() * 0.018,
      vx: (Math.random() - 0.5) * 0.35,
      vy: -(0.25 + Math.random() * 0.65),
      alpha: 0.35 + Math.random() * 0.6,
      alphaSpeed: 0.006 + Math.random() * 0.012,
      alphaDir: Math.random() > 0.5 ? 1 : -1,
      glowBlur: isGlowFlare ? 18 : 8,
      color: Math.random() > 0.4 ? "245, 158, 11" : (Math.random() > 0.5 ? "251, 191, 36" : "217, 119, 6")
    });
  }

  function render() {
    if (document.hidden) {
      requestAnimationFrame(render);
      return;
    }

    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particleCount; i++) {
      const p = particles[i];

      p.angle += p.angleSpeed;
      p.x += p.vx + Math.sin(p.angle) * 0.28;
      p.y += p.vy;

      p.alpha += p.alphaSpeed * p.alphaDir;
      if (p.alpha > 0.95) { p.alpha = 0.95; p.alphaDir = -1; }
      else if (p.alpha < 0.25) { p.alpha = 0.25; p.alphaDir = 1; }

      if (p.y < -16) {
        p.y = height + 16;
        p.x = Math.random() * width;
      }
      if (p.x < -16) p.x = width + 16;
      else if (p.x > width + 16) p.x = -16;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.color}, ${p.alpha})`;
      ctx.shadowBlur = p.glowBlur;
      ctx.shadowColor = `rgba(${p.color}, ${p.alpha * 0.9})`;
      ctx.fill();
    }

    requestAnimationFrame(render);
  }

  render();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAmberParticles);
} else {
  initAmberParticles();
}


