#!/usr/bin/env bash
# 启动导航桥接并用外部命令控制 DOCX workflow 循环。
#
# 主终端运行本脚本后，会先拉起导航桥接，持续显示导航输出；其它终端通过：
#   bash scripts_1/send_nav_workflow_command.sh go
#   bash scripts_1/send_nav_workflow_command.sh back
# 控制 workflow 开始和剧本结束后的返航。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NAV_EXAMPLE_DIR="${NAV_EXAMPLE_DIR:-/mnt/ssd/navgation/projects/unitree_slam_example_new/example}"
NAV_BRIDGE_SCRIPT="${NAV_BRIDGE_SCRIPT:-${NAV_EXAMPLE_DIR}/start_nav_arm_bridge.sh}"
NAV_INTERFACE="${NAV_INTERFACE:-eno1}"
NAV_PCD_PATH="${NAV_PCD_PATH:-/home/unitree/test.pcd}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
WS_SETUP="${WS_SETUP:-/mnt/ssd/navgation/projects/custom_action_ws/install/setup.bash}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-/workspace/projects/rabbitbot-dev-ros2-master}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-${CONTAINER_RABBITBOT_DIR}/logs/unified_runtime}"
HOST_LOG_DIR="${HOST_LOG_DIR:-${PROJECT_DIR}/logs}"
CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTROL_DIR:-/tmp/rabbitbot_nav_workflow_control}"
COMMAND_FILE="${RABBITBOT_NAV_WORKFLOW_COMMAND_FILE:-${CONTROL_DIR}/command}"
RUN_DIR="${HOST_LOG_DIR}/nav_workflow_control"
START_POINT_TASK="${RABBITBOT_NAV_WORKFLOW_START_POINT:-(0.6906, 0.8284, 0.0262, -0.0289, 0.0174, 0.7443, -0.6669)}"
BACK_TIMEOUT_SECONDS="${RABBITBOT_NAV_WORKFLOW_BACK_TIMEOUT_SECONDS:-240}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"
RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}"
RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}"
RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-0}"

nav_group_pid=""
workflow_tail_pid=""

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

require_path() {
    if [ ! -e "$1" ]; then
        log_error "缺少必要路径：$1"
        exit 1
    fi
}

port_open() {
    local port="$1"
    timeout 2 bash -lc "</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
}

wait_port() {
    local port="$1"
    local seconds="$2"
    local count=0
    echo -n "等待端口 ${port} 就绪"
    until port_open "${port}"; do
        sleep 1
        count=$((count + 1))
        echo -n "."
        if [ "${count}" -ge "${seconds}" ]; then
            echo ""
            log_error "端口 ${port} 等待超时 (${seconds} 秒)"
            return 1
        fi
    done
    echo ""
    log_info "端口 ${port} 已就绪"
}

json_field() {
    local field="$1"
    python3 -c 'import json, sys
field = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
else:
    print(data.get(field, ""))
' "${field}"
}

workflow_running() {
    docker exec "${CONTAINER_NAME}" bash -lc 'pgrep -f "[e]xamples/run_kuavo_agno.py" >/dev/null || pgrep -f "[s]cripts/start_kuavo_agno_workflow.bash" >/dev/null' >/dev/null 2>&1
}

cleanup() {
    local reason="${1:-EXIT}"
    trap - INT TERM EXIT
    if [ -n "${workflow_tail_pid}" ] && kill -0 "${workflow_tail_pid}" 2>/dev/null; then
        kill "${workflow_tail_pid}" 2>/dev/null || true
    fi
    if [ -n "${nav_group_pid}" ] && kill -0 -- "-${nav_group_pid}" 2>/dev/null; then
        log_info "收到 ${reason}，正在停止导航桥接进程组：pgid=${nav_group_pid}"
        kill -TERM -- "-${nav_group_pid}" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-${nav_group_pid}" 2>/dev/null || true
    fi
}

trap 'cleanup INT; exit 130' INT
trap 'cleanup TERM; exit 143' TERM
trap 'cleanup EXIT' EXIT

