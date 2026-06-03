#!/usr/bin/env bash
# 启动导航桥接并用外部命令控制 DOCX workflow 循环。
#
# 主终端运行本脚本后，会先拉起导航桥接，持续显示导航输出；其它终端通过：
#   bash scripts_1/send_nav_workflow_command.sh go
#   bash scripts_1/send_nav_workflow_command.sh back
# 控制 workflow 开始和剧本结束后的返航。
#
# 为降低 go 后开场延迟，本脚本会在等待 go 前预启动 workflow，让 Python 和 AppContext
# 初始化完成后停在启动闸门；收到 go 时只释放闸门。相关可调变量：
#   RABBITBOT_NAV_WORKFLOW_GATE_READY_TIMEOUT_SECONDS：等待 workflow 预启动就绪的超时秒数。
#   RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS：workflow 内部等待 go 闸门文件的轮询间隔。
#   RABBITBOT_NAV_WORKFLOW_STATUS_POLL_SECONDS：workflow 运行期间检查状态和预接收 back 的轮询间隔。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NAV_EXAMPLE_DIR="${NAV_EXAMPLE_DIR:-/mnt/ssd/navgation/projects/unitree_slam_example_new/example}"
NAV_BRIDGE_SCRIPT="${NAV_BRIDGE_SCRIPT:-${NAV_EXAMPLE_DIR}/start_nav_arm_bridge.sh}"
NAV_INTERFACE="${NAV_INTERFACE:-eno1}"
NAV_PCD_PATH="${NAV_PCD_PATH:-/home/unitree/test1.pcd}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
WS_SETUP="${WS_SETUP:-/mnt/ssd/navgation/projects/custom_action_ws/install/setup.bash}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-/workspace/projects/rabbitbot-dev-ros2-master}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-${CONTAINER_RABBITBOT_DIR}/logs/unified_runtime}"
HOST_LOG_DIR="${HOST_LOG_DIR:-${PROJECT_DIR}/logs}"
CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTROL_DIR:-/tmp/rabbitbot_nav_workflow_control}"
COMMAND_FILE="${RABBITBOT_NAV_WORKFLOW_COMMAND_FILE:-${CONTROL_DIR}/command}"
RUN_DIR="${HOST_LOG_DIR}/nav_workflow_control"
POINT_1_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_1:-(1.9105, -1.6180, -0.0029, 0.0265, -0.2046, 0.9785)}"
POINT_1_TO_2_TRANSITION_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_1_TO_2_TRANSITION:-(8.6465, -2.5763, 0.0547, 0.0907, 0.5347, 0.8384)}"
POINT_2_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_2:-(10.1203, 0.8162, 0.0904, 0.0373, 0.9074, 0.4087)}"
POINT_3_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_3:-(11.1090, 4.3229, 0.0937, 0.0170, 0.9717, 0.2162)}"
POINT_3_TO_5_TRANSITION_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_3_TO_5_TRANSITION:-(5.5507, 14.4097, 0.0779, 0.0578, 0.7806, 0.6174)}"
POINT_5_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_5:-(4.7039, 20.4749, 0.0876, -0.0269, 0.9076, -0.4096)}"
START_POINT_TASK="${RABBITBOT_NAV_WORKFLOW_START_POINT:-${POINT_1_TASK}}"
BACK_TIMEOUT_SECONDS="${RABBITBOT_NAV_WORKFLOW_BACK_TIMEOUT_SECONDS:-240}"
COMMAND_POLL_SECONDS="${RABBITBOT_NAV_WORKFLOW_COMMAND_POLL_SECONDS:-0.2}"
WORKFLOW_STATUS_POLL_SECONDS="${RABBITBOT_NAV_WORKFLOW_STATUS_POLL_SECONDS:-0.2}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"
RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}"
RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}"
RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-0}"
HOST_WORKFLOW_RUN_DIR="${RABBITBOT_NAV_WORKFLOW_HOST_RUN_DIR:-${RUN_DIR}}"
CONTAINER_WORKFLOW_RUN_DIR="${RABBITBOT_NAV_WORKFLOW_CONTAINER_RUN_DIR:-${CONTAINER_RABBITBOT_DIR}/logs/nav_workflow_control}"
HOST_WORKFLOW_CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_HOST_CONTROL_DIR:-${HOST_WORKFLOW_RUN_DIR}/workflow_control}"
CONTAINER_WORKFLOW_CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTAINER_CONTROL_DIR:-${CONTAINER_WORKFLOW_RUN_DIR}/workflow_control}"
WORKFLOW_GATE_READY_TIMEOUT_SECONDS="${RABBITBOT_NAV_WORKFLOW_GATE_READY_TIMEOUT_SECONDS:-30}"
WORKFLOW_GATE_POLL_SECONDS="${RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS:-0.05}"

