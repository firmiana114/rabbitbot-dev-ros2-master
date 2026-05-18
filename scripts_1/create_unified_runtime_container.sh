#!/usr/bin/env bash
# 创建夸父机器人统一运行时实验容器。
# 默认只创建容器；如需立即启动，设置 START_AFTER_CREATE=1。
# 如需停止旧的四容器释放 host 端口，设置 STOP_LEGACY_CONTAINERS=1。

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-rabbitbot-unified-runtime:20260518}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/ssd/navgation/projects}"
CONTAINER_PROJECT_ROOT="${CONTAINER_PROJECT_ROOT:-/workspace/projects}"
MODELS_DIR="${MODELS_DIR:-${PROJECT_ROOT}/models}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-${CONTAINER_PROJECT_ROOT}/rabbitbot-dev-ros2-master}"
RECREATE_CONTAINER="${RECREATE_CONTAINER:-1}"
START_AFTER_CREATE="${START_AFTER_CREATE:-0}"
STOP_LEGACY_CONTAINERS="${STOP_LEGACY_CONTAINERS:-0}"

LEGACY_CONTAINERS=(
    vlm
    navid-vllm-cuda-mic-audio
    kuavo-agno-projects-only-test
    neo4j-community
)

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

require_dir() {
    if [ ! -d "$1" ]; then
        echo "[ERROR] 目录不存在：$1" >&2
        exit 1
    fi
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
    echo "[ERROR] 镜像不存在：${IMAGE_NAME}，请先运行 scripts_1/build_unified_runtime_image.sh" >&2
    exit 1
fi

require_dir "${PROJECT_ROOT}"
require_dir "${MODELS_DIR}"

if [ "${STOP_LEGACY_CONTAINERS}" = "1" ]; then
    log_warn "将停止旧四容器以释放 host 端口"
    docker stop "${LEGACY_CONTAINERS[@]}" >/dev/null 2>&1 || true
fi

if container_exists "${CONTAINER_NAME}"; then
    if [ "${RECREATE_CONTAINER}" = "1" ]; then
        log_warn "删除已有统一容器：${CONTAINER_NAME}"
        docker rm -f "${CONTAINER_NAME}" >/dev/null
    else
        log_info "统一容器已存在：${CONTAINER_NAME}"
        exit 0
    fi
fi

docker volume create rabbitbot_unified_neo4j_data >/dev/null
docker volume create rabbitbot_unified_neo4j_logs >/dev/null

audio_args=()
if [ -e /dev/snd ]; then
    audio_args+=(
        -v /dev/snd:/dev/snd
        --device-cgroup-rule 'c 116:* rwm'
    )
fi

log_info "创建统一容器：${CONTAINER_NAME}"
docker create \
    --name "${CONTAINER_NAME}" \
    --network host \
    --ipc host \
    --runtime nvidia \
    "${audio_args[@]}" \
    -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
    -e RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-0}" \
    -e RABBITBOT_UNIFIED_TTS_DEVICE="${RABBITBOT_UNIFIED_TTS_DEVICE:-cpu}" \
    -e RABBITBOT_UNIFIED_TTS_FAST_SOUND_PRELOAD="${RABBITBOT_UNIFIED_TTS_FAST_SOUND_PRELOAD:-0}" \
    -e RABBITBOT_UNIFIED_TTS_STARTUP_SPEECH="${RABBITBOT_UNIFIED_TTS_STARTUP_SPEECH:-0}" \
    -e RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}" \
    -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}" \
    -e AUTO_START_WORKFLOW="${AUTO_START_WORKFLOW:-1}" \
    -e WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}" \
    -e WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}" \
    -v "${PROJECT_ROOT}:${CONTAINER_PROJECT_ROOT}" \
    -v "${MODELS_DIR}:/models" \
    -v rabbitbot_unified_neo4j_data:/var/lib/neo4j/data \
    -v rabbitbot_unified_neo4j_logs:/var/lib/neo4j/logs \
    "${IMAGE_NAME}" >/dev/null

log_info "统一容器创建完成：${CONTAINER_NAME}"

if [ "${START_AFTER_CREATE}" = "1" ]; then
    log_info "启动统一容器：${CONTAINER_NAME}"
    docker start "${CONTAINER_NAME}" >/dev/null
fi
