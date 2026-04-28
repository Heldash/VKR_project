const STORAGE_KEY = "netauto-dashboard-settings";
const DEFAULT_DOMAIN = "lab.local";
const DEFAULT_BANNER = "Managed by NetAuto";

const appState = {
  devices: [],
  profiles: [],
  selectedDeviceName: null,
  selectedDevice: null,
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
  const headers = {
    Accept: "application/json",
  };
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
  if (status === "reachable" || status === "success" || status === "succeeded") {
    return "success";
  }
  if (status === "queued" || status === "running") {
    return "warn";
  }
  return "error";
}

function setSelectedDeviceName(deviceName) {
  appState.selectedDeviceName = deviceName;
}

function renderDevices(devices) {
  const table = document.getElementById("devices-table");
  const reachable = devices.filter((device) => device.status === "reachable").length;
  const maintenance = devices.filter((device) => device.status === "maintenance").length;
  const unreachable = devices.filter((device) => device.status === "unreachable").length;

  document.getElementById("devices-value").textContent = String(devices.length);
  document.getElementById("devices-meta").textContent =
    `${reachable} reachable / ${unreachable} unreachable / ${maintenance} maintenance`;
  document.getElementById("devices-caption").textContent = `Загружено устройств: ${devices.length}`;

  if (!devices.length) {
    table.innerHTML = '<tr><td colspan="5" class="placeholder">Устройства не найдены</td></tr>';
    return;
  }

  if (!appState.selectedDeviceName || !devices.some((device) => device.name === appState.selectedDeviceName)) {
    setSelectedDeviceName(devices[0].name);
  }

  table.innerHTML = devices
    .map(
      (device) => `
        <tr class="device-row ${device.name === appState.selectedDeviceName ? "selected" : ""}" data-device-name="${escapeHtml(device.name)}">
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
    row.addEventListener("click", async () => {
      const deviceName = row.dataset.deviceName;
      if (!deviceName || deviceName === appState.selectedDeviceName) {
        return;
      }
      setSelectedDeviceName(deviceName);
      renderDevices(appState.devices);
      await refreshSelectedDeviceDetails(getSettings());
    });
  });
}

function renderProfiles(profiles) {
  const node = document.getElementById("profiles-list");
  document.getElementById("profiles-value").textContent = String(profiles.length);
  document.getElementById("profiles-meta").textContent = "готовые baseline-профили";

  if (!profiles.length) {
    node.innerHTML = '<p class="placeholder">Профили не настроены</p>';
    return;
  }

  node.innerHTML = profiles
    .map(
      (profile) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(profile.name)}</strong>
            <span class="badge">${profile.interfaces.length} интерфейсов</span>
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
    ? `последний статус: ${jobs[0].status}`
    : "очередь пуста";

  if (!jobs.length) {
    node.innerHTML = '<p class="placeholder">Очередь пока пустая</p>';
    return;
  }

  node.innerHTML = jobs
    .map(
      (job) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(job.job_type)}</strong>
            <span class="badge ${statusClass(job.status)}">${escapeHtml(job.status)}</span>
          </header>
          <p>Устройство: ${escapeHtml(job.device_name)}</p>
          <p>Backend: ${escapeHtml(job.queue_backend)}</p>
        </article>
      `,
    )
    .join("");
}

function renderOperationsSummary(summary) {
  document.getElementById("operations-value").textContent = String(summary.total);
  document.getElementById("operations-meta").textContent = `${summary.success} success / ${summary.failed} failed`;
}