nav_group_pid=""
workflow_tail_pid=""
queued_back_after_workflow=0
current_run_id=""
current_control_dir=""
current_host_control_dir=""
current_workflow_log=""
current_host_workflow_log=""
current_status_file=""
current_exit_code_file=""
current_pid_file=""
current_finished_at_file=""
current_gate_file=""
current_gate_ready_file=""
current_host_gate_file=""
current_host_gate_ready_file=""

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

now_ms() {
    date +%s%3N
}

elapsed_ms_since() {
    local start_ms="$1"
    echo $(( $(now_ms) - start_ms ))
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

normalize_go_to_task() {
    local task="$1"
    python3 - "${task}" <<'PY'
import ast
import sys

def convert_pose(value):
    if isinstance(value, tuple) and len(value) == 7:
        # 28180 直接 go_to_async 接口使用 (x, y, ox, oy, oz, ow)，不包含 z。
        return (value[0], value[1], value[3], value[4], value[5], value[6])
    return value

raw = sys.argv[1]
try:
    parsed = ast.literal_eval(raw)
except Exception:
    print(raw)
    raise SystemExit(0)

if isinstance(parsed, list):
    parsed = [convert_pose(item) for item in parsed]
else:
    parsed = convert_pose(parsed)
print(repr(parsed))
PY
}

workflow_running() {
    docker exec "${CONTAINER_NAME}" bash -lc 'pgrep -f "[e]xamples/run_kuavo_agno.py" >/dev/null || pgrep -f "[s]cripts/run_kuavo_agno_workflow.py" >/dev/null || pgrep -f "[s]cripts/start_kuavo_agno_workflow.bash" >/dev/null' >/dev/null 2>&1
}

current_workflow_process_active() {
    if [ -z "${current_pid_file}" ] || [ ! -s "${current_pid_file}" ]; then
        return 1
    fi
    local workflow_pid=""
    workflow_pid="$(cat "${current_pid_file}" 2>/dev/null || true)"
    if [ -z "${workflow_pid}" ]; then
        return 1
    fi
    docker exec "${CONTAINER_NAME}" bash -lc "kill -0 '${workflow_pid}' 2>/dev/null" >/dev/null 2>&1
}

stop_workflow_tail() {
    if [ -n "${workflow_tail_pid}" ] && kill -0 "${workflow_tail_pid}" 2>/dev/null; then
        kill "${workflow_tail_pid}" 2>/dev/null || true
        workflow_tail_pid=""
    fi
}

stop_current_workflow() {
    if [ -z "${current_run_id}" ] || [ -z "${current_pid_file}" ] || [ ! -s "${current_pid_file}" ]; then
        return 0
    fi
    local status=""
    status="$(cat "${current_status_file}" 2>/dev/null || true)"
    if [ "${status}" = "finished" ]; then
        return 0
    fi
    local workflow_pid=""
    workflow_pid="$(cat "${current_pid_file}" 2>/dev/null || true)"
    if [ -z "${workflow_pid}" ]; then
        return 0
    fi
    log_info "正在停止当前 workflow 进程组：run_id=${current_run_id}, pgid=${workflow_pid}"
    docker exec "${CONTAINER_NAME}" bash -lc "if kill -0 '${workflow_pid}' 2>/dev/null; then kill -TERM -- -'${workflow_pid}' 2>/dev/null || kill -TERM '${workflow_pid}' 2>/dev/null || true; sleep 2; kill -KILL -- -'${workflow_pid}' 2>/dev/null || kill -KILL '${workflow_pid}' 2>/dev/null || true; fi" >/dev/null 2>&1 || true
}

cleanup() {
    local reason="${1:-EXIT}"
    trap - INT TERM EXIT
    stop_workflow_tail
    stop_current_workflow
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
    mkdir -p "${CONTROL_DIR}" "${RUN_DIR}" "${HOST_LOG_DIR}" "${HOST_WORKFLOW_RUN_DIR}" "${HOST_WORKFLOW_CONTROL_DIR}"
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

read_pending_command() {
    if [ ! -s "${COMMAND_FILE}" ]; then
        return 1
    fi
    local command
    command="$(head -n 1 "${COMMAND_FILE}" | tr -d $'\r' | xargs || true)"
    rm -f "${COMMAND_FILE}"
    if [ -z "${command}" ]; then
        return 1
    fi
    printf '%s\n' "${command}"
}

handle_unexpected_command() {
    local command="$1"
    local expected="$2"
    case "${command}" in
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
}

wait_command() {
    local expected="$1"
    local label="$2"
    log_info "等待命令：${label}"
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        if [ -n "${command}" ]; then
            if [ "${command}" = "${expected}" ]; then
                log_info "收到命令：${command}"
                return 0
            fi
            handle_unexpected_command "${command}" "${expected}"
        fi
        sleep "${COMMAND_POLL_SECONDS}"
    done
}
launch_workflow_detached() {
    if workflow_running; then
        log_error "检测到已有 workflow 正在运行，拒绝重复启动。"
        return 1
    fi

    current_run_id="$(date +%Y%m%d_%H%M%S)"
    current_control_dir="${CONTAINER_WORKFLOW_CONTROL_DIR}"
    current_host_control_dir="${HOST_WORKFLOW_CONTROL_DIR}"
    current_workflow_log="${CONTAINER_WORKFLOW_RUN_DIR}/rabbitbot_workflow_${current_run_id}.log"
    current_host_workflow_log="${HOST_WORKFLOW_RUN_DIR}/rabbitbot_workflow_${current_run_id}.log"
    current_status_file="${current_host_control_dir}/${current_run_id}.status"
    current_exit_code_file="${current_host_control_dir}/${current_run_id}.exit_code"
    current_pid_file="${current_host_control_dir}/${current_run_id}.pid"
    current_finished_at_file="${current_host_control_dir}/${current_run_id}.finished_at"
    current_gate_file="${current_control_dir}/${current_run_id}.go"
    current_gate_ready_file="${current_control_dir}/${current_run_id}.ready"
    current_host_gate_file="${current_host_control_dir}/${current_run_id}.go"
    current_host_gate_ready_file="${current_host_control_dir}/${current_run_id}.ready"

    mkdir -p "${current_host_control_dir}" "$(dirname "${current_host_workflow_log}")"
    rm -f "${current_status_file}" "${current_exit_code_file}" "${current_pid_file}" "${current_finished_at_file}" "${current_host_gate_file}" "${current_host_gate_ready_file}"
    if ! : >"${current_host_workflow_log}"; then
        log_error "无法创建 workflow 宿主日志：${current_host_workflow_log}，请检查目录权限"
        return 1
    fi
    docker exec "${CONTAINER_NAME}" bash -lc "mkdir -p '${current_control_dir}' '$(dirname "${current_workflow_log}")' && rm -f '${current_control_dir}/${current_run_id}.status' '${current_control_dir}/${current_run_id}.exit_code' '${current_control_dir}/${current_run_id}.pid' '${current_control_dir}/${current_run_id}.finished_at' '${current_gate_file}' '${current_gate_ready_file}'" >/dev/null

    local start_ms
    start_ms="$(now_ms)"
    log_info "预启动 workflow 并等待 go 闸门：run_id=${current_run_id}"
    docker exec -d \
        -e RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
        -e RABBITBOT_LOG_DIR="${CONTAINER_WORKFLOW_RUN_DIR}" \
        -e RABBITBOT_WORKFLOW_RUN_ID="${current_run_id}" \
        -e RABBITBOT_WORKFLOW_START_GATE_FILE="${current_gate_file}" \
        -e RABBITBOT_WORKFLOW_START_GATE_READY_FILE="${current_gate_ready_file}" \
        -e RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS="${WORKFLOW_GATE_POLL_SECONDS}" \
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
echo "Workflow启动闸门文件: ${RABBITBOT_WORKFLOW_START_GATE_FILE}" >>"${log_path}"
PYTHONUNBUFFERED=1 bash scripts/start_kuavo_agno_workflow.bash >>"${log_path}" 2>&1
status=\$?
echo "\${status}" >"${control_dir}/${run_id}.exit_code"
date "+%Y-%m-%d %H:%M:%S" >"${control_dir}/${run_id}.finished_at"
echo finished >"${control_dir}/${run_id}.status"
exit "\${status}"
RUNNER
chmod +x "${runner}"
setsid "${runner}" >/dev/null 2>&1 &
echo "$!" >"${control_dir}/${run_id}.pid"
'

    log_info "workflow 预启动命令已发送：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
    log_info "workflow 日志：${current_workflow_log}"
    tail -n +1 -F "${current_host_workflow_log}" &
    workflow_tail_pid=$!
}

wait_workflow_gate_ready() {
    local attempts=$(( WORKFLOW_GATE_READY_TIMEOUT_SECONDS * 10 ))
    local start_ms
    start_ms="$(now_ms)"
    log_info "等待 workflow 预启动完成：run_id=${current_run_id}, timeout=${WORKFLOW_GATE_READY_TIMEOUT_SECONDS}s"
    local i
    for ((i = 0; i < attempts; i++)); do
        local status=""
        status="$(cat "${current_status_file}" 2>/dev/null || true)"
        if [ "${status}" = "finished" ]; then
            local exit_code="unknown"
            exit_code="$(cat "${current_exit_code_file}" 2>/dev/null || true)"
            log_error "workflow 在等待 go 前已退出：run_id=${current_run_id}, exit_code=${exit_code:-unknown}"
            return 1
        fi
        if [ -s "${current_host_gate_ready_file}" ]; then
            if current_workflow_process_active; then
                log_info "workflow 已完成预启动并停在 go 闸门：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
                return 0
            fi
            log_warn "workflow ready 文件存在但进程不在，准备重新预启动：run_id=${current_run_id}"
            return 1
        fi
        sleep 0.1
    done
    log_error "workflow 预启动等待超时：run_id=${current_run_id}, timeout=${WORKFLOW_GATE_READY_TIMEOUT_SECONDS}s"
    return 1
}

wait_go_or_back() {
    WAITED_COMMAND=""
    log_info "等待命令：go 启动 workflow；此阶段收到 back 将直接返航"
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        case "${command}" in
            go|back)
                WAITED_COMMAND="${command}"
                log_info "收到命令：${command}"
                return 0
                ;;
            "")
                ;;
            *)
                handle_unexpected_command "${command}" "go 或 back"
                ;;
        esac
        if ! current_workflow_process_active; then
            log_warn "等待 go/back 时发现预启动 workflow 已退出，准备重新预启动：run_id=${current_run_id}"
            return 1
        fi
        sleep "${COMMAND_POLL_SECONDS}"
    done
}

