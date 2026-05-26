const STORAGE_KEY = "netauto-dashboard-settings";
const DEFAULT_DOMAIN = "lab.local";
const DEFAULT_BANNER = "Managed by NetAuto";

const appState = {
  devices: [],
  profiles: [],
  selectedDeviceName: null,
  selectedDevice: null,
  selectedBatchNames: new Set(),
  selectedJobId: null,
  selectedSnapshotId: null,
  selectorDevices: [],
};

function buildInterfaceDraft(iface = {}) {
  return {
    name: iface.name || "",
    description: iface.description || "",
    ipv4_address: iface.ipv4_address || "",
    enabled: iface.enabled ?? true,
  };
}

function loadSettings() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveSettings(settings) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function getSettings() {
  return {
    baseUrl: document.getElementById("base-url").value.trim() || "/api",
    apiKey: document.getElementById("api-key").value.trim(),
    username: document.getElementById("username").value.trim(),
    password: document.getElementById("password").value.trim(),
  };
}

function hydrateConnectionForm() {
  const settings = loadSettings();
  document.getElementById("base-url").value = settings.baseUrl || "/api";
  document.getElementById("api-key").value = settings.apiKey || "";
  document.getElementById("username").value = settings.username || "";
  document.getElementById("password").value = settings.password || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildHeaders(settings) {
  const headers = { Accept: "application/json" };
  if (settings.apiKey) {
    headers["X-API-Key"] = settings.apiKey;
  }
  if (settings.username && settings.password) {
    headers.Authorization = `Basic ${window.btoa(`${settings.username}:${settings.password}`)}`;
  }
  return headers;
}

async function requestApi(path, settings, options = {}) {
  const response = await fetch(`${settings.baseUrl}${path}`, {
    method: options.method || "GET",
    headers: {
      ...buildHeaders(settings),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const details = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${details}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function requestJson(path, settings) {
  return requestApi(path, settings);
}

function setStatus(text, isError = false) {
  const node = document.getElementById("connection-status");
  node.textContent = text;
  node.classList.toggle("error-text", isError);
}

function statusClass(status) {
  if (["reachable", "success", "succeeded"].includes(status)) {
    return "success";
  }
  if (["queued", "running"].includes(status)) {
    return "warn";
  }
  return "error";
}

function setSelectedDeviceName(deviceName) {
  appState.selectedDeviceName = deviceName;
}

function updateBatchSelectionCaption() {
  const names = Array.from(appState.selectedBatchNames);
  document.getElementById("batch-selection-caption").textContent = names.length
    ? `${names.length} selected: ${names.join(", ")}`
    : "No devices selected";
}

function renderDevices(devices) {
  const table = document.getElementById("devices-table");
  const reachable = devices.filter((device) => device.status === "reachable").length;
  const maintenance = devices.filter((device) => device.status === "maintenance").length;
  const unreachable = devices.filter((device) => device.status === "unreachable").length;

  document.getElementById("devices-value").textContent = String(devices.length);
  document.getElementById("devices-meta").textContent =
    `${reachable} reachable / ${unreachable} unreachable / ${maintenance} maintenance`;
  document.getElementById("devices-caption").textContent = `Loaded devices: ${devices.length}`;

  const validNames = new Set(devices.map((device) => device.name));
  appState.selectedBatchNames = new Set([...appState.selectedBatchNames].filter((name) => validNames.has(name)));

  if (!devices.length) {
    table.innerHTML = '<tr><td colspan="6" class="placeholder">No devices found.</td></tr>';
    updateBatchSelectionCaption();
    return;
  }

  if (!appState.selectedDeviceName || !devices.some((device) => device.name === appState.selectedDeviceName)) {
    setSelectedDeviceName(devices[0].name);
  }

  table.innerHTML = devices
    .map(
      (device) => `
        <tr class="device-row ${device.name === appState.selectedDeviceName ? "selected" : ""}" data-device-name="${escapeHtml(device.name)}">
          <td><input class="device-checkbox" type="checkbox" data-device-name="${escapeHtml(device.name)}" ${appState.selectedBatchNames.has(device.name) ? "checked" : ""} /></td>
          <td><strong>${escapeHtml(device.name)}</strong><br /><span class="muted">${escapeHtml(device.platform)}</span></td>
          <td>${escapeHtml(device.site)}</td>
          <td>${escapeHtml(device.role)}</td>
          <td><span class="badge ${statusClass(device.status)}">${escapeHtml(device.status)}</span></td>
          <td>${escapeHtml(device.management_ip)}</td>
        </tr>
      `,
    )
    .join("");

  table.querySelectorAll(".device-row").forEach((row) => {
    row.addEventListener("click", async (event) => {
      if (event.target instanceof HTMLInputElement) {
        return;
      }
      const deviceName = row.dataset.deviceName;
      if (!deviceName || deviceName === appState.selectedDeviceName) {
        return;
      }
      setSelectedDeviceName(deviceName);
      renderDevices(appState.devices);
      await refreshSelectedDeviceDetails(getSettings());
    });
  });

  table.querySelectorAll(".device-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", () => {
      const deviceName = checkbox.dataset.deviceName;
      if (!deviceName) {
        return;
      }
      if (checkbox.checked) {
        appState.selectedBatchNames.add(deviceName);
      } else {
        appState.selectedBatchNames.delete(deviceName);
      }
      updateBatchSelectionCaption();
    });
  });

  updateBatchSelectionCaption();
}

function renderProfiles(profiles) {
  const node = document.getElementById("profiles-list");
  document.getElementById("profiles-value").textContent = String(profiles.length);
  document.getElementById("profiles-meta").textContent = "baseline templates";

  if (!profiles.length) {
    node.innerHTML = '<p class="placeholder">Profiles are not configured.</p>';
    return;
  }

  node.innerHTML = profiles
    .map(
      (profile) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(profile.name)}</strong>
            <span class="badge">${profile.interfaces.length} interfaces</span>
          </header>
          <p>${escapeHtml(profile.description)}</p>
        </article>
      `,
    )
    .join("");
}

function renderJobs(jobs) {
  const node = document.getElementById("jobs-list");
  document.getElementById("jobs-value").textContent = String(jobs.length);
  document.getElementById("jobs-meta").textContent = jobs.length
    ? `latest status: ${jobs[0].status}`
    : "queue is empty";

  if (!jobs.length) {
    node.innerHTML = '<p class="placeholder">No jobs yet.</p>';
    appState.selectedJobId = null;
    return;
  }

  if (!appState.selectedJobId || !jobs.some((job) => job.job_id === appState.selectedJobId)) {
    appState.selectedJobId = jobs[0].job_id;
  }

  node.innerHTML = jobs
    .map(
      (job) => `
        <article class="stack-item selectable ${job.job_id === appState.selectedJobId ? "selected-item" : ""}" data-job-id="${escapeHtml(job.job_id)}">
          <header>
            <strong>${escapeHtml(job.operation)}</strong>
            <span class="badge ${statusClass(job.status)}">${escapeHtml(job.status)}</span>
          </header>
          <p>Device: ${escapeHtml(job.device_name)}</p>
          <p>Backend: ${escapeHtml(job.queue_backend)}${job.dry_run ? " / dry-run" : ""}</p>
          <p class="muted">Job ID: ${escapeHtml(job.job_id)}</p>
        </article>
      `,
    )
    .join("");

  node.querySelectorAll("[data-job-id]").forEach((card) => {
    card.addEventListener("click", () => {
      appState.selectedJobId = card.dataset.jobId;
      renderJobs(jobs);
    });
  });
}

function renderOperationsSummary(summary) {
  document.getElementById("operations-value").textContent = String(summary.total_operations ?? summary.total ?? 0);
  document.getElementById("operations-meta").textContent =
    `${summary.successful_operations ?? summary.success} success / ${summary.failed_operations ?? summary.failed} failed`;
}

function renderOperations(operations) {
  const node = document.getElementById("operations-list");

  if (!operations.length) {
    node.innerHTML = '<p class="placeholder">Operations have not been executed yet.</p>';
    return;
  }

  node.innerHTML = operations
    .map(
      (operation) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(operation.operation)}</strong>
            <span class="badge ${statusClass(operation.status)}">${escapeHtml(operation.status)}</span>
          </header>
          <p>Device: ${escapeHtml(operation.device_name)}</p>
          <p>Backend: ${escapeHtml(operation.backend)}</p>
        </article>
      `,
    )
    .join("");
}

function renderHealth() {
  document.getElementById("health-value").textContent = "OK";
  document.getElementById("health-meta").textContent = "FastAPI is reachable";
}

function renderDatabase(database) {
  document.getElementById("database-value").textContent = database.initialized ? "READY" : "DOWN";
  document.getElementById("database-meta").textContent = `${database.roles_count} roles / ${database.users_count} users`;
}

function renderDeviceDetail(device, runningConfigLines, runningConfigError = "", runningConfigCached = false) {
  const container = document.getElementById("device-detail");
  const badge = document.getElementById("device-status-badge");
  document.getElementById("device-caption").textContent = `${device.name} · ${device.management_ip}`;
  document.getElementById("snapshots-caption").textContent = `Snapshots for ${device.name} (mock backend only)`;
  badge.textContent = device.status;
  badge.className = `badge ${statusClass(device.status)}`;

  const interfacesHtml = device.interfaces.length
    ? device.interfaces
        .map(
          (iface) => `
            <article class="interface-card">
              <header>
                <strong>${escapeHtml(iface.name)}</strong>
                <span class="badge ${iface.enabled ? "success" : "error"}">${iface.enabled ? "up" : "shutdown"}</span>
              </header>
              <p>${escapeHtml(iface.description || "No description")}</p>
              <p class="muted">${escapeHtml(iface.ipv4_address || "IP not set")}</p>
            </article>
          `,
        )
        .join("")
    : '<p class="placeholder">No interfaces described.</p>';

  const runningConfigState = runningConfigCached
    ? '<span class="badge warn">cached</span>'
    : '<span class="badge success">live</span>';
  const runningConfigWarning = runningConfigError
    ? `<p class="placeholder ${runningConfigCached ? "" : "error-text"}">${escapeHtml(runningConfigError)}</p>`
    : "";

  container.innerHTML = `
    <div class="detail-grid">
      <article class="detail-card">
        <span class="label">Hostname</span>
        <strong>${escapeHtml(device.hostname)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Site</span>
        <strong>${escapeHtml(device.site)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Role</span>
        <strong>${escapeHtml(device.role)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Platform</span>
        <strong>${escapeHtml(device.platform)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Vendor</span>
        <strong>${escapeHtml(device.vendor)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">SSH endpoint</span>
        <strong>${escapeHtml(`${device.management_ip}:${device.port}`)}</strong>
      </article>
    </div>
    <div class="detail-columns">
      <section class="panel-subsection">
        <div class="panel-heading compact">
          <h3>Interfaces</h3>
          <span class="caption">${device.interfaces.length} items</span>
        </div>
        <div class="interface-list">${interfacesHtml}</div>
      </section>
      <section class="panel-subsection">
        <div class="panel-heading compact">
          <h3>Running-config</h3>
          <span class="caption">Current backend view</span>
        </div>
        <div class="running-config-state">${runningConfigState}</div>
        ${runningConfigWarning}
        <pre class="code-block">${escapeHtml((runningConfigLines || []).join("\n") || "Empty configuration")}</pre>
      </section>
    </div>
  `;
}

function buildInterfaceEditorCard(iface, index) {
  return `
    <article class="interface-editor" data-index="${index}">
      <div class="interface-editor-header">
        <strong>Port ${index + 1}</strong>
        <div class="interface-editor-actions">
          <label class="checkbox-inline">
            <input type="checkbox" data-field="enabled" ${iface.enabled ? "checked" : ""} />
            <span>Enabled</span>
          </label>
          <button type="button" class="secondary-action remove-interface">Remove</button>
        </div>
      </div>
      <label>
        <span>Port name</span>
        <input type="text" data-field="name" value="${escapeHtml(iface.name)}" placeholder="GigabitEthernet0/0" />
      </label>
      <label>
        <span>Description</span>
        <input type="text" data-field="description" value="${escapeHtml(iface.description || "")}" />
      </label>
      <label>
        <span>IPv4 / prefix</span>
        <input type="text" data-field="ipv4_address" value="${escapeHtml(iface.ipv4_address || "")}" placeholder="10.0.12.1/30" />
      </label>
    </article>
  `;
}

function refreshInterfaceEditorTitles() {
  document.querySelectorAll(".interface-editor").forEach((node, index) => {
    node.dataset.index = String(index);
    const title = node.querySelector(".interface-editor-header strong");
    if (title) {
      title.textContent = `Port ${index + 1}`;
    }
  });
}

function attachInterfaceEditorEvents() {
  document.querySelectorAll(".remove-interface").forEach((button) => {
    button.onclick = () => {
      button.closest(".interface-editor")?.remove();
      const container = document.getElementById("config-interfaces");
      if (!container.querySelector(".interface-editor")) {
        container.innerHTML = '<p class="placeholder">No configured ports yet. Use "Add port" to build the request.</p>';
      }
      refreshInterfaceEditorTitles();
    };
  });
}

function appendInterfaceEditor(iface = buildInterfaceDraft()) {
  const container = document.getElementById("config-interfaces");
  const placeholder = container.querySelector(".placeholder");
  if (placeholder) {
    container.innerHTML = "";
  }
  const nextIndex = container.querySelectorAll(".interface-editor").length;
  container.insertAdjacentHTML("beforeend", buildInterfaceEditorCard(iface, nextIndex));
  attachInterfaceEditorEvents();
  refreshInterfaceEditorTitles();
}

function buildInterfaceEditor(interfaces) {
  const container = document.getElementById("config-interfaces");
  const drafts = (interfaces || []).map((iface) => buildInterfaceDraft(iface));
  if (!drafts.length) {
    container.innerHTML = '<p class="placeholder">No configured ports yet. Use "Add port" to build the request.</p>';
    return;
  }

  container.innerHTML = drafts.map((iface, index) => buildInterfaceEditorCard(iface, index)).join("");
  attachInterfaceEditorEvents();
  refreshInterfaceEditorTitles();
}

function populateConfigForm(device) {
  document.getElementById("config-device-name").textContent = `${device.name} · ${device.management_ip}`;
  document.getElementById("config-hostname").value = device.hostname || device.name;
  document.getElementById("config-domain").value = DEFAULT_DOMAIN;
  document.getElementById("config-banner").value = DEFAULT_BANNER;
  document.getElementById("config-ntp").value = "";
  buildInterfaceEditor(device.interfaces || []);
}

function collectConfigPayload() {
  const hostname = document.getElementById("config-hostname").value.trim();
  const domainName = document.getElementById("config-domain").value.trim() || DEFAULT_DOMAIN;
  const bannerMotd = document.getElementById("config-banner").value.trim() || DEFAULT_BANNER;
  const ntpServer = document.getElementById("config-ntp").value.trim();
  const interfaces = Array.from(document.querySelectorAll(".interface-editor"))
    .map((node) => {
      const readField = (name) => node.querySelector(`[data-field="${name}"]`);
      return {
        name: readField("name").value.trim(),
        description: readField("description").value.trim(),
        ipv4_address: readField("ipv4_address").value.trim() || null,
        enabled: Boolean(readField("enabled").checked),
      };
    })
    .filter((iface) => iface.name);

  return {
    hostname,
    domain_name: domainName,
    banner_motd: bannerMotd,
    ntp_server: ntpServer || null,
    interfaces,
  };
}

function buildSelectorPayload() {
  const payload = {};
  const site = document.getElementById("selector-site").value.trim();
  const role = document.getElementById("selector-role").value;
  const status = document.getElementById("selector-status").value;
  const vendor = document.getElementById("selector-vendor").value.trim();
  if (site) payload.site = site;
  if (role) payload.role = role;
  if (status) payload.status = status;
  if (vendor) payload.vendor = vendor;
  return payload;
}

function formatResult(result) {
  return JSON.stringify(result, null, 2);
}

function renderTextResult(nodeId, text) {
  const node = document.getElementById(nodeId);
  node.classList.remove("placeholder");
  node.textContent = typeof text === "string" ? text : formatResult(text);
}

function renderBatchResult(mode, result) {
  renderTextResult("batch-result", { mode, summary: result.summary, items: result.items });
}

function renderAutomationResult(mode, result) {
  const node = document.getElementById("automation-result");
  const caption = document.getElementById("automation-result-caption");

  caption.textContent = `${mode} · ${result.device_name || appState.selectedDeviceName}`;
  node.classList.remove("placeholder");

  if (Array.isArray(result.commands)) {
    const summary = [
      `device: ${result.device_name}`,
      `dry_run: ${result.dry_run ?? false}`,
      `changed: ${result.changed ?? false}`,
      `would_change: ${result.would_change ?? false}`,
      "",
      "commands:",
      ...result.commands,
    ];

    if (Array.isArray(result.after) && result.after.length) {
      summary.push("", "after:", ...result.after);
    }

    if (Array.isArray(result.current_lines) && Array.isArray(result.expected_lines)) {
      summary.push("", `compliant: ${result.compliant}`, "", "drift:", formatResult(result.drift));
    }

    node.textContent = summary.join("\n");
    return;
  }

  node.textContent = formatResult(result);
}

function renderAutomationError(mode, error) {
  const node = document.getElementById("automation-result");
  const caption = document.getElementById("automation-result-caption");
  caption.textContent = `${mode} failed`;
  node.classList.remove("placeholder");
  node.textContent = error.message;
}

function buildBatchRequest() {
  const request = collectConfigPayload();
  return {
    items: Array.from(appState.selectedBatchNames).map((deviceName) => ({ device_name: deviceName, request })),
  };
}

async function refreshSelectedDeviceDetails(settings, preserveForm = false) {
  const deviceName = appState.selectedDeviceName;
  if (!deviceName) {
    return;
  }

  try {
    const [device, runningConfigResult] = await Promise.all([
      requestJson(`/devices/${deviceName}`, settings),
      requestJson(`/automation/devices/${deviceName}/running-config`, settings)
        .then((payload) => ({ ok: true, payload }))
        .catch((error) => ({ ok: false, error })),
    ]);

    appState.selectedDevice = device;
    renderDevices(appState.devices);
    renderDeviceDetail(
      device,
      runningConfigResult.ok ? runningConfigResult.payload.lines : [],
      runningConfigResult.ok ? (runningConfigResult.payload.collection_error || "") : runningConfigResult.error.message,
      runningConfigResult.ok ? Boolean(runningConfigResult.payload.cached) : false,
    );
    if (!preserveForm) {
      populateConfigForm(device);
    }
    await refreshSnapshots(true);
  } catch (error) {
    document.getElementById("device-detail").innerHTML = `<p class="placeholder error-text">${escapeHtml(error.message)}</p>`;
    document.getElementById("device-caption").textContent = "Failed to load device";
    document.getElementById("device-status-badge").textContent = "error";
    document.getElementById("device-status-badge").className = "badge error";
  }
}

async function runAutomation(mode) {
  if (!appState.selectedDeviceName) {
    setStatus("Select a device in the table first.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const payload = collectConfigPayload();
  const deviceName = appState.selectedDeviceName;

  try {
    setStatus(`Running ${mode} for ${deviceName}...`);
    let path = `/automation/devices/${deviceName}/base-config/preview`;
    if (mode === "dry-run") {
      path = `/automation/devices/${deviceName}/base-config/apply?dry_run=true`;
    }
    if (mode === "apply") {
      path = `/automation/devices/${deviceName}/base-config/apply`;
    }
    if (mode === "compliance") {
      path = `/automation/devices/${deviceName}/base-config/compliance`;
    }

    const result = await requestApi(path, settings, {
      method: "POST",
      body: payload,
    });

    renderAutomationResult(mode, result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Operation ${mode} for ${deviceName} completed.`);
  } catch (error) {
    renderAutomationError(mode, error);
    setStatus(`Failed to execute ${mode}: ${error.message}`, true);
  }
}

async function runBatchOperation(mode) {
  if (!appState.selectedBatchNames.size) {
    setStatus("Select at least one device for batch mode.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const payload = buildBatchRequest();

  try {
    setStatus(`Running batch ${mode} for ${appState.selectedBatchNames.size} devices...`);
    let path = "/automation/batch/base-config/preview";
    if (mode === "dry-run") {
      path = "/automation/batch/base-config/apply?dry_run=true";
    }
    if (mode === "apply") {
      path = "/automation/batch/base-config/apply";
    }
    if (mode === "compliance") {
      path = "/automation/batch/base-config/compliance";
    }

    const result = await requestApi(path, settings, { method: "POST", body: payload });
    renderBatchResult(mode, result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Batch ${mode} completed.`);
  } catch (error) {
    renderTextResult("batch-result", error.message);
    setStatus(`Batch ${mode} failed: ${error.message}`, true);
  }
}

function renderSelectorDevices(response) {
  const node = document.getElementById("selector-results");
  const devices = response.devices || [];
  appState.selectorDevices = devices;
  document.getElementById("selector-summary").textContent = `${response.total_devices} devices matched`;

  if (!devices.length) {
    node.innerHTML = '<p class="placeholder">No devices matched the selector.</p>';
    return;
  }

  node.innerHTML = devices
    .map(
      (device) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(device.name)}</strong>
            <span class="badge ${statusClass(device.status)}">${escapeHtml(device.status)}</span>
          </header>
          <p>${escapeHtml(device.site)} / ${escapeHtml(device.role)} / ${escapeHtml(device.vendor)}</p>
          <p>${escapeHtml(device.management_ip)}</p>
        </article>
      `,
    )
    .join("");
}

async function resolveSelector() {
  const settings = getSettings();
  saveSettings(settings);
  const selector = buildSelectorPayload();

  try {
    const response = await requestApi("/automation/selection/resolve", settings, { method: "POST", body: selector });
    renderSelectorDevices(response);
    renderTextResult("selector-result", response);
    setStatus(`Resolved ${response.total_devices} devices from selector.`);
  } catch (error) {
    renderTextResult("selector-result", error.message);
    setStatus(`Selector resolve failed: ${error.message}`, true);
  }
}

async function runSelectorOperation(mode) {
  const settings = getSettings();
  saveSettings(settings);
  const payload = {
    selector: buildSelectorPayload(),
    request: collectConfigPayload(),
  };

  try {
    let path = "/automation/selection/base-config/preview";
    if (mode === "dry-run") {
      path = "/automation/selection/base-config/apply?dry_run=true";
    }
    if (mode === "apply") {
      path = "/automation/selection/base-config/apply";
    }
    if (mode === "compliance") {
      path = "/automation/selection/base-config/compliance";
    }

    const response = await requestApi(path, settings, { method: "POST", body: payload });
    if (response.devices) {
      renderSelectorDevices(response);
    }
    renderTextResult("selector-result", response);
    setStatus(`Selector ${mode} completed.`);
  } catch (error) {
    renderTextResult("selector-result", error.message);
    setStatus(`Selector ${mode} failed: ${error.message}`, true);
  }
}

async function createJob() {
  if (!appState.selectedDeviceName) {
    setStatus("Select a device before creating a job.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const body = {
    operation: document.getElementById("job-operation").value,
    device_name: appState.selectedDeviceName,
    request: collectConfigPayload(),
    dry_run: document.getElementById("job-dry-run").checked,
  };

  try {
    const result = await requestApi("/automation/jobs", settings, { method: "POST", body });
    appState.selectedJobId = result.job_id;
    renderTextResult("jobs-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Job ${result.job_id} created.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Failed to create job: ${error.message}`, true);
  }
}

async function executeSelectedJob() {
  if (!appState.selectedJobId) {
    setStatus("Select a job first.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/jobs/${appState.selectedJobId}/execute`, settings, { method: "POST" });
    renderTextResult("jobs-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Job ${appState.selectedJobId} executed.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Failed to execute job: ${error.message}`, true);
  }
}

async function retrySelectedJob() {
  if (!appState.selectedJobId) {
    setStatus("Select a job first.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/jobs/${appState.selectedJobId}/retry`, settings, { method: "POST" });
    renderTextResult("jobs-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Job ${appState.selectedJobId} retried.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Failed to retry job: ${error.message}`, true);
  }
}

function renderSnapshots(snapshots) {
  const node = document.getElementById("snapshots-list");
  if (!snapshots.length) {
    node.innerHTML = '<p class="placeholder">No snapshots for the selected device.</p>';
    appState.selectedSnapshotId = null;
    return;
  }

  if (!appState.selectedSnapshotId || !snapshots.some((snapshot) => snapshot.snapshot_id === appState.selectedSnapshotId)) {
    appState.selectedSnapshotId = snapshots[0].snapshot_id;
  }

  node.innerHTML = snapshots
    .map(
      (snapshot) => `
        <article class="stack-item selectable ${snapshot.snapshot_id === appState.selectedSnapshotId ? "selected-item" : ""}" data-snapshot-id="${escapeHtml(snapshot.snapshot_id)}">
          <header>
            <strong>${escapeHtml(snapshot.device_name)}</strong>
            <span class="badge">snapshot</span>
          </header>
          <p>Snapshot ID: ${escapeHtml(snapshot.snapshot_id)}</p>
          <p>${escapeHtml(snapshot.created_at)}</p>
        </article>
      `,
    )
    .join("");

  node.querySelectorAll("[data-snapshot-id]").forEach((card) => {
    card.addEventListener("click", () => {
      appState.selectedSnapshotId = card.dataset.snapshotId;
      renderSnapshots(snapshots);
    });
  });
}

async function refreshSnapshots(silent = false) {
  if (!appState.selectedDeviceName) {
    if (!silent) {
      setStatus("Select a device before loading snapshots.", true);
    }
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestJson(`/automation/devices/${appState.selectedDeviceName}/snapshots`, settings);
    renderSnapshots(result);
    if (!silent) {
      renderTextResult("snapshots-result", result);
      setStatus(`Loaded ${result.length} snapshots for ${appState.selectedDeviceName}.`);
    }
  } catch (error) {
    renderTextResult("snapshots-result", error.message);
    if (!silent) {
      setStatus(`Failed to load snapshots: ${error.message}`, true);
    }
  }
}

async function rollbackSelectedSnapshot() {
  if (!appState.selectedDeviceName || !appState.selectedSnapshotId) {
    setStatus("Select a device and snapshot first.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/devices/${appState.selectedDeviceName}/rollback/${appState.selectedSnapshotId}`, settings, { method: "POST" });
    renderTextResult("snapshots-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Rollback to snapshot ${appState.selectedSnapshotId} completed.`);
  } catch (error) {
    renderTextResult("snapshots-result", error.message);
    setStatus(`Rollback failed: ${error.message}`, true);
  }
}

async function refreshDashboard(options = {}) {
  const settings = getSettings();
  saveSettings(settings);
  setStatus("Refreshing dashboard...");

  try {
    const [health, database, devices, profiles, jobs, operations, operationsSummary] = await Promise.all([
      requestJson("/health", settings),
      requestJson("/system/database", settings),
      requestJson("/devices", settings),
      requestJson("/automation/profiles", settings),
      requestJson("/automation/jobs", settings),
      requestJson("/automation/operations?limit=5", settings),
      requestJson("/automation/operations/summary", settings),
    ]);

    appState.devices = devices;
    appState.profiles = profiles;

    if (health.status === "ok") {
      renderHealth();
    }
    renderDatabase(database);
    renderDevices(devices);
    renderProfiles(profiles);
    renderJobs(jobs);
    renderOperationsSummary(operationsSummary);
    renderOperations(operations);
    await refreshSelectedDeviceDetails(settings, options.preserveForm);
    setStatus("Dashboard refreshed. You can use device, batch, selector, jobs and snapshots scenarios.");
  } catch (error) {
    setStatus(`Failed to refresh dashboard: ${error.message}`, true);
  }
}

function resetConfigForm() {
  if (appState.selectedDevice) {
    populateConfigForm(appState.selectedDevice);
    setStatus(`Configuration form reset from ${appState.selectedDevice.name}.`);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  hydrateConnectionForm();
  document.getElementById("refresh-all").addEventListener("click", () => refreshDashboard());
  document.getElementById("connection-form").addEventListener("submit", (event) => {
    event.preventDefault();
    refreshDashboard();
  });
  document.getElementById("preview-config").addEventListener("click", () => runAutomation("preview"));
  document.getElementById("dry-run-config").addEventListener("click", () => runAutomation("dry-run"));
  document.getElementById("apply-config").addEventListener("click", () => runAutomation("apply"));
  document.getElementById("check-compliance").addEventListener("click", () => runAutomation("compliance"));
  document.getElementById("batch-preview").addEventListener("click", () => runBatchOperation("preview"));
  document.getElementById("batch-dry-run").addEventListener("click", () => runBatchOperation("dry-run"));
  document.getElementById("batch-apply").addEventListener("click", () => runBatchOperation("apply"));
  document.getElementById("batch-compliance").addEventListener("click", () => runBatchOperation("compliance"));
  document.getElementById("selector-resolve").addEventListener("click", resolveSelector);
  document.getElementById("selector-preview").addEventListener("click", () => runSelectorOperation("preview"));
  document.getElementById("selector-dry-run").addEventListener("click", () => runSelectorOperation("dry-run"));
  document.getElementById("selector-apply").addEventListener("click", () => runSelectorOperation("apply"));
  document.getElementById("selector-compliance").addEventListener("click", () => runSelectorOperation("compliance"));
  document.getElementById("create-job").addEventListener("click", createJob);
  document.getElementById("execute-job").addEventListener("click", executeSelectedJob);
  document.getElementById("retry-job").addEventListener("click", retrySelectedJob);
  document.getElementById("refresh-snapshots").addEventListener("click", () => refreshSnapshots());
  document.getElementById("rollback-snapshot").addEventListener("click", rollbackSelectedSnapshot);
  document.getElementById("reset-config").addEventListener("click", resetConfigForm);
  document.getElementById("add-interface").addEventListener("click", () => {
    appendInterfaceEditor();
    setStatus("Added a new port row. Fill in the interface name and IP before running automation.");
  });
  refreshDashboard();
});
