#!/usr/bin/env bash
# ローカル Web UI を 127.0.0.1:5000 で起動する
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

# 作業ディレクトリの存在確認
mkdir -p work/input work/output work/logs

echo "=== FLAIR セキュア分析 Web UI ==="
echo "  URL : http://127.0.0.1:5000"
echo "  Ctrl+C で停止"
echo ""

# Flask 起動後にブラウザを自動で開く
(
  sleep 1.5
  if command -v open &>/dev/null; then
    open "http://127.0.0.1:5000"          # macOS
  elif command -v xdg-open &>/dev/null; then
    xdg-open "http://127.0.0.1:5000"     # Linux
  elif command -v start &>/dev/null; then
    start "http://127.0.0.1:5000"        # Windows Git Bash
  fi
) &

PYTHONPATH="${PROJECT_DIR}" \
  uv run python -m ui.app