prepare_runtime() {
    mkdir -p "${CONTROL_DIR}" "${RUN_DIR}" "${HOST_LOG_DIR}"
    require_path "${NAV_BRIDGE_SCRIPT}"
    require_path "${ROS_SETUP}"
    require_path "${WS_SETUP}"
    require_path "${PROJECT_DIR}/scripts_1/start_unified_integration_workflow.sh"
    rm -f "${COMMAND_FILE}"
    log_info "控制命令文件：${COMMAND_FILE}"
    log_info "其它终端发送 go：bash ${PROJECT_DIR}/scripts_1/send_nav_workflow_command.sh go"
    log_info "其它终端发送 back：bash ${PROJECT_DIR}/scripts_1/send_nav_workflow_command.sh back"
}

start_nav_bridge() {
    if port_open 28180; then
        log_error "28180 端口已被占用，无法由本脚本统一拉起导航桥接。请先停止旧导航桥接或占用进程。"
        return 1
    fi

    local nav_log="${RUN_DIR}/nav_bridge_$(date +%Y%m%d_%H%M%S).log"
    log_info "启动导航桥接：${NAV_BRIDGE_SCRIPT} ${NAV_INTERFACE} ${NAV_PCD_PATH}"
    log_info "导航桥接日志：${nav_log}"
    setsid bash -lc 'source "$1" && source "$2" && "$3" "$4" "$5" 2>&1 | tee -a "$6"' bash "${ROS_SETUP}" "${WS_SETUP}" "${NAV_BRIDGE_SCRIPT}" "${NAV_INTERFACE}" "${NAV_PCD_PATH}" "${nav_log}" &
    nav_group_pid=$!
    log_info "导航桥接进程组已启动：pgid=${nav_group_pid}"
    wait_port 28180 60
}

ensure_unified_services() {
    log_info "确认 unified 基础服务就绪；本步骤不会启动 workflow"
    (
        cd "${PROJECT_DIR}"
        RUN_WORKFLOW_AFTER_START=0 \
        RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN}" \
        WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS}" \
        WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS}" \
        bash scripts_1/start_unified_integration_workflow.sh
    )
}

wait_command() {
    local expected="$1"
    local label="$2"
    log_info "等待命令：${label}"
    while true; do
        if [ -s "${COMMAND_FILE}" ]; then
            local command
            command="$(head -n 1 "${COMMAND_FILE}" | tr -d '\r' | xargs || true)"
            rm -f "${COMMAND_FILE}"
            case "${command}" in
                "${expected}")
                    log_info "收到命令：${command}"
                    return 0
                    ;;
                quit|exit)
                    log_info "收到退出命令：${command}"
                    exit 0
                    ;;
                "")
                    ;;
                *)
                    log_warn "当前阶段需要 ${expected}，忽略命令：${command}"
                    ;;
            esac
        fi
        sleep 1
    done
}

