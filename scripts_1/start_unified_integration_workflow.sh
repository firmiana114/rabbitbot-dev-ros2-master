#!/usr/bin/env bash
# 启动夸父机器人统一容器联调 workflow。
#
# 运行模型：
#   1. 统一容器只作为基础服务底座，容器内入口固定 AUTO_START_WORKFLOW=0。
#   2. 本脚本等待 Neo4j、TTS、Memory Agent、Robot Agent 就绪；VLM/Embedding/STT 默认跳过。
#   3. workflow 通过 docker exec 在当前终端前台启动，联调/非联调模式由本次执行传入。
#
# 常用环境变量：
#   START_AFTER_CREATE=0            只创建容器，不启动服务和 workflow
#   RUN_WORKFLOW_AFTER_START=0      只启动基础服务，不启动 workflow
#   RECREATE_CONTAINER=1            强制删除并重建统一容器
#   RABBITBOT_WORKFLOW_VERBOSE=1    显示 workflow 详细日志
#   RABBITBOT_UNIFIED_ATTACH_STDIN=1 将终端输入传给 workflow
#   RABBITBOT_UNIFIED_START_VLM=1 显式启动 VLM
#   RABBITBOT_UNIFIED_START_EMBEDDING=1 显式启动 Embedding
#   RABBITBOT_UNIFIED_START_STT=1 显式启动 STT（默认不启动，当前 workflow 不再需要）
#
# workflow 运行环境变量速查：
# - RABBITBOT_STRICT_DOCX_SCRIPT：是否启用严格 DOCX 剧本模式，默认启用。
# - RABBITBOT_SCRIPTED_TOUR：是否启用脚本化导览推进，默认启用。
# - RABBITBOT_WORKFLOW_NON_INTEGRATION：是否使用非联调手动确认导航模式。
# - RABBITBOT_WORKFLOW_VERBOSE：是否打印调试级 workflow 过程日志。
# - RABBITBOT_WORKFLOW_PROFILE：是否写入 workflow profile JSONL，默认启用。
# - RABBITBOT_WORKFLOW_PROFILE_LOG：显式指定 workflow profile JSONL 路径。
# - RABBITBOT_LOG_DIR：未指定 profile 路径时的日志目录。
# - RABBITBOT_WORKFLOW_SUMMARY：是否在退出时打印 workflow 耗时汇总，默认启用。
# - RABBITBOT_TTS_STRICT_FAILURE：TTS 请求失败时是否按致命错误终止 workflow，默认 0，即记录错误并继续导览。
# - RABBITBOT_DIALOGUE_INDEX：选择 conf/dialogue_<序号>.json，未设置时默认 0。
# - RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX：旧版台词序号变量，仅在 RABBITBOT_DIALOGUE_INDEX 未设置时兜底。
# - RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE：直接指定台词 JSON 文件完整路径，优先级高于序号。
# - RABBITBOT_COFFEE_DELIVERY_COMMAND：覆盖“呼叫咖啡车”的后台命令。
# - RABBITBOT_COFFEE_DELIVERY_COMMAND_TIMEOUT：呼叫咖啡车后台命令等待超时时间，单位秒。
# - RABBITBOT_OPENING_MODE：控制开场流程，full 为完整开场，skip/0/false/off 为跳过。
# - RABBITBOT_ENABLE_NAVI：是否真实执行导航，设为 0/false/no/off 时跳过导航。
# - RABBITBOT_HAND_GESTURE_<ACTION>：为指定手臂动作配置灵巧手 ROS 字符串命令。
# - RABBITBOT_HAND_GESTURE_TOPIC：灵巧手命令发布 topic，默认 /gesture_cmd。
# - RABBITBOT_HAND_GESTURE_PUB_TIMEOUT：灵巧手命令发布超时，单位秒。
# - RABBITBOT_HANDSHAKE_BEFORE_RELEASE_DELAY：握手动作收手前等待时间，单位秒。
# - RABBITBOT_ARM_BEFORE_RELEASE_DELAY：其它前置动作收手前默认等待时间，单位秒。
# - RABBITBOT_ARM_AFTER_SPEECH_RELEASE_DELAY：台词后收手动作的等待时间，单位秒。
# - RABBITBOT_ARM_CONCURRENT_RELEASE_DELAY：动作与台词并发时收手前等待时间，单位秒。
# - RABBITBOT_ARM_RELEASE_WAIT_SECONDS：发送 release 后额外等待时间，单位秒。
# - RABBITBOT_VIEW_MODE：视觉问答来源，robot 使用机器人视觉，其它值使用 mock。
# - RABBITBOT_MOCK_IMAGE：mock 视觉问答使用的本地图片路径。

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
RABBITBOT_TTS_STRICT_FAILURE="${RABBITBOT_TTS_STRICT_FAILURE:-0}"
STOP_EXISTING_WORKFLOW="${STOP_EXISTING_WORKFLOW:-1}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"
RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM:-0}"
RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING:-0}"
RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT:-0}"
RABBITBOT_TTS_BACKEND="${RABBITBOT_TTS_BACKEND:-unitree}"
RABBITBOT_UNITREE_TTS_INTERFACE="${RABBITBOT_UNITREE_TTS_INTERFACE:-eno1}"
RABBITBOT_UNITREE_TTS_VOLUME="${RABBITBOT_UNITREE_TTS_VOLUME:-100}"
RABBITBOT_UNITREE_TTS_SPEAKER_ID="${RABBITBOT_UNITREE_TTS_SPEAKER_ID:-0}"
RABBITBOT_UNITREE_TTS_TIMEOUT="${RABBITBOT_UNITREE_TTS_TIMEOUT:-10}"
RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST="${RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST:-1}"
RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER="${RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER:-1}"
RABBITBOT_UNITREE_TTS_REQUIRE_IPV4="${RABBITBOT_UNITREE_TTS_REQUIRE_IPV4:-1}"
RABBITBOT_UNITREE_TTS_AUTO_PROBE="${RABBITBOT_UNITREE_TTS_AUTO_PROBE:-1}"
RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT="${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT:-3}"

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

