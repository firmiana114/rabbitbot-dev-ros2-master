#!/usr/bin/env bash
# 启动 VLM 语音问答测试 workflow。
#
# 该入口会先启动统一容器基础服务，并显式启用 VLM、STT 和 TTS；随后在容器前台
# 运行 scripts/start_vlm_qa_workflow.bash，持续监听用户语音并播报 VLM 回答。
#
# 常用环境变量：
#   RECREATE_CONTAINER=1                 强制重建统一容器
#   RABBITBOT_QA_INCLUDE_IMAGE=1          每轮抓取图像传给 VLM
#   RABBITBOT_QA_IMAGE_SOURCE=mock        使用 mock 图像测试视觉问答
#   RABBITBOT_QA_LISTEN_TIMEOUT=30        单轮 STT 监听超时秒数
#   RABBITBOT_QA_MAX_ANSWER_CHARS=180     单次回答播报长度上限
#   RABBITBOT_QA_STREAM_TTS=1             按句流式提交 TTS，设为 0 可回退整段播报
#   RABBITBOT_QA_DIALOGUE_LOG=/path/a.log  问答日志路径，默认写入 workflow 日志目录
#   RABBITBOT_QA_VERBOSE=1                输出 DEBUG 级别 workflow 日志

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RABBITBOT_REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_PROJECT_ROOT="$(cd "${RABBITBOT_REPO_DIR}/.." && pwd)"
PORTABLE_ENV_FILE="${RABBITBOT_PORTABLE_ENV_FILE:-${RABBITBOT_REPO_DIR}/runtime/portable.env}"

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

if [ -f "${PORTABLE_ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${PORTABLE_ENV_FILE}"
    set +a
elif [ -f "${PORTABLE_ENV_FILE}.example" ]; then
    log_info "未找到本机配置 ${PORTABLE_ENV_FILE}，回退读取模板 ${PORTABLE_ENV_FILE}.example"
    set -a
    # shellcheck disable=SC1090
    source "${PORTABLE_ENV_FILE}.example"
    set +a
fi

RABBITBOT_RUNTIME_MODE="${RABBITBOT_RUNTIME_MODE:-legacy}"
PROJECT_ROOT="${PROJECT_ROOT:-${DEFAULT_PROJECT_ROOT}}"
CONTAINER_PROJECT_ROOT="${CONTAINER_PROJECT_ROOT:-/workspace/projects}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-${CONTAINER_PROJECT_ROOT}/rabbitbot-dev-ros2-master}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-${CONTAINER_RABBITBOT_DIR}/logs/unified_runtime}"

if [ "${RABBITBOT_RUNTIME_MODE}" = "portable" ]; then
    IMAGE_NAME="${IMAGE_NAME:-${RABBITBOT_PORTABLE_CORE_IMAGE:-ghcr.io/aaronai/rabbitbot-core-portable:20260611}}"
    CONTAINER_NAME="${CONTAINER_NAME:-${RABBITBOT_PORTABLE_CORE_CONTAINER_NAME:-rabbitbot-unified-runtime}}"
    export RABBITBOT_UNIFIED_START_ROBOT_AGENT="${RABBITBOT_UNIFIED_START_ROBOT_AGENT:-0}"
else
    IMAGE_NAME="${IMAGE_NAME:-rabbitbot-unified-runtime:20260518}"
    CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
fi

export IMAGE_NAME
export CONTAINER_NAME
export PROJECT_ROOT
export CONTAINER_PROJECT_ROOT
export CONTAINER_RABBITBOT_DIR
export CONTAINER_LOG_DIR
export RABBITBOT_UNIFIED_START_VLM=1
export RABBITBOT_UNIFIED_START_STT=1
export RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING:-0}"
export RUN_WORKFLOW_AFTER_START=0
export START_AFTER_CREATE="${START_AFTER_CREATE:-1}"