function renderOperations(operations) {
  const node = document.getElementById("operations-list");

  if (!operations.length) {
    node.innerHTML = '<p class="placeholder">Операции ещё не выполнялись</p>';
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
          <p>Устройство: ${escapeHtml(operation.device_name)}</p>
          <p>Backend: ${escapeHtml(operation.backend)}</p>
        </article>
      `,
    )
    .join("");
}

function renderHealth() {
  document.getElementById("health-value").textContent = "OK";
  document.getElementById("health-meta").textContent = "FastAPI доступен";
}

function renderDatabase(database) {
  document.getElementById("database-value").textContent = database.initialized ? "READY" : "DOWN";
  document.getElementById("database-meta").textContent = `${database.roles_count} roles / ${database.users_count} users`;
}

function renderDeviceDetail(device, runningConfigLines, runningConfigError = "", runningConfigCached = false) {
  const container = document.getElementById("device-detail");
  const badge = document.getElementById("device-status-badge");
  document.getElementById("device-caption").textContent = `${device.name} · ${device.management_ip}`;
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
              <p>${escapeHtml(iface.description || "Без описания")}</p>
              <p class="muted">${escapeHtml(iface.ipv4_address || "IP не задан")}</p>
            </article>
          `,
        )
        .join("")
    : '<p class="placeholder">Интерфейсы не описаны.</p>';

  const runningConfigState = runningConfigCached
    ? '<span class="badge warn">cached</span>'
    : '<span class="badge success">live</span>';
  const runningConfigWarning = runningConfigError
    ? `<p class="placeholder ${runningConfigCached ? "" : "error-text"}">${escapeHtml(runningConfigError)}</p>`
    : "";
  const runningConfigHtml = `
    <div class="running-config-state">${runningConfigState}</div>
    ${runningConfigWarning}
    <pre class="code-block">${escapeHtml((runningConfigLines || []).join("\n") || "Пустая конфигурация")}</pre>
  `;

  container.innerHTML = `
    <div class="detail-grid">
      <article class="detail-card">
        <span class="label">Имя</span>
        <strong>${escapeHtml(device.hostname)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Площадка</span>
        <strong>${escapeHtml(device.site)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Роль</span>
        <strong>${escapeHtml(device.role)}</strong>
      </article>
      <article class="detail-card">
        <span class="label">Платформа</span>
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
          <h3>Интерфейсы</h3>
          <span class="caption">${device.interfaces.length} шт.</span>
        </div>
        <div class="interface-list">${interfacesHtml}</div>
      </section>
      <section class="panel-subsection">
        <div class="panel-heading compact">
          <h3>Running-config</h3>
          <span class="caption">Текущее состояние устройства</span>
        </div>
        ${runningConfigHtml}
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

    node.textContent = summary.join("\n");
    return;
  }

  node.textContent = JSON.stringify(result, null, 2);
}

function renderAutomationError(mode, error) {
  const node = document.getElementById("automation-result");
  const caption = document.getElementById("automation-result-caption");
  caption.textContent = `${mode} завершился с ошибкой`;
  node.classList.remove("placeholder");
  node.textContent = error.message;
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
  } catch (error) {
    document.getElementById("device-detail").innerHTML = `<p class="placeholder error-text">${escapeHtml(error.message)}</p>`;
    document.getElementById("device-caption").textContent = "Не удалось загрузить устройство";
    document.getElementById("device-status-badge").textContent = "error";
    document.getElementById("device-status-badge").className = "badge error";
  }
}

async function runAutomation(mode) {
  if (!appState.selectedDeviceName) {
    setStatus("Сначала выбери устройство в таблице.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const payload = collectConfigPayload();
  const deviceName = appState.selectedDeviceName;

  try {
    setStatus(`Выполняется ${mode} для ${deviceName}...`);
    let path = `/automation/devices/${deviceName}/base-config/preview`;
    if (mode === "dry-run") {
      path = `/automation/devices/${deviceName}/base-config/apply?dry_run=true`;
    }
    if (mode === "apply") {
      path = `/automation/devices/${deviceName}/base-config/apply`;
    }

    const result = await requestApi(path, settings, {
      method: "POST",
      body: payload,
    });

    renderAutomationResult(mode, result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Операция ${mode} для ${deviceName} завершена.`);
  } catch (error) {
    renderAutomationError(mode, error);
    setStatus(`Не удалось выполнить ${mode}: ${error.message}`, true);
  }
}

async function refreshDashboard(options = {}) {
  const settings = getSettings();
  saveSettings(settings);
  setStatus("Обновление панели...");

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
    setStatus("Панель обновлена. Можно работать с выбранным устройством.");
  } catch (error) {
    setStatus(`Не удалось обновить данные: ${error.message}`, true);
  }
}

function resetConfigForm() {
  if (appState.selectedDevice) {
    populateConfigForm(appState.selectedDevice);
    setStatus(`Форма сброшена по данным ${appState.selectedDevice.name}.`);
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
  document.getElementById("reset-config").addEventListener("click", resetConfigForm);
  document.getElementById("add-interface").addEventListener("click", () => {
    appendInterfaceEditor();
    setStatus("Added a new port row. Fill in the interface name and IP before running automation.");
  });
  refreshDashboard();
});
