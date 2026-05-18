#!/usr/bin/env bash
# 构建夸父机器人统一运行时实验镜像。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-rabbitbot-unified-runtime:20260518}"

echo "[INFO] 构建统一运行时镜像：${IMAGE_NAME}"
cd "${PROJECT_DIR}"
docker build -f docker/unified_runtime/Dockerfile -t "${IMAGE_NAME}" .

echo "[INFO] 运行冒烟检查"
docker run --rm --network host --runtime nvidia \
    -v /mnt/ssd/navgation/projects:/workspace/projects \
    -v /mnt/ssd/navgation/projects/models:/models \
    --entrypoint /usr/local/bin/rabbitbot-unified-smoke-check \
    "${IMAGE_NAME}"
