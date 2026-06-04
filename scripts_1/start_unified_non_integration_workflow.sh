#!/usr/bin/env bash
#
# =============================================================================
# 夸父机器人 - 统一容器非联调模式启动 workflow
# =============================================================================
#
# 说明：
#   1. 与联调模式共用同一个统一容器：rabbitbot-unified-runtime。
#   2. 自动开启 RABBITBOT_WORKFLOW_NON_INTEGRATION=1。
#   3. 默认把终端输入传给容器内 workflow，导航点位可在终端按回车确认成功。
#   4. 基础服务常驻在统一容器内，workflow 每次由本脚本 docker exec 前台启动。
#
# 使用方法：
#   cd rabbitbot-dev-ros2-master
#   bash scripts_1/start_unified_non_integration_workflow.sh
#
# 可选环境变量：
#   RABBITBOT_WORKFLOW_VERBOSE=1    显示详细调试日志
#   RECREATE_CONTAINER=1            删除并重建统一容器
#   RUN_WORKFLOW_AFTER_START=0      只启动基础服务，不启动 workflow
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
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
export RABBITBOT_WORKFLOW_NON_INTEGRATION=1
export START_AFTER_CREATE="${START_AFTER_CREATE:-1}"
export RUN_WORKFLOW_AFTER_START="${RUN_WORKFLOW_AFTER_START:-1}"
export RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-1}"
export RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-1}"

echo "[INFO] 启动统一容器非联调 workflow：导航点位由终端按回车确认成功"
echo "[INFO] 项目目录：${PROJECT_DIR}"
echo "[INFO] 共用统一容器：${CONTAINER_NAME}"

cd "${PROJECT_DIR}"
exec bash scripts_1/start_unified_integration_workflow.sh
