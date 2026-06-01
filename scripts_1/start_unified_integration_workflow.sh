#!/usr/bin/env bash
# 启动夸父机器人统一容器联调 workflow。
#
# 运行模型：
#   1. 统一容器只作为基础服务底座，容器内入口固定 AUTO_START_WORKFLOW=0。
#   2. 本脚本等待 Neo4j、VLM、Embedding、TTS、STT、Memory Agent、Robot Agent 就绪。
#   3. workflow 通过 docker exec 在当前终端前台启动，联调/非联调模式由本次执行传入。
#
# 常用环境变量：
#   START_AFTER_CREATE=0            只创建容器，不启动服务和 workflow
#   RUN_WORKFLOW_AFTER_START=0      只启动基础服务，不启动 workflow
#   RECREATE_CONTAINER=1            强制删除并重建统一容器
#   RABBITBOT_WORKFLOW_VERBOSE=1    显示 workflow 详细日志
#   RABBITBOT_UNIFIED_ATTACH_STDIN=1 将终端输入传给 workflow

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-rabbitbot-unified-runtime:20260518}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/ssd/navgation/projects}"
CONTAINER_PROJECT_ROOT="${CONTAINER_PROJECT_ROOT:-/workspace/projects}"
MODELS_DIR="${MODELS_DIR:-${PROJECT_ROOT}/models}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-${CONTAINER_PROJECT_ROOT}/rabbitbot-dev-ros2-master}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-${CONTAINER_RABBITBOT_DIR}/logs/unified_runtime}"
RECREATE_CONTAINER="${RECREATE_CONTAINER:-0}"
RECREATE_INCOMPATIBLE_CONTAINER="${RECREATE_INCOMPATIBLE_CONTAINER:-1}"
START_AFTER_CREATE="${START_AFTER_CREATE:-1}"
RUN_WORKFLOW_AFTER_START="${RUN_WORKFLOW_AFTER_START:-${AUTO_START_WORKFLOW:-1}}"
RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-0}"
RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}"
RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}"
STOP_EXISTING_WORKFLOW="${STOP_EXISTING_WORKFLOW:-1}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

require_dir() {
    if [ ! -d "$1" ]; then
        log_error "目录不存在：$1"
        exit 1
    fi
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

container_running() {
    docker ps --format '{{.Names}}' | grep -qx "$1"
}

container_env_value() {
    local container="$1"
    local key="$2"
    docker inspect "${container}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | sed -n "s/^${key}=//p" \
        | tail -n 1
}

port_open() {
    local port="$1"
    timeout 2 bash -lc "</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
}

http_ok() {
    local url="$1"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null || true)
    [ "${code}" = "200" ]
}

json_model_ok() {
    curl -s --max-time 5 "$1" 2>/dev/null | grep -q '"data"'
}

wait_until() {
    local name="$1"
    local seconds="$2"
    shift 2
    local count=0
    echo -n "等待 ${name} 就绪"
    until "$@"; do
        sleep 2
        count=$((count + 2))
        echo -n "."
        if [ "${count}" -ge "${seconds}" ]; then
            echo ""
            log_error "${name} 启动超时 (${seconds} 秒)"
            return 1
        fi
    done
    echo ""
    log_success "${name} 已就绪"
}

wait_for_base_services() {
    log_info "等待统一容器基础服务就绪：${CONTAINER_NAME}"
    wait_until "Neo4j Bolt (7687)" "${WAIT_DEFAULT_SECONDS}" port_open 7687
    wait_until "VLM 服务 (8000)" "${WAIT_VLM_SECONDS}" json_model_ok http://127.0.0.1:8000/v1/models
    wait_until "Embedding 服务 (8005)" "${WAIT_DEFAULT_SECONDS}" json_model_ok http://127.0.0.1:8005/v1/models
    wait_until "TTS 服务 (28185)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28185/docs
    wait_until "STT 服务 (28184)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28184/docs
    wait_until "Memory Agent 服务 (28182)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28182/docs
    wait_until "Robot Agent 服务 (28180)" "${WAIT_DEFAULT_SECONDS}" port_open 28180
}

ensure_compatible_container() {
    if ! container_exists "${CONTAINER_NAME}"; then
        return 0
    fi

    if [ "${RECREATE_CONTAINER}" = "1" ]; then
        log_warn "删除已有统一容器：${CONTAINER_NAME}"
        docker rm -f "${CONTAINER_NAME}" >/dev/null
        return 0
    fi

    local container_auto_start
    container_auto_start="$(container_env_value "${CONTAINER_NAME}" AUTO_START_WORKFLOW || true)"
    if [ "${container_auto_start}" != "0" ]; then
        if [ "${RECREATE_INCOMPATIBLE_CONTAINER}" = "1" ]; then
            log_warn "已有统一容器仍是旧的自启动 workflow 模式，将重建为基础服务模式：${CONTAINER_NAME}"
            docker rm -f "${CONTAINER_NAME}" >/dev/null
        else
            log_error "已有统一容器 AUTO_START_WORKFLOW=${container_auto_start:-未设置}，不适合单容器双模式启动。"
            log_error "请设置 RECREATE_CONTAINER=1 或 RECREATE_INCOMPATIBLE_CONTAINER=1 后重试。"
            exit 1
        fi
    fi
}

