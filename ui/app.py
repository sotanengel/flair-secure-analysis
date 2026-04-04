"""FLAIR セキュア分析 ローカル Web UI。

127.0.0.1 のみにバインド。分析ワーカーはサブプロセスで起動し、
UI 自体にはネットワーク遮断・権限制限は適用しない（ホスト側 UI のため）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

BASE_DIR = Path(__file__).resolve().parent.parent
WORK_DIR = BASE_DIR / "work"
INPUT_DIR = WORK_DIR / "input"
OUTPUT_DIR = WORK_DIR / "output"
LOG_DIR = WORK_DIR / "logs"

ALLOWED_EXTENSIONS = {".csv"}
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE + 1024


# ── セキュリティヘッダー ─────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ── ページ ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── API: ファイルアップロード ────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload():
    """CSV ファイルを受け取り input/{job_id}/ へ保存する。"""
    if "file" not in request.files:
        return jsonify({"error": "ファイルが添付されていません"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "ファイル名が空です"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"許可されていない拡張子: {ext}。CSV のみ受け付けます"}), 400

    job_id = str(uuid.uuid4())
    job_input_dir = INPUT_DIR / job_id
    job_input_dir.mkdir(parents=True, exist_ok=True)

    # パストラバーサル対策: ファイル名をサニタイズ
    safe_name = _sanitize_filename(f.filename)
    dest = job_input_dir / safe_name
    f.save(str(dest))

    size = dest.stat().st_size
    if size == 0:
        dest.unlink()
        job_input_dir.rmdir()
        return jsonify({"error": "空のファイルです"}), 400
    if size > MAX_UPLOAD_SIZE:
        dest.unlink()
        job_input_dir.rmdir()
        return jsonify({"error": "ファイルサイズ上限 (500MB) を超えています"}), 400

    # CSV の列名だけ取得して返す（設定画面で使用）
    columns = _get_csv_columns(dest)

    return jsonify(
        {
            "job_id": job_id,
            "filename": safe_name,
            "size_bytes": size,
            "columns": columns,
        }
    )


# ── API: ジョブ実行 ──────────────────────────────────────────────────────────
@app.route("/api/run", methods=["POST"])
def run_job():
    """ワーカーをサブプロセスで起動する。"""
    data = request.get_json(force=True)
    job_id = data.get("job_id", "")
    if not job_id or not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id です"}), 400

    job_input_dir = INPUT_DIR / job_id
    if not job_input_dir.exists():
        return jsonify({"error": "ジョブの入力ファイルが見つかりません"}), 404

    csv_files = list(job_input_dir.glob("*.csv"))
    if not csv_files:
        return jsonify({"error": "入力 CSV が見つかりません"}), 404

    input_path = str(csv_files[0])

    # パラメータ取得（デフォルト付き）
    datetime_col = data.get("datetime_col", "timestamp")
    value_col = data.get("value_col", "value")
    freq = data.get("freq") or None
    horizon = int(data.get("horizon", 24))
    seed = int(data.get("seed", 42))
    n_samples = int(data.get("n_samples", 200))
    missing = data.get("missing", "ffill")

    python = str(Path(sys.executable))
    cmd = [
        python,
        "-m",
        "worker.main",
        "--input",
        input_path,
        "--job-id",
        job_id,
        "--datetime-col",
        datetime_col,
        "--value-col",
        value_col,
        "--horizon",
        str(horizon),
        "--seed",
        str(seed),
        "--n-samples",
        str(n_samples),
        "--missing",
        missing,
        "--output-dir",
        str(OUTPUT_DIR),
        "--log-dir",
        str(LOG_DIR),
    ]
    if freq:
        cmd += ["--freq", freq]

    # バックグラウンド実行（non-blocking）
    env = {**os.environ, "PYTHONPATH": str(BASE_DIR)}
    job_out_dir = OUTPUT_DIR / job_id
    job_out_dir.mkdir(parents=True, exist_ok=True)

    log_fh = (job_out_dir / "worker.log").open("w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        stdout=log_fh,
        stderr=log_fh,
    )

    # PID を job ディレクトリに保存（状態確認用）
    (job_out_dir / "worker.pid").write_text(str(proc.pid))

    return jsonify({"job_id": job_id, "pid": proc.pid, "status": "running"})


# ── API: ジョブ状態確認 ──────────────────────────────────────────────────────
@app.route("/api/status/<job_id>")
def job_status(job_id: str):
    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    job_dir = OUTPUT_DIR / job_id
    forecast_csv = job_dir / "forecast.csv"
    report_json = job_dir / "report.json"

    # 完了チェック
    if forecast_csv.exists() and report_json.exists():
        return jsonify({"job_id": job_id, "status": "done"})

    # 監査ログで失敗チェック
    audit_log = LOG_DIR / "audit.jsonl"
    if audit_log.exists():
        for line in audit_log.read_text().splitlines():
            try:
                entry = json.loads(line)
                if entry.get("job_id") == job_id and entry.get("event") == "job_failure":
                    return jsonify(
                        {
                            "job_id": job_id,
                            "status": "failed",
                            "error": entry.get("error_summary", "不明なエラー"),
                        }
                    )
            except json.JSONDecodeError:
                continue

    return jsonify({"job_id": job_id, "status": "running"})


# ── API: 結果取得 ────────────────────────────────────────────────────────────
@app.route("/api/result/<job_id>")
def job_result(job_id: str):
    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    report_path = OUTPUT_DIR / job_id / "report.json"
    forecast_path = OUTPUT_DIR / job_id / "forecast.csv"
    if not report_path.exists():
        return jsonify({"error": "結果が見つかりません"}), 404

    report = json.loads(report_path.read_text())

    # forecast.csv を読んで rows に変換
    rows = []
    if forecast_path.exists():
        import csv as csv_mod

        with forecast_path.open() as f:
            reader = csv_mod.DictReader(f)
            rows = list(reader)

    return jsonify({"report": report, "forecast_rows": rows})


# ── API: 予測 CSV ダウンロード ───────────────────────────────────────────────
@app.route("/api/result/<job_id>/forecast.csv")
def job_forecast_csv(job_id: str):
    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    forecast_path = OUTPUT_DIR / job_id / "forecast.csv"
    if not forecast_path.exists():
        return jsonify({"error": "CSVが見つかりません"}), 404
    return send_file(
        str(forecast_path), mimetype="text/csv", as_attachment=True, download_name="forecast.csv"
    )


# ── API: グラフ画像 ──────────────────────────────────────────────────────────
@app.route("/api/chart/<job_id>")
def job_chart(job_id: str):
    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    chart_path = OUTPUT_DIR / job_id / "forecast_chart.png"
    if not chart_path.exists():
        return jsonify({"error": "グラフが見つかりません"}), 404
    return send_file(str(chart_path), mimetype="image/png")


# ── API: 実データ（ブラウザ側グラフ用） ────────────────────────────────────
@app.route("/api/history/<job_id>")
def job_history(job_id: str):
    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    history_path = OUTPUT_DIR / job_id / "history.json"
    if not history_path.exists():
        return jsonify({"error": "履歴データが見つかりません"}), 404

    import json as _json

    with history_path.open(encoding="utf-8") as f:
        data = _json.load(f)
    return jsonify(data)


# ── API: ジョブ一覧 ──────────────────────────────────────────────────────────
@app.route("/api/jobs")
def list_jobs():
    jobs = []
    audit_log = LOG_DIR / "audit.jsonl"
    if not audit_log.exists():
        return jsonify({"jobs": []})

    # job_id → イベント集約
    job_events: dict[str, dict] = {}
    for line in audit_log.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        jid = entry.get("job_id")
        if not jid:
            continue
        if jid not in job_events:
            job_events[jid] = {}
        event = entry.get("event")
        job_events[jid][event] = entry

    for jid, events in job_events.items():
        start = events.get("job_start", {})
        success = events.get("job_success", {})
        failure = events.get("job_failure", {})

        if success:
            status = "done"
        elif failure:
            status = "failed"
        else:
            status = "running"

        jobs.append(
            {
                "job_id": jid,
                "status": status,
                "input_filename": start.get("input_filename", ""),
                "started_at": start.get("started_at", ""),
                "finished_at": success.get("finished_at") or failure.get("finished_at") or "",
                "warnings": success.get("warnings", []),
            }
        )

    # 新しい順
    jobs.sort(key=lambda x: x["started_at"], reverse=True)
    return jsonify({"jobs": jobs})


# ── API: ジョブ削除 ──────────────────────────────────────────────────────────
@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    import shutil

    if not _is_safe_job_id(job_id):
        return jsonify({"error": "無効な job_id"}), 400

    deleted = []
    for d in [INPUT_DIR / job_id, OUTPUT_DIR / job_id]:
        if d.exists():
            shutil.rmtree(str(d))
            deleted.append(str(d))

    return jsonify({"job_id": job_id, "deleted": deleted})


# ── ヘルパー ─────────────────────────────────────────────────────────────────
def _sanitize_filename(name: str) -> str:
    import re

    n = Path(name).name
    n = re.sub(r"[^a-zA-Z0-9._\-]", "_", n)
    return n or "input.csv"


def _is_safe_job_id(job_id: str) -> bool:
    import re

    uuid_re = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    return bool(re.fullmatch(uuid_re, job_id))


def _get_csv_columns(path: Path) -> list[str]:
    import csv as csv_mod

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv_mod.reader(f)
            header = next(reader, [])
            return [c.strip() for c in header]
    except Exception:
        return []


if __name__ == "__main__":
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
