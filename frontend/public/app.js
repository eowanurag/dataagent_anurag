// UP Police Data Analyst frontend — single-origin against the same backend.
"use strict";

const $ = (id) => document.getElementById(id);

let currentInvestigationId = null;

async function loadHealth() {
  const badge = $("provider-badge");
  try {
    const res = await fetch("/health");
    const body = await res.json();
    const { provider, model, key_configured: keyed } = body.data || {};
    if (!keyed) {
      badge.textContent = "no API key — set one in .env";
      badge.classList.add("stub");
    } else if (provider && model) {
      badge.textContent = `${provider} · ${model}`;
    } else {
      badge.textContent = "backend reachable";
    }
  } catch {
    badge.textContent = "backend unreachable";
    badge.classList.add("stub");
  }
}

async function createInvestigation() {
  const errBox = $("inv-error");
  errBox.hidden = true;
  const title = ($("title").value || "").trim();
  const payload = { title: title || "Untitled" };
  const res = await fetch("/investigations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    errBox.textContent = msg;
    errBox.hidden = false;
    return;
  }
  currentInvestigationId = body.data.investigation_id;
  $("inv-id").textContent = `Investigation: ${currentInvestigationId}`;
  $("upload-btn").disabled = false;
  $("ask-btn").disabled = false;
  $("history").innerHTML = "";
  $("result-wrap").hidden = true;
}

async function uploadCsv() {
  const errBox = $("file-error");
  errBox.hidden = true;
  const input = $("file-input");
  const file = input.files && input.files[0];
  if (!file) {
    errBox.textContent = "Choose a CSV file first.";
    errBox.hidden = false;
    return;
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/files`, {
    method: "POST",
    body: form,
  });
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.detail?.message || `HTTP ${res.status}`;
    errBox.textContent = msg;
    errBox.hidden = false;
    return;
  }
  const data = body.data;
  $("file-meta").textContent = `Uploaded: ${data.original_filename} — ${data.row_count} rows, ${data.columns.join(", ")}`;
}

async function askQuestion() {
  const errBox = $("error");
  const status = $("status");
  errBox.hidden = true;
  $("result-wrap").hidden = true;
  const question = ($("question").value || "").trim();
  if (!question) {
    errBox.textContent = "Type a question first.";
    errBox.hidden = false;
    return;
  }
  $("ask-btn").disabled = true;
  status.textContent = "Thinking…";
  status.hidden = false;
  try {
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const body = await res.json();
    if (!res.ok) {
      const msg = body?.detail?.message || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    const data = body.data;
    if (data.status === "failed") {
      throw new Error(data.error_message || "The analysis failed.");
    }
    appendMessage("user", question);
    appendMessage("assistant", data.answer_text, data.citations, data.sql, data.latency_ms);
    $("answer").textContent = data.answer_text || "";
    if (data.followup_suggestions && data.followup_suggestions.length) {
      const ul = document.createElement("ul");
      ul.className = "followups";
      data.followup_suggestions.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        ul.appendChild(li);
      });
      $("followups").innerHTML = "";
      $("followups").appendChild(ul);
    }
    $("chart-wrap").innerHTML = "";
    if (data.chart_spec && data.chart_spec.type === "table" && Array.isArray(data.chart_spec.data)) {
      const table = document.createElement("table");
      table.className = "chart-wrap";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      Object.keys(data.chart_spec.data[0] || {}).forEach((col) => {
        const th = document.createElement("th");
        th.textContent = col;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      data.chart_spec.data.slice(0, 200).forEach((row) => {
        const tr = document.createElement("tr");
        Object.values(row).forEach((val) => {
          const td = document.createElement("td");
          td.textContent = val == null ? "" : String(val);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      $("chart-wrap").appendChild(table);
    }
    $("result-meta").textContent = `run ${data.run_id} · ${data.provider || ""} ${data.model || ""} · ${data.latency_ms || 0}ms`;
    $("result-wrap").hidden = false;
    loadHistory();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.hidden = false;
  } finally {
    $("ask-btn").disabled = false;
    status.hidden = true;
  }
}

async function loadHistory() {
  if (!currentInvestigationId) return;
  try {
    const res = await fetch(`/investigations/${encodeURIComponent(currentInvestigationId)}/history`);
    const body = await res.json();
    if (!res.ok) {
      return;
    }
    const container = $("history");
    container.innerHTML = "";
    (body.data && body.data.items || []).forEach((msg) => {
      appendMessage(msg.role, msg.content, msg.citations || [], null, null, true);
    });
  } catch {
    // ignore history fetch errors in Phase 1
  }
}

function appendMessage(role, content, citations, sql, latencyMs, silent) {
  const container = $("history");
  const el = document.createElement("div");
  el.className = `message ${role}`;
  const title = document.createElement("div");
  title.className = "muted";
  title.textContent = role === "user" ? "You" : "Analyst";
  const body = document.createElement("div");
  body.textContent = content || "";
  el.appendChild(title);
  el.appendChild(body);
  const meta = document.createElement("div");
  meta.className = "meta";
  const parts = [];
  if (sql) parts.push(`SQL: ${sql}`);
  if (citations && citations.length) parts.push(`Citations: ${citations.length}`);
  if (typeof latencyMs === "number") parts.push(`latency: ${latencyMs}ms`);
  if (parts.length) meta.textContent = parts.join(" · ");
  el.appendChild(meta);
  container.appendChild(el);
  if (!silent) {
    container.scrollTop = container.scrollHeight;
  }
}

$("create-btn").addEventListener("click", createInvestigation);
$("upload-btn").addEventListener("click", uploadCsv);
$("ask-btn").addEventListener("click", askQuestion);
loadHealth();
