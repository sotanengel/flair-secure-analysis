/* FLAIR セキュア分析 — フロントエンド (vanilla JS, 外部依存なし) */

"use strict";

// ── 状態 ──────────────────────────────────────────────────────────────────
const state = {
  jobId: null,
  columns: [],
  pollTimer: null,
  pollStart: null,
  currentResultJobId: null,
};

// ── タブ切替 ──────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${tab}`).classList.add("active");

    if (tab === "history") loadHistory();
  });
});

function switchTab(name) {
  document.querySelector(`.tab-btn[data-tab="${name}"]`).click();
}

// ── ファイル投入 ──────────────────────────────────────────────────────────
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});
dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  const resultEl = document.getElementById("upload-result");
  resultEl.className = "info-box";
  resultEl.textContent = `📤 アップロード中: ${file.name} …`;
  resultEl.classList.remove("hidden");

  const fd = new FormData();
  fd.append("file", file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) {
      resultEl.className = "error-box";
      resultEl.textContent = `❌ エラー: ${data.error}`;
      return;
    }

    state.jobId = data.job_id;
    state.columns = data.columns;

    resultEl.className = "success-box";
    resultEl.innerHTML =
      `✅ アップロード完了<br>` +
      `<small>ファイル: ${data.filename} (${fmtBytes(data.size_bytes)})</small><br>` +
      `<small>列: ${data.columns.join(", ")}</small>`;

    // 設定タブを初期化して切替
    initSettingsForm(data.columns);
    switchTab("settings");
  } catch (err) {
    resultEl.className = "error-box";
    resultEl.textContent = `❌ 通信エラー: ${err.message}`;
  }
}

// ── 設定フォーム ──────────────────────────────────────────────────────────
function initSettingsForm(columns) {
  document.getElementById("settings-no-file").classList.add("hidden");
  const form = document.getElementById("settings-form");
  form.classList.remove("hidden");
  document.getElementById("s-job-id").value = state.jobId;

  const dtSel = document.getElementById("s-datetime-col");
  const valSel = document.getElementById("s-value-col");
  [dtSel, valSel].forEach((sel) => {
    sel.innerHTML = "";
    columns.forEach((col) => {
      const opt = document.createElement("option");
      opt.value = col;
      opt.textContent = col;
      sel.appendChild(opt);
    });
  });

  // よくある列名を自動選択
  const trySelect = (sel, names) => {
    for (const name of names) {
      for (const opt of sel.options) {
        if (opt.value.toLowerCase().includes(name)) {
          sel.value = opt.value;
          return;
        }
      }
    }
  };
  trySelect(dtSel, ["timestamp", "date", "time", "datetime", "日時"]);
  trySelect(valSel, ["value", "val", "sales", "demand", "値", "売上"]);
  // dt と val が同じ場合は value を次の選択肢に
  if (dtSel.value === valSel.value && columns.length > 1) {
    valSel.selectedIndex = (valSel.selectedIndex + 1) % columns.length;
  }
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const jobId = document.getElementById("s-job-id").value;
  if (!jobId) return;

  const payload = {
    job_id: jobId,
    datetime_col: document.getElementById("s-datetime-col").value,
    value_col: document.getElementById("s-value-col").value,
    freq: document.getElementById("s-freq").value || null,
    horizon: parseInt(document.getElementById("s-horizon").value, 10),
    seed: parseInt(document.getElementById("s-seed").value, 10),
    n_samples: parseInt(document.getElementById("s-n-samples").value, 10),
    missing: document.getElementById("s-missing").value,
  };

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(`エラー: ${data.error}`);
      return;
    }
    switchTab("status");
    startPolling(jobId);
  } catch (err) {
    alert(`通信エラー: ${err.message}`);
  }
});

