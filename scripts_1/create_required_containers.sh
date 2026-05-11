#!/usr/bin/env bash
#
# =============================================================================
#  夸父机器人 - 迁移环境容器创建脚本
# =============================================================================
#
# 用途：
#   在新 Orin 上按当前项目约定创建一键启动脚本依赖的 Docker 容器。
#   本脚本只负责创建容器，不负责迁移代码、模型、镜像或 Neo4j 数据。
#
# 前置条件：
#   1. Docker 已安装并可用。
#   2. 下列镜像已导入新 Orin：
#        - foxy-ros-cam-orb-ubuntu20:latest
#        - navid-rabbitbot:stt-tts-audio-ct2cuda-20260427
#        - dustynv/vllm:0.9.2-r36.4-cu128-24.04
#        - neo4j:5.26-community
#      如需 VLN，再导入：
#        - air_vln:1.0
#   3. 项目和模型目录已存在：
#        - /mnt/ssd/navgation/projects
#        - /mnt/ssd/navgation/projects/models
#
# 常用用法：
#   bash scripts_1/create_required_containers.sh
#   START_AFTER_CREATE=1 bash scripts_1/create_required_containers.sh
#
# 可选环境变量：
#   PROJECT_DIR=/mnt/ssd/navgation/projects        项目根挂载目录
#   MODELS_DIR=/mnt/ssd/navgation/projects/models  VLM/Embedding 模型目录
#   START_AFTER_CREATE=1                           创建后立即 docker start
#   RECREATE_CONTAINERS=1                          删除同名旧容器后重建
#   CREATE_VLN=1                                   同时创建当前默认跳过的 air-vln 容器
#   NEO4J_AUTH=neo4j/neo4j_pass                    Neo4j 初始账号密码
#
# 注意：
#   默认不会删除或覆盖已有容器；如果容器已存在会直接跳过。
# =============================================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/mnt/ssd/navgation/projects}"
MODELS_DIR="${MODELS_DIR:-${PROJECT_DIR}/models}"
START_AFTER_CREATE="${START_AFTER_CREATE:-0}"
RECREATE_CONTAINERS="${RECREATE_CONTAINERS:-0}"
CREATE_VLN="${CREATE_VLN:-0}"
NEO4J_AUTH="${NEO4J_AUTH:-neo4j/neo4j_pass}"

VLM_CONTAINER="vlm"
AUDIO_CONTAINER="navid-vllm-cuda-mic-audio"
WORKFLOW_CONTAINER="kuavo-agno-projects-only-test"
NEO4J_CONTAINER="neo4j-community"
VLN_CONTAINER="air-vln"

VLM_IMAGE="dustynv/vllm:0.9.2-r36.4-cu128-24.04"
AUDIO_IMAGE="navid-rabbitbot:stt-tts-audio-ct2cuda-20260427"
WORKFLOW_IMAGE="foxy-ros-cam-orb-ubuntu20:latest"
NEO4J_IMAGE="neo4j:5.26-community"
VLN_IMAGE="air_vln:1.0"

NEO4J_DATA_VOLUME="rabbitbot_neo4j_data"
NEO4J_LOGS_VOLUME="rabbitbot_neo4j_logs"

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

require_command() {
    local command_name="$1"
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        log_error "缺少命令：${command_name}"
        exit 1
    fi
}

require_dir() {
    local dir="$1"
    if [ ! -d "${dir}" ]; then
        log_error "目录不存在：${dir}"
        exit 1
    fi
}

image_exists() {
    local image="$1"
    docker image inspect "${image}" >/dev/null 2>&1
}

require_image() {
    local image="$1"
    if ! image_exists "${image}"; then
        log_error "镜像不存在：${image}"
        log_error "请先在新 Orin 上 docker load 或 docker pull 该镜像。"
        exit 1
    fi
}

container_exists() {
    local container="$1"
    docker ps -a --format '{{.Names}}' | grep -qx "${container}"
}

container_running() {
    local container="$1"
    docker ps --format '{{.Names}}' | grep -qx "${container}"
}

remove_container_if_requested() {
    local container="$1"
    if ! container_exists "${container}"; then
        return 0
    fi

    if [ "${RECREATE_CONTAINERS}" != "1" ]; then
        log_success "容器 ${container} 已存在，跳过创建"
        return 1
    fi

    log_warn "RECREATE_CONTAINERS=1，删除已有容器 ${container}"
    if container_running "${container}"; then
        docker stop "${container}" >/dev/null
    fi
    docker rm "${container}" >/dev/null
    return 0
}

nvidia_runtime_args() {
    if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
        printf '%s\n' "--runtime" "nvidia"
    else
        log_warn "Docker 未检测到 nvidia runtime，将不添加 --runtime nvidia"
    fi
}

create_vlm_container() {
    remove_container_if_requested "${VLM_CONTAINER}" || return 0
    log_info "创建容器 ${VLM_CONTAINER}"
    local runtime_args=()
    mapfile -t runtime_args < <(nvidia_runtime_args)
    docker create \
        --name "${VLM_CONTAINER}" \
        --network host \
        "${runtime_args[@]}" \
        --group-add video \
        -v "${MODELS_DIR}:/models" \
        "${VLM_IMAGE}" \
        tail -f /dev/null >/dev/null
    log_success "容器 ${VLM_CONTAINER} 创建完成"
}

