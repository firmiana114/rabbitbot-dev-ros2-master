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
