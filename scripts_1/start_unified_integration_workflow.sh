#!/usr/bin/env bash
# 启动夸父机器人统一容器联调 workflow。
# 默认创建或复用容器后立即前台启动/附加输出；如只创建不启动，设置 START_AFTER_CREATE=0。
# 默认保留已有统一容器，避免丢失 vLLM 编译缓存；如需重建，设置 RECREATE_CONTAINER=1。
# 默认前台附加容器输出，接近旧四容器 workflow 体验。
# 如需后台启动统一容器，设置 ATTACH_AFTER_START=0。
# 如需把终端输入传给容器内 workflow，设置 RABBITBOT_UNIFIED_ATTACH_STDIN=1。
# 如需停止旧的四容器释放 host 端口，设置 STOP_LEGACY_CONTAINERS=1。

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-rabbitbot-unified-runtime:20260518}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/ssd/navgation/projects}"
CONTAINER_PROJECT_ROOT="${CONTAINER_PROJECT_ROOT:-/workspace/projects}"
MODELS_DIR="${MODELS_DIR:-${PROJECT_ROOT}/models}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-${CONTAINER_PROJECT_ROOT}/rabbitbot-dev-ros2-master}"
RECREATE_CONTAINER="${RECREATE_CONTAINER:-0}"
START_AFTER_CREATE="${START_AFTER_CREATE:-1}"
ATTACH_AFTER_START="${ATTACH_AFTER_START:-1}"
RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-0}"
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

container_running() {
    docker ps --format '{{.Names}}' | grep -qx "$1"
}

start_or_attach_container() {
    if [ "${ATTACH_AFTER_START}" = "1" ]; then
        if container_running "${CONTAINER_NAME}"; then
            log_info "统一容器已运行，前台附加输出：${CONTAINER_NAME}"
            log_info "后续输出会直接显示在当前终端，按 Ctrl+C 会向统一容器转发中断信号"
            docker attach "${CONTAINER_NAME}"
        else
            log_info "前台启动统一容器：${CONTAINER_NAME}"
            log_info "后续输出会直接显示在当前终端，按 Ctrl+C 会向统一容器转发中断信号"
            start_args=(--attach)
            if [ "${RABBITBOT_UNIFIED_ATTACH_STDIN}" = "1" ]; then
                start_args+=(--interactive)
            fi
            docker start "${start_args[@]}" "${CONTAINER_NAME}"
        fi
    else
        if container_running "${CONTAINER_NAME}"; then
            log_info "统一容器已运行：${CONTAINER_NAME}"
        else
            log_info "后台启动统一容器：${CONTAINER_NAME}"
            docker start "${CONTAINER_NAME}" >/dev/null
        fi
    fi
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
        log_info "复用已有统一容器：${CONTAINER_NAME}"
        if [ "${START_AFTER_CREATE}" = "1" ]; then
            start_or_attach_container
        fi
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

stdin_args=()
if [ "${RABBITBOT_UNIFIED_ATTACH_STDIN}" = "1" ]; then
    stdin_args+=(-i)
fi

log_info "创建统一容器：${CONTAINER_NAME}"
docker create \
    --name "${CONTAINER_NAME}" \
    --network host \
    --ipc host \
    --runtime nvidia \
    "${stdin_args[@]}" \
    "${audio_args[@]}" \
    -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
    -e RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-0}" \
    -e RABBITBOT_UNIFIED_TTS_DEVICE="${RABBITBOT_UNIFIED_TTS_DEVICE:-cuda}" \
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
    start_or_attach_container
fi
