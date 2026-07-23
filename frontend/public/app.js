"use strict";

const $ = (id) => document.getElementById(id);
let currentInvestigationId = null;
let isRunning = false;
let knownFileIds = new Set();
let selectedFileItems = [];
let pendingFileItems = [];

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

async function loadHealth() {
  const badge = $("provider-badge");
  try {
    const res = await fetch("/health");
    const body = await res.json();
    const { provider, model, key_configured: keyed } = body.data || {};
    badge.textContent = keyed && provider && model ? `Backend ready · ${provider} · ${model}` : "Backend ready";
  } catch {
    badge.textContent = "Backend unreachable";
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
    $("inv-id").innerHTML = `<span>Analysis file <strong>${escapeHtml(currentInvestigationId)}</strong></span>`;
    $("files-list").innerHTML = "";
    $("file-meta").textContent = "";
    $("pending-files-list").innerHTML = "";
    $("datasets").innerHTML = "";
    $("er-diagram").innerHTML = "";
    $("history").innerHTML = "";
    $("history-panel").innerHTML = "";
    $("audit-list").innerHTML = "";
    $("audit-summary").textContent = "";
    knownFileIds.clear();
    selectedFileItems.length = 0;
    pendingFileItems.length = 0;
    $("export-csv-btn").disabled = false;
    $("export-pdf-btn").disabled = false;
    $("upload-btn").disabled = false;
    $("ask-btn").disabled = false;
    renderPendingFiles();
    loadAssets();
    loadAuditLogs();
    loadHistory();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  } finally {
    $("create-btn").disabled = false;
    $("create-btn").textContent = "Create new file";
  }
}

async function uploadCsv() {
  const errBox = $("file-error");
  errBox.hidden = true;
  const input = $("panel-file-input");
  const files = input.files && input.files.length ? input.files : [];
  if (!files.length) { errBox.textContent = "Choose CSV files first."; errBox.hidden = false; return; }
  selectedFileItems = Array.from(files).map((file) => ({ file }));
  renderPendingFiles();
  $("upload-btn").disabled = true;
  $("upload-btn").textContent = "Uploading…";
  try {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    const url = `/investigations/${encodeURIComponent(currentInvestigationId)}/files`;
    const res = await fetch(url, { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body?.detail?.message || body?.detail || `HTTP ${res.status}`);
    const items = Array.isArray(body.data?.items) ? body.data.items : [];
    $("file-meta").textContent = `${items.length} file(s) uploaded`;
    input.value = "";
    selectedFileItems.length = 0;
    pendingFileItems.length = 0;
    renderPendingFiles();
    loadAssets();
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
  const nativeSetter = Object.getOwnPropertyDescriptor(window.FileList, "0")?.set;
  // Keep native input simple by re-creating a FileList-like array isn't supported; use current files for upload only
  const formData = new FormData();
  Array.from(fileList).forEach((file) => formData.append("files", file, file.name));
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
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/runs`, { method: "POST", headers: {"content-type":"application/json"}, body: JSON.stringify({ question }) });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.detail?.message || `HTTP ${res.status}`);
    const data = body.data;
    if (data.status === "failed") throw new Error(data.error_message || "The analysis failed.");
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
    if (data.chart_spec && data.chart_spec.type === "table" && Array.isArray(data.chart_spec.data)) {
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
    loadAuditLogs();
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
  const nodes = datasets.map(d => `<div class="er-node"><strong>${escapeHtml(d.name || d.id || d.investigation_id)}</strong><div class="muted">${(d.columns || []).slice(0, 6).join(", ")}${(d.columns || []).length > 6 ? " …" : ""}</div></div>`).join("");
  const links = relations.slice(0, 50).map(r => `<div class="er-edge"><div><strong>${escapeHtml(r.label || r.src)}</strong> · ${escapeHtml(r.type || "1:1")} · confidence ${escapeHtml(String(Math.round((r.confidence || 0) * 100)))}%</div><div class="muted">${escapeHtml(r.src)} → ${escapeHtml(r.dst)}</div></div>`).join("");
  const relationHtml = `<div class="er-graph"><div class="er-nodes">${nodes}</div><div class="er-links">${links}</div></div>`;
  let mermaidHtml = "";
  if (typeof mermaidEr === "string" && mermaidEr.trim()) {
    mermaidHtml = `<details style="margin-top:12px"><summary>Mermaid ER Diagram</summary><div class="mermaid">${mermaidEr}</div><pre class="mermaid-fallback" style="display:none;margin-top:8px;white-space:pre-wrap;font:12px/1.4 ui-monospace,monospace;color:#333;">${escapeHtml(mermaidEr)}</pre></details>`;
  }
  container.innerHTML = relationHtml + mermaidHtml;
  if (typeof mermaidEr === "string" && mermaidEr.trim() && typeof mermaid !== "undefined") {
    mermaid.run({ querySelector: ".mermaid" }).catch((error) => {
      console.warn("Mermaid render failed; showing fallback.", error);
      const fallback = container.querySelector(".mermaid-fallback");
      if (fallback) fallback.hidden = false;
      if (fallback) fallback.style.border = "1px solid #ddd";
      if (fallback) fallback.style.padding = "8px";
      if (fallback) fallback.style.background = "#fafafa";
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

async function loadAuditLogs() {
  if (!currentInvestigationId) return;
  try {
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/audit`);
    const body = await res.json();
    if (!res.ok) return;
    const summary = $("audit-summary");
    const list = $("audit-list");
    if (summary) summary.textContent = body.data?.summary || "Audit events loaded.";
    if (list) {
      list.innerHTML = "";
      const items = Array.isArray(body.data?.items) ? body.data.items : [];
      items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "audit-row";
        row.innerHTML = `<div><strong>${escapeHtml(item.action || "event")}</strong> <span class="muted">${escapeHtml(item.timestamp || "")}</span></div><div class="audit-meta">${escapeHtml(item.error_message || JSON.stringify(item.payload || {}))}</div>`;
        list.appendChild(row);
      });
    }
  } catch {
    // ignore
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

document.addEventListener("DOMContentLoaded", () => {
  loadHealth();
  loadHistory();
  loadAuditLogs();
  wireDatasetRemoveButtons();
  const createBtn = $("create-btn");
  const uploadBtn = $("upload-btn");
  const askBtn = $("ask-btn");
  if (createBtn) createBtn.addEventListener("click", createInvestigation);
  if (uploadBtn) uploadBtn.addEventListener("click", uploadCsv);
  if (askBtn) askBtn.addEventListener("click", askQuestion);

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
