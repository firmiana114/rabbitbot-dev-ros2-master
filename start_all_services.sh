#!/bin/bash
#
# =============================================================================
# 夸父机器人 - 开机后一键启动所有服务脚本
# =============================================================================
# 
# 功能说明：
#   本脚本用于在机器开机后，按正确顺序启动所有 RabbitBot 相关服务，包括：
#   1. Docker 容器启动
#   2. VLM 大模型服务 (端口 8000)
#   3. Embedding 模型服务 (端口 8005)
#   4. TTS 语音合成服务 (端口 28185)
#   5. STT 语音识别服务 (端口 28184)
#   6. VLN 视觉导航服务 (端口 8001)
#   7. Neo4j 知识图谱数据库 (端口 7474/7687)
#   8. Memory Agent 知识图谱服务 (端口 28182)
#   9. Workflow 主程序
#
# 使用方法：
#   chmod +x start_all_services.sh
#   ./start_all_services.sh
#
# 注意事项：
#   - 需要在宿主机上执行（不是容器内）
#   - 确保 Docker 服务已启动
#   - 脚本会检测服务是否已运行，避免重复启动
#
# =============================================================================

# -----------------------------------------------------------------------------
# 配置区域
# -----------------------------------------------------------------------------

# 项目根目录
PROJECT_DIR="/mnt/ssd/navgation/projects"
RABBITBOT_DIR="${PROJECT_DIR}/rabbitbot-dev-ros2"

# 容器名称
VLM_CONTAINER="vlm"
AUDIO_CONTAINER="navid-vllm-cuda-mic-audio"
WORKFLOW_CONTAINER="kuavo-agno-projects-only-test"
VLN_CONTAINER="air-vln"
NEO4J_CONTAINER="neo4j-community"

# 服务端口
VLM_PORT=8000
EMBEDDING_PORT=8005
STT_PORT=28184
TTS_PORT=28185
VLN_PORT=8001
NEO4J_WEB_PORT=7474
NEO4J_BOLT_PORT=7687
MEMORY_AGENT_PORT=28182

# 音频设备名称（根据实际情况修改）
TTS_DEVICE_NAME="BT67"
STT_DEVICE_NAME="Wireless Mic Rx"

# 日志目录
LOG_DIR="${PROJECT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# =============================================================================
# 函数定义
# =============================================================================

# 输出带颜色的消息
log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

# 检查服务端口是否可用
check_port() {
    local port=$1
    if nc -z localhost $port 2>/dev/null; then
        return 0  # 端口已占用
    else
        return 1  # 端口可用
    fi
}

# 检查容器是否运行
check_container() {
    local container=$1
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        return 0  # 容器运行中
    else
        return 1  # 容器未运行
    fi
}

# 等待服务就绪
wait_for_service() {
    local port=$1
    local name=$2
    local max_wait=60
    local count=0
    
    echo -n "等待 ${name} (端口 ${port}) 就绪"
    while ! check_port $port; do
        sleep 1
        count=$((count + 1))
        echo -n "."
        if [ $count -ge $max_wait ]; then
            echo ""
            log_error "${name} 启动超时 (${max_wait}秒)"
            return 1
        fi
    done
    echo ""
    log_success "${name} 已就绪"
    return 0
}

# =============================================================================
# 主流程
# =============================================================================

echo "========================================"
echo "  夸父机器人 - 一键启动所有服务"
echo "========================================"
echo ""

# -----------------------------------------------------------------------------
# 步骤 0: 前置检查
# -----------------------------------------------------------------------------
log_info "步骤 0: 前置检查"

# 检查 Docker 服务
if ! systemctl is-active --quiet docker; then
    log_error "Docker 服务未运行，正在启动..."
    systemctl start docker
    sleep 2
fi
log_success "Docker 服务状态正常"

# 检查项目目录
if [ ! -d "${RABBITBOT_DIR}" ]; then
    log_error "项目目录不存在: ${RABBITBOT_DIR}"
    exit 1
fi
log_success "项目目录正常"

echo ""

# -----------------------------------------------------------------------------
# 步骤 1: 启动 Docker 容器
# -----------------------------------------------------------------------------
log_info "步骤 1: 启动 Docker 容器"

containers=("${VLM_CONTAINER}" "${AUDIO_CONTAINER}" "${VLN_CONTAINER}" "${NEO4J_CONTAINER}" "${WORKFLOW_CONTAINER}")

for container in "${containers[@]}"; do
    if check_container $container; then
        log_success "容器 ${container} 已在运行"
    else
        log_info "启动容器 ${container}..."
        docker start $container
        if [ $? -eq 0 ]; then
            log_success "容器 ${container} 启动成功"
        else
            log_warn "容器 ${container} 启动失败或不存在"
        fi
    fi
done

echo ""

# -----------------------------------------------------------------------------
# 步骤 2: 启动 VLM 大模型服务 (端口 8000)
# -----------------------------------------------------------------------------
log_info "步骤 2: 启动 VLM 大模型服务 (端口 ${VLM_PORT})"