start_workflow_detached() {
    if workflow_running; then
        log_error "检测到已有 workflow 正在运行，拒绝重复启动。"
        return 1
    fi

    local run_id="$(date +%Y%m%d_%H%M%S)"
    local control_dir="${CONTAINER_LOG_DIR}/workflow_control"
    local workflow_log="${CONTAINER_LOG_DIR}/rabbitbot_workflow_${run_id}.log"
    docker exec "${CONTAINER_NAME}" bash -lc "mkdir -p '${control_dir}' && rm -f '${control_dir}/${run_id}.status' '${control_dir}/${run_id}.exit_code' '${control_dir}/${run_id}.pid'" >/dev/null

    log_info "后台启动 workflow：run_id=${run_id}"
    docker exec -d \
        -e RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
        -e RABBITBOT_LOG_DIR="${CONTAINER_LOG_DIR}" \
        -e RABBITBOT_WORKFLOW_RUN_ID="${run_id}" \
        -e PYTHONUNBUFFERED=1 \
        "${CONTAINER_NAME}" bash -lc '
set -euo pipefail
cd "${RABBITBOT_DIR}"
log_dir="${RABBITBOT_LOG_DIR:-${RABBITBOT_DIR}/logs/unified_runtime}"
control_dir="${log_dir}/workflow_control"
run_id="${RABBITBOT_WORKFLOW_RUN_ID}"
mkdir -p "${log_dir}" "${control_dir}"
log_path="${log_dir}/rabbitbot_workflow_${run_id}.log"
ln -sf "${log_path}" "${log_dir}/rabbitbot_workflow_latest.log"
runner="${control_dir}/workflow_runner_${run_id}.sh"
cat >"${runner}" <<RUNNER
#!/usr/bin/env bash
set +e
cd "${RABBITBOT_DIR}"
echo running >"${control_dir}/${run_id}.status"
echo "Workflow容器日志: ${log_path}" >>"${log_path}"
PYTHONUNBUFFERED=1 bash scripts/start_kuavo_agno_workflow.bash >>"${log_path}" 2>&1
status=\$?
echo "\${status}" >"${control_dir}/${run_id}.exit_code"
date "+%Y-%m-%d %H:%M:%S" >"${control_dir}/${run_id}.finished_at"
echo finished >"${control_dir}/${run_id}.status"
exit "\${status}"
RUNNER
chmod +x "${runner}"
nohup "${runner}" >/dev/null 2>&1 &
echo "$!" >"${control_dir}/${run_id}.pid"
'

    log_info "workflow 日志：${workflow_log}"
    docker exec "${CONTAINER_NAME}" bash -lc "tail -n +1 -F '${workflow_log}'" &
    workflow_tail_pid=$!

    while true; do
        local status=""
        status="$(docker exec "${CONTAINER_NAME}" bash -lc "cat '${control_dir}/${run_id}.status' 2>/dev/null || true" 2>/dev/null || true)"
        if [ "${status}" = "finished" ]; then
            break
        fi
        if [ "${status}" = "running" ] && ! workflow_running; then
            log_warn "workflow 进程已不在，但状态文件尚未标记完成，继续等待状态落盘"
        fi
        sleep 2
    done

    if [ -n "${workflow_tail_pid}" ] && kill -0 "${workflow_tail_pid}" 2>/dev/null; then
        kill "${workflow_tail_pid}" 2>/dev/null || true
        workflow_tail_pid=""
    fi

    local exit_code="unknown"
    exit_code="$(docker exec "${CONTAINER_NAME}" bash -lc "cat '${control_dir}/${run_id}.exit_code' 2>/dev/null || true" 2>/dev/null || true)"
    if [ -z "${exit_code}" ]; then
        exit_code="unknown"
    fi
    log_info "workflow 已结束：run_id=${run_id}, exit_code=${exit_code}"
}

return_to_start() {
    log_info "收到 back 后返回起点：${START_POINT_TASK}"
    local reset_response
    reset_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' 2>&1 || true)"
    log_info "重置导航状态返回：${reset_response}"

    local response
    response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_async --form-string "task=${START_POINT_TASK}" 2>&1 || true)"
    log_info "返航命令返回：${response}"
    local success
    success="$(printf '%s' "${response}" | json_field success || true)"
    if [ "${success}" != "True" ] && [ "${success}" != "true" ]; then
        log_error "返航命令未成功发送，请检查 28180 bridge 和导航状态。"
        return 1
    fi

    local waited=0
    local last_status=""
    while [ "${waited}" -lt "${BACK_TIMEOUT_SECONDS}" ]; do
        local status_response status sub
        status_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_status --form-string 'task=' 2>&1 || true)"
        status="$(printf '%s' "${status_response}" | json_field status || true)"
        sub="$(printf '%s' "${status_response}" | json_field sub || true)"
        if [ "${status}:${sub}" != "${last_status}" ]; then
            log_info "返航导航状态：status=${status:-未知}, sub=${sub:-空}, waited=${waited}s"
            last_status="${status}:${sub}"
        fi
        case "${status}" in
            3)
                log_info "已返回起点"
                curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' >/dev/null 2>&1 || true
                return 0
                ;;
            2|4)
                log_error "返航导航失败或被抢占：status=${status}, response=${status_response}"
                return 1
                ;;
        esac
        sleep 1
        waited=$((waited + 1))
    done
    log_error "返航等待超时：timeout=${BACK_TIMEOUT_SECONDS}s"
    return 1
}

main() {
    prepare_runtime
    start_nav_bridge
    ensure_unified_services

    log_info "导航桥接与基础服务已就绪。命令循环开始。"
    while true; do
        wait_command go "go 启动 workflow"
        start_workflow_detached
        wait_command back "back 返回起点"
        return_to_start
        log_info "返航流程结束，继续等待下一次 go。"
    done
}

main "$@"
