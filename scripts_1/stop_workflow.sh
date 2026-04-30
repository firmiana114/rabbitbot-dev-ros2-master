#!/bin/bash
#
# 只关闭 Workflow 主程序。
# 说明：该脚本只停止 workflow 相关 Python/启动脚本进程，不停止容器，也不停止
# Memory Agent、TTS、STT、VLM、Neo4j 等基础服务。

set -e

# Workflow 所在容器名；如后续容器名变化，可通过环境变量覆盖：
#   WORKFLOW_CONTAINER=your-container bash scripts_1/stop_workflow.sh
WORKFLOW_CONTAINER="${WORKFLOW_CONTAINER:-kuavo-agno-projects-only-test}"

echo "正在停止 Workflow 主程序，容器：${WORKFLOW_CONTAINER}"

docker exec "${WORKFLOW_CONTAINER}" bash -lc '
pkill -9 -f "[e]xamples/run_kuavo_agno.py" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_kuavo_agno_workflow.bash" 2>/dev/null || true
'

echo "Workflow 主程序已停止。"