if check_port $VLM_PORT; then
    log_success "VLM 服务已在运行 (端口 ${VLM_PORT})"
else
    log_info "启动 VLM 服务..."
    docker exec -d ${VLM_CONTAINER} bash -lc '
        # 检查是否已有 vllm 进程
        if pgrep -f "vllm serve" > /dev/null; then
            echo "VLM already running"
        else
            cd /models
            vllm serve /models/Qwen2.5-VL-7B-Instruct-GPTQ-Int4 \
                --seed 42 \
                --gpu-memory-utilization 0.6 \
                --max-num-seqs 2 \
                --limit-mm-per-prompt "image=4,video=1" \
                --max-num-batched-tokens 2048 \
                --enable-chunked-prefill \
                --mm-processor-kwargs "{\"max_pixels\": 802816, \"fps\": 1}" \
                --max-model-len 65536 \
                --served-model-name Qwen2.5-VL-7B-Instruct \
                --port 8000 \
                > /models/qwen2.5-vl-7b-gptq.log 2>&1
        fi
    '
    wait_for_service $VLM_PORT "VLM 大模型服务"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 3: 启动 Embedding 模型服务 (端口 8005)
# -----------------------------------------------------------------------------
log_info "步骤 3: 启动 Embedding 模型服务 (端口 ${EMBEDDING_PORT})"

if check_port $EMBEDDING_PORT; then
    log_success "Embedding 服务已在运行 (端口 ${EMBEDDING_PORT})"
else
    log_info "启动 Embedding 服务..."
    docker exec -d ${VLM_CONTAINER} bash -lc '
        # 检查是否已有 embedding 进程
        if pgrep -f "Qwen3-Embedding" > /dev/null; then
            echo "Embedding already running"
        else
            cd /models
            vllm serve /models/Qwen3-Embedding-0.6B \
                --served-model-name Qwen3-Embedding-0.6B \
                --port 8005 \
                --gpu-memory-utilization 0.1 \
                --max-num-seqs 5 \
                --trust-remote-code \
                > /models/embedding.log 2>&1
        fi
    '
    wait_for_service $EMBEDDING_PORT "Embedding 模型服务"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 4: 启动 TTS 语音合成服务 (端口 28185)
# -----------------------------------------------------------------------------
log_info "步骤 4: 启动 TTS 语音合成服务 (端口 ${TTS_PORT})"

if check_port $TTS_PORT; then
    log_success "TTS 服务已在运行 (端口 ${TTS_PORT})"
else
    log_info "启动 TTS 服务..."
    docker exec -d ${AUDIO_CONTAINER} bash -lc "
        cd /data/rabbitbot-dev-ros2-master
        export TTS_DEVICE_NAME=${TTS_DEVICE_NAME}
        # 检查是否已有进程
        if pgrep -f 'uvicorn tts_app:app' > /dev/null; then
            echo 'TTS already running'
        else
            bash scripts/start_tts_app.bash > /tmp/rabbitbot_tts.log 2>&1 &
        fi
    "
    wait_for_service $TTS_PORT "TTS 语音合成服务"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 5: 启动 STT 语音识别服务 (端口 28184)
# -----------------------------------------------------------------------------
log_info "步骤 5: 启动 STT 语音识别服务 (端口 ${STT_PORT})"

if check_port $STT_PORT; then
    log_success "STT 服务已在运行 (端口 ${STT_PORT})"
else
    log_info "启动 STT 服务..."
    docker exec -d ${AUDIO_CONTAINER} bash -lc "
        cd /data/rabbitbot-dev-ros2-master
        export STT_DEVICE_NAME='${STT_DEVICE_NAME}'
        # 检查是否已有进程
        if pgrep -f 'uvicorn stt_app:app' > /dev/null; then
            echo 'STT already running'
        else
            bash scripts/start_stt_app.bash > /tmp/rabbitbot_stt.log 2>&1 &
        fi
    "
    wait_for_service $STT_PORT "STT 语音识别服务"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 6: 验证 VLN 服务 (端口 8001)
# -----------------------------------------------------------------------------
log_info "步骤 6: 验证 VLN 视觉导航服务 (端口 ${VLN_PORT})"

if check_port $VLN_PORT; then
    log_success "VLN 服务已在运行 (端口 ${VLN_PORT})"
    # 发送测试请求
    curl -s -X POST http://127.0.0.1:${VLN_PORT}/reset > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        log_success "VLN 服务响应正常"
    else
        log_warn "VLN 服务可能未正常响应"
    fi
else
    log_warn "VLN 服务未运行，请检查 air-vln 容器"
    log_info "在 VLN 容器内执行: cd /data/v-fuchengjia/Projects/robot_car && sh tools/run_navid_app.sh"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 7: 验证 Neo4j 知识图谱数据库 (端口 7474/7687)