// ── ジョブ状態ポーリング ──────────────────────────────────────────────────
function startPolling(jobId) {
  stopPolling();
  state.pollStart = Date.now();
  state.currentResultJobId = jobId;

  show("status-running");
  hide("status-idle");
  hide("status-done");
  hide("status-failed");
  document.getElementById("status-job-id-display").textContent = `job_id: ${jobId}`;

  state.pollTimer = setInterval(async () => {
    const elapsed = Math.floor((Date.now() - state.pollStart) / 1000);
    document.getElementById("status-elapsed").textContent = elapsed;

    try {
      const res = await fetch(`/api/status/${jobId}`);
      const data = await res.json();

      if (data.status === "done") {
        stopPolling();
        hide("status-running");
        show("status-done");
        loadResult(jobId);
      } else if (data.status === "failed") {
        stopPolling();
        hide("status-running");
        show("status-failed");
        document.getElementById("status-error-msg").textContent = data.error || "不明なエラー";
      }
    } catch (_) { /* 通信エラーは無視して継続 */ }
  }, 2000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

document.getElementById("btn-goto-result").addEventListener("click", () => {
  switchTab("result");
});

// ── 結果表示 ──────────────────────────────────────────────────────────────
async function loadResult(jobId) {
  try {
    const res = await fetch(`/api/result/${jobId}`);
    if (!res.ok) return;
    const data = await res.json();
    renderResult(jobId, data);
    // 実行完了後に結果タブへ自動切替
    switchTab("result");
  } catch (_) {}
}

function renderResult(jobId, data) {
  const { report, forecast_rows } = data;
  hide("result-none");
  show("result-body");

  // メタ情報
  const meta = document.getElementById("result-meta");
  meta.innerHTML = [
    metaItem("ジョブ ID", report.job_id),
    metaItem("生成日時", fmtDatetime(report.generated_at)),
    metaItem("入力ファイル", report.input?.filename || ""),
    metaItem("SHA-256 (先頭12)", (report.input?.sha256 || "").slice(0, 12) + "..."),
    metaItem("flaircast", report.library_versions?.flaircast || ""),
    metaItem("データ点数", report.preprocessing?.series_length ?? ""),
    metaItem("予測ホライズン", report.forecast?.horizon ?? ""),
    metaItem("周波数", report.forecast?.freq || ""),
    metaItem("シード", report.forecast?.seed ?? ""),
  ].join("");

  // グラフ（チャートが生成されている場合）
  const chartImg = document.getElementById("result-chart");
  chartImg.src = `/api/chart/${jobId}?t=${Date.now()}`;
  chartImg.onerror = () => { chartImg.style.display = "none"; };

  // 注意喚起
  const warnEl = document.getElementById("result-warnings");
  warnEl.innerHTML = "";
  if (report.warnings && report.warnings.length > 0) {
    const box = document.createElement("div");
    box.className = "warn-box";
    box.innerHTML = "<strong>⚠ 注意喚起</strong><ul style='margin:6px 0 0 16px'>" +
      report.warnings.map((w) => `<li>${escHtml(w)}</li>`).join("") + "</ul>";
    warnEl.appendChild(box);
  }

  // 予測表
  const tbody = document.getElementById("result-tbody");
  tbody.innerHTML = "";
  (forecast_rows || []).slice(0, 200).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escHtml(row.timestamp || "")}</td>
      <td>${fmtNum(row.point)}</td>
      <td>${fmtNum(row.lower_10)}</td>
      <td>${fmtNum(row.upper_90)}</td>`;
    tbody.appendChild(tr);
  });

  // 再現情報
  document.getElementById("result-repro").textContent =
    JSON.stringify(report.reproducibility, null, 2);
}

function metaItem(label, value) {
  return `<div class="meta-item"><label>${escHtml(label)}</label><span>${escHtml(String(value ?? ""))}</span></div>`;
}

// ── ジョブ履歴 ────────────────────────────────────────────────────────────
document.getElementById("btn-refresh-history").addEventListener("click", loadHistory);

async function loadHistory() {
  try {
    const res = await fetch("/api/jobs");
    const data = await res.json();
    renderHistory(data.jobs || []);
  } catch (err) {
    console.error(err);
  }
}

function renderHistory(jobs) {
  const empty = document.getElementById("history-empty");
  const table = document.getElementById("history-table");
  const tbody = document.getElementById("history-tbody");

  if (jobs.length === 0) {
    show("history-empty");
    hide("history-table");
    return;
  }
  hide("history-empty");
  show("history-table");

  tbody.innerHTML = "";
  jobs.forEach((job) => {
    const tr = document.createElement("tr");
    const badge = statusBadge(job.status);
    tr.innerHTML =
      `<td>${escHtml(fmtDatetime(job.started_at))}</td>
       <td>${escHtml(job.input_filename || "")}</td>
       <td>${badge}</td>
       <td>
         ${job.status === "done"
           ? `<button class="btn-link" onclick="viewHistoryResult('${job.job_id}')">結果</button> `
           : ""}
         <button class="btn-danger" onclick="deleteJob('${job.job_id}', this)">削除</button>
       </td>`;
    tbody.appendChild(tr);
  });
}

async function viewHistoryResult(jobId) {
  state.currentResultJobId = jobId;
  await loadResult(jobId);
}

async function deleteJob(jobId, btn) {
  if (!confirm(`ジョブ ${jobId.slice(0, 8)}… を削除しますか？`)) return;
  btn.disabled = true;
  try {
    await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    loadHistory();
  } catch (err) {
    alert("削除に失敗しました: " + err.message);
    btn.disabled = false;
  }
}

function statusBadge(status) {
  const map = {
    done: ["badge-done", "完了"],
    running: ["badge-running", "実行中"],
    failed: ["badge-failed", "失敗"],
  };
  const [cls, label] = map[status] || ["badge-running", status];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ── ユーティリティ ────────────────────────────────────────────────────────
function show(id) { document.getElementById(id).classList.remove("hidden"); }
function hide(id) { document.getElementById(id).classList.add("hidden"); }

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

function fmtNum(s) {
  const n = parseFloat(s);
  return isNaN(n) ? s : n.toFixed(4);
}

function fmtDatetime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch (_) { return iso; }
}
