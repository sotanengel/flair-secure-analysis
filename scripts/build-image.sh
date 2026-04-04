#!/usr/bin/env bash
# コンテナイメージをビルドする
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-flair-secure-analysis}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

cd "${PROJECT_DIR}"

# コンテナランタイム検出
if command -v docker &>/dev/null; then
  RUNTIME=docker
elif command -v podman &>/dev/null; then
  RUNTIME=podman
else
  echo "ERROR: docker または podman が必要です" >&2
  exit 1
fi

echo "=== FLAIR セキュア分析コンテナ ビルド ==="
echo "  runtime : ${RUNTIME}"
echo "  image   : ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

"${RUNTIME}" build \
  --file Containerfile \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  .

echo ""
echo "=== ビルド完了 ==="
echo "  ${IMAGE_NAME}:${IMAGE_TAG}"