# -----------------------------------------------------------------------------
log_info "步骤 7: 验证 Neo4j 知识图谱数据库 (端口 ${NEO4J_BOLT_PORT})"

if check_port $NEO4J_BOLT_PORT; then
    log_success "Neo4j 数据库已在运行 (端口 ${NEO4J_BOLT_PORT})"
else
    log_warn "Neo4j 数据库未运行，请检查 neo4j-community 容器"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 8: 启动 Memory Agent 知识图谱服务 (端口 28182)
# -----------------------------------------------------------------------------
log_info "步骤 8: 启动 Memory Agent 知识图谱服务 (端口 ${MEMORY_AGENT_PORT})"

if check_port $MEMORY_AGENT_PORT; then
    log_success "Memory Agent 服务已在运行 (端口 ${MEMORY_AGENT_PORT})"
else
    log_info "启动 Memory Agent 服务..."
    docker exec -d ${WORKFLOW_CONTAINER} bash -lc '
        cd /data/rabbitbot-dev-ros2-master
        export NEO4J_PASSWORD="your_password"
        export RABBITBOT_MODEL_SERVER="http://127.0.0.1:8000/v1"
        export GRAPHITI_RERANK_MODEL_URL=${RABBITBOT_MODEL_SERVER}
        export GRAPHITI_EMBD_MODEL_URL="http://127.0.0.1:8005/v1"
        
        # 检查是否已有进程
        if pgrep -f "uvicorn memory_app:app" > /dev/null; then
            echo "Memory Agent already running"
        else
            uvicorn memory_app:app --host 0.0.0.0 --port 28182 --reload --log-level debug > /tmp/memory_agent.log 2>&1 &
        fi
    '
    wait_for_service $MEMORY_AGENT_PORT "Memory Agent 知识图谱服务"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 9: 汇总服务状态
# -----------------------------------------------------------------------------
log_info "========================================"
log_info "  服务状态汇总"
log_info "========================================"

echo ""
echo "| 服务 | 端口 | 状态 |"
echo "| --- | --- | --- |"

# VLM
if check_port $VLM_PORT; then
    echo "| VLM 大模型 | ${VLM_PORT} | ✅ 运行中 |"
else
    echo "| VLM 大模型 | ${VLM_PORT} | ❌ 未运行 |"
fi

# Embedding
if check_port $EMBEDDING_PORT; then
    echo "| Embedding | ${EMBEDDING_PORT} | ✅ 运行中 |"
else
    echo "| Embedding | ${EMBEDDING_PORT} | ❌ 未运行 |"
fi

# TTS
if check_port $TTS_PORT; then
    echo "| TTS 语音合成 | ${TTS_PORT} | ✅ 运行中 |"
else
    echo "| TTS 语音合成 | ${TTS_PORT} | ❌ 未运行 |"
fi

# STT
if check_port $STT_PORT; then
    echo "| STT 语音识别 | ${STT_PORT} | ✅ 运行中 |"
else
    echo "| STT 语音识别 | ${STT_PORT} | ❌ 未运行 |"
fi

# VLN
if check_port $VLN_PORT; then
    echo "| VLN 视觉导航 | ${VLN_PORT} | ✅ 运行中 |"
else
    echo "| VLN 视觉导航 | ${VLN_PORT} | ❌ 未运行 |"
fi

# Neo4j
if check_port $NEO4J_BOLT_PORT; then
    echo "| Neo4j 知识图谱 | ${NEO4J_BOLT_PORT} | ✅ 运行中 |"
else
    echo "| Neo4j 知识图谱 | ${NEO4J_BOLT_PORT} | ❌ 未运行 |"
fi

# Memory Agent
if check_port $MEMORY_AGENT_PORT; then
    echo "| Memory Agent | ${MEMORY_AGENT_PORT} | ✅ 运行中 |"
else
    echo "| Memory Agent | ${MEMORY_AGENT_PORT} | ❌ 未运行 |"
fi

echo ""

# -----------------------------------------------------------------------------
# 步骤 10: 启动 Workflow
# -----------------------------------------------------------------------------
log_info "========================================"
log_info "  启动 Workflow"
log_info "========================================"

log_info ""
log_info "所有基础服务已启动，现在可以启动 Workflow 主程序。"
log_info ""
log_info "进入 workflow 容器执行："
log_info "  cd /data/rabbitbot-dev-ros2-master"
log_info "  source py310/bin/activate"
log_info "  bash scripts/start_kuavo_agno_workflow.bash"
log_info ""

read -p "是否立即启动 Workflow? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "启动 Workflow..."
    docker exec -it ${WORKFLOW_CONTAINER} bash -lc '
        cd /data/rabbitbot-dev-ros2-master
        source py310/bin/activate
        bash scripts/start_kuavo_agno_workflow.bash
    '
else
    log_info "跳过 Workflow 启动，可在后续手动执行"
fi

echo ""
log_success "启动脚本执行完成！"