release_workflow_gate() {
    local start_ms
    start_ms="$(now_ms)"
    printf 'go\n' >"${current_host_gate_file}"
    log_info "已释放 workflow go 闸门：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
}

monitor_workflow_until_finished() {
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        case "${command}" in
            back)
                queued_back_after_workflow=1
                log_info "已预接收 back 命令，workflow 结束后自动返航"
                ;;
            go)
                log_warn "workflow 正在运行，忽略重复 go 命令"
                ;;
            "")
                ;;
            *)
                handle_unexpected_command "${command}" "back"
                ;;
        esac

        local status=""
        status="$(cat "${current_status_file}" 2>/dev/null || true)"
        if [ "${status}" = "finished" ]; then
            break
        fi
        if [ "${status}" = "running" ] && ! workflow_running; then
            log_warn "workflow 进程已不在，但状态文件尚未标记完成，继续等待状态落盘"
        fi
        sleep "${WORKFLOW_STATUS_POLL_SECONDS}"
    done

    stop_workflow_tail

    local exit_code="unknown"
    exit_code="$(cat "${current_exit_code_file}" 2>/dev/null || true)"
    if [ -z "${exit_code}" ]; then
        exit_code="unknown"
    fi
    log_info "workflow 已结束：run_id=${current_run_id}, exit_code=${exit_code}"
}

