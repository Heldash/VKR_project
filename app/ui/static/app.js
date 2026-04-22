const STORAGE_KEY = "netauto-dashboard-settings";

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

async function requestJson(path, settings) {
  const response = await fetch(`${settings.baseUrl}${path}`, {
    headers: buildHeaders(settings),
  });

  if (!response.ok) {
    const details = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${details}`);
  }

  return response.json();
}

function setStatus(text, isError = false) {
  const node = document.getElementById("connection-status");
  node.textContent = text;
  node.classList.toggle("error-text", isError);
}

function renderDevices(devices) {
  const table = document.getElementById("devices-table");
  const reachable = devices.filter((device) => device.status === "reachable").length;
  document.getElementById("devices-value").textContent = String(devices.length);
  document.getElementById("devices-meta").textContent = `${reachable} reachable / ${devices.length - reachable} maintenance`;
  document.getElementById("devices-caption").textContent = `Загружено устройств: ${devices.length}`;

  if (!devices.length) {
    table.innerHTML = '<tr><td colspan="5" class="placeholder">Устройства не найдены</td></tr>';
    return;
  }

  table.innerHTML = devices
    .map(
      (device) => `
        <tr>
          <td><strong>${device.name}</strong><br /><span class="muted">${device.platform}</span></td>
          <td>${device.site}</td>
          <td>${device.role}</td>
          <td><span class="badge ${device.status === "reachable" ? "success" : "error"}">${device.status}</span></td>
          <td>${device.management_ip}</td>
        </tr>
      `,
    )
    .join("");
}

function renderProfiles(profiles) {
  const node = document.getElementById("profiles-list");
  document.getElementById("profiles-value").textContent = String(profiles.length);
  document.getElementById("profiles-meta").textContent = "готовых baseline-профилей";

  if (!profiles.length) {
    node.innerHTML = '<p class="placeholder">Профили не настроены</p>';
    return;
  }

  node.innerHTML = profiles
    .map(
      (profile) => `
        <article class="stack-item">
          <header>
            <strong>${profile.name}</strong>
            <span class="badge">${profile.interfaces.length} интерфейсов</span>
          </header>
          <p>${profile.description}</p>
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
            <strong>${job.job_type}</strong>
            <span class="badge ${job.status === "succeeded" ? "success" : job.status === "failed" ? "error" : ""}">${job.status}</span>
          </header>
          <p>Устройство: ${job.device_name}</p>
          <p>Backend: ${job.queue_backend}</p>
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
            <strong>${operation.operation}</strong>
            <span class="badge ${operation.status === "success" ? "success" : "error"}">${operation.status}</span>
          </header>
          <p>Устройство: ${operation.device_name}</p>
          <p>Backend: ${operation.backend}</p>
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

async function refreshDashboard() {
  const settings = getSettings();
  saveSettings(settings);
  setStatus("Обновление панели...");

  try {
    const [health, database, devices, profiles, jobs, operations, operationsSummary] =
      await Promise.all([
        requestJson("/health", settings),
        requestJson("/system/database", settings),
        requestJson("/devices", settings),
        requestJson("/automation/profiles", settings),
        requestJson("/automation/jobs", settings),
        requestJson("/automation/operations?limit=5", settings),
        requestJson("/automation/operations/summary", settings),
      ]);

    if (health.status === "ok") {
      renderHealth();
    }
    renderDatabase(database);
    renderDevices(devices);
    renderProfiles(profiles);
    renderJobs(jobs);
    renderOperationsSummary(operationsSummary);
    renderOperations(operations);
    setStatus("Панель обновлена. Можно переходить к следующим сценариям автоматизации.");
  } catch (error) {
    setStatus(`Не удалось обновить данные: ${error.message}`, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  hydrateConnectionForm();
  document.getElementById("refresh-all").addEventListener("click", refreshDashboard);
  document.getElementById("connection-form").addEventListener("submit", (event) => {
    event.preventDefault();
    refreshDashboard();
  });
  refreshDashboard();
});