create_container_if_needed() {
    if container_exists "${CONTAINER_NAME}"; then
        log_info "复用已有统一容器：${CONTAINER_NAME}"
        return 0
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

    log_info "创建统一容器基础服务底座：${CONTAINER_NAME}"
    docker create \
        --name "${CONTAINER_NAME}" \
        --network host \
        --ipc host \
        --runtime nvidia \
        "${audio_args[@]}" \
        -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
        -e RABBITBOT_LOG_DIR="${CONTAINER_LOG_DIR}" \
        -e RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-0}" \
        -e RABBITBOT_UNIFIED_TTS_DEVICE="${RABBITBOT_UNIFIED_TTS_DEVICE:-cuda}" \
        -e RABBITBOT_UNIFIED_TTS_FAST_SOUND_PRELOAD="${RABBITBOT_UNIFIED_TTS_FAST_SOUND_PRELOAD:-0}" \
        -e RABBITBOT_UNIFIED_TTS_STARTUP_SPEECH="${RABBITBOT_UNIFIED_TTS_STARTUP_SPEECH:-0}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e AUTO_START_WORKFLOW=0 \
        -e WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS}" \
        -e WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS}" \
        -v "${PROJECT_ROOT}:${CONTAINER_PROJECT_ROOT}" \
        -v "${MODELS_DIR}:/models" \
        -v rabbitbot_unified_neo4j_data:/var/lib/neo4j/data \
        -v rabbitbot_unified_neo4j_logs:/var/lib/neo4j/logs \
        "${IMAGE_NAME}" >/dev/null

    log_info "统一容器创建完成：${CONTAINER_NAME}"
}

start_container_if_needed() {
    if container_running "${CONTAINER_NAME}"; then
        log_info "统一容器基础服务底座已运行：${CONTAINER_NAME}"
    else
        log_info "后台启动统一容器基础服务底座：${CONTAINER_NAME}"
        docker start "${CONTAINER_NAME}" >/dev/null
    fi
}

stop_existing_workflow_if_needed() {
    if [ "${STOP_EXISTING_WORKFLOW}" != "1" ]; then
        return 0
    fi
    log_info "清理容器内已有 workflow 进程，避免重复启动"
    docker exec "${CONTAINER_NAME}" bash -lc '
pkill -f "[e]xamples/run_kuavo_agno.py" 2>/dev/null || true
pkill -f "[s]cripts/start_kuavo_agno_workflow.bash" 2>/dev/null || true
' >/dev/null 2>&1 || true
}

run_workflow_foreground() {
    local mode_label="联调"
    if [ "${RABBITBOT_WORKFLOW_NON_INTEGRATION}" = "1" ]; then
        mode_label="非联调"
    fi

    docker_exec_args=()
    if [ "${RABBITBOT_UNIFIED_ATTACH_STDIN}" = "1" ]; then
        docker_exec_args+=(-i)
    fi
    if [ -t 1 ]; then
        docker_exec_args+=(-t)
    fi

    log_info "前台启动统一容器 ${mode_label} workflow：${CONTAINER_NAME}"
    log_info "后续输出会直接显示在当前终端；日志同步写入容器 ${CONTAINER_LOG_DIR}/rabbitbot_workflow_latest.log"

    exec docker exec "${docker_exec_args[@]}" \
        -e RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
        -e RABBITBOT_LOG_DIR="${CONTAINER_LOG_DIR}" \
        -e PYTHONUNBUFFERED=1 \
        "${CONTAINER_NAME}" bash -lc '
set -euo pipefail
cd "${RABBITBOT_DIR}"
log_dir="${RABBITBOT_LOG_DIR:-${RABBITBOT_DIR}/logs/unified_runtime}"
mkdir -p "${log_dir}"
log_path="${log_dir}/rabbitbot_workflow_$(date +%Y%m%d_%H%M%S).log"
ln -sf "${log_path}" "${log_dir}/rabbitbot_workflow_latest.log"
echo "Workflow容器日志: ${log_path}"
PYTHONUNBUFFERED=1 bash scripts/start_kuavo_agno_workflow.bash 2>&1 | tee -a "${log_path}"
'
}

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
    log_error "镜像不存在：${IMAGE_NAME}，请先运行 scripts_1/build_unified_runtime_image.sh"
    exit 1
fi

require_dir "${PROJECT_ROOT}"
require_dir "${MODELS_DIR}"

ensure_compatible_container
create_container_if_needed

if [ "${START_AFTER_CREATE}" != "1" ]; then
    log_info "START_AFTER_CREATE=${START_AFTER_CREATE}，仅完成容器创建/复用，不启动基础服务和 workflow"
    exit 0
fi

start_container_if_needed
wait_for_base_services

if [ "${RUN_WORKFLOW_AFTER_START}" != "1" ]; then
    log_info "RUN_WORKFLOW_AFTER_START=${RUN_WORKFLOW_AFTER_START}，仅保持基础服务运行，不启动 workflow"
    exit 0
fi

stop_existing_workflow_if_needed
run_workflow_foreground
