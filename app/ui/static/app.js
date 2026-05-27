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

const STATUS_LABELS = {
  reachable: "доступно",
  maintenance: "обслуживание",
  unreachable: "недоступно",
  queued: "в очереди",
  running: "выполняется",
  success: "успешно",
  succeeded: "успешно",
  failed: "ошибка",
};

const MODE_LABELS = {
  preview: "предпросмотр",
  "dry-run": "пробный запуск",
  apply: "применение",
  compliance: "проверка соответствия",
  rollback: "откат",
};

function translateStatus(status) {
  return STATUS_LABELS[status] || status;
}

function translateMode(mode) {
  return MODE_LABELS[mode] || mode;
}

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
    ? `Выбрано ${names.length}: ${names.join(", ")}`
    : "Устройства не выбраны";
}

function renderDevices(devices) {
  const table = document.getElementById("devices-table");
  const reachable = devices.filter((device) => device.status === "reachable").length;
  const maintenance = devices.filter((device) => device.status === "maintenance").length;
  const unreachable = devices.filter((device) => device.status === "unreachable").length;

  document.getElementById("devices-value").textContent = String(devices.length);
  document.getElementById("devices-meta").textContent =
    `${reachable} доступно / ${unreachable} недоступно / ${maintenance} обслуживание`;
  document.getElementById("devices-caption").textContent = `Загружено устройств: ${devices.length}`;

  const validNames = new Set(devices.map((device) => device.name));
  appState.selectedBatchNames = new Set([...appState.selectedBatchNames].filter((name) => validNames.has(name)));

  if (!devices.length) {
    table.innerHTML = '<tr><td colspan="6" class="placeholder">Устройства не найдены.</td></tr>';
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
          <td><span class="badge ${statusClass(device.status)}">${escapeHtml(translateStatus(device.status))}</span></td>
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
  document.getElementById("profiles-meta").textContent = "базовые шаблоны";

  if (!profiles.length) {
    node.innerHTML = '<p class="placeholder">Профили не настроены.</p>';
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
    ? `последний статус: ${translateStatus(jobs[0].status)}`
    : "очередь пуста";

  if (!jobs.length) {
    node.innerHTML = '<p class="placeholder">Задач пока нет.</p>';
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
            <strong>${escapeHtml(translateMode(job.operation))}</strong>
            <span class="badge ${statusClass(job.status)}">${escapeHtml(translateStatus(job.status))}</span>
          </header>
          <p>Устройство: ${escapeHtml(job.device_name)}</p>
          <p>Бэкенд очереди: ${escapeHtml(job.queue_backend)}${job.dry_run ? " / пробный запуск" : ""}</p>
          <p class="muted">ID задачи: ${escapeHtml(job.job_id)}</p>
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
    `${summary.successful_operations ?? summary.success} успешно / ${summary.failed_operations ?? summary.failed} с ошибкой`;
}

function renderOperations(operations) {
  const node = document.getElementById("operations-list");

  if (!operations.length) {
    node.innerHTML = '<p class="placeholder">Операции ещё не выполнялись.</p>';
    return;
  }

  node.innerHTML = operations
    .map(
      (operation) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(translateMode(operation.operation))}</strong>
            <span class="badge ${statusClass(operation.status)}">${escapeHtml(translateStatus(operation.status))}</span>
          </header>
          <p>Устройство: ${escapeHtml(operation.device_name)}</p>
          <p>Бэкенд: ${escapeHtml(operation.backend)}</p>
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
  document.getElementById("database-value").textContent = database.initialized ? "ГОТОВО" : "НЕДОСТУПНО";
  document.getElementById("database-meta").textContent = `${database.roles_count} ролей / ${database.users_count} пользователей`;
}

function parseInterfaceStateFromRunningConfig(device, runningConfigLines) {
  const fallback = (device.interfaces || []).map((iface) => ({
    name: iface.name,
    description: iface.description || "",
    ipv4_address: iface.ipv4_address || "",
    enabled: iface.enabled ?? true,
    source: "inventory",
  }));

  if (!Array.isArray(runningConfigLines) || !runningConfigLines.length) {
    return fallback;
  }

  const platform = String(device.platform || "").toLowerCase();
  if (platform.includes("juniper")) {
    return parseJuniperInterfaces(runningConfigLines, fallback);
  }
  if (platform.includes("huawei")) {
    return parseBlockInterfaces(runningConfigLines, fallback, "quit", "undo shutdown");
  }
  return parseBlockInterfaces(runningConfigLines, fallback, "exit", "no shutdown");
}

function cloneInterfaceMap(fallback) {
  const map = new Map();
  fallback.forEach((iface) => {
    map.set(iface.name, { ...iface });
  });
  return map;
}

function finalizeInterfaceList(interfaceMap, fallback) {
  const fallbackNames = fallback.map((iface) => iface.name);
  const known = fallbackNames
    .map((name) => interfaceMap.get(name))
    .filter(Boolean);
  const dynamic = Array.from(interfaceMap.values()).filter((iface) => !fallbackNames.includes(iface.name));
  return [...known, ...dynamic];
}

function parseBlockInterfaces(runningConfigLines, fallback, sectionTerminator, enabledLine) {
  const interfaceMap = cloneInterfaceMap(fallback);
  let current = null;

  const ensureInterface = (name) => {
    if (!interfaceMap.has(name)) {
      interfaceMap.set(name, {
        name,
        description: "",
        ipv4_address: "",
        enabled: true,
        source: "live",
      });
    }
    return interfaceMap.get(name);
  };

  runningConfigLines.forEach((rawLine) => {
    const line = String(rawLine || "");
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }
    if (trimmed.startsWith("interface ")) {
      const name = trimmed.slice("interface ".length).trim();
      current = ensureInterface(name);
      current.source = "live";
      return;
    }
    if (trimmed === sectionTerminator) {
      current = null;
      return;
    }
    if (!current) {
      return;
    }
    if (trimmed.startsWith("description ")) {
      current.description = trimmed.slice("description ".length).trim();
      return;
    }
    if (trimmed.startsWith("ip address ")) {
      current.ipv4_address = trimmed.slice("ip address ".length).trim();
      return;
    }
    if (trimmed === "shutdown") {
      current.enabled = false;
      return;
    }
    if (trimmed === enabledLine) {
      current.enabled = true;
    }
  });

  return finalizeInterfaceList(interfaceMap, fallback);
}

function parseJuniperInterfaces(runningConfigLines, fallback) {
  const interfaceMap = cloneInterfaceMap(fallback);

  const ensureInterface = (name) => {
    if (!interfaceMap.has(name)) {
      interfaceMap.set(name, {
        name,
        description: "",
        ipv4_address: "",
        enabled: true,
        source: "live",
      });
    }
    return interfaceMap.get(name);
  };

  runningConfigLines.forEach((rawLine) => {
    const trimmed = String(rawLine || "").trim();
    if (!trimmed.startsWith("set interfaces ") && !trimmed.startsWith("delete interfaces ")) {
      return;
    }
    const parts = trimmed.split(/\s+/);
    const name = parts[2];
    if (!name) {
      return;
    }
    const iface = ensureInterface(name);
    iface.source = "live";

    if (trimmed.includes(" description ")) {
      const description = trimmed.split(" description ")[1] || "";
      iface.description = description.replace(/^"|"$/g, "");
      return;
    }
    if (trimmed.includes(" family inet address ")) {
      iface.ipv4_address = trimmed.split(" family inet address ")[1] || "";
      return;
    }
    if (trimmed === `set interfaces ${name} disable`) {
      iface.enabled = false;
      return;
    }
    if (trimmed === `delete interfaces ${name} disable`) {
      iface.enabled = true;
    }
  });

  return finalizeInterfaceList(interfaceMap, fallback);
}

function renderDeviceDetail(device, runningConfigLines, runningConfigError = "", runningConfigCached = false) {
  const container = document.getElementById("device-detail");
  const badge = document.getElementById("device-status-badge");
  document.getElementById("device-caption").textContent = `${device.name} · ${device.management_ip}`;
  document.getElementById("snapshots-caption").textContent = `Снимки состояния для ${device.name} (только mock backend)`;
  badge.textContent = translateStatus(device.status);
  badge.className = `badge ${statusClass(device.status)}`;

  const liveInterfaces = parseInterfaceStateFromRunningConfig(device, runningConfigLines);

  const interfacesHtml = liveInterfaces.length
    ? liveInterfaces
        .map(
          (iface) => `
            <article class="interface-card">
              <header>
                <strong>${escapeHtml(iface.name)}</strong>
                <span class="badge ${iface.enabled ? "success" : "error"}">${iface.enabled ? "включен" : "выключен"}</span>
              </header>
              <p>${escapeHtml(iface.description || "Описание отсутствует")}</p>
              <p class="muted">${escapeHtml(iface.ipv4_address || "IP не задан")}</p>
            </article>
          `,
        )
        .join("")
    : '<p class="placeholder">Интерфейсы не описаны.</p>';

  const runningConfigState = runningConfigCached
    ? '<span class="badge warn">кэш</span>'
    : '<span class="badge success">актуально</span>';
  const runningConfigWarning = runningConfigError
    ? `<p class="placeholder ${runningConfigCached ? "" : "error-text"}">${escapeHtml(runningConfigError)}</p>`
    : "";

  container.innerHTML = `
    <div class="detail-grid">
      <article class="detail-card">
        <span class="label">Имя узла</span>
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
        <span class="label">Вендор</span>
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
          <span class="caption">${liveInterfaces.length} шт. · текущее состояние</span>
        </div>
        <div class="interface-list">${interfacesHtml}</div>
      </section>
      <section class="panel-subsection">
        <div class="panel-heading compact">
          <h3>Running-config</h3>
          <span class="caption">Текущее представление backend</span>
        </div>
        <div class="running-config-state">${runningConfigState}</div>
        ${runningConfigWarning}
        <pre class="code-block">${escapeHtml((runningConfigLines || []).join("\n") || "Конфигурация отсутствует")}</pre>
      </section>
    </div>
  `;
}

function buildInterfaceEditorCard(iface, index) {
  return `
    <article class="interface-editor" data-index="${index}">
      <div class="interface-editor-header">
        <strong>Порт ${index + 1}</strong>
        <div class="interface-editor-actions">
          <label class="checkbox-inline">
            <input type="checkbox" data-field="enabled" ${iface.enabled ? "checked" : ""} />
            <span>Включен</span>
          </label>
          <button type="button" class="secondary-action remove-interface">Удалить</button>
        </div>
      </div>
      <label>
        <span>Имя порта</span>
        <input type="text" data-field="name" value="${escapeHtml(iface.name)}" placeholder="GigabitEthernet0/0" />
      </label>
      <label>
        <span>Описание</span>
        <input type="text" data-field="description" value="${escapeHtml(iface.description || "")}" />
      </label>
      <label>
        <span>IPv4 / префикс</span>
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
      title.textContent = `Порт ${index + 1}`;
    }
  });
}

function attachInterfaceEditorEvents() {
  document.querySelectorAll(".remove-interface").forEach((button) => {
    button.onclick = () => {
      button.closest(".interface-editor")?.remove();
      const container = document.getElementById("config-interfaces");
      if (!container.querySelector(".interface-editor")) {
        container.innerHTML = '<p class="placeholder">Порты ещё не добавлены. Используйте кнопку "Добавить порт".</p>';
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
    container.innerHTML = '<p class="placeholder">Порты ещё не добавлены. Используйте кнопку "Добавить порт".</p>';
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
  document.getElementById("config-help").textContent = "Эталонная конфигурация для автоматизации";
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
  renderTextResult("batch-result", { mode: translateMode(mode), summary: result.summary, items: result.items });
}

function renderAutomationResult(mode, result) {
  const node = document.getElementById("automation-result");
  const caption = document.getElementById("automation-result-caption");

  caption.textContent = `${translateMode(mode)} ? ${result.device_name || appState.selectedDeviceName}`;
  node.classList.remove("placeholder");

  if (Array.isArray(result.commands)) {
    const summary = [
      `??????????: ${result.device_name}`,
      `??????? ??????: ${result.dry_run ?? false}`,
      `????????: ${result.changed ?? false}`,
      `????? ?????????: ${result.would_change ?? false}`,
      "",
      "???????:",
      ...result.commands,
    ];

    if (Array.isArray(result.after) && result.after.length) {
      summary.push(
        "",
        result.dry_run ? "????????? ????????? ????? ??????????:" : "????????? ????? ??????????:",
        ...result.after,
      );
    }

    if (Array.isArray(result.current_lines) && Array.isArray(result.expected_lines)) {
      summary.push("", `?????????????: ${result.compliant}`, "", "???????????:", formatResult(result.drift));
    }

    node.textContent = summary.join("
");
    return;
  }

  node.textContent = formatResult(result);
}

function renderAutomationError(mode, error) {
  const node = document.getElementById("automation-result");
  const caption = document.getElementById("automation-result-caption");
  caption.textContent = `${translateMode(mode)}: ??????`;
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
    document.getElementById("device-caption").textContent = "Не удалось загрузить устройство";
    document.getElementById("device-status-badge").textContent = "ошибка";
    document.getElementById("device-status-badge").className = "badge error";
  }
}

async function runAutomation(mode) {
  if (!appState.selectedDeviceName) {
    setStatus("Сначала выберите устройство в таблице.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const payload = collectConfigPayload();
  const deviceName = appState.selectedDeviceName;

  try {
    setStatus(`Выполняется "${translateMode(mode)}" для ${deviceName}...`);
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
    setStatus(`Операция "${translateMode(mode)}" для ${deviceName} завершена.`);
  } catch (error) {
    renderAutomationError(mode, error);
    setStatus(`Не удалось выполнить "${translateMode(mode)}": ${error.message}`, true);
  }
}

async function runBatchOperation(mode) {
  if (!appState.selectedBatchNames.size) {
    setStatus("Выберите хотя бы одно устройство для пакетного режима.", true);
    return;
  }

  const settings = getSettings();
  saveSettings(settings);
  const payload = buildBatchRequest();

  try {
    setStatus(`Выполняется пакетная операция "${translateMode(mode)}" для ${appState.selectedBatchNames.size} устройств...`);
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
    setStatus(`Пакетная операция "${translateMode(mode)}" завершена.`);
  } catch (error) {
    renderTextResult("batch-result", error.message);
    setStatus(`Пакетная операция "${translateMode(mode)}" завершилась ошибкой: ${error.message}`, true);
  }
}

function renderSelectorDevices(response) {
  const node = document.getElementById("selector-results");
  const devices = response.devices || [];
  appState.selectorDevices = devices;
  document.getElementById("selector-summary").textContent = `Совпадений: ${response.total_devices}`;

  if (!devices.length) {
    node.innerHTML = '<p class="placeholder">По селектору устройства не найдены.</p>';
    return;
  }

  node.innerHTML = devices
    .map(
      (device) => `
        <article class="stack-item">
          <header>
            <strong>${escapeHtml(device.name)}</strong>
            <span class="badge ${statusClass(device.status)}">${escapeHtml(translateStatus(device.status))}</span>
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
    setStatus(`По селектору найдено ${response.total_devices} устройств.`);
  } catch (error) {
    renderTextResult("selector-result", error.message);
    setStatus(`Не удалось выполнить подбор по селектору: ${error.message}`, true);
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
    setStatus(`Операция по селектору "${translateMode(mode)}" завершена.`);
  } catch (error) {
    renderTextResult("selector-result", error.message);
    setStatus(`Операция по селектору "${translateMode(mode)}" завершилась ошибкой: ${error.message}`, true);
  }
}

async function createJob() {
  if (!appState.selectedDeviceName) {
    setStatus("Перед созданием задачи выберите устройство.", true);
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
    setStatus(`Задача ${result.job_id} создана.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Не удалось создать задачу: ${error.message}`, true);
  }
}

async function executeSelectedJob() {
  if (!appState.selectedJobId) {
    setStatus("Сначала выберите задачу.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/jobs/${appState.selectedJobId}/execute`, settings, { method: "POST" });
    renderTextResult("jobs-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Задача ${appState.selectedJobId} выполнена.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Не удалось выполнить задачу: ${error.message}`, true);
  }
}

async function retrySelectedJob() {
  if (!appState.selectedJobId) {
    setStatus("Сначала выберите задачу.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/jobs/${appState.selectedJobId}/retry`, settings, { method: "POST" });
    renderTextResult("jobs-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Задача ${appState.selectedJobId} повторно запущена.`);
  } catch (error) {
    renderTextResult("jobs-result", error.message);
    setStatus(`Не удалось повторить задачу: ${error.message}`, true);
  }
}

function renderSnapshots(snapshots) {
  const node = document.getElementById("snapshots-list");
  if (!snapshots.length) {
    node.innerHTML = '<p class="placeholder">Для выбранного устройства снимков нет.</p>';
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
            <span class="badge">снимок</span>
          </header>
          <p>ID снимка: ${escapeHtml(snapshot.snapshot_id)}</p>
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
      setStatus("Перед загрузкой снимков выберите устройство.", true);
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
      setStatus(`Загружено ${result.length} снимков для ${appState.selectedDeviceName}.`);
    }
  } catch (error) {
    renderTextResult("snapshots-result", error.message);
    if (!silent) {
      setStatus(`Не удалось загрузить снимки: ${error.message}`, true);
    }
  }
}

async function rollbackSelectedSnapshot() {
  if (!appState.selectedDeviceName || !appState.selectedSnapshotId) {
    setStatus("Сначала выберите устройство и снимок.", true);
    return;
  }
  const settings = getSettings();
  saveSettings(settings);

  try {
    const result = await requestApi(`/automation/devices/${appState.selectedDeviceName}/rollback/${appState.selectedSnapshotId}`, settings, { method: "POST" });
    renderTextResult("snapshots-result", result);
    await refreshDashboard({ preserveForm: true });
    setStatus(`Откат к снимку ${appState.selectedSnapshotId} завершён.`);
  } catch (error) {
    renderTextResult("snapshots-result", error.message);
    setStatus(`Откат завершился ошибкой: ${error.message}`, true);
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
    setStatus("Панель обновлена. Доступны сценарии по устройствам, пакетным операциям, селекторам, задачам и снимкам.");
  } catch (error) {
    setStatus(`Не удалось обновить панель: ${error.message}`, true);
  }
}

function resetConfigForm() {
  if (appState.selectedDevice) {
    populateConfigForm(appState.selectedDevice);
    setStatus(`Форма конфигурации сброшена по данным ${appState.selectedDevice.name}.`);
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
    setStatus("Добавлена новая строка порта. Заполните имя интерфейса и IP перед запуском автоматизации.");
  });
  refreshDashboard();
});
