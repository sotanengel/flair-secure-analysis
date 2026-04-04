#!/usr/bin/env bash
# smoke-test: サンプルデータで分析ワーカーが動作することを確認する
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORK_DIR="${PROJECT_DIR}/work"

cd "${PROJECT_DIR}"

echo "=== FLAIR セキュア分析コンテナ smoke-test ==="

# サンプル CSV 生成（連続した1時間間隔、200点）
SAMPLE_CSV="${WORK_DIR}/input/smoke_test_sample.csv"
mkdir -p "${WORK_DIR}/input" "${WORK_DIR}/output" "${WORK_DIR}/logs"

python3 - <<PYEOF
import csv, math, os
from datetime import datetime, timedelta
out = "${SAMPLE_CSV}"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "value"])
    base = datetime(2023, 1, 1, 0, 0, 0)
    for i in range(200):
        ts = (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%S")
        val = round(10 + 5 * math.sin(2 * math.pi * i / 7) + (i % 3) * 0.1, 4)  # 週次周期
        w.writerow([ts, val])
print(f"サンプル CSV 生成完了: {out}")
PYEOF

echo ""
echo "--- ワーカー実行 ---"
uv run python -m worker.main \
  --input       "${SAMPLE_CSV}" \
  --datetime-col timestamp \
  --value-col   value \
  --freq        D \
  --horizon     24 \
  --seed        42 \
  --output-dir  "${WORK_DIR}/output" \
  --log-dir     "${WORK_DIR}/logs"

echo ""
echo "--- 出力確認 ---"
echo "output/ 一覧:"
ls -la "${WORK_DIR}/output/" 2>/dev/null || echo "(空)"

echo ""
echo "logs/audit.jsonl (最新エントリ):"
tail -1 "${WORK_DIR}/logs/audit.jsonl" 2>/dev/null | python3 -m json.tool || echo "(ログなし)"

echo ""
echo "=== smoke-test 完了 ==="