navigate_back_segment() {
    local label="$1"
    local task="$2"
    local segment_index="$3"
    local segment_total="$4"

    local task_payload
    task_payload="$(normalize_go_to_task "${task}")"
    if [ "${task_payload}" != "${task}" ]; then
        log_warn "返航分段 ${segment_index}/${segment_total} 任务格式已兼容转换：label=${label}, original=${task}, payload=${task_payload}"
    fi
    log_info "返航分段 ${segment_index}/${segment_total} 开始：${label}，目标=${task_payload}"
    local reset_response
    reset_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' 2>&1 || true)"
    log_info "返航分段 ${segment_index}/${segment_total} 重置导航状态返回：${reset_response}"

    local response
    response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_async --form-string "task=${task_payload}" 2>&1 || true)"
    log_info "返航分段 ${segment_index}/${segment_total} 命令返回：${response}"
    local success
    success="$(printf '%s' "${response}" | json_field success || true)"
    if [ "${success}" != "True" ] && [ "${success}" != "true" ]; then
        log_error "返航分段 ${segment_index}/${segment_total} 命令未成功发送：label=${label}，请检查 28180 bridge 和导航状态。"
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
            log_info "返航分段 ${segment_index}/${segment_total} 状态：label=${label}, status=${status:-未知}, sub=${sub:-空}, waited=${waited}s"
            last_status="${status}:${sub}"
        fi
        case "${status}" in
            3)
                log_info "返航分段 ${segment_index}/${segment_total} 完成：${label}，耗时=${waited}s"
                curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' >/dev/null 2>&1 || true
                return 0
                ;;
            2|4)
                log_error "返航分段 ${segment_index}/${segment_total} 失败或被抢占：label=${label}, status=${status}, response=${status_response}"
                return 1
                ;;
        esac
        sleep 1
        waited=$((waited + 1))
    done
    log_error "返航分段 ${segment_index}/${segment_total} 等待超时：label=${label}, timeout=${BACK_TIMEOUT_SECONDS}s"
    return 1
}

