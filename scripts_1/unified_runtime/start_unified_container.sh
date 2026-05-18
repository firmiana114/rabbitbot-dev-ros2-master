#!/usr/bin/env bash
# 单容器实验入口：在一个容器内启动 Neo4j、VLM、Embedding、TTS、STT、Memory Agent、Robot Agent 和 workflow。

set -Eeuo pipefail

PROJECT_DIR="${RABBITBOT_DIR:-/data/rabbitbot-dev-ros2-master}"
MODELS_DIR="${RABBITBOT_MODELS_DIR:-/models}"
LOG_DIR="${RABBITBOT_LOG_DIR:-${PROJECT_DIR}/logs}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"
AUTO_START_WORKFLOW="${AUTO_START_WORKFLOW:-1}"
RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}"
RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}"

mkdir -p "${LOG_DIR}"

log_info() { echo -e "\033[32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1"; }
log_success() { echo -e "\033[32m[SUCCESS]\033[0m $1"; }

require_path() {
    if [ ! -e "$1" ]; then
        log_error "缺少必要路径：$1"
        exit 1
    fi
}

port_open() {
    local port="$1"
    timeout 2 bash -lc "</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
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

start_background() {
    local name="$1"
    local logfile="$2"
    shift 2
    log_info "启动 ${name}，日志：${logfile}"
    ( "$@" ) >"${logfile}" 2>&1 &
}

start_neo4j() {
    if port_open 7687; then
        log_success "Neo4j Bolt 已运行"
        return 0
    fi
    export NEO4J_HOME="${NEO4J_HOME:-/var/lib/neo4j}"
    export NEO4J_EDITION="${NEO4J_EDITION:-community}"
    export NEO4J_AUTH="${NEO4J_AUTH:-neo4j/neo4j_pass}"
    export NEO4J_PLUGINS='["apoc"]'
    mkdir -p /var/lib/neo4j/data /var/lib/neo4j/logs
    chown -R neo4j:neo4j /var/lib/neo4j/data /var/lib/neo4j/logs || true
    start_background "Neo4j" "${LOG_DIR}/neo4j_unified.log" /startup/docker-entrypoint.sh neo4j
    wait_until "Neo4j Bolt (7687)" "${WAIT_DEFAULT_SECONDS}" port_open 7687
}

start_vlm_and_embedding() {
    if json_model_ok http://127.0.0.1:8000/v1/models && json_model_ok http://127.0.0.1:8005/v1/models; then
        log_success "VLM 和 Embedding 已运行"
        return 0
    fi

    local embedding_model="${RABBITBOT_EMBEDDING_MODEL_DIR:-${MODELS_DIR}/Qwen3-Embedding-0.6B}"
    local vlm_model="${RABBITBOT_VLM_MODEL_DIR:-${MODELS_DIR}/Qwen2.5-VL-7B-Instruct-GPTQ-Int4}"
    if [ ! -d "${vlm_model}" ] && [ -d "${MODELS_DIR}/Qwen2.5-VL-7B-Instruct" ]; then
        vlm_model="${MODELS_DIR}/Qwen2.5-VL-7B-Instruct"
    fi
    require_path "${embedding_model}"
    require_path "${vlm_model}"

    local vlm_gpu_memory_utilization="${RABBITBOT_UNIFIED_VLM_GPU_MEMORY_UTILIZATION:-0.75}"
    local vlm_max_model_len="${RABBITBOT_UNIFIED_VLM_MAX_MODEL_LEN:-32768}"
    local vlm_max_num_batched_tokens="${RABBITBOT_UNIFIED_VLM_MAX_NUM_BATCHED_TOKENS:-1024}"
    start_background "VLM" "${LOG_DIR}/qwen2.5-vl-7b-gptq.log" \
        /opt/rabbitbot-vllm-venv/bin/python -m vllm.entrypoints.cli.main serve "${vlm_model}" \
        --seed 42 --gpu-memory-utilization "${vlm_gpu_memory_utilization}" --max-num-seqs 2 \
        --limit-mm-per-prompt "image=4,video=1" --max-num-batched-tokens "${vlm_max_num_batched_tokens}" \
        --enable-chunked-prefill --mm-processor-kwargs '{"max_pixels": 802816, "fps": 1}' \
        --max-model-len "${vlm_max_model_len}" --served-model-name Qwen2.5-VL-7B-Instruct --port 8000

    wait_until "VLM 服务 (8000)" "${WAIT_VLM_SECONDS}" json_model_ok http://127.0.0.1:8000/v1/models

    start_background "Embedding" "${LOG_DIR}/qwen3-embedding-0.6b.log" \
        /opt/rabbitbot-vllm-venv/bin/python -m vllm.entrypoints.cli.main serve "${embedding_model}" \
        --served-model-name Qwen3-Embedding-0.6B --task embed --port 8005
    wait_until "Embedding 服务 (8005)" "${WAIT_DEFAULT_SECONDS}" json_model_ok http://127.0.0.1:8005/v1/models
}

start_tts() {
    if http_ok http://127.0.0.1:28185/docs; then
        log_success "TTS 已运行"
        return 0
    fi
    start_background "TTS" "${LOG_DIR}/rabbitbot_tts.log" bash -lc "cd '${PROJECT_DIR}' && export RABBITBOT_TTS_DEVICE=\${RABBITBOT_UNIFIED_TTS_DEVICE:-cpu} && export RABBITBOT_TTS_FAST_SOUND_PRELOAD=\${RABBITBOT_UNIFIED_TTS_FAST_SOUND_PRELOAD:-0} && export RABBITBOT_TTS_STARTUP_SPEECH=\${RABBITBOT_UNIFIED_TTS_STARTUP_SPEECH:-0} && bash scripts/start_tts_app.bash"
    wait_until "TTS 服务 (28185)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28185/docs
}

start_stt() {
    if http_ok http://127.0.0.1:28184/docs; then
        log_success "STT 已运行"
        return 0
    fi
    start_background "STT" "${LOG_DIR}/rabbitbot_stt.log" bash -lc "cd '${PROJECT_DIR}' && bash scripts/start_stt_funasr_app.bash"
    wait_until "STT 服务 (28184)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28184/docs
}

start_memory_agent() {
    if http_ok http://127.0.0.1:28182/docs; then
        log_success "Memory Agent 已运行"
        return 0
    fi
    start_background "Memory Agent" "${LOG_DIR}/memory_agent.log" bash -lc "cd '${PROJECT_DIR}' && bash scripts/start_memory_agent.sh"
    wait_until "Memory Agent 服务 (28182)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28182/docs
}

start_robot_agent() {
    if port_open 28180; then
        log_success "Robot Agent 已运行"
        return 0
    fi
    start_background "Robot Agent" "${LOG_DIR}/robot_agent.log" bash -lc "cd '${PROJECT_DIR}' && source scripts/path_env.sh && source /opt/ros/foxy/setup.bash && source \"\${RABBITBOT_VLN_WS_DIR}/install/setup.bash\" && export CUR_DIR=\$(pwd) && cd \"\${RABBITBOT_PYORBBEC_DIR}\" && export PYTHONPATH=\$PYTHONPATH:\$(pwd)/install/lib/ && cd \${CUR_DIR} && export PYTHONPATH=/usr/local/lib:\$(pwd):\${PROJECT_DIR}/py38/lib/python3.8/site-packages:\${PYTHONPATH} && export RABBITBOT_MODEL_SERVER=http://127.0.0.1:8000/v1 && export RABBITBOT_VLN_URL=http://127.0.0.1:8001 && export RABBITBOT_MEMORY_AGENT_URL=http://127.0.0.1:28182 && export REALTIME_STT_BASE_URL=http://localhost:28184/v1 && export REALTIME_TTS_BASE_URL=http://localhost:28185/v1 && export RABBITBOT_STT_AGENT_URL=\${REALTIME_STT_BASE_URL} && export RABBITBOT_TTS_AGENT_URL=\${REALTIME_TTS_BASE_URL} && export RABBITBOT_ROBOT_CAMERA=\${RABBITBOT_ROBOT_CAMERA:-null} && export DEBUG_PROPAGATE_EXCEPTIONS=True && /usr/bin/python3.8 -m uvicorn robot_app:app --host 0.0.0.0 --port 28180 --log-level debug"
    wait_until "Robot Agent 服务 (28180)" "${WAIT_DEFAULT_SECONDS}" port_open 28180
}

start_workflow() {
    if [ "${AUTO_START_WORKFLOW}" != "1" ]; then
        log_info "AUTO_START_WORKFLOW=${AUTO_START_WORKFLOW}，跳过 workflow"
        tail -f /dev/null
    fi
    local workflow_log="${LOG_DIR}/rabbitbot_workflow_$(date +%Y%m%d_%H%M%S).log"
    ln -sf "${workflow_log}" "${LOG_DIR}/rabbitbot_workflow_latest.log"
    log_info "前台启动 workflow，日志：${workflow_log}"
    cd "${PROJECT_DIR}"
    export RABBITBOT_WORKFLOW_VERBOSE
    export RABBITBOT_WORKFLOW_NON_INTEGRATION
    exec bash scripts/start_kuavo_agno_workflow.bash 2>&1 | tee -a "${workflow_log}"
}

main() {
    require_path "${PROJECT_DIR}"
    require_path "${MODELS_DIR}"
    log_info "统一容器项目路径：${PROJECT_DIR}"
    log_info "统一容器模型路径：${MODELS_DIR}"
    start_neo4j
    start_vlm_and_embedding
    start_tts
    start_stt
    start_memory_agent
    start_robot_agent
    start_workflow
}

main "$@"