tts_exec_ok() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -X POST http://127.0.0.1:28185/exec \
        --form-string 'task={"task":"wait_speech","lang":"","text":"","timeout":1}' 2>/dev/null || true)
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
    if [ "${RABBITBOT_UNIFIED_START_VLM}" = "1" ]; then
        wait_until "VLM 服务 (8000)" "${WAIT_VLM_SECONDS}" json_model_ok http://127.0.0.1:8000/v1/models
    else
        log_info "RABBITBOT_UNIFIED_START_VLM=0，跳过等待 VLM 服务 (8000)"
    fi
    if [ "${RABBITBOT_UNIFIED_START_EMBEDDING}" = "1" ]; then
        wait_until "Embedding 服务 (8005)" "${WAIT_DEFAULT_SECONDS}" json_model_ok http://127.0.0.1:8005/v1/models
    else
        log_info "RABBITBOT_UNIFIED_START_EMBEDDING=0，跳过等待 Embedding 服务 (8005)"
    fi
    wait_until "TTS /exec 服务 (28185)" "${WAIT_DEFAULT_SECONDS}" tts_exec_ok
    if [ "${RABBITBOT_UNIFIED_START_STT}" = "1" ]; then
        wait_until "STT 服务 (28184)" "${WAIT_DEFAULT_SECONDS}" http_ok http://127.0.0.1:28184/docs
    else
        log_info "RABBITBOT_UNIFIED_START_STT=0，跳过等待 STT 服务 (28184)"
    fi
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
    local container_start_vlm
    container_start_vlm="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNIFIED_START_VLM || true)"
    local container_start_embedding
    container_start_embedding="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNIFIED_START_EMBEDDING || true)"
    local container_start_stt
    container_start_stt="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNIFIED_START_STT || true)"
    local container_tts_backend
    container_tts_backend="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_TTS_BACKEND || true)"
    local container_unitree_interface
    container_unitree_interface="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNITREE_TTS_INTERFACE || true)"
    local container_unitree_volume
    container_unitree_volume="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNITREE_TTS_VOLUME || true)"
    local container_unitree_set_volume_each_request
    container_unitree_set_volume_each_request="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST || true)"
    local container_unitree_auto_probe
    container_unitree_auto_probe="$(container_env_value "${CONTAINER_NAME}" RABBITBOT_UNITREE_TTS_AUTO_PROBE || true)"
    local incompatible_reason=""
    if [ "${container_auto_start}" != "0" ]; then
        incompatible_reason="旧的自启动 workflow 模式"
    elif [ "${container_start_vlm:-未设置}" != "${RABBITBOT_UNIFIED_START_VLM}" ]; then
        incompatible_reason="VLM 启动配置变化：container=${container_start_vlm:-未设置}, expected=${RABBITBOT_UNIFIED_START_VLM}"
    elif [ "${container_start_embedding:-未设置}" != "${RABBITBOT_UNIFIED_START_EMBEDDING}" ]; then
        incompatible_reason="Embedding 启动配置变化：container=${container_start_embedding:-未设置}, expected=${RABBITBOT_UNIFIED_START_EMBEDDING}"
    elif [ "${container_start_stt:-未设置}" != "${RABBITBOT_UNIFIED_START_STT}" ]; then
        incompatible_reason="STT 启动配置变化：container=${container_start_stt:-未设置}, expected=${RABBITBOT_UNIFIED_START_STT}"
    elif [ "${container_tts_backend:-local}" != "${RABBITBOT_TTS_BACKEND}" ]; then
        incompatible_reason="TTS 后端配置变化：container=${container_tts_backend:-local}, expected=${RABBITBOT_TTS_BACKEND}"
    elif [ "${RABBITBOT_TTS_BACKEND}" = "unitree" ] && [ "${container_unitree_interface:-eno1}" != "${RABBITBOT_UNITREE_TTS_INTERFACE}" ]; then
        incompatible_reason="Unitree TTS 网卡配置变化：container=${container_unitree_interface:-eno1}, expected=${RABBITBOT_UNITREE_TTS_INTERFACE}"
    elif [ "${RABBITBOT_TTS_BACKEND}" = "unitree" ] && [ "${container_unitree_volume:-85}" != "${RABBITBOT_UNITREE_TTS_VOLUME}" ]; then
        incompatible_reason="Unitree TTS 音量配置变化：container=${container_unitree_volume:-85}, expected=${RABBITBOT_UNITREE_TTS_VOLUME}"
    elif [ "${RABBITBOT_TTS_BACKEND}" = "unitree" ] && [ "${container_unitree_set_volume_each_request:-0}" != "${RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST}" ]; then
        incompatible_reason="Unitree TTS 每次请求设置音量配置变化：container=${container_unitree_set_volume_each_request:-0}, expected=${RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST}"
    elif [ "${RABBITBOT_TTS_BACKEND}" = "auto" ] && [ "${container_unitree_auto_probe:-0}" != "${RABBITBOT_UNITREE_TTS_AUTO_PROBE}" ]; then
        incompatible_reason="Unitree TTS auto 探测配置变化：container=${container_unitree_auto_probe:-0}, expected=${RABBITBOT_UNITREE_TTS_AUTO_PROBE}"
    elif port_open 28185 && ! tts_exec_ok; then
        incompatible_reason="TTS 端口 28185 存在但 /exec 健康检查无响应，疑似旧 TTS 播放进程卡死"
    fi

    if [ -n "${incompatible_reason}" ]; then
        if [ "${RECREATE_INCOMPATIBLE_CONTAINER}" = "1" ]; then
            log_warn "已有统一容器配置不匹配，将重建：${CONTAINER_NAME}，原因：${incompatible_reason}"
            docker rm -f "${CONTAINER_NAME}" >/dev/null
        else
            log_error "已有统一容器配置不匹配：${incompatible_reason}"
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
    log_info "TTS 默认后端：${RABBITBOT_TTS_BACKEND}，Unitree 网卡：${RABBITBOT_UNITREE_TTS_INTERFACE}，音量：${RABBITBOT_UNITREE_TTS_VOLUME}，每次请求设置音量：${RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST}，auto_probe=${RABBITBOT_UNITREE_TTS_AUTO_PROBE}"
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
        -e RABBITBOT_TTS_BACKEND="${RABBITBOT_TTS_BACKEND}" \
        -e RABBITBOT_UNITREE_TTS_INTERFACE="${RABBITBOT_UNITREE_TTS_INTERFACE}" \
        -e RABBITBOT_UNITREE_TTS_VOLUME="${RABBITBOT_UNITREE_TTS_VOLUME}" \
        -e RABBITBOT_UNITREE_TTS_SPEAKER_ID="${RABBITBOT_UNITREE_TTS_SPEAKER_ID}" \
        -e RABBITBOT_UNITREE_TTS_TIMEOUT="${RABBITBOT_UNITREE_TTS_TIMEOUT}" \
        -e RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST="${RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST}" \
        -e RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER="${RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER}" \
        -e RABBITBOT_UNITREE_TTS_REQUIRE_IPV4="${RABBITBOT_UNITREE_TTS_REQUIRE_IPV4}" \
        -e RABBITBOT_UNITREE_TTS_AUTO_PROBE="${RABBITBOT_UNITREE_TTS_AUTO_PROBE}" \
        -e RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT="${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e RABBITBOT_TTS_STRICT_FAILURE="${RABBITBOT_TTS_STRICT_FAILURE}" \
        -e RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM}" \
        -e RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING}" \
        -e RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT}" \
        -e AUTO_START_WORKFLOW=0 \
        -e WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS}" \
        -e WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS}" \
        -v "${PROJECT_ROOT}:${CONTAINER_PROJECT_ROOT}" \
        -v "${MODELS_DIR}:/models" \
        -v rabbitbot_unified_neo4j_data:/var/lib/neo4j/data \
        -v rabbitbot_unified_neo4j_logs:/var/lib/neo4j/logs \
        "${IMAGE_NAME}" \
        bash "${CONTAINER_RABBITBOT_DIR}/scripts_1/unified_runtime/start_unified_container.sh" >/dev/null

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
        -e RABBITBOT_TTS_STRICT_FAILURE="${RABBITBOT_TTS_STRICT_FAILURE}" \
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
