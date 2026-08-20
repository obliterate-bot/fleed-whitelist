const state = {
  token: sessionStorage.getItem("o_bfuscate_admin_token") || "",
  overview: null,
  projects: [],
  licenses: [],
  selectedLicenseId: null,
  expiration: "30",
  delivery: "inline",
  loaderResult: null,
  codeMode: "one_liner",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);

function friendlyAction(action) {
  return {
    license_issued: "License issued",
    license_revoked: "License revoked",
    license_restored: "License restored",
    hwid_bound: "HWID bound",
    hwid_reset: "HWID reset",
    hwid_lock_enabled: "HWID lock enabled",
    hwid_lock_disabled: "HWID lock disabled",
    expiration_updated: "Expiration updated",
    release_published: "Release published",
    project_saved: "Project saved",
    project_enabled: "Project enabled",
    project_disabled: "Project disabled",
    admin_token_rotated: "Admin token rotated",
  }[action] || String(action || "Activity").replaceAll("_", " ");
}

function actionIcon(action) {
  if (action?.includes("hwid")) return "⌁";
  if (action?.includes("release")) return "↗";
  if (action?.includes("revoke")) return "×";
  if (action?.includes("expiration")) return "◷";
  return "⌘";
}

function dateLabel(value, lifetime = "Never") {
  if (!value) return lifetime;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function relativeTime(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const intervals = [
    [31536000, "year"],
    [2592000, "month"],
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ];
  for (const [amount, unit] of intervals) {
    if (Math.abs(seconds) >= amount) return formatter.format(Math.round(seconds / amount), unit);
  }
  return formatter.format(seconds, "second");
}

function statusBadge(status) {
  return `<span class="badge badge-${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast${error ? " is-error" : ""}`;
  element.textContent = message;
  $("#toast-region").append(element);
  window.setTimeout(() => element.remove(), 3500);
}

async function copyText(value, success = "Copied to clipboard") {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  toast(success);
}

async function api(path, options = {}) {
  const headers = {
    Authorization: `Bearer ${state.token}`,
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(path, { ...options, headers });
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) {
    if (response.status === 401) showAuth();
    const error = new Error(data.detail || String(data.reason || `Request failed (${response.status})`));
    error.status = response.status;
    throw error;
  }
  return data;
}

function showAuth(invalid = false) {
  $("#auth-screen").hidden = false;
  $("#app-shell").setAttribute("aria-hidden", "true");
  if (invalid) $("#auth-error").textContent = "That admin token was not accepted.";
}

function showApp() {
  $("#auth-screen").hidden = true;
  $("#app-shell").setAttribute("aria-hidden", "false");
}

async function refreshData({ quiet = false } = {}) {
  const [overview, projects, licenses] = await Promise.all([
    api("/api/admin/overview"),
    api("/api/admin/projects"),
    api("/api/admin/licenses"),
  ]);
  state.overview = overview;
  state.projects = projects.projects;
  state.licenses = licenses.licenses;
  renderAll();
  if (!quiet) toast("Dashboard refreshed");
}

async function bootstrap() {
  if (!state.token) {
    showAuth();
    return;
  }
  try {
    await api("/api/admin/session");
    await refreshData({ quiet: true });
    showApp();
  } catch (error) {
    showAuth(error.status === 401);
  }
}

function renderAll() {
  renderOverview();
  renderProjectOptions();
  renderLicenseTable();
  renderLoaderOptions();
  renderReleases();
  $("#nav-license-count").textContent = state.licenses.length;
}

function renderOverview() {
  const totals = state.overview?.totals || {};
  $("#stat-total").textContent = totals.licenses ?? 0;
  $("#stat-active").textContent = totals.active ?? 0;
  $("#stat-active-inline").textContent = totals.active ?? 0;
  $("#stat-hwid").textContent = totals.hwid_bound ?? 0;
  $("#stat-expiring").textContent = totals.expiring_soon ?? 0;
  $("#health-active").textContent = totals.active ?? 0;
  $("#health-expired").textContent = totals.expired ?? 0;
  $("#health-revoked").textContent = totals.revoked ?? 0;

  const total = Math.max(1, totals.licenses || 0);
  const activePercent = Math.round(((totals.active || 0) / total) * 100);
  const expiredPercent = ((totals.expired || 0) / total) * 100;
  const revokedPercent = ((totals.revoked || 0) / total) * 100;
  $("#health-percent").textContent = `${totals.licenses ? activePercent : 0}%`;
  $("#health-ring").style.setProperty("--health", `${totals.licenses ? activePercent : 0}%`);
  $("#track-active").style.width = `${activePercent}%`;
  $("#track-expired").style.width = `${expiredPercent}%`;
  $("#track-revoked").style.width = `${revokedPercent}%`;

  const recent = state.overview?.recent_licenses || [];
  $("#recent-license-rows").innerHTML = recent.length
    ? recent.map((license) => licenseRow(license, true)).join("")
    : `<tr><td colspan="6"><div class="empty-compact">No licenses yet. Create your first key to get started.</div></td></tr>`;

  const activity = state.overview?.activity || [];
  $("#activity-list").innerHTML = activity.length
    ? activity.slice(0, 6).map((event) => `
      <div class="activity-item">
        <span class="activity-icon">${escapeHtml(actionIcon(event.action))}</span>
        <span>
          <strong>${escapeHtml(friendlyAction(event.action))}</strong>
          <small>${escapeHtml(event.detail || event.project || event.license_id || "System")}</small>
        </span>
        <span class="activity-time">${escapeHtml(relativeTime(event.at))}</span>
      </div>`).join("")
    : `<div class="empty-compact">Activity will appear as you issue keys and publish builds.</div>`;
}

function licenseRow(license, compact = false) {
  const title = license.label || license.id;
  const hwid = license.hwid_bound
    ? `<span class="hwid-state is-bound"><i></i>${escapeHtml(license.hwid_fingerprint)}…</span>`
    : license.hwid_lock
      ? `<span class="hwid-state"><i></i>Awaiting device</span>`
      : `<span class="hwid-state"><i></i>Not required</span>`;
  const action = `<button class="row-action" data-manage="${escapeHtml(license.id)}">Manage</button>`;
  if (compact) {
    return `<tr>
      <td><div class="license-cell"><span class="key-avatar">K</span><span><strong>${escapeHtml(title)}</strong><code>${escapeHtml(license.key_hint)}</code></span></div></td>
      <td>${escapeHtml(license.project)}</td>
      <td>${statusBadge(license.status)}</td>
      <td>${hwid}</td>
      <td>${escapeHtml(dateLabel(license.expires_at, "Lifetime"))}</td>
      <td>${action}</td>
    </tr>`;
  }
  return `<tr>
    <td><div class="license-cell"><span class="key-avatar">K</span><span><strong>${escapeHtml(title)}</strong><code>${escapeHtml(license.key_hint)}</code></span></div></td>
    <td>${escapeHtml(license.project)}</td>
    <td>${statusBadge(license.status)}</td>
    <td>${hwid}</td>
    <td>${escapeHtml(relativeTime(license.last_seen_at))}</td>
    <td>${escapeHtml(dateLabel(license.expires_at, "Lifetime"))}</td>
    <td>${action}</td>
  </tr>`;
}

function renderProjectOptions() {
  const options = state.projects.map((project) =>
    `<option value="${escapeHtml(project.id)}">${escapeHtml(project.id)}</option>`
  ).join("");
  const filter = $("#project-filter");
  const oldFilter = filter.value;
  filter.innerHTML = `<option value="">All projects</option>${options}`;
  if ([...filter.options].some((option) => option.value === oldFilter)) filter.value = oldFilter;

  for (const selector of ["#create-project", "#publish-project"]) {
    const select = $(selector);
    const old = select.value;
    select.innerHTML = options || `<option value="">No projects available</option>`;
    if ([...select.options].some((option) => option.value === old)) select.value = old;
  }
}

function filteredLicenses() {
  const needle = $("#license-search").value.trim().toLowerCase();
  const status = $("#status-filter").value;
  const project = $("#project-filter").value;
  return state.licenses.filter((license) => {
    if (status !== "all" && license.status !== status) return false;
    if (project && license.project !== project) return false;
    if (!needle) return true;
    return [license.label, license.id, license.key_hint, license.project, license.note]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });
}

function renderLicenseTable() {
  const licenses = filteredLicenses();
  $("#license-rows").innerHTML = licenses.map((license) => licenseRow(license)).join("");
  $("#license-result-count").textContent = `${licenses.length} ${licenses.length === 1 ? "key" : "keys"}`;
  $("#license-empty").hidden = licenses.length !== 0;
  $("#license-rows").closest(".table-wrap").hidden = licenses.length === 0;
}

function renderLoaderOptions() {
  const select = $("#loader-license");
  const old = select.value;
  const eligible = state.licenses.filter((license) => license.recoverable);
  select.innerHTML = `<option value="">Select a license…</option>` + eligible.map((license) => `
    <option value="${escapeHtml(license.id)}"${license.status !== "active" ? " disabled" : ""}>
      ${escapeHtml(license.label || license.key_hint)} · ${escapeHtml(license.project)}
    </option>`).join("");
  if ([...select.options].some((option) => option.value === old && !option.disabled)) select.value = old;
  renderLoaderBuilds();
}

function selectedLoaderLicense() {
  return state.licenses.find((license) => license.id === $("#loader-license").value);
}

function renderLoaderBuilds() {
  const select = $("#loader-build");
  const old = select.value;
  const license = selectedLoaderLicense();
  const project = state.projects.find((item) => item.id === license?.project);
  const releases = project?.releases || [];
  select.innerHTML = `<option value="">Latest published release</option>` + releases.map((release) =>
    `<option value="${escapeHtml(release.build_id)}">${escapeHtml(release.build_id)} · ${escapeHtml(release.delivery)}</option>`
  ).join("");
  if ([...select.options].some((option) => option.value === old)) select.value = old;
}

function renderReleases() {
  const releases = state.projects.flatMap((project) =>
    project.releases.map((release) => ({ ...release, project: project.id, latest: project.latest_release === release.build_id }))
  );
  $("#release-list").innerHTML = releases.length
    ? releases.slice(0, 8).map((release) => `
      <div class="release-item">
        <span class="release-icon">${release.latest ? "★" : "↗"}</span>
        <span>
          <strong>${escapeHtml(release.project)} / ${escapeHtml(release.build_id)}</strong>
          <small>${escapeHtml(relativeTime(release.published_at))}${release.latest ? " · Latest" : ""}</small>
        </span>
        <span class="delivery-pill">${escapeHtml(release.delivery)}</span>
      </div>`).join("")
    : `<div class="empty-compact">No builds published yet.</div>`;
}

function switchView(view) {
  $$(".nav-item").forEach((item) => item.classList.toggle("is-active", item.dataset.view === view));
  $$("[data-view-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.viewPanel === view));
  $("#page-crumb").textContent = { overview: "Overview", licenses: "License keys", loaders: "Loaders" }[view];
  $("#sidebar").classList.remove("is-open");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openModal(id) {
  $(id).hidden = false;
  document.body.style.overflow = "hidden";
}

function closeModals() {
  $$(".modal-backdrop").forEach((modal) => { modal.hidden = true; });
  document.body.style.overflow = "";
}

function openCreateModal() {
  if (!state.projects.length) {
    toast("Create a project from the CLI before issuing keys.", true);
    return;
  }
  $("#create-license-form").reset();
  $("#create-hwid-lock").checked = true;
  state.expiration = "30";
  $$("[data-expiration]").forEach((button) => button.classList.toggle("is-active", button.dataset.expiration === "30"));
  $("#custom-expiration-field").hidden = true;
  $("#created-key-panel").hidden = true;
  $("#create-submit").hidden = false;
  $("#create-error").textContent = "";
  openModal("#create-modal");
}

async function createLicense(event) {
  event.preventDefault();
  const body = {
    label: $("#create-label").value.trim(),
    project: $("#create-project").value,
    hwid_lock: $("#create-hwid-lock").checked,
    hwid: $("#create-hwid").value.trim() || null,
    note: $("#create-note").value.trim(),
  };
  if (state.expiration === "custom") {
    if (!$("#custom-expiration").value) {
      $("#create-error").textContent = "Choose a custom expiration date.";
      return;
    }
    body.expires_at = new Date(`${$("#custom-expiration").value}T23:59:59`).toISOString();
  } else if (state.expiration !== "never") {
    body.days = Number(state.expiration);
  }
  const button = $("#create-submit");
  button.disabled = true;
  $("#create-error").textContent = "";
  try {
    const result = await api("/api/admin/licenses", { method: "POST", body: JSON.stringify(body) });
    $("#created-key-value").textContent = result.license_key;
    $("#created-key-panel").hidden = false;
    button.hidden = true;
    await refreshData({ quiet: true });
    toast("License created");
  } catch (error) {
    $("#create-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function getLicense(id) {
  return state.licenses.find((license) => license.id === id);
}

function openManage(id) {
  const license = getLicense(id);
  if (!license) return;
  state.selectedLicenseId = id;
  const expiresDate = license.expires_at ? license.expires_at.slice(0, 10) : "";
  $("#manage-title").textContent = license.label || "Manage license";
  $("#manage-body").innerHTML = `
    <div class="manage-summary">
      <div>
        <h3>${escapeHtml(license.label || license.id)}</h3>
        <code id="manage-key-value">${escapeHtml(license.key_hint)}</code>
      </div>
      ${statusBadge(license.status)}
    </div>
    <div class="manage-action-row">
      <button class="button button-secondary button-full" id="manage-reveal"${license.recoverable ? "" : " disabled"}>Reveal & copy key</button>
      <button class="button button-secondary button-full" id="manage-loader">Open loader generator</button>
    </div>
    <div class="manage-meta-grid">
      <div class="manage-meta"><small>Project</small><strong>${escapeHtml(license.project)}</strong></div>
      <div class="manage-meta"><small>Last used</small><strong>${escapeHtml(relativeTime(license.last_seen_at))}</strong></div>
      <div class="manage-meta"><small>HWID resets</small><strong>${license.hwid_reset_count}</strong></div>
    </div>
    <div class="manage-section">
      <div class="manage-section-title"><strong>Expiration</strong><small>Leave empty for lifetime</small></div>
      <div class="manage-action-row">
        <label class="field"><span>Expiration date</span><input id="manage-expiration" type="date" value="${escapeHtml(expiresDate)}"></label>
        <button class="button button-secondary" id="manage-save-expiration">Save</button>
      </div>
    </div>
    <div class="toggle-card">
      <span class="toggle-copy">
        <strong>HWID locking</strong>
        <small>${license.hwid_bound ? `Bound to ${escapeHtml(license.hwid_fingerprint)}…` : "Will bind on the next successful request."}</small>
      </span>
      <label class="switch"><input id="manage-hwid-lock" type="checkbox"${license.hwid_lock ? " checked" : ""}><span></span></label>
    </div>
    <button class="button button-secondary button-full" id="manage-reset-hwid"${license.hwid_bound ? "" : " disabled"}>Reset bound HWID</button>
  `;
  const revokeButton = $("#manage-revoke");
  revokeButton.textContent = license.revoked ? "Restore license" : "Revoke license";
  revokeButton.className = license.revoked ? "button button-secondary" : "button button-danger-ghost";
  bindManageActions(license);
  openModal("#manage-modal");
}

function bindManageActions(license) {
  $("#manage-reveal").addEventListener("click", async () => {
    try {
      const result = await api(`/api/admin/licenses/${encodeURIComponent(license.id)}/key`);
      $("#manage-key-value").textContent = result.license_key;
      await copyText(result.license_key, "License key copied");
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("#manage-loader").addEventListener("click", () => {
    closeModals();
    switchView("loaders");
    $("#loader-license").value = license.id;
    renderLoaderBuilds();
  });
  $("#manage-save-expiration").addEventListener("click", async () => {
    const value = $("#manage-expiration").value;
    const expiresAt = value ? new Date(`${value}T23:59:59`).toISOString() : null;
    await mutateLicense(license.id, { action: "set_expiration", expires_at: expiresAt }, "Expiration updated");
  });
  $("#manage-hwid-lock").addEventListener("change", async (event) => {
    await mutateLicense(license.id, { action: "set_hwid_lock", enabled: event.target.checked }, "HWID policy updated");
  });
  $("#manage-reset-hwid").addEventListener("click", async () => {
    if (!window.confirm("Reset this license's HWID binding? The next device can claim it.")) return;
    await mutateLicense(license.id, { action: "reset_hwid" }, "HWID binding reset");
  });
  $("#manage-revoke").onclick = async () => {
    const action = license.revoked ? "restore" : "revoke";
    if (!license.revoked && !window.confirm("Revoke this license immediately?")) return;
    await mutateLicense(license.id, { action }, license.revoked ? "License restored" : "License revoked");
  };
}

async function mutateLicense(id, body, message) {
  try {
    await api(`/api/admin/licenses/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    await refreshData({ quiet: true });
    toast(message);
    openManage(id);
  } catch (error) {
    toast(error.message, true);
  }
}

async function generateLoader() {
  const license = selectedLoaderLicense();
  if (!license) {
    toast("Select an active license first.", true);
    return;
  }
  const baseUrl = $("#loader-base-url").value.trim();
  if (!baseUrl) {
    toast("Enter the public service URL.", true);
    return;
  }
  const button = $("#generate-loader");
  button.disabled = true;
  try {
    state.loaderResult = await api("/api/admin/loaders", {
      method: "POST",
      body: JSON.stringify({
        license_id: license.id,
        base_url: baseUrl,
        build_id: $("#loader-build").value || null,
      }),
    });
    renderLoaderCode();
    toast("Loader generated");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function renderLoaderCode() {
  if (!state.loaderResult) return;
  $("#loader-code").textContent = state.loaderResult[state.codeMode];
}

function openPublishModal() {
  if (!state.projects.length) {
    toast("Create a project from the CLI first.", true);
    return;
  }
  $("#publish-form").reset();
  state.delivery = "inline";
  $$("[data-delivery]").forEach((button) => button.classList.toggle("is-active", button.dataset.delivery === "inline"));
  $("#inline-source-field").hidden = false;
  $("#remote-url-field").hidden = true;
  $("#publish-error").textContent = "";
  openModal("#publish-modal");
}

async function publishRelease(event) {
  event.preventDefault();
  const body = {
    project: $("#publish-project").value,
    build_id: $("#publish-build").value.trim(),
  };
  if (state.delivery === "inline") body.artifact_source = $("#publish-source").value;
  else body.artifact_url = $("#publish-url").value.trim();
  $("#publish-error").textContent = "";
  try {
    await api("/api/admin/releases", { method: "POST", body: JSON.stringify(body) });
    closeModals();
    await refreshData({ quiet: true });
    toast("Release published");
  } catch (error) {
    $("#publish-error").textContent = error.message;
  }
}

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = $("#admin-token").value.trim();
  $("#auth-error").textContent = "";
  try {
    await api("/api/admin/session");
    sessionStorage.setItem("o_bfuscate_admin_token", state.token);
    await refreshData({ quiet: true });
    showApp();
  } catch (error) {
    $("#auth-error").textContent = error.status === 401 ? "That admin token was not accepted." : error.message;
  }
});

$("#toggle-token").addEventListener("click", () => {
  const input = $("#admin-token");
  input.type = input.type === "password" ? "text" : "password";
  $("#toggle-token").textContent = input.type === "password" ? "Show" : "Hide";
});

$("#logout-button").addEventListener("click", () => {
  sessionStorage.removeItem("o_bfuscate_admin_token");
  state.token = "";
  $("#admin-token").value = "";
  showAuth();
});

$$(".nav-item").forEach((item) => item.addEventListener("click", () => switchView(item.dataset.view)));
$$("[data-go-licenses]").forEach((button) => button.addEventListener("click", () => switchView("licenses")));
$$("[data-open-create]").forEach((button) => button.addEventListener("click", openCreateModal));
$$("[data-close-modal]").forEach((button) => button.addEventListener("click", closeModals));
$$(".modal-backdrop").forEach((backdrop) => backdrop.addEventListener("mousedown", (event) => {
  if (event.target === backdrop) closeModals();
}));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModals();
});
document.addEventListener("click", (event) => {
  const manage = event.target.closest("[data-manage]");
  if (manage) openManage(manage.dataset.manage);
});

$("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("is-open"));
$("#refresh-overview").addEventListener("click", () => refreshData().catch((error) => toast(error.message, true)));
$("#license-search").addEventListener("input", renderLicenseTable);
$("#status-filter").addEventListener("change", renderLicenseTable);
$("#project-filter").addEventListener("change", renderLicenseTable);
$("#create-license-form").addEventListener("submit", createLicense);
$("#copy-created-key").addEventListener("click", () => copyText($("#created-key-value").textContent, "License key copied"));

$$("[data-expiration]").forEach((button) => button.addEventListener("click", () => {
  state.expiration = button.dataset.expiration;
  $$("[data-expiration]").forEach((item) => item.classList.toggle("is-active", item === button));
  $("#custom-expiration-field").hidden = state.expiration !== "custom";
}));

$("#loader-license").addEventListener("change", renderLoaderBuilds);
$("#loader-base-url").value = window.location.origin;
$("#generate-loader").addEventListener("click", generateLoader);
$("#copy-loader").addEventListener("click", () => {
  if (!state.loaderResult) {
    toast("Generate a loader first.", true);
    return;
  }
  copyText(state.loaderResult[state.codeMode], "Loader copied");
});
$$("[data-code-mode]").forEach((button) => button.addEventListener("click", () => {
  state.codeMode = button.dataset.codeMode;
  $$("[data-code-mode]").forEach((item) => item.classList.toggle("is-active", item === button));
  renderLoaderCode();
}));

$("#open-publish").addEventListener("click", openPublishModal);
$("#open-publish-secondary").addEventListener("click", openPublishModal);
$("#publish-form").addEventListener("submit", publishRelease);
$$("[data-delivery]").forEach((button) => button.addEventListener("click", () => {
  state.delivery = button.dataset.delivery;
  $$("[data-delivery]").forEach((item) => item.classList.toggle("is-active", item === button));
  $("#inline-source-field").hidden = state.delivery !== "inline";
  $("#remote-url-field").hidden = state.delivery !== "remote";
}));

bootstrap();
