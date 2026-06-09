#!/bin/bash
#
# =============================================================================
# 夸父机器人 - 断电重启后一键启动工作流
# =============================================================================
#
# 设计原则：
#   1. 本脚本只负责编排、健康检查和日志归档。
#   2. 具体服务启动尽量交给 scripts/ 下已经准备好的启动脚本。
#   3. 容器启动不等于服务启动，每个关键服务都做 HTTP 健康检查。
#   4. 默认非交互启动 workflow，适合断电重启后直接执行。
#
# 使用方法：
#   cd rabbitbot-dev-ros2-master
#   bash scripts/start_all_services.sh
#
# 可选环境变量：
#   AUTO_START_WORKFLOW=0      只启动基础服务，不启动 workflow
#   RESTART_EXISTING=1         先停止已有同类服务进程再启动
#   WAIT_VLM_SECONDS=600       VLM 最长等待时间
#   WAIT_DEFAULT_SECONDS=180   其他服务最长等待时间
#
# =============================================================================

set -u

# -----------------------------------------------------------------------------
# 配置区域
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RABBITBOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd "${RABBITBOT_DIR}/.." && pwd)"
MODELS_DIR="${RABBITBOT_MODELS_DIR:-${PROJECT_DIR}/models}"
LOG_DIR="${RABBITBOT_LOG_DIR:-${RABBITBOT_DIR}/logs}"
CONTAINER_PROJECT_ROOT="${RABBITBOT_CONTAINER_PROJECT_ROOT:-/data}"
CONTAINER_PROJECT_DIR="${RABBITBOT_CONTAINER_PROJECT_DIR:-${CONTAINER_PROJECT_ROOT}/$(basename "${RABBITBOT_DIR}")}"
CONTAINER_LOG_DIR="${RABBITBOT_CONTAINER_LOG_DIR:-${CONTAINER_PROJECT_DIR}/logs}"

VLM_CONTAINER="vlm"
AUDIO_CONTAINER="navid-vllm-cuda-mic-audio"
WORKFLOW_CONTAINER="kuavo-agno-projects-only-test"
VLN_CONTAINER="air-vln"
NEO4J_CONTAINER="neo4j-community"

VLM_PORT=8000
EMBEDDING_PORT=8005
STT_PORT=28184
TTS_PORT=28185
VLN_PORT=8001
NEO4J_WEB_PORT=7474
NEO4J_BOLT_PORT=7687
MEMORY_AGENT_PORT=28182
ROBOT_AGENT_PORT=28180

TTS_DEVICE_NAME="${TTS_DEVICE_NAME:-BT67}"
STT_DEVICE_NAME="${STT_DEVICE_NAME:-Wireless Mic Rx}"
RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT:-0}"

AUTO_START_WORKFLOW="${AUTO_START_WORKFLOW:-1}"
RESTART_EXISTING="${RESTART_EXISTING:-0}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-180}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"

mkdir -p "${LOG_DIR}"

# -----------------------------------------------------------------------------
# 日志与通用工具
# -----------------------------------------------------------------------------

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

run_host() {
    log_info "执行: $*"
    "$@"
}

is_port_open() {
    local port="$1"
    nc -z 127.0.0.1 "${port}" >/dev/null 2>&1
}

http_ok() {
    local url="$1"
    local method="${2:-GET}"
    local code
    if [ "${method}" = "POST" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST "${url}" 2>/dev/null || true)
    else
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null || true)
    fi
    [ "${code}" = "200" ]
}

json_model_ok() {
    local url="$1"
    curl -s --max-time 5 "${url}" 2>/dev/null | grep -q '"data"'
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
    return 0
}

container_running() {
    local container="$1"
    docker ps --format '{{.Names}}' | grep -qx "${container}"
}

ensure_container() {
    local container="$1"
    if container_running "${container}"; then
        log_success "容器 ${container} 已运行"
        return 0
    fi

    log_info "启动容器 ${container}"
    if docker start "${container}" >/dev/null; then
        wait_until "容器 ${container}" 60 container_running "${container}"
        return $?
    fi

    log_error "容器 ${container} 启动失败，请先确认容器是否存在"
    return 1
}

exec_detached() {
    local container="$1"
    shift
    docker exec -d "${container}" bash -lc "$*"
}

