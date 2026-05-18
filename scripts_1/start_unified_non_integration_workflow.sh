#!/usr/bin/env bash
#
# =============================================================================
# 夸父机器人 - 统一容器非联调模式启动 workflow
# =============================================================================
#
# 说明：
#   1. 使用独立的统一非联调容器名，避免覆盖普通统一容器的环境。
#   2. 自动开启 RABBITBOT_WORKFLOW_NON_INTEGRATION=1。
#   3. 默认把终端输入传给容器内 workflow，导航点位可在终端按回车确认成功。
#   4. 默认复用已有非联调统一容器，保留 vLLM 编译缓存；如需重建，设置 RECREATE_CONTAINER=1。
#
# 使用方法：
#   cd rabbitbot-dev-ros2-master
#   bash scripts_1/start_unified_non_integration_workflow.sh
#
# 可选环境变量：
#   RABBITBOT_WORKFLOW_VERBOSE=1    显示详细调试日志
#   RECREATE_CONTAINER=1            删除并重建非联调统一容器
#   STOP_UNIFIED_CONTAINER=0        不自动停止普通统一容器
#   STOP_LEGACY_CONTAINERS=0        不自动停止旧四容器
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime-non-integration}"
STOP_UNIFIED_CONTAINER="${STOP_UNIFIED_CONTAINER:-1}"

export CONTAINER_NAME
export RABBITBOT_WORKFLOW_NON_INTEGRATION=1
export AUTO_START_WORKFLOW="${AUTO_START_WORKFLOW:-1}"
export START_AFTER_CREATE="${START_AFTER_CREATE:-1}"
export ATTACH_AFTER_START="${ATTACH_AFTER_START:-1}"
export RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-1}"
export RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-1}"
export STOP_LEGACY_CONTAINERS="${STOP_LEGACY_CONTAINERS:-1}"

echo "[INFO] 启动统一容器非联调 workflow：导航点位由终端按回车确认成功"
echo "[INFO] 项目目录：${PROJECT_DIR}"
echo "[INFO] 统一非联调容器：${CONTAINER_NAME}"

if [ "${STOP_UNIFIED_CONTAINER}" = "1" ] && [ "${CONTAINER_NAME}" != "rabbitbot-unified-runtime" ]; then
    echo "[INFO] 停止普通统一容器以释放 host 端口：rabbitbot-unified-runtime"
    docker stop rabbitbot-unified-runtime >/dev/null 2>&1 || true
fi

cd "${PROJECT_DIR}"
exec bash scripts_1/start_unified_integration_workflow.sh
