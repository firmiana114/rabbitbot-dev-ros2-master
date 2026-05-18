#!/usr/bin/env bash
#
# =============================================================================
# 夸父机器人 - 停止统一容器 workflow
# =============================================================================
#
# 说明：
#   1. 停止普通统一容器和统一非联调容器内的 workflow 及后台服务。
#   2. 默认只停止容器，不删除容器，保留 vLLM 编译缓存。
#   3. 如需删除统一容器，设置 REMOVE_UNIFIED_CONTAINERS=1。
#
# 使用方法：
#   cd rabbitbot-dev-ros2-master
#   bash scripts_1/stop_unified_workflow.sh
#
# =============================================================================

set -euo pipefail

UNIFIED_CONTAINERS=(
    "${UNIFIED_CONTAINER:-rabbitbot-unified-runtime}"
    "${UNIFIED_NON_INTEGRATION_CONTAINER:-rabbitbot-unified-runtime-non-integration}"
)

REMOVE_UNIFIED_CONTAINERS="${REMOVE_UNIFIED_CONTAINERS:-0}"

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

container_running() {
    docker ps --format '{{.Names}}' | grep -qx "$1"
}

exec_if_running() {
    local container="$1"
    shift
    if container_running "${container}"; then
        docker exec "${container}" bash -lc "$*"
    else
        echo "[INFO] 容器 ${container} 未运行，跳过进程清理。"
    fi
}

stop_container_if_exists() {
    local container="$1"
    if ! container_exists "${container}"; then
        echo "[INFO] 容器 ${container} 不存在，跳过。"
        return 0
    fi

    if container_running "${container}"; then
        docker stop "${container}" >/dev/null || true
        echo "[INFO] 已停止容器 ${container}"
    else
        echo "[INFO] 容器 ${container} 已经停止。"
    fi

    if [ "${REMOVE_UNIFIED_CONTAINERS}" = "1" ]; then
        docker rm "${container}" >/dev/null || true
        echo "[INFO] 已删除容器 ${container}"
    fi
}

for container in "${UNIFIED_CONTAINERS[@]}"; do
    echo "[INFO] 清理统一容器服务进程：${container}"
    exec_if_running "${container}" '
pkill -9 -f "[e]xamples/run_kuavo_agno.py" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_kuavo_agno_workflow.bash" 2>/dev/null || true
pkill -9 -f "[u]vicorn memory_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_memory_agent.sh" 2>/dev/null || true
pkill -9 -f "[u]vicorn robot_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_robot_app.bash" 2>/dev/null || true
pkill -9 -f "[u]vicorn tts_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_tts_app.bash" 2>/dev/null || true
pkill -9 -f "[s]tt_app_funasr.py" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_stt_funasr_app.bash" 2>/dev/null || true
pkill -9 -f "[v]llm.entrypoints.cli.main serve" 2>/dev/null || true
pkill -9 -f "[v]llm serve" 2>/dev/null || true
pkill -9 -f "[s]tart_unified_container.sh" 2>/dev/null || true
'

    stop_container_if_exists "${container}"
done

echo "[INFO] 统一容器 workflow 停止流程完成。"
