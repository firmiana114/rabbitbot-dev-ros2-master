#!/usr/bin/env bash
# 启动持续语音问答 workflow。
#
# 该脚本只负责进入项目 Python 环境并运行问答入口；TTS、STT、VLM 等基础服务
# 由 scripts_1/start_unified_vlm_qa_workflow.sh 在宿主侧统一启动。
#
# 常用环境变量：
#   RABBITBOT_QA_LISTEN_TIMEOUT=30        单轮 STT 监听超时秒数
#   RABBITBOT_QA_INCLUDE_IMAGE=0          是否每轮抓取图像传给 VLM
#   RABBITBOT_QA_IMAGE_SOURCE=robot       图像来源：robot 或 mock
#   RABBITBOT_QA_MOCK_IMAGE=/path/a.jpg   mock 图像路径
#   RABBITBOT_QA_MAX_ANSWER_CHARS=180     单次播报回答最大长度
#   RABBITBOT_QA_STREAM_TTS=1             是否按句流式提交 TTS，设为 0 可回退整段播报
#   RABBITBOT_QA_VLM_STREAM=0             是否启用 VLM token 流式输出，AGX 默认关闭以规避长回答卡住
#   RABBITBOT_QA_VLM_MAX_TOKENS=180       VLM 单次生成 token 上限
#   RABBITBOT_QA_GUIDE_TRIGGER_PHRASES=开始导览 触发导览 workflow 的口令，多个口令用逗号分隔
#   RABBITBOT_QA_GUIDE_COMMAND_FILE=/path/command 写入 go 命令的共享文件
#   RABBITBOT_QA_GUIDE_STATE_FILE=/path/state 读取导览状态的共享文件
#   RABBITBOT_QA_DIALOGUE_LOG=/path/a.log  问答日志路径，默认写入 RABBITBOT_LOG_DIR

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/path_env.sh"

cd "${REPO_DIR}"

if [ -f py310/bin/activate ]; then
    # shellcheck disable=SC1091
    source py310/bin/activate
fi

export PYTHONPATH="/usr/local/lib:${REPO_DIR}:${PYTHONPATH:-}"
export RABBITBOT_MODEL_SERVER="${RABBITBOT_MODEL_SERVER:-http://127.0.0.1:8000/v1}"
export RABBITBOT_VLN_URL="${RABBITBOT_VLN_URL:-http://127.0.0.1:8001}"
export RABBITBOT_MEMORY_AGENT_URL="${RABBITBOT_MEMORY_AGENT_URL:-http://127.0.0.1:28182}"
export RABBITBOT_ROBOT_AGENT_URL="${RABBITBOT_ROBOT_AGENT_URL:-http://127.0.0.1:28180}"
export REALTIME_STT_BASE_URL="${REALTIME_STT_BASE_URL:-http://127.0.0.1:28184/v1}"
export REALTIME_TTS_BASE_URL="${REALTIME_TTS_BASE_URL:-http://127.0.0.1:28185/v1}"
export RABBITBOT_STT_AGENT_URL="${RABBITBOT_STT_AGENT_URL:-${REALTIME_STT_BASE_URL}}"
export RABBITBOT_TTS_AGENT_URL="${RABBITBOT_TTS_AGENT_URL:-${REALTIME_TTS_BASE_URL}}"
export RABBITBOT_QA_LISTEN_TIMEOUT="${RABBITBOT_QA_LISTEN_TIMEOUT:-30}"
export RABBITBOT_QA_INCLUDE_IMAGE="${RABBITBOT_QA_INCLUDE_IMAGE:-0}"
export RABBITBOT_QA_MAX_ANSWER_CHARS="${RABBITBOT_QA_MAX_ANSWER_CHARS:-180}"
export RABBITBOT_QA_STREAM_TTS="${RABBITBOT_QA_STREAM_TTS:-1}"
export RABBITBOT_QA_VLM_STREAM="${RABBITBOT_QA_VLM_STREAM:-0}"
export RABBITBOT_QA_VLM_MAX_TOKENS="${RABBITBOT_QA_VLM_MAX_TOKENS:-}"
export RABBITBOT_QA_GUIDE_TRIGGER_PHRASES="${RABBITBOT_QA_GUIDE_TRIGGER_PHRASES:-开始导览}"
export RABBITBOT_QA_GUIDE_COMMAND_FILE="${RABBITBOT_QA_GUIDE_COMMAND_FILE:-${REPO_DIR}/runtime/nav_workflow_control/command}"
export RABBITBOT_QA_GUIDE_STATE_FILE="${RABBITBOT_QA_GUIDE_STATE_FILE:-${REPO_DIR}/runtime/nav_workflow_control/guide_state}"
export RABBITBOT_QA_GUIDE_START_TIMEOUT_SECONDS="${RABBITBOT_QA_GUIDE_START_TIMEOUT_SECONDS:-90}"
export RABBITBOT_QA_GUIDE_FINISH_TIMEOUT_SECONDS="${RABBITBOT_QA_GUIDE_FINISH_TIMEOUT_SECONDS:-1200}"
export RABBITBOT_QA_DIALOGUE_LOG="${RABBITBOT_QA_DIALOGUE_LOG:-}"

echo "[INFO] 启动 VLM 问答 workflow：model_server=${RABBITBOT_MODEL_SERVER}, stt=${RABBITBOT_STT_AGENT_URL}, tts=${RABBITBOT_TTS_AGENT_URL}, include_image=${RABBITBOT_QA_INCLUDE_IMAGE}, stream_tts=${RABBITBOT_QA_STREAM_TTS}, vlm_stream=${RABBITBOT_QA_VLM_STREAM}, vlm_max_tokens=${RABBITBOT_QA_VLM_MAX_TOKENS:-自动}, guide_trigger=${RABBITBOT_QA_GUIDE_TRIGGER_PHRASES}, guide_command_file=${RABBITBOT_QA_GUIDE_COMMAND_FILE}, guide_state_file=${RABBITBOT_QA_GUIDE_STATE_FILE}, prompt_profile=qa_independent, dialogue_log=${RABBITBOT_QA_DIALOGUE_LOG:-默认}"

exec py310/bin/python scripts/run_vlm_qa_workflow.py "$@"
