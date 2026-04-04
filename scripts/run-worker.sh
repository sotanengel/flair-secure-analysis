#!/usr/bin/env bash
# 分析ワーカーをコンテナ外（ローカル環境）で実行する
# コンテナビルド前の動作確認・開発用途向け
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

if [[ $# -eq 0 ]]; then
  echo "使い方: $0 --input <csv_file> [--datetime-col <col>] [--value-col <col>] [options]"
  echo ""
  echo "例:"
  echo "  $0 --input work/input/mydata.csv --datetime-col timestamp --value-col value --horizon 24"
  echo ""
  echo "オプション一覧:"
  uv run python -m worker.main --help
  exit 0
fi

echo "=== FLAIR 分析ワーカー起動 ==="
uv run python -m worker.main \
  --output-dir "${PROJECT_DIR}/work/output" \
  --log-dir    "${PROJECT_DIR}/work/logs" \
  "$@"
