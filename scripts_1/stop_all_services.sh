#!/bin/bash
#
# 关闭 RabbitBot 一键启动流程中拉起的所有服务进程。
# 默认只停止容器内服务进程，不停止 Docker 容器本身，方便后续查看日志和重新启动。
#
# 如确实需要同时停止容器，可执行：
#   STOP_CONTAINERS=1 bash scripts_1/stop_all_services.sh

set -e

VLM_CONTAINER="${VLM_CONTAINER:-vlm}"
AUDIO_CONTAINER="${AUDIO_CONTAINER:-navid-vllm-cuda-mic-audio}"
WORKFLOW_CONTAINER="${WORKFLOW_CONTAINER:-kuavo-agno-projects-only-test}"
VLN_CONTAINER="${VLN_CONTAINER:-air-vln}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-neo4j-community}"
STOP_CONTAINERS="${STOP_CONTAINERS:-0}"

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
        echo "容器 ${container} 未运行，跳过。"
    fi
}

stop_container_if_exists() {
    local container="$1"
    if container_exists "${container}"; then
        docker stop "${container}" >/dev/null || true
        echo "已停止容器 ${container}"
    else
        echo "容器 ${container} 不存在，跳过。"
    fi
}

echo "正在停止 Workflow 和 Memory Agent..."
exec_if_running "${WORKFLOW_CONTAINER}" '
pkill -9 -f "[e]xamples/run_kuavo_agno.py" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_kuavo_agno_workflow.bash" 2>/dev/null || true
pkill -9 -f "[u]vicorn memory_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_memory_agent.sh" 2>/dev/null || true
'

echo "正在停止 TTS/STT 音频服务..."
exec_if_running "${AUDIO_CONTAINER}" '
pkill -9 -f "[u]vicorn tts_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_tts_app.bash" 2>/dev/null || true
pkill -9 -f "[u]vicorn stt_app:app" 2>/dev/null || true
pkill -9 -f "[s]cripts/start_stt_app.bash" 2>/dev/null || true
'

echo "正在停止 VLM/Embedding 服务..."
exec_if_running "${VLM_CONTAINER}" '
pkill -9 -f "[v]llm serve" 2>/dev/null || true
pkill -9 -f "/models/[s]tart_vllm_runtime.sh" 2>/dev/null || true
'

echo "正在停止 VLN 服务（如果容器存在且正在运行）..."
exec_if_running "${VLN_CONTAINER}" '
pkill -9 -f "[t]ools/run_navid_app.sh" 2>/dev/null || true
pkill -9 -f "[r]un_navid_app" 2>/dev/null || true
'

if [ "${STOP_CONTAINERS}" = "1" ]; then
    echo "STOP_CONTAINERS=1，开始停止相关 Docker 容器..."
    stop_container_if_exists "${VLM_CONTAINER}"
    stop_container_if_exists "${AUDIO_CONTAINER}"
    stop_container_if_exists "${WORKFLOW_CONTAINER}"
    stop_container_if_exists "${VLN_CONTAINER}"
    stop_container_if_exists "${NEO4J_CONTAINER}"
else
    echo "默认不停止 Docker 容器。如需停止容器，请使用 STOP_CONTAINERS=1。"
fi

echo "所有服务停止流程完成。"