stop_existing_if_requested() {
    if [ "${RESTART_EXISTING}" != "1" ]; then
        return 0
    fi

    log_warn "RESTART_EXISTING=1，将停止已有 RabbitBot 服务进程"
    docker exec "${AUDIO_CONTAINER}" bash -lc '
        pkill -9 -f "uvicorn tts_app:app" 2>/dev/null || true
        pkill -9 -f "scripts/start_tts_app.bash" 2>/dev/null || true
        pkill -9 -f "uvicorn stt_app:app" 2>/dev/null || true
        pkill -9 -f "scripts/start_stt_app.bash" 2>/dev/null || true
    ' 2>/dev/null || true
    docker exec "${WORKFLOW_CONTAINER}" bash -lc '
        pkill -9 -f "uvicorn memory_app:app" 2>/dev/null || true
        pkill -9 -f "scripts/start_memory_agent.sh" 2>/dev/null || true
        pkill -9 -f "examples/run_kuavo_agno.py" 2>/dev/null || true
        pkill -9 -f "scripts/run_kuavo_agno_workflow.py" 2>/dev/null || true
        pkill -9 -f "scripts/start_kuavo_agno_workflow.bash" 2>/dev/null || true
    ' 2>/dev/null || true
    docker exec "${VLM_CONTAINER}" bash -lc '
        pkill -9 -f "/opt/venv/bin/python.*vllm serve" 2>/dev/null || true
    ' 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# 服务健康检查
# -----------------------------------------------------------------------------

vlm_ready() {
    json_model_ok "http://127.0.0.1:${VLM_PORT}/v1/models"
}

embedding_ready() {
    json_model_ok "http://127.0.0.1:${EMBEDDING_PORT}/v1/models"
}

tts_ready() {
    http_ok "http://127.0.0.1:${TTS_PORT}/docs"
}

stt_ready() {
    http_ok "http://127.0.0.1:${STT_PORT}/docs"
}

memory_ready() {
    http_ok "http://127.0.0.1:${MEMORY_AGENT_PORT}/docs"
}

neo4j_ready() {
    is_port_open "${NEO4J_BOLT_PORT}"
}

vln_ready() {
    http_ok "http://127.0.0.1:${VLN_PORT}/reset" "POST"
}

robot_agent_ready() {
    is_port_open "${ROBOT_AGENT_PORT}"
}

# -----------------------------------------------------------------------------
# 服务启动函数
# -----------------------------------------------------------------------------

start_vlm_and_embedding() {
    if vlm_ready && embedding_ready; then
        log_success "VLM 和 Embedding 服务已运行"
        return 0
    fi

    log_info "启动 VLM 和 Embedding 服务"
    log_info "VLM 容器未挂载项目脚本目录，运行时从项目脚本生成 /models/start_vllm_runtime.sh"

    # 这里仍以项目已有 start_vllm_v2.sh 为模板，只修正当前容器真实挂载路径和实际模型目录。
    # 不直接把长命令写在本编排脚本里，便于后续统一维护 VLM 启动脚本。
    sed \
        -e 's#/data/Qwen2.5-VL-7B-Instruct#/models/Qwen2.5-VL-7B-Instruct-GPTQ-Int4#g' \
        -e 's#/data/Qwen3-Embedding-0.6B#/models/Qwen3-Embedding-0.6B#g' \
        -e 's#> /data/#> /models/#g' \
        -e 's#tee /data/#tee /models/#g' \
        "${RABBITBOT_DIR}/scripts/start_vllm_v2.sh" \
        > "${MODELS_DIR}/start_vllm_runtime.sh"

    chmod +x "${MODELS_DIR}/start_vllm_runtime.sh"
    ln -sf "${MODELS_DIR}/start_vllm_runtime.log" "${LOG_DIR}/start_vllm_runtime.log"
    ln -sf "${MODELS_DIR}/qwen2.5-vl-7b.log" "${LOG_DIR}/qwen2.5-vl-7b.log"
    ln -sf "${MODELS_DIR}/qwen2.5-vl-7b-gptq.log" "${LOG_DIR}/qwen2.5-vl-7b-gptq.log"
    ln -sf "${MODELS_DIR}/qwen3-embedding-0.6b.log" "${LOG_DIR}/qwen3-embedding-0.6b.log"

    exec_detached "${VLM_CONTAINER}" 'bash /models/start_vllm_runtime.sh > /models/start_vllm_runtime.log 2>&1'

    wait_until "VLM 服务 (${VLM_PORT})" "${WAIT_VLM_SECONDS}" vlm_ready || return 1
    wait_until "Embedding 服务 (${EMBEDDING_PORT})" "${WAIT_DEFAULT_SECONDS}" embedding_ready || return 1
}

start_tts() {
    if tts_ready; then
        log_success "TTS 服务已运行"
        return 0
    fi

    log_info "通过 scripts/start_tts_app.bash 启动 TTS"
    exec_detached "${AUDIO_CONTAINER}" "cd '${CONTAINER_PROJECT_DIR}' && mkdir -p '${CONTAINER_LOG_DIR}' && export TTS_DEVICE_NAME='${TTS_DEVICE_NAME}' && bash scripts/start_tts_app.bash > '${CONTAINER_LOG_DIR}/rabbitbot_tts.log' 2>&1"
    wait_until "TTS 服务 (${TTS_PORT})" "${WAIT_DEFAULT_SECONDS}" tts_ready
}

start_stt() {
    if stt_ready; then
        log_success "STT 服务已运行"
        return 0
    fi

    log_info "通过 scripts/start_stt_app.bash 启动 STT"
    exec_detached "${AUDIO_CONTAINER}" "cd '${CONTAINER_PROJECT_DIR}' && mkdir -p '${CONTAINER_LOG_DIR}' && export STT_DEVICE_NAME='${STT_DEVICE_NAME}' && bash scripts/start_stt_app.bash > '${CONTAINER_LOG_DIR}/rabbitbot_stt.log' 2>&1"
    wait_until "STT 服务 (${STT_PORT})" "${WAIT_DEFAULT_SECONDS}" stt_ready
}

start_vln() {
    if vln_ready; then
        log_success "VLN 服务已运行"
        return 0
    fi

    log_info "启动 VLN 服务"
    exec_detached "${VLN_CONTAINER}" 'cd /data/v-fuchengjia/Projects/robot_car && sh tools/run_navid_app.sh > /tmp/air_vln.log 2>&1'
    wait_until "VLN 服务 (${VLN_PORT})" "${WAIT_DEFAULT_SECONDS}" vln_ready
}

start_memory_agent() {
    if memory_ready; then
        log_success "Memory Agent 服务已运行"
        return 0
    fi

    log_info "通过 scripts/start_memory_agent.sh 启动 Memory Agent"
    exec_detached "${WORKFLOW_CONTAINER}" "cd '${CONTAINER_PROJECT_DIR}' && mkdir -p '${CONTAINER_LOG_DIR}' && bash scripts/start_memory_agent.sh > '${CONTAINER_LOG_DIR}/memory_agent.log' 2>&1"
    wait_until "Memory Agent 服务 (${MEMORY_AGENT_PORT})" "${WAIT_DEFAULT_SECONDS}" memory_ready
}

start_workflow() {
    if [ "${AUTO_START_WORKFLOW}" != "1" ]; then
        log_info "AUTO_START_WORKFLOW=${AUTO_START_WORKFLOW}，跳过 workflow 启动"
        return 0
    fi

    local workflow_log_path="${LOG_DIR}/rabbitbot_workflow_$(date +%Y%m%d_%H%M%S).log"
    local workflow_latest_log="${LOG_DIR}/rabbitbot_workflow_latest.log"
    ln -sf "${workflow_log_path}" "${workflow_latest_log}"

    log_info "前台启动 Workflow，后续输出会直接显示在当前终端"
    log_info "Workflow 输出会同时保存到本机 ${workflow_latest_log}"
    log_info "Workflow 输出会同时保存到容器 ${WORKFLOW_CONTAINER}:${CONTAINER_LOG_DIR}/rabbitbot_workflow_latest.log"
    log_info "按 Ctrl+C 可停止前台 workflow"
    docker exec -it "${WORKFLOW_CONTAINER}" bash -lc "mkdir -p '${CONTAINER_LOG_DIR}' && log_path='${CONTAINER_LOG_DIR}'/rabbitbot_workflow_\$(date +%Y%m%d_%H%M%S).log && ln -sf \${log_path} '${CONTAINER_LOG_DIR}'/rabbitbot_workflow_latest.log && echo Workflow容器日志: \${log_path} && cd '${CONTAINER_PROJECT_DIR}' && PYTHONUNBUFFERED=1 bash scripts/start_kuavo_agno_workflow.bash 2>&1 | tee -a \${log_path}" 2>&1 | tee -a "${workflow_log_path}"
    local workflow_status=${PIPESTATUS[0]}
    return "${workflow_status}"
}

print_status() {
    echo ""
    log_info "服务状态汇总"
    echo "| 服务 | 端口 | 状态 |"
    echo "| --- | --- | --- |"

    if vlm_ready; then echo "| VLM 大模型 | ${VLM_PORT} | 运行中 |"; else echo "| VLM 大模型 | ${VLM_PORT} | 未运行 |"; fi
    if embedding_ready; then echo "| Embedding | ${EMBEDDING_PORT} | 运行中 |"; else echo "| Embedding | ${EMBEDDING_PORT} | 未运行 |"; fi
    if tts_ready; then echo "| TTS 语音合成 | ${TTS_PORT} | 运行中 |"; else echo "| TTS 语音合成 | ${TTS_PORT} | 未运行 |"; fi
    if stt_ready; then echo "| STT 语音识别 | ${STT_PORT} | 运行中 |"; else echo "| STT 语音识别 | ${STT_PORT} | 未运行 |"; fi
    # 当前阶段暂不需要 VLN，避免一键启动时额外拉起 air-vln 容器和 8001 服务。
    echo "| VLN 视觉导航 | ${VLN_PORT} | 已跳过 |"
    if neo4j_ready; then echo "| Neo4j Bolt | ${NEO4J_BOLT_PORT} | 运行中 |"; else echo "| Neo4j Bolt | ${NEO4J_BOLT_PORT} | 未运行 |"; fi
    if memory_ready; then echo "| Memory Agent | ${MEMORY_AGENT_PORT} | 运行中 |"; else echo "| Memory Agent | ${MEMORY_AGENT_PORT} | 未运行 |"; fi
    if robot_agent_ready; then echo "| Robot Agent | ${ROBOT_AGENT_PORT} | 运行中 |"; else echo "| Robot Agent | ${ROBOT_AGENT_PORT} | 未运行或未配置 |"; fi

    echo ""
    log_info "主要日志位置："
    echo "  VLM:        ${LOG_DIR}/start_vllm_runtime.log"
    echo "  VLM 模型:   ${LOG_DIR}/qwen2.5-vl-7b.log 或 ${LOG_DIR}/qwen2.5-vl-7b-gptq.log"
    echo "  Embedding:  ${LOG_DIR}/qwen3-embedding-0.6b.log"
    echo "  TTS:        ${LOG_DIR}/rabbitbot_tts.log"
    echo "  STT:        ${LOG_DIR}/rabbitbot_stt.log"
    echo "  VLN:        当前已跳过，不启动 ${VLN_CONTAINER}"
    echo "  Memory:     ${LOG_DIR}/memory_agent.log"
    echo "  Workflow:   前台输出到当前终端，并保存到 ${LOG_DIR}/rabbitbot_workflow_latest.log"
    echo "  Profile:    ${LOG_DIR}/workflow_profile.jsonl"
}

# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------

echo "========================================"
echo "  夸父机器人 - 断电重启后一键启动工作流"
echo "========================================"
echo ""

log_info "前置检查"
if ! docker info >/dev/null 2>&1; then
    log_error "Docker 不可用。请先确认 Docker daemon 已启动且当前用户有权限访问 Docker。"
    exit 1
fi

if [ ! -d "${RABBITBOT_DIR}" ]; then
    log_error "项目目录不存在: ${RABBITBOT_DIR}"
    exit 1
fi

if [ ! -d "${MODELS_DIR}" ]; then
    log_error "模型目录不存在: ${MODELS_DIR}"
    exit 1
fi

if ! command -v nc >/dev/null 2>&1; then
    log_error "缺少 nc 命令，无法做端口健康检查"
    exit 1
fi

log_info "启动基础容器"
ensure_container "${VLM_CONTAINER}" || exit 1
ensure_container "${AUDIO_CONTAINER}" || exit 1
ensure_container "${WORKFLOW_CONTAINER}" || exit 1
# 当前阶段暂不需要 VLN，先不启动 air-vln 容器。
# ensure_container "${VLN_CONTAINER}" || exit 1
ensure_container "${NEO4J_CONTAINER}" || exit 1

stop_existing_if_requested

log_info "等待 Neo4j"
wait_until "Neo4j Bolt (${NEO4J_BOLT_PORT})" "${WAIT_DEFAULT_SECONDS}" neo4j_ready || exit 1

start_vlm_and_embedding || exit 1
start_tts || exit 1
if [ "${RABBITBOT_UNIFIED_START_STT}" = "1" ]; then
    start_stt || exit 1
else
    log_info "RABBITBOT_UNIFIED_START_STT=0，跳过 STT（当前 workflow 不再需要语音识别服务）"
fi
# 当前阶段暂不需要 VLN，先不启动 8001 服务。
# start_vln || log_warn "VLN 未就绪，workflow 中 VLN 相关能力可能不可用"
start_memory_agent || exit 1

print_status
start_workflow

log_success "一键启动流程完成"