create_audio_container() {
    remove_container_if_requested "${AUDIO_CONTAINER}" || return 0
    log_info "创建容器 ${AUDIO_CONTAINER}"
    local runtime_args=()
    local device_args=()
    mapfile -t runtime_args < <(nvidia_runtime_args)
    if [ -e /dev/snd ]; then
        device_args+=(--device /dev/snd)
    else
        log_warn "宿主机没有 /dev/snd，音频容器仍会创建，但 STT/TTS 现场音频可能不可用"
    fi
    docker create \
        --name "${AUDIO_CONTAINER}" \
        --network host \
        --ipc host \
        "${runtime_args[@]}" \
        "${device_args[@]}" \
        -v "${PROJECT_DIR}:/data" \
        "${AUDIO_IMAGE}" \
        tail -f /dev/null >/dev/null
    log_success "容器 ${AUDIO_CONTAINER} 创建完成"
}

create_workflow_container() {
    remove_container_if_requested "${WORKFLOW_CONTAINER}" || return 0
    log_info "创建容器 ${WORKFLOW_CONTAINER}"
    docker create \
        --name "${WORKFLOW_CONTAINER}" \
        --network host \
        -e NVIDIA_VISIBLE_DEVICES=all \
        -e NVIDIA_DRIVER_CAPABILITIES=all \
        -v "${PROJECT_DIR}:/data" \
        -v "${PROJECT_DIR}:/datanvme/fuchengjia/projects" \
        "${WORKFLOW_IMAGE}" \
        tail -f /dev/null >/dev/null
    log_success "容器 ${WORKFLOW_CONTAINER} 创建完成"
}

create_neo4j_container() {
    remove_container_if_requested "${NEO4J_CONTAINER}" || return 0
    log_info "创建 Neo4j 数据卷"
    docker volume create "${NEO4J_DATA_VOLUME}" >/dev/null
    docker volume create "${NEO4J_LOGS_VOLUME}" >/dev/null

    log_info "创建容器 ${NEO4J_CONTAINER}"
    docker create \
        --name "${NEO4J_CONTAINER}" \
        --network host \
        -e "NEO4J_AUTH=${NEO4J_AUTH}" \
        -e 'NEO4J_PLUGINS=["apoc"]' \
        -v "${NEO4J_DATA_VOLUME}:/data" \
        -v "${NEO4J_LOGS_VOLUME}:/logs" \
        "${NEO4J_IMAGE}" >/dev/null
    log_success "容器 ${NEO4J_CONTAINER} 创建完成"
}

create_vln_container() {
    if [ "${CREATE_VLN}" != "1" ]; then
        log_info "CREATE_VLN=${CREATE_VLN}，跳过 ${VLN_CONTAINER}"
        return 0
    fi

    require_image "${VLN_IMAGE}"
    remove_container_if_requested "${VLN_CONTAINER}" || return 0
    log_info "创建容器 ${VLN_CONTAINER}"
    local runtime_args=()
    mapfile -t runtime_args < <(nvidia_runtime_args)
    docker create \
        --name "${VLN_CONTAINER}" \
        --network host \
        "${runtime_args[@]}" \
        -v "${PROJECT_DIR}:/data" \
        "${VLN_IMAGE}" \
        tail -f /dev/null >/dev/null
    log_success "容器 ${VLN_CONTAINER} 创建完成"
}

start_container_if_requested() {
    local container="$1"
    if [ "${START_AFTER_CREATE}" != "1" ]; then
        return 0
    fi
    if container_running "${container}"; then
        log_success "容器 ${container} 已运行"
        return 0
    fi
    if container_exists "${container}"; then
        log_info "启动容器 ${container}"
        docker start "${container}" >/dev/null
    fi
}

print_next_steps() {
    echo ""
    log_info "后续步骤"
    echo "  1. 确认代码和模型已迁移到：${PROJECT_DIR}"
    echo "  2. 如需迁移 Neo4j 旧数据，请把旧数据导入卷：${NEO4J_DATA_VOLUME}"
    echo "  3. 启动服务：bash ${PROJECT_DIR}/rabbitbot-dev-ros2-master/scripts_1/start_all_services.sh"
    echo "  4. 非联调启动：bash ${PROJECT_DIR}/rabbitbot-dev-ros2-master/scripts_1/start_non_integration_workflow.sh"
}

main() {
    echo "========================================"
    echo "  夸父机器人 - 创建迁移所需 Docker 容器"
    echo "========================================"
    echo ""

    require_command docker
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker 不可用，请先确认 Docker daemon 已启动且当前用户有 Docker 权限。"
        exit 1
    fi

    require_dir "${PROJECT_DIR}"
    require_dir "${MODELS_DIR}"
    require_image "${VLM_IMAGE}"
    require_image "${AUDIO_IMAGE}"
    require_image "${WORKFLOW_IMAGE}"
    require_image "${NEO4J_IMAGE}"

    create_vlm_container
    create_audio_container
    create_workflow_container
    create_neo4j_container
    create_vln_container

    start_container_if_requested "${VLM_CONTAINER}"
    start_container_if_requested "${AUDIO_CONTAINER}"
    start_container_if_requested "${WORKFLOW_CONTAINER}"
    start_container_if_requested "${NEO4J_CONTAINER}"
    if [ "${CREATE_VLN}" = "1" ]; then
        start_container_if_requested "${VLN_CONTAINER}"
    fi

    print_next_steps
    log_success "容器创建脚本执行完成"
}

main "$@"
