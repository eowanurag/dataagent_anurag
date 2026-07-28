"use strict";

const $ = (id) => document.getElementById(id);
let currentInvestigationId = null;
let isRunning = false;
let knownFileIds = new Set();
let selectedFileItems = [];
let pendingFileItems = [];

const SESSION_KEY = "uppolice.lastInvestigationId";
function loadSession() {
  try {
    const saved = localStorage.getItem(SESSION_KEY);
    if (saved) currentInvestigationId = saved;
  } catch {}
}
function saveSession() {
  try {
    if (currentInvestigationId) localStorage.setItem(SESSION_KEY, currentInvestigationId);
  } catch {}
}
function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch {}
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatBytes(n) {
  if (!Number.isFinite(n)) return "";
  if (n < 1024) return `${n} bytes`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(2)} MB`;
}

function showToast(message, type = "info") {
  let container = $("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.style.position = "fixed";
    container.style.right = "16px";
    container.style.bottom = "16px";
    container.style.zIndex = "9999";
    container.style.display = "flex";
    container.style.flexDirection = "column";
    container.style.gap = "8px";
    document.body.appendChild(container);
  }
  const el = document.createElement("div");
  el.textContent = message;
  el.style.padding = "10px 12px";
  el.style.borderRadius = "6px";
  el.style.background = type === "error" ? "#b91c1c" : type === "success" ? "#15803d" : "#1f2937";
  el.style.color = "#fff";
  el.style.font = "12px ui-sans-serif, system-ui, sans-serif";
  el.style.boxShadow = "0 4px 12px rgba(0,0,0,0.25)";
  el.style.maxWidth = "320px";
  container.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 0.2s ease";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 200);
  }, 2500);
}

function openPreview(rows, title) {
  let overlay = $("preview-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "preview-overlay";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.zIndex = "9000";
    overlay.style.background = "rgba(15,23,42,0.55)";
    overlay.style.display = "none";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.padding = "24px";
    document.body.appendChild(overlay);

    const modal = document.createElement("div");
    modal.id = "preview-modal";
    modal.style.background = "#ffffff";
    modal.style.borderRadius = "8px";
    modal.style.maxWidth = "960px";
    modal.style.width = "100%";
    modal.style.maxHeight = "85vh";
    modal.style.overflow = "auto";
    modal.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";
    modal.innerHTML = `
      <div style="padding:12px 14px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between;">
        <strong id="preview-title">Preview</strong>
        <button id="preview-close" style="background:#e5e7eb;border:0;border-radius:4px;padding:6px 10px;cursor:pointer;">Close</button>
      </div>
      <div id="preview-body" style="padding:12px 14px;"></div>
    `;
    overlay.appendChild(modal);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.style.display = "none";
    });
    modal.querySelector("#preview-close").addEventListener("click", () => {
      overlay.style.display = "none";
    });
  }
  const body = overlay.querySelector("#preview-body");
  const titleEl = overlay.querySelector("#preview-title");
  titleEl.textContent = title || "Preview";
  body.innerHTML = "";
  if (!Array.isArray(rows) || !rows.length) {
    body.innerHTML = `<div class="muted">No rows available for preview.</div>`;
  } else {
    const table = document.createElement("table");
    table.style.width = "100%";
    table.style.borderCollapse = "collapse";
    table.style.font = "12px ui-sans-serif, system-ui, sans-serif";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    Object.keys(rows[0] || {}).forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col;
      th.style.textAlign = "left";
      th.style.padding = "8px";
      th.style.borderBottom = "1px solid #e5e7eb";
      th.style.background = "#f8fafc";
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.slice(0, 200).forEach((row) => {
      const tr = document.createElement("tr");
      Object.values(row).forEach((val) => {
        const td = document.createElement("td");
        td.textContent = val == null ? "" : String(val);
        td.style.padding = "8px";
        td.style.borderBottom = "1px solid #f1f5f9";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    body.appendChild(table);
  }
  overlay.style.display = "flex";
}

async function loadHealth() {
  const badge = $("provider-badge");
  let provider = null;
  let model = null;
  try {
    const res = await fetch("/health");
    const body = await res.json();
    const { provider: p, model: m, key_configured: keyed } = body.data || {};
    provider = p || null;
    model = m || null;
    badge.textContent = keyed && provider && model ? `Backend ready · ${provider} · ${model}` : "Backend ready";
  } catch {
    badge.textContent = "Backend unreachable";
  }
  await loadModelUsage(provider, model);
}

async function loadModelUsage(provider, model) {
  const providerText = $("usage-provider");
  const modelText = $("usage-model");
  const lastIo = $("usage-last-io");
  const todayIo = $("usage-today-io");
  const contextRow = $("usage-context");
  const datasetsRow = $("usage-datasets");
  const costRow = $("usage-cost");
  const modelSelect = $("model-select");
  const providerSelect = $("provider-select");
  const errorBox = $("model-error");

  if (providerText) providerText.textContent = provider ? String(provider).toUpperCase() : "—";
  if (modelText) modelText.textContent = model || "—";
  if (lastIo) lastIo.textContent = "— / —";
  if (todayIo) todayIo.textContent = "0 / 0 / 0";
  if (contextRow) contextRow.textContent = "0 / 10,00,000";
  if (datasetsRow) datasetsRow.textContent = "0 · 0";
  if (costRow) costRow.textContent = "$0.00000";
  if (modelSelect) modelSelect.innerHTML = "";
  if (providerSelect) providerSelect.innerHTML = "";

  let registry = null;
  try {
    const res = await fetch('/models');
    if (res.ok) {
      registry = await res.json();
    }
  } catch {
    registry = null;
  }

  const seenProviders = new Map();

  if (registry?.models?.length && providerSelect && modelSelect) {
    for (const m of registry.models) {
      if (!seenProviders.has(m.provider)) {
        const opt = document.createElement('option');
        opt.value = m.provider;
        opt.textContent = m.provider;
        if (provider && m.provider === provider) opt.selected = true;
        if (!provider && m.provider === 'openrouter') opt.selected = true;
        providerSelect.appendChild(opt);
        seenProviders.set(m.provider, true);
      }
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = `${m.label} (${m.provider})`;
      if (model && m.id === model) opt.selected = true;
      if (!model && m.default) opt.selected = true;
      modelSelect.appendChild(opt);
    }
  } else {
    if (providerSelect) {
      const opt = document.createElement('option');
      opt.value = 'openrouter';
      opt.textContent = 'openrouter';
      providerSelect.appendChild(opt);
    }
    if (modelSelect) {
      const opt = document.createElement('option');
      opt.value = 'meta-llama/llama-3.1-70b-instruct';
      opt.textContent = 'Llama 3.1 70B Instruct';
      modelSelect.appendChild(opt);
    }
  }

  const chosenProvider = (providerSelect?.value || provider || "openrouter").trim();
  const chosenModel = (modelSelect?.value || model || "meta-llama/llama-3.1-70b-instruct").trim();
  if (providerText) providerText.textContent = chosenProvider || "—";
  if (modelText) modelText.textContent = chosenModel || "—";
}

function loadSettingsFromUI() {
  const providerSelect = $("provider-select");
  const modelSelect = $("model-select");
  return {
    provider: providerSelect ? providerSelect.value : null,
    model: modelSelect ? modelSelect.value : null,
  };
}

async function applyModel() {
  const errorBox = $("model-error");
  errorBox.hidden = true;
  const provider = ($("provider-select")?.value || "").trim();
  const model = ($("model-select")?.value || "").trim();
  if (!provider || !model) { if (errorBox) { errorBox.textContent = "Choose provider and model."; errorBox.hidden = false; } return; }
  try {
    const res = await fetch("/settings/provider-model", {
      method: "POST",
      headers: {"content-type":"application/json"},
      body: JSON.stringify({provider, model}),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body?.detail?.message || body?.detail || `HTTP ${res.status}`);
    await loadModelUsage(provider, model);
    if (errorBox) { errorBox.textContent = "Model selection saved."; errorBox.hidden = false; }
  } catch (err) {
    if (errorBox) { errorBox.textContent = err.message; errorBox.hidden = false; }
  }
}

async function createInvestigation() {
  const errBox = $("inv-error");
  errBox.hidden = true;
  const payload = { title: ($("title").value || "").trim() || "Untitled" };
  $("create-btn").disabled = true;
  $("create-btn").textContent = "Creating…";
  try {
    const res = await fetch("/investigations", { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify(payload) });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.detail?.message || `HTTP ${res.status}`);
    currentInvestigationId = body.data.investigation_id;
    saveSession();
    $("inv-id").innerHTML = `<span>Analysis file <strong>${escapeHtml(currentInvestigationId)}</strong></span>`;
    $("files-list").innerHTML = "";
    $("file-meta").textContent = "";
    $("pending-files-list").innerHTML = "";
    $("datasets").innerHTML = "";
    $("er-diagram").innerHTML = "";
    $("history").innerHTML = "";
    $("history-panel").innerHTML = "";
    $("audit-summary").textContent = "";
    $("audit-list").innerHTML = "";
    knownFileIds.clear();
    selectedFileItems.length = 0;
    pendingFileItems.length = 0;
    $("export-csv-btn").disabled = false;
    $("export-pdf-btn").disabled = false;
    $("upload-btn").disabled = false;
    $("ask-btn").disabled = false;
    renderPendingFiles();
    loadAssets();
    loadHistory();
    showToast("New file ready.", "success");
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
    showToast(err.message, "error");
  } finally {
    $("create-btn").disabled = false;
    $("create-btn").textContent = "Create new file";
  }
}

async function uploadCsv() {
  const errBox = $("file-error");
  errBox.hidden = true;
  const input = $("panel-file-input");
  const files = input.files && input.files.length ? Array.from(input.files) : [];
  if (!files.length) { errBox.textContent = "Choose CSV files first."; errBox.hidden = false; return; }
  if (!currentInvestigationId) {
    errBox.textContent = "Create a new file first, then upload CSVs into it.";
    errBox.hidden = false;
    return;
  }
  selectedFileItems = files.map((file) => ({ file }));
  renderPendingFiles();
  $("upload-btn").disabled = true;
  $("upload-btn").textContent = "Uploading…";
  const items = [];
  try {
    for (const file of files) {
      const form = new FormData();
      form.append("file", file, file.name);
      const url = `/investigations/${encodeURIComponent(currentInvestigationId)}/files`;
      const res = await fetch(url, { method: "POST", body: form });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body?.detail?.message || body?.detail || `HTTP ${res.status}`);
      const uploaded = body.data || {};
      items.push(uploaded);
    }
    $("file-meta").textContent = `${items.length} file(s) uploaded`;
    input.value = "";
    selectedFileItems.length = 0;
    pendingFileItems.length = 0;
    renderPendingFiles();
    loadAssets();
    loadModelUsage();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  } finally {
    $("upload-btn").disabled = false;
    $("upload-btn").textContent = "Upload CSV";
  }
}

function renderPendingFiles() {
  const container = $("pending-files-list");
  if (!container) return;
  container.innerHTML = "";
  pendingFileItems.forEach((item, index) => {
    const file = item.file;
    const row = document.createElement("div");
    row.className = "pending-file";
    row.innerHTML = `<div><strong>${escapeHtml(file.name)}</strong><div class="muted">${formatBytes(file.size)} · ready to upload</div></div><div class="file-actions"><button class="danger" data-pending-index="${index}">Remove</button></div>`;
    container.appendChild(row);
  });
  document.querySelectorAll("button[data-pending-index]").forEach((btn) => {
    if (btn._pendingWired) return;
    btn._pendingWired = true;
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.pendingIndex);
      if (Number.isFinite(idx)) {
        pendingFileItems.splice(idx, 1);
        renderPendingFiles();
        syncInputFromPending();
      }
    });
  });
}

function syncInputFromPending() {
  const input = $("panel-file-input");
  if (!input || !pendingFileItems.length) return;
  const dt = new DataTransfer();
  pendingFileItems.forEach((item) => dt.items.add(item.file));
  const fileList = dt.files;
  const formData = new FormData();
  Array.from(fileList).forEach((file) => formData.append("files", file, file.name));
}

function renderChart(spec, container) {
  if (!container || !spec || !spec.type || spec.type === "empty") {
    if (container) container.innerHTML = '<div class="muted">No data to chart.</div>';
    return;
  }

  if (spec.type === "table") {
    container.innerHTML = "";
    if (!Array.isArray(spec.data) || !spec.data.length) {
      container.innerHTML = '<div class="muted">No data to chart.</div>';
      return;
    }
    const table = document.createElement("table");
    table.className = "result-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    Object.keys(spec.data[0]).forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    spec.data.slice(0, 250).forEach((row) => {
      const tr = document.createElement("tr");
      Object.values(row).forEach((val) => {
        const td = document.createElement("td");
        td.textContent = val == null ? "" : String(val);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
    return;
  }

  if (!Array.isArray(spec.data) || !spec.data.length) {
    container.innerHTML = '<div class="muted">No data to chart.</div>';
    return;
  }

  const isNumeric = (value) => {
    if (typeof value === "number") return true;
    if (typeof value === "string" && value.trim().replace(".", "", 1).replace("-", "", 1).trim() !== "") {
      return !Number.isNaN(Number(value));
    }
    return false;
  };

  const _fmt = (value) => {
    if (Number.isInteger(value)) return String(value);
    if (Math.abs(value) >= 1000) return value.toLocaleString("en-IN", { maximumFractionDigits: 0 });
    if (Math.abs(value) >= 1) return value.toLocaleString("en-IN", { maximumFractionDigits: 1 });
    return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  };

  const keys = Object.keys(spec.data[0]);
  const xKey = spec.x || keys[0];
  const yKey = spec.y || keys.find((key) => isNumeric(spec.data[0][key])) || keys[1];

  const stepCount = (spec.type === "pie" ? 12 : 24);
  const maxLabel = (spec.type === "pie" ? 14 : 18);
  const dataSet = spec.data.slice(0, stepCount);
  const labels = dataSet.map((item) => String(item[xKey] ?? "").slice(0, maxLabel));
  const values = dataSet.map((item) => {
    const raw = Number(item[yKey]);
    return Number.isFinite(raw) ? raw : 0;
  });

  const titleEl = document.createElement("div");
  titleEl.className = "chart-title";
  titleEl.textContent = `${spec.type === "pie" ? "Breakdown" : spec.type === "line" ? "Trend" : "Ranked counts"} — ${yKey} by ${xKey}`;
  container.appendChild(titleEl);

  const canvas = document.createElement("canvas");
  canvas.style.width = "100%";
  canvas.style.maxWidth = "760px";
  canvas.style.height = "340px";
  container.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(rect.width, 320) * dpr;
  canvas.height = 360 * dpr;
  ctx.scale(dpr, dpr);
  const width = rect.width || 720;
  const height = 360;
  const padding = { top: 24, right: 24, bottom: 60, left: 64 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--chart-fill").trim() || "#ffffff";
  ctx.fillRect(0, 0, width, height);

  const maxValue = Math.max(...values, 1);
  const gridColor = getComputedStyle(document.body).getPropertyValue("--chart-grid").trim() || "rgba(100,116,139,0.18)";
  ctx.strokeStyle = gridColor;
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartHeight * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartWidth, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  ctx.strokeStyle = "rgba(71,85,105,0.55)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + chartHeight);
  ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);
  ctx.stroke();

  for (let i = 0; i <= 4; i++) {
    const tick = (maxValue * (4 - i)) / 4;
    const y = padding.top + (chartHeight * i) / 4;
    ctx.fillStyle = "#475569";
    ctx.font = "11px ui-monospace,monospace";
    ctx.textAlign = "right";
    ctx.fillText(_fmt(tick), padding.left - 8, y + 4);
  }

  const sorted = dataSet.map((item, i) => ({ index: i, value: values[i], label: labels[i] })).sort((a, b) => b.value - a.value);
  const topIndex = sorted[0]?.index;

  if (spec.type === "line") {
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    const xUnit = chartWidth / Math.max(labels.length - 1, 1);
    const yUnit = chartHeight / maxValue;
    ctx.beginPath();
    labels.forEach((label, index) => {
      const x = padding.left + index * xUnit;
      const y = padding.top + chartHeight - values[index] * yUnit;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    labels.forEach((label, index) => {
      const x = padding.left + index * xUnit;
      const y = padding.top + chartHeight - values[index] * yUnit;
      if (index === topIndex) {
        ctx.fillStyle = "#dc2626";
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = "#334155";
      ctx.font = "12px ui-monospace,monospace";
      ctx.save();
      ctx.translate(x, padding.top + chartHeight + 18);
      ctx.rotate(Math.PI / (labels.length > 12 ? 4 : 6));
      ctx.fillText(label, 0, 0);
      ctx.restore();
    });
    return;
  }

  if (spec.type === "pie") {
    const total = values.reduce((sum, value) => sum + value, 0) || 1;
    let angle = -Math.PI / 2;
    const palette = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#9333ea", "#0891b2", "#db2777", "#475569"];
    values.forEach((value, index) => {
      const slice = (value / total) * 2 * Math.PI;
      ctx.beginPath();
      ctx.moveTo(width / 2, height / 2);
      ctx.arc(width / 2, height / 2, Math.min(chartWidth, chartHeight) / 2 - 12, angle, angle + slice);
      ctx.fillStyle = palette[index % palette.length];
      ctx.fill();
      ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue("--chart-fill").trim() || "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      if (slice > 0.08) {
        const mid = angle + slice / 2;
        const labelRadius = (Math.min(chartWidth, chartHeight) / 2 - 40) / 2 + 16;
        ctx.fillStyle = "#ffffff";
        ctx.font = "12px ui-monospace,monospace";
        ctx.textAlign = "center";
        ctx.save();
        ctx.translate(width / 2 + Math.cos(mid) * labelRadius, height / 2 + Math.sin(mid) * labelRadius);
        ctx.rotate(mid + Math.PI / 2);
        ctx.fillText(labels[index], 0, 0);
        ctx.restore();
      }
      angle += slice;
    });

    const legendX = padding.left + chartWidth + 8;
    let legendY = padding.top;
    ctx.textAlign = "left";
    ctx.font = "12px ui-monospace,monospace";
    values.forEach((value, index) => {
      const pct = ((value / total) * 100).toFixed(1) + "%";
      ctx.fillStyle = palette[index % palette.length];
      ctx.fillRect(legendX, legendY + 2, 10, 10);
      ctx.fillStyle = "#e2e8f0";
      ctx.fillText(`${labels[index]}`, legendX + 14, legendY + 12);
      ctx.fillStyle = "#94a3b8";
      ctx.fillText(`${_fmt(value)} (${pct})`, legendX + 14, legendY + 26);
      legendY += 34;
    });
    canvas.style.height = "320px";
    return;
  }

  const barCount = values.length;
  const gap = 10;
  const barWidth = Math.max((chartWidth - gap * (barCount + 1)) / barCount, 4);
  const startX = padding.left + gap + barWidth / 2;
  const yUnit = chartHeight / maxValue;
  const palette = ["#2563eb", "#16a34a", "#dc2626", "#d97706", "#9333ea", "#0891b2", "#db2777", "#475569"];

  values.forEach((value, index) => {
    const barHeight = value * yUnit;
    const x = startX + index * (barWidth + gap);
    const y = padding.top + chartHeight - barHeight;
    const isTop = index === topIndex;
    ctx.fillStyle = isTop ? "#1d4ed8" : palette[index % palette.length];
    ctx.beginPath();
    const radius = Math.min(barWidth / 2, 6);
    if (barHeight > radius * 2) {
      ctx.moveTo(x - barWidth / 2, y + barHeight);
      ctx.lineTo(x - barWidth / 2, y + radius);
      ctx.quadraticCurveTo(x - barWidth / 2, y, x - barWidth / 2 + radius, y);
      ctx.lineTo(x + barWidth / 2 - radius, y);
      ctx.quadraticCurveTo(x + barWidth / 2, y, x + barWidth / 2, y + radius);
      ctx.lineTo(x + barWidth / 2, y + barHeight);
    } else if (barHeight > 0) {
      ctx.rect(x - barWidth / 2, y, barWidth, barHeight);
    }
    ctx.fill();
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "11px ui-monospace,monospace";
    ctx.textAlign = "center";
    const labelY = Math.max(y - 8, padding.top + 12);
    ctx.fillText(_fmt(value), x, labelY);
    ctx.fillStyle = "#334155";
    ctx.textAlign = "center";
    ctx.save();
    ctx.translate(x, padding.top + chartHeight + 16);
    ctx.rotate(Math.PI / (barCount > 12 ? 5 : 7));
    ctx.fillText(labels[index], 0, 0);
    ctx.restore();
  });

  container.innerHTML = '<div class="muted">Chart type not supported yet.</div>';
}

async function askQuestion() {
  const errBox = $("error");
  const status = $("status");
  errBox.hidden = true;
  $("result-wrap").hidden = true;
  const question = ($("question").value || "").trim();
  if (!question) { errBox.textContent = "Type a question first."; errBox.hidden = false; return; }
  if (isRunning) return;
  isRunning = true;
  $("ask-btn").disabled = true;
  status.textContent = "Analysing…";
  status.hidden = false;
  try {
    const bodyPayload = { question, investigation_id: currentInvestigationId };
    const fileIds = Array.from(knownFileIds).filter(Boolean);
    if (fileIds.length) bodyPayload.file_ids = fileIds;
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/runs`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify(bodyPayload) });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.detail?.message || `HTTP ${res.status}`);
    const data = body.data;
    if (data.status === "failed") {
      const msg = data.error_message || "The analysis failed.";
      throw new Error(msg);
    }
    appendMessage("user", question, [], null, null, false, []);
    appendMessage("assistant", data.answer_text, data.citations || [], data.sql, data.latency_ms, false, data.followup_suggestions || []);
    $("answer").textContent = data.answer_text || "";
    $("followups").innerHTML = "";
    if (Array.isArray(data.followup_suggestions) && data.followup_suggestions.length) {
      const ul = document.createElement("ul");
      ul.className = "followups";
      data.followup_suggestions.forEach((item) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "#";
        a.className = "followup-link";
        a.textContent = item;
        a.addEventListener("click", (e) => { e.preventDefault(); $("question").value = item; askQuestion(); });
        li.appendChild(a);
        ul.appendChild(li);
      });
      $("followups").appendChild(ul);
    }
    $("chart-wrap").innerHTML = "";
    let chartRendered = false;
    if (data.chart_spec && Array.isArray(data.chart_spec.data)) {
      if (data.chart_spec.type === "table") {
        const table = document.createElement("table");
        table.className = "result-table";
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        Object.keys(data.chart_spec.data[0] || {}).forEach((col) => { const th = document.createElement("th"); th.textContent = col; headRow.appendChild(th); });
        thead.appendChild(headRow);
        table.appendChild(thead);
        const tbody = document.createElement("tbody");
        data.chart_spec.data.slice(0, 250).forEach((row) => {
          const tr = document.createElement("tr");
          Object.values(row).forEach((val) => { const td = document.createElement("td"); td.textContent = val == null ? "" : String(val); tr.appendChild(td); });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        $("chart-wrap").appendChild(table);
        chartRendered = true;
      }
    }
    if (!chartRendered && data.chart_spec) {
      renderChart(data.chart_spec, $("chart-wrap"));
    }
    $("citations").innerHTML = "";
    const citeItems = data.citations || [];
    if (citeItems.length) {
      const cites = document.createElement("div");
      cites.className = "citations-block";
      cites.innerHTML = `<details><summary>Show ${citeItems.length} citation${citeItems.length === 1 ? "" : "s"}</summary><ul class="cite-list">` + citeItems.map(c => `<li>${escapeHtml(String(c))}</li>`).join("") + `</ul></details>`;
      $("citations").appendChild(cites);
    }
    $("result-meta").textContent = `run ${data.run_id} · provider ${data.provider || ""} ${data.model || ""} · ${data.latency_ms || 0}ms`;
    $("result-wrap").hidden = false;
    loadHistory();
    loadModelUsage();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  } finally {
    $("ask-btn").disabled = false;
    status.hidden = true;
    isRunning = false;
  }
}