log_info "启动统一容器问答底座：container=${CONTAINER_NAME}, image=${IMAGE_NAME}, runtime=${RABBITBOT_RUNTIME_MODE}, vlm=1, stt=1"
bash "${SCRIPT_DIR}/start_unified_integration_workflow.sh"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    log_error "统一容器未运行：${CONTAINER_NAME}"
    exit 1
fi

stop_existing_vlm_qa_workflow() {
    log_info "清理已有 VLM 问答 workflow 进程（不停止容器或基础服务）"
    docker exec "${CONTAINER_NAME}" bash -lc '
set +e
collect_pids() {
    {
        pgrep -f "[r]un_vlm_qa_workflow.py" || true
        pgrep -f "[s]cripts/start_vlm_qa_workflow.bash" || true
        pgrep -f "[t]ee -a .*/vlm_qa_workflow_.*\.log" || true
    } | awk "NF && !seen[\$1]++ {print \$1}"
}

pids="$(collect_pids)"
if [ -z "${pids}" ]; then
    echo "[INFO] 未发现已有 VLM 问答 workflow 进程"
    exit 0
fi

echo "[INFO] 准备停止已有 VLM 问答 workflow 进程: ${pids}"
kill -TERM ${pids} 2>/dev/null || true
for _ in 1 2 3 4 5; do
    sleep 0.4
    remaining="$(collect_pids)"
    [ -z "${remaining}" ] && break
done
remaining="$(collect_pids)"
if [ -n "${remaining}" ]; then
    echo "[WARN] VLM 问答 workflow 进程未按时退出，强制停止: ${remaining}" >&2
    kill -KILL ${remaining} 2>/dev/null || true
fi
'
}

stop_existing_vlm_qa_workflow

docker_exec_args=()
if [ -t 0 ]; then
    docker_exec_args+=(-i)
fi
if [ -t 1 ]; then
    docker_exec_args+=(-t)
fi

mkdir -p "${RABBITBOT_REPO_DIR}/logs/vlm_qa_workflow"
log_info "前台启动 VLM 问答 workflow；日志目录：${CONTAINER_RABBITBOT_DIR}/logs/vlm_qa_workflow"

exec docker exec "${docker_exec_args[@]}" \
    -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
    -e RABBITBOT_LOG_DIR="${CONTAINER_RABBITBOT_DIR}/logs/vlm_qa_workflow" \
    -e RABBITBOT_QA_LISTEN_TIMEOUT="${RABBITBOT_QA_LISTEN_TIMEOUT:-30}" \
    -e RABBITBOT_QA_INCLUDE_IMAGE="${RABBITBOT_QA_INCLUDE_IMAGE:-0}" \
    -e RABBITBOT_QA_IMAGE_SOURCE="${RABBITBOT_QA_IMAGE_SOURCE:-robot}" \
    -e RABBITBOT_QA_MAX_ANSWER_CHARS="${RABBITBOT_QA_MAX_ANSWER_CHARS:-180}" \
    -e RABBITBOT_QA_STREAM_TTS="${RABBITBOT_QA_STREAM_TTS:-1}" \
    -e RABBITBOT_QA_DIALOGUE_LOG="${RABBITBOT_QA_DIALOGUE_LOG:-}" \
    -e RABBITBOT_QA_VERBOSE="${RABBITBOT_QA_VERBOSE:-0}" \
    -e PYTHONUNBUFFERED=1 \
    "${CONTAINER_NAME}" bash -lc "cd \"\${RABBITBOT_DIR}\" && mkdir -p \"\${RABBITBOT_LOG_DIR}\" && log_name=\"vlm_qa_workflow_\$(date +%Y%m%d_%H%M%S).log\" && log_path=\"\${RABBITBOT_LOG_DIR}/\${log_name}\" && ln -sfn \"\${log_name}\" \"\${RABBITBOT_LOG_DIR}/vlm_qa_workflow_latest.log\" && echo \"VLM问答workflow日志: \${log_path}\" && PYTHONUNBUFFERED=1 bash scripts/start_vlm_qa_workflow.bash 2>&1 | tee -a \"\${log_path}\""
