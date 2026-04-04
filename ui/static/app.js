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

  // ダウンロードリンク
  document.getElementById("btn-dl-png").href = `/api/chart/${jobId}`;
  document.getElementById("btn-dl-csv").href = `/api/result/${jobId}/forecast.csv`;

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

  // インタラクティブグラフを非同期で描画
  fetchAndDrawChart(jobId, forecast_rows || []);
}

function metaItem(label, value) {
  return `<div class="meta-item"><label>${escHtml(label)}</label><span>${escHtml(String(value ?? ""))}</span></div>`;
}

// ── インタラクティブグラフ描画 ────────────────────────────────────────────
async function fetchAndDrawChart(jobId, forecastRows) {
  const canvas = document.getElementById("forecast-canvas");
  const tooltip = document.getElementById("chart-tooltip");
  try {
    const res = await fetch(`/api/history/${jobId}`);
    if (!res.ok) return;
    const { rows: histRows } = await res.json();
    drawForecastChart(canvas, tooltip, histRows, forecastRows);
  } catch (_) {}
}

function drawForecastChart(canvas, tooltip, histRows, fcRows) {
  const DPR = window.devicePixelRatio || 1;
  const W = canvas.parentElement.clientWidth || 800;
  const H = Math.round(W * 0.42);
  const PAD = { top: 24, right: 20, bottom: 56, left: 64 };

  canvas.width  = W * DPR;
  canvas.height = H * DPR;
  canvas.style.width  = W + "px";
  canvas.style.height = H + "px";

  const ctx = canvas.getContext("2d");
  ctx.scale(DPR, DPR);

  // --- データ変換 ---
  const parseTs = (s) => new Date(s).getTime();
  const hist = histRows.map((r) => ({ t: parseTs(r.timestamp), v: r.value }));
  const fc   = fcRows.map((r) => ({
    t: parseTs(r.timestamp), v: parseFloat(r.point),
    lo: parseFloat(r.lower_10), hi: parseFloat(r.upper_90),
  }));

  const allT  = [...hist.map((r) => r.t), ...fc.map((r) => r.t)];
  const allV  = [...hist.map((r) => r.v),
    ...fc.map((r) => r.v), ...fc.map((r) => r.lo), ...fc.map((r) => r.hi)];
  const minT = Math.min(...allT), maxT = Math.max(...allT);
  const minV = Math.min(...allV), maxV = Math.max(...allV);
  const vRange = maxV - minV || 1;
  const padV   = vRange * 0.08;

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top  - PAD.bottom;

  const xOf = (t) => PAD.left + ((t - minT) / (maxT - minT)) * plotW;
  const yOf = (v) => PAD.top  + (1 - (v - (minV - padV)) / (vRange + 2 * padV)) * plotH;

  // --- 背景 ---
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, W, H);

  // --- グリッド & Y軸ラベル ---
  const yTicks = 5;
  ctx.strokeStyle = "#e5e7eb";
  ctx.lineWidth   = 1;
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillStyle = "#6b7280";
  ctx.textAlign = "right";
  for (let i = 0; i <= yTicks; i++) {
    const v = (minV - padV) + (vRange + 2 * padV) * (i / yTicks);
    const y = yOf(v);
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
    ctx.fillText(fmtAxis(v), PAD.left - 6, y + 4);
  }

  // --- X軸ラベル ---
  const xTicks = Math.min(6, hist.length + fc.length);
  ctx.textAlign = "center";
  for (let i = 0; i <= xTicks; i++) {
    const t = minT + (maxT - minT) * (i / xTicks);
    const x = xOf(t);
    ctx.fillStyle = "#6b7280";
    ctx.fillText(fmtAxisDate(t), x, H - PAD.bottom + 18);
    ctx.strokeStyle = "#e5e7eb";
    ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, H - PAD.bottom); ctx.stroke();
  }

  // --- 境界線（実績 / 予測） ---
  if (hist.length && fc.length) {
    const xBound = xOf(hist[hist.length - 1].t);
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "#94a3b8";
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(xBound, PAD.top); ctx.lineTo(xBound, H - PAD.bottom); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("▶ 予測", xBound + 24, PAD.top + 14);
  }

  // --- 信頼区間シェーディング ---
  if (fc.length) {
    ctx.beginPath();
    ctx.moveTo(xOf(fc[0].t), yOf(fc[0].hi));
    fc.forEach((r) => ctx.lineTo(xOf(r.t), yOf(r.hi)));
    for (let i = fc.length - 1; i >= 0; i--) ctx.lineTo(xOf(fc[i].t), yOf(fc[i].lo));
    ctx.closePath();
    ctx.fillStyle = "rgba(251, 146, 60, 0.18)";
    ctx.fill();

    // 上限・下限ライン
    ctx.strokeStyle = "rgba(251, 146, 60, 0.5)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ["hi", "lo"].forEach((key) => {
      ctx.beginPath();
      fc.forEach((r, i) => (i === 0 ? ctx.moveTo : ctx.lineTo).call(ctx, xOf(r.t), yOf(r[key])));
      ctx.stroke();
    });
    ctx.setLineDash([]);
  }

  // --- 実績ライン（青） ---
  if (hist.length) {
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    hist.forEach((r, i) => (i === 0 ? ctx.moveTo : ctx.lineTo).call(ctx, xOf(r.t), yOf(r.v)));
    ctx.stroke();
  }

  // --- 予測点推定ライン（オレンジ） ---
  if (fc.length) {
    // 接続：最後の実績点から予測開始へ
    if (hist.length) {
      ctx.strokeStyle = "#f97316";
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      const last = hist[hist.length - 1];
      ctx.moveTo(xOf(last.t), yOf(last.v));
      fc.forEach((r) => ctx.lineTo(xOf(r.t), yOf(r.v)));
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // --- 凡例 ---
  const legend = [
    { color: "#2563eb", dash: false, label: "実データ" },
    { color: "#f97316", dash: true,  label: "予測（点推定）" },
    { color: "rgba(251,146,60,.5)", dash: false, label: "予測（10%–90% 区間）", fill: true },
  ];
  let lx = PAD.left;
  legend.forEach(({ color, dash, label, fill }) => {
    ctx.beginPath();
    if (fill) {
      ctx.fillStyle = "rgba(251, 146, 60, 0.28)";
      ctx.fillRect(lx, H - PAD.bottom + 30, 22, 10);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(lx, H - PAD.bottom + 30, 22, 10);
    } else {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash(dash ? [5, 3] : []);
      ctx.moveTo(lx, H - PAD.bottom + 35);
      ctx.lineTo(lx + 22, H - PAD.bottom + 35);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.fillStyle = "#374151";
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, lx + 26, H - PAD.bottom + 39);
    lx += 26 + ctx.measureText(label).width + 20;
  });

  // --- ホバー tooltip ---
  // 全描画データをまとめる
  const allPoints = [
    ...hist.map((r) => ({ t: r.t, v: r.v, type: "hist" })),
    ...fc.map((r)  => ({ t: r.t, v: r.v, lo: r.lo, hi: r.hi, type: "fc" })),
  ];
  allPoints.sort((a, b) => a.t - b.t);

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    // 最も近い x の点を探す
    let best = null, bestDx = Infinity;
    allPoints.forEach((p) => {
      const dx = Math.abs(xOf(p.t) - mx);
      if (dx < bestDx) { bestDx = dx; best = p; }
    });
    if (!best || bestDx > 30) { tooltip.classList.add("hidden"); return; }

    const py = e.clientY - rect.top;
    let html = `<strong>${fmtAxisDateFull(best.t)}</strong><br>`;
    if (best.type === "hist") {
      html += `実データ: <b>${fmtNum(best.v)}</b>`;
    } else {
      html += `予測: <b>${fmtNum(best.v)}</b><br>`;
      html += `区間: ${fmtNum(best.lo)} – ${fmtNum(best.hi)}`;
    }
    tooltip.innerHTML = html;
    tooltip.classList.remove("hidden");

    const ttW = tooltip.offsetWidth || 160;
    const ttH = tooltip.offsetHeight || 60;
    let tx = xOf(best.t) + 12;
    let ty = py - ttH - 8;
    if (tx + ttW > W - 10) tx = xOf(best.t) - ttW - 12;
    if (ty < 4) ty = py + 16;
    tooltip.style.left = tx + "px";
    tooltip.style.top  = ty + "px";
  };
  canvas.onmouseleave = () => tooltip.classList.add("hidden");
}

// 軸用フォーマット
function fmtAxis(v) {
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + "k";
  return v.toFixed(Math.abs(v) < 10 ? 2 : 0);
}
function fmtAxisDate(ts) {
  const d = new Date(ts);
  const mo = d.getMonth() + 1, da = d.getDate();
  const h  = d.getHours();
  if (h !== 0) return `${mo}/${da} ${String(h).padStart(2,"0")}:00`;
  return `${d.getFullYear()}/${mo}/${da}`;
}
function fmtAxisDateFull(ts) {
  return new Date(ts).toLocaleString("ja-JP", {
    month:"2-digit", day:"2-digit",
    hour:"2-digit", minute:"2-digit",
  });
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