async function loadHistory() {
  if (!currentInvestigationId) return;
  try {
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/history`);
    if (!res.ok) return;
    const { data } = await res.json();
    const container = $("history");
    const panel = $("history-panel");
    if (data && Array.isArray(data.items)) {
      container.innerHTML = "";
      if (panel) panel.innerHTML = "";
      data.items.forEach((msg) => appendMessage(msg.role, msg.content, msg.citations || [], null, null, false, []));
    }
  } catch {
    // ignore
  }
}

function renderDatasetCard(item) {
  const container = $("datasets");
  if (!container) return;
  const id = item.id || item.file_id || item.investigation_id;
  if (item.status === "removed" || item._remove) {
    const existing = container.querySelector(`[data-file-id="${CSS.escape(id)}"]`);
    if (existing) existing.remove();
    return;
  }
  const columns = Array.isArray(item.columns) ? item.columns.slice(0, 40) : [];
  const sampleRows = Array.isArray(item.sample_rows) ? item.sample_rows.slice(0, 5) : [];
  let sampleHtml = "";
  if (sampleRows.length) {
    const keys = Object.keys(sampleRows[0]);
    sampleHtml = `<table class="result-table"><thead><tr>${keys.map(k => `<th>${escapeHtml(k)}</th>`).join("")}</tr></thead><tbody>${sampleRows.map(row => `<tr>${keys.map(k => `<td>${escapeHtml(row[k] == null ? "" : String(row[k]))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  const html = `<div class="dataset-card" id="dataset-${escapeHtml(id)}" data-file-id="${escapeHtml(id)}">
    <div class="dataset-header">
      <div>
        <strong>${escapeHtml(item.name || item.original_filename || item.filename || id)}</strong>
        <div class="muted">${escapeHtml(String(item.row_count ?? 0))} rows · ${columns.length} columns · ${formatBytes(item.size_bytes || 0)}</div>
        <div class="muted">status: ${escapeHtml(item.status || "uploaded")}${item.derived?.summary ? ` · ${escapeHtml(item.derived.summary)}` : ""}</div>
      </div>
      <button class="danger sm" data-remove-file="${escapeHtml(id)}">Remove</button>
    </div>
    <details>
      <summary>Schema · ${columns.length} columns</summary>
      <table class="result-table schema-table"><thead><tr><th>column</th><th>type</th></tr></thead><tbody>${columns.map(col => `<tr><td>${escapeHtml(col)}</td><td class="muted">unknown</td></tr>`).join("")}</tbody></table>
      ${sampleHtml ? `<div class="sample-title">Sample rows</div>${sampleHtml}` : ""}
    </details>
  </div>`;
  const existing = container.querySelector(`[data-file-id="${CSS.escape(id)}"]`);
  if (existing) existing.outerHTML = html;
  else container.insertAdjacentHTML("beforeend", html);
  wireDatasetRemoveButtons();
}

function wireDatasetRemoveButtons() {
  document.querySelectorAll("button[data-remove-file]").forEach((btn) => {
    if (btn._datasetWired) return;
    btn._datasetWired = true;
    btn.addEventListener("click", async () => {
      const fileId = btn.dataset.removeFile;
      const card = btn.closest(".dataset-card");
      if (!fileId || !currentInvestigationId) return;
      btn.disabled = true;
      btn.textContent = "Removing…";
      try {
        const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/files/${encodeURIComponent(fileId)}`, { method: "DELETE" });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body?.detail?.message || `HTTP ${res.status}`);
        if (card) card.remove();
        loadAssets();
      } catch (err) {
        const errBox = $("file-error");
        errBox.textContent = err.message;
        errBox.hidden = false;
      } finally {
        btn.disabled = false;
        btn.textContent = "Remove";
      }
    });
  });
}

function renderErDiagram(datasets, relations, mermaidEr) {
  const container = $("er-diagram");
  const summary = $("er-summary");
  if (summary) summary.textContent = `${datasets.length} datasets · ${relations.length} relationships inferred`;
  container.innerHTML = "";
  if (typeof mermaidEr === "string" && mermaidEr.trim()) {
    const wrap = document.createElement("div");
    wrap.style.cursor = "pointer";
    wrap.title = "Click to zoom";
    wrap.addEventListener("click", () => openMermaidErOverlay(mermaidEr));

    const mermaidDiv = document.createElement("div");
    mermaidDiv.className = "mermaid";
    mermaidDiv.textContent = mermaidEr;
    wrap.appendChild(mermaidDiv);

    const fallback = document.createElement("pre");
    fallback.className = "mermaid-fallback";
    fallback.style.display = "none";
    fallback.style.marginTop = "8px";
    fallback.style.whiteSpace = "pre-wrap";
    fallback.style.font = "12px/1.4 ui-monospace,monospace";
    fallback.style.color = "#333";
    fallback.textContent = mermaidEr;
    wrap.appendChild(fallback);

    container.appendChild(wrap);
    if (typeof mermaid !== "undefined") {
      mermaid.run({ querySelector: "#er-diagram .mermaid" }).catch((error) => {
        console.warn("Mermaid render failed; showing fallback.", error);
        fallback.style.display = "block";
      });
    }
  }
}

function openMermaidErOverlay(mermaidEr) {
  let overlay = $("mermaid-er-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "mermaid-er-overlay";
    overlay.style.position = "fixed";
    overlay.style.inset = "0";
    overlay.style.zIndex = "9100";
    overlay.style.background = "rgba(15,23,42,0.55)";
    overlay.style.display = "none";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.padding = "24px";
    document.body.appendChild(overlay);

    const modal = document.createElement("div");
    modal.id = "mermaid-er-modal";
    modal.style.background = "#ffffff";
    modal.style.borderRadius = "8px";
    modal.style.maxWidth = "1100px";
    modal.style.width = "100%";
    modal.style.maxHeight = "88vh";
    modal.style.overflow = "auto";
    modal.style.boxShadow = "0 10px 30px rgba(0,0,0,0.35)";
    modal.innerHTML = `
      <div style="padding:12px 14px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between;">
        <strong>Mermaid ER Diagram</strong>
        <div>
          <button id="mermaid-er-minimize" style="background:#e5e7eb;border:0;border-radius:4px;padding:6px 10px;cursor:pointer;margin-right:8px;">Minimize</button>
          <button id="mermaid-er-close" style="background:#e5e7eb;border:0;border-radius:4px;padding:6px 10px;cursor:pointer;">Close</button>
        </div>
      </div>
      <div id="mermaid-er-body" style="padding:12px 14px;"></div>
    `;
    overlay.appendChild(modal);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.style.display = "none";
    });
    modal.querySelector("#mermaid-er-close").addEventListener("click", () => {
      overlay.style.display = "none";
    });
    modal.querySelector("#mermaid-er-minimize").addEventListener("click", () => {
      overlay.style.display = "none";
    });
  }
  const body = overlay.querySelector("#mermaid-er-body");
  body.innerHTML = `<div class="mermaid">${escapeHtml(mermaidEr)}</div><pre class="mermaid-fallback" style="display:none;margin-top:8px;white-space:pre-wrap;font:12px/1.4 ui-monospace,monospace;color:#333;">${escapeHtml(mermaidEr)}</pre>`;
  overlay.style.display = "flex";
  if (typeof mermaid !== "undefined") {
    mermaid.run({ querySelector: "#mermaid-er-body .mermaid" }).catch((error) => {
      console.warn("Mermaid render failed; showing fallback.", error);
      const fallback = body.querySelector(".mermaid-fallback");
      if (fallback) fallback.hidden = false;
    });
  }
}

async function loadAssets() {
  if (!currentInvestigationId) return;
  try {
    const [filesRes, erRes] = await Promise.all([
      fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/files`).then(r => r.json()).catch(() => ({ data: { items: [] } })),
      fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/assets/er`).then(r => r.json()).catch(() => ({ data: { datasets: [], relations: [] } })),
    ]);
    const datasetsContainer = $("datasets");
    const erContainer = $("er-diagram");
    if (datasetsContainer) datasetsContainer.innerHTML = "";
    if (erContainer) erContainer.innerHTML = "";
    const fileItems = Array.isArray(filesRes?.data?.items) ? filesRes.data.items : [];
    const erData = erRes?.data || { datasets: [], relations: [] };
    fileItems.forEach((item) => knownFileIds.add(item.file_id));
    if (Array.isArray(erData?.datasets)) erData.datasets.forEach(renderDatasetCard);
    renderErDiagram(erData?.datasets || [], erData?.relations || [], erData?.mermaid_er || "");
  } catch {
    // ignore asset load failures
  }
}

function appendMessage(role, content, citations, sql, latency, isHistory, followups) {
  if (isHistory) {
    const historyPanel = $("history-panel");
    if (historyPanel) {
      const bubble = document.createElement("div");
      bubble.className = `bubble ${role}`;
      const title = document.createElement("strong");
      title.textContent = role === "user" ? "You" : "Assistant";
      bubble.appendChild(title);
      const text = document.createElement("div");
      text.className = "bubble-text";
      text.textContent = content || "";
      bubble.appendChild(text);
      if (Array.isArray(citations) && citations.length) {
        const cites = document.createElement("div");
        cites.className = "cites";
        cites.textContent = citations.join(" | ");
        bubble.appendChild(cites);
      }
      if (sql) { const sqlBlock = document.createElement("pre"); sqlBlock.className = "sql-block"; sqlBlock.textContent = sql; bubble.appendChild(sqlBlock); }
      if (Array.isArray(followups) && followups.length && role === "assistant") {
        const ul = document.createElement("ul");
        ul.className = "followups";
        followups.forEach((item) => {
          const li = document.createElement("li");
          const a = document.createElement("a");
          a.href = "#";
          a.className = "followup-link";
          a.textContent = item;
          a.addEventListener("click", (e) => { e.preventDefault(); $("question").value = item; askQuestion(); });
          li.appendChild(a);
          ul.appendChild(li);
        });
        bubble.appendChild(ul);
      }
      historyPanel.appendChild(bubble);
    }
    return;
  }
  const historyContainer = $("history");
  if (!historyContainer) return;
  historyContainer.innerHTML = "";
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  const title = document.createElement("strong");
  title.textContent = role === "user" ? "You" : "Assistant";
  bubble.appendChild(title);
  const text = document.createElement("div");
  text.className = "bubble-text";
  text.textContent = content || "";
  bubble.appendChild(text);
  if (Array.isArray(citations) && citations.length) {
    const cites = document.createElement("div");
    cites.className = "cites";
    cites.textContent = citations.join(" | ");
    bubble.appendChild(cites);
  }
  if (sql) { const sqlBlock = document.createElement("pre"); sqlBlock.className = "sql-block"; sqlBlock.textContent = sql; bubble.appendChild(sqlBlock); }
  if (Array.isArray(followups) && followups.length && role === "assistant") {
    const ul = document.createElement("ul");
    ul.className = "followups";
    followups.forEach((item) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = "#";
      a.className = "followup-link";
      a.textContent = item;
      a.addEventListener("click", (e) => { e.preventDefault(); $("question").value = item; askQuestion(); });
      li.appendChild(a);
      ul.appendChild(li);
    });
    bubble.appendChild(ul);
  }
  historyContainer.appendChild(bubble);
}

async function exportCsv() {
  if (!currentInvestigationId) return;
  const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/export/csv`);
  if (!res.ok) { alert(`CSV export failed: ${res.status}`); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `investigation-${currentInvestigationId}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function exportPdf() {
  if (!currentInvestigationId) return;
  const images = [];
  document.querySelectorAll("#chart-wrap canvas").forEach((canvas) => {
    try { images.push(canvas.toDataURL("image/png")); } catch {}
  });
  const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/export/pdf`, {
    method: "POST",
    headers: {"content-type":"application/json"},
    body: JSON.stringify({chart_images: images}),
  });
  if (!res.ok) { alert(`PDF export failed: ${res.status}`); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `investigation-${currentInvestigationId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

document.addEventListener("DOMContentLoaded", () => {
  loadHealth();
  loadHistory();
  loadModelUsage();
  wireDatasetRemoveButtons();
  const createBtn = $("create-btn");
  const uploadBtn = $("upload-btn");
  const askBtn = $("ask-btn");
  if (createBtn) createBtn.addEventListener("click", createInvestigation);
  if (uploadBtn) uploadBtn.addEventListener("click", uploadCsv);
  if (askBtn) askBtn.addEventListener("click", askQuestion);

  const applyBtn = $("apply-model-btn");
  if (applyBtn) applyBtn.addEventListener("click", applyModel);

  const exportCsvBtn = $("export-csv-btn");
  const exportPdfBtn = $("export-pdf-btn");
  if (exportCsvBtn) exportCsvBtn.addEventListener("click", exportCsv);
  if (exportPdfBtn) exportPdfBtn.addEventListener("click", exportPdf);

  const assetsToggle = $("assets-toggle");
  const assetsBody = $("assets-body");
  if (assetsToggle && assetsBody) {
    assetsToggle.addEventListener("click", () => {
      const collapsed = assetsBody.classList.toggle("collapsed");
      assetsToggle.textContent = collapsed ? "▸" : "▾";
      assetsToggle.setAttribute("aria-expanded", String(!collapsed));
    });
  }

  const maximizeBtn = $("assets-maximize");
  const minimizeBtn = $("assets-minimize");
  const overlay = $("assets-overlay");
  const overlayBody = $("assets-overlay-body");
  if (maximizeBtn && assetsBody && overlay && overlayBody) {
    maximizeBtn.addEventListener("click", () => {
      overlayBody.appendChild(assetsBody);
      overlay.hidden = false;
    });
  }
  if (minimizeBtn && assetsBody && overlay && overlayBody) {
    minimizeBtn.addEventListener("click", () => {
      const panel = $("assets-panel");
      if (panel) panel.appendChild(assetsBody);
      overlay.hidden = true;
    });
  }

  const filesToggle = $("files-toggle");
  const filesBody = $("files-body");
  if (filesToggle && filesBody) {
    filesToggle.addEventListener("click", () => {
      const collapsed = filesBody.classList.toggle("collapsed");
      filesToggle.textContent = collapsed ? "▸" : "▾";
      filesToggle.setAttribute("aria-expanded", String(!collapsed));
    });
  }

  const panelInput = $("panel-file-input");
  if (panelInput) {
    panelInput.addEventListener("change", () => {
      const files = panelInput.files && panelInput.files.length ? panelInput.files : [];
      if (!files.length) return;
      const mapped = Array.from(files).map((file) => ({ file }));
      selectedFileItems = mapped;
      pendingFileItems = mapped;
      renderPendingFiles();
      $("upload-btn").disabled = false;
    });
  }

  const erHandle = $("er-resize-handle");
  const erDiagram = $("er-diagram");
  if (erHandle && erDiagram) {
    let startY = 0;
    let startHeight = 0;
    const onMouseDown = (event) => {
      startY = event.clientY || event.touches?.[0]?.clientY || 0;
      startHeight = erDiagram.getBoundingClientRect().height;
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("touchmove", onTouchMove, { passive: true });
      document.addEventListener("mouseup", onMouseUp);
      document.addEventListener("touchend", onMouseUp);
    };
    const onMouseMove = (event) => {
      const dy = (event.clientY || 0) - startY;
      erDiagram.style.height = `${Math.max(120, Math.min(600, startHeight + dy))}px`;
    };
    const onTouchMove = (event) => {
      const currentY = event.touches?.[0]?.clientY || 0;
      const dy = currentY - startY;
      erDiagram.style.height = `${Math.max(120, Math.min(600, startY + dy))}px`;
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("touchend", onMouseUp);
    };
    erHandle.addEventListener("mousedown", onMouseDown);
    erHandle.addEventListener("touchstart", onMouseDown, { passive: true });
  }
});
