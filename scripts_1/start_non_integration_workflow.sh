#!/bin/bash
#
# =============================================================================
# 夸父机器人 - 非联调模式启动 workflow
# =============================================================================
#
# 说明：
#   1. 复用 scripts_1/start_all_services.sh 启动基础服务和 workflow。
#   2. 自动开启 RABBITBOT_WORKFLOW_NON_INTEGRATION=1。
#   3. workflow 需要导航到点位时，不会等待 body 实际导航状态；
#      在终端按任意键即可视为到达成功，随后继续剧本流程。
#
# 使用方法：
#   cd rabbitbot-dev-ros2-master
#   bash scripts_1/start_non_integration_workflow.sh
#
# 可选环境变量：
#   RABBITBOT_WORKFLOW_VERBOSE=1    显示详细调试日志
#   RESTART_EXISTING=1              启动前停止已有同类服务进程
#
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RABBITBOT_WORKFLOW_NON_INTEGRATION=1
export AUTO_START_WORKFLOW="${AUTO_START_WORKFLOW:-1}"

echo "[INFO] 启动非联调 workflow：导航点位由终端按键确认成功"
echo "[INFO] 项目目录：${PROJECT_DIR}"

cd "${PROJECT_DIR}"
exec bash scripts_1/start_all_services.sh