return_to_start() {
    local labels=("点位5" "3->5过渡点位" "点位3" "点位2" "1->2过渡点位" "点位1")
    local tasks=("${POINT_5_TASK}" "${POINT_3_TO_5_TRANSITION_TASK}" "${POINT_3_TASK}" "${POINT_2_TASK}" "${POINT_1_TO_2_TRANSITION_TASK}" "${START_POINT_TASK}")
    local segment_total="${#labels[@]}"
    local start_epoch
    start_epoch="$(date +%s)"

    log_info "收到 back 后先前往点位5，再按逆序路径返航：点位5 -> 3->5过渡点位 -> 点位3 -> 点位2 -> 1->2过渡点位 -> 点位1"
    log_info "返航最终点位1目标：${START_POINT_TASK}"

    local i
    for i in "${!labels[@]}"; do
        local segment_index=$((i + 1))
        if ! navigate_back_segment "${labels[$i]}" "${tasks[$i]}" "${segment_index}" "${segment_total}"; then
            local elapsed=$(( $(date +%s) - start_epoch ))
            log_error "返航流程中止：失败分段=${labels[$i]}，已耗时=${elapsed}s"
            return 1
        fi
    done

    local elapsed=$(( $(date +%s) - start_epoch ))
    log_info "已按逆序路径返回点位1，总耗时=${elapsed}s"
}

main() {
    prepare_runtime
    start_nav_bridge
    ensure_unified_services

    log_info "导航桥接与基础服务已就绪。命令循环开始。"
    while true; do
        queued_back_after_workflow=0
        launch_workflow_detached
        if ! wait_workflow_gate_ready; then
            stop_workflow_tail
            stop_current_workflow
            log_warn "本轮 workflow 预启动不可用，重新预启动"
            continue
        fi
        if ! wait_go_or_back; then
            stop_workflow_tail
            stop_current_workflow
            log_warn "等待 go/back 阶段检测到预启动 workflow 异常，重新预启动"
            continue
        fi
        if [ "${WAITED_COMMAND}" = "back" ]; then
            log_info "等待 go 阶段收到 back，停止预启动 workflow 后直接返航"
            stop_workflow_tail
            stop_current_workflow
            return_to_start
            log_info "返航流程结束，继续预启动下一次 workflow。"
            continue
        fi
        release_workflow_gate
        monitor_workflow_until_finished
        if [ "${queued_back_after_workflow}" = "1" ]; then
            log_info "使用 workflow 运行期间预接收的 back 命令进入返航"
            queued_back_after_workflow=0
        else
            wait_command back "back 返回起点"
        fi
        return_to_start
        log_info "返航流程结束，继续预启动下一次 workflow。"
    done
}

main "$@"
