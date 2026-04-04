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

PYTHONPATH="${PROJECT_DIR}" \
  uv run python -m ui.app
