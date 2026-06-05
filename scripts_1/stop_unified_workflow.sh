#!/usr/bin/env bash
#
# =============================================================================
# 夸父机器人 - 停止统一容器 workflow
# =============================================================================
#
# 说明：
#   1. 停止普通统一容器和统一非联调容器内的 workflow 及后台服务。
#   2. 同时停止宿主机上的导航节点、手臂动作服务和 28180 bridge。
#   3. 默认只停止容器，不删除容器，保留 vLLM 编译缓存。
#   4. 如需删除统一容器，设置 REMOVE_UNIFIED_CONTAINERS=1。
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
HOST_NAV_EXAMPLE_DIR="${HOST_NAV_EXAMPLE_DIR:-/mnt/ssd/navgation/projects/unitree_slam_example_new/example}"
HOST_NAV_RUN_LOG_DIR="${HOST_NAV_RUN_LOG_DIR:-${HOST_NAV_EXAMPLE_DIR}/run_logs}"
HOST_NAV_CLEANUP_WAIT_SECONDS="${HOST_NAV_CLEANUP_WAIT_SECONDS:-2}"

log_info() {
    echo "[INFO] $1"
}

log_warn() {
    echo "[WARN] $1" >&2
}

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
        log_info "容器 ${container} 未运行，跳过进程清理。"
    fi
}

stop_container_if_exists() {
    local container="$1"
    if ! container_exists "${container}"; then
        log_info "容器 ${container} 不存在，跳过。"
        return 0
    fi

    if container_running "${container}"; then
        docker stop "${container}" >/dev/null || true
        log_info "已停止容器 ${container}"
    else
        log_info "容器 ${container} 已经停止。"
    fi

    if [ "${REMOVE_UNIFIED_CONTAINERS}" = "1" ]; then
        docker rm "${container}" >/dev/null || true
        log_info "已删除容器 ${container}"
    fi
}


process_alive() {
    local pid="$1"
    [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null
}

process_cmdline() {
    local pid="$1"
    ps -p "${pid}" -o args= 2>/dev/null || true
}

terminate_pid() {
    local pid="$1"
    local label="$2"
    local cmdline=""
    if ! process_alive "${pid}"; then
        return 0
    fi
    cmdline="$(process_cmdline "${pid}")"
    log_info "停止宿主机进程：label=${label}, pid=${pid}, cmd=${cmdline}"
    kill -TERM "${pid}" 2>/dev/null || true
    local waited=0
    while process_alive "${pid}" && [ "${waited}" -lt "${HOST_NAV_CLEANUP_WAIT_SECONDS}" ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if process_alive "${pid}"; then
        log_warn "进程未在 ${HOST_NAV_CLEANUP_WAIT_SECONDS}s 内退出，强制停止：label=${label}, pid=${pid}"
        kill -KILL "${pid}" 2>/dev/null || true
    fi
}

terminate_process_group_from_pid() {
    local pid="$1"
    local label="$2"
    local pgid=""
    if ! process_alive "${pid}"; then
        return 0
    fi
    pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
    if [ -z "${pgid}" ]; then
        terminate_pid "${pid}" "${label}"
        return 0
    fi
    log_info "停止宿主机进程组：label=${label}, pid=${pid}, pgid=${pgid}"
    kill -TERM -- "-${pgid}" 2>/dev/null || true
    sleep "${HOST_NAV_CLEANUP_WAIT_SECONDS}"
    if process_alive "${pid}"; then
        log_warn "进程组未正常退出，强制停止：label=${label}, pid=${pid}, pgid=${pgid}"
        kill -KILL -- "-${pgid}" 2>/dev/null || true
    fi
}

terminate_pattern_processes() {
    local label="$1"
    local pattern="$2"
    local pids=""
    pids="$(pgrep -f "${pattern}" 2>/dev/null || true)"
    if [ -z "${pids}" ]; then
        log_info "未发现宿主机进程：label=${label}"
        return 0
    fi
    local pid=""
    for pid in ${pids}; do
        if [ "${pid}" = "$$" ]; then
            continue
        fi
        terminate_pid "${pid}" "${label}"
    done
}

terminate_pid_file_if_matches() {
    local pid_file="$1"
    local label="$2"
    local expected_regex="$3"
    local pid=""
    local cmdline=""
    if [ ! -s "${pid_file}" ]; then
        return 0
    fi
    pid="$(cat "${pid_file}" 2>/dev/null | head -n 1 | tr -cd '0-9' || true)"
    if [ -z "${pid}" ] || ! process_alive "${pid}"; then
        return 0
    fi
    cmdline="$(process_cmdline "${pid}")"
    if printf '%s
' "${cmdline}" | grep -Eq "${expected_regex}"; then
        terminate_pid "${pid}" "${label}"
    else
        log_warn "跳过可能已复用的 pid 文件：file=${pid_file}, pid=${pid}, cmd=${cmdline}"
    fi
}

cleanup_host_nav_arm_bridge() {
    log_info "清理宿主机导航、手臂动作服务和 28180 bridge"

    # 先停止上层启动脚本，让它们自己的 trap 优先清理子进程。
    local loop_pids=""
    loop_pids="$(pgrep -f '[s]cripts_1/start_nav_bridge_workflow_loop.sh' 2>/dev/null || true)"
    if [ -n "${loop_pids}" ]; then
        local pid=""
        for pid in ${loop_pids}; do
            [ "${pid}" = "$$" ] && continue
            terminate_process_group_from_pid "${pid}" "start_nav_bridge_workflow_loop.sh"
        done
    else
        log_info "未发现 start_nav_bridge_workflow_loop.sh 进程"
    fi

    terminate_pattern_processes "start_nav_arm_bridge.sh" '[s]tart_nav_arm_bridge.sh'

    # 再按明确进程名兜底，覆盖终端断开、父脚本已退出或旧进程残留的情况。
    terminate_pattern_processes "28180 bridge" '[u]vicorn humble_robot_agent_bridge:app'
    terminate_pattern_processes "28180 bridge" '[p]ython3 -m uvicorn humble_robot_agent_bridge:app'
    terminate_pattern_processes "导航节点 goGoalNavigation66" '[g]oGoalNavigation66'
    terminate_pattern_processes "手臂动作服务 g1ArmOfficialActionServer" '[g]1ArmOfficialActionServer'
    terminate_pattern_processes "导航日志 tail" '[t]ail -n \+1 -F .*/01_goGoalNavigation66\.log'

    # 最后按启动脚本记录的 pid 文件补充清理，同时校验命令行，避免误杀复用 PID。
    if [ -d "${HOST_NAV_RUN_LOG_DIR}" ]; then
        while IFS= read -r pid_file; do
            case "${pid_file}" in
                *01_goGoalNavigation66.pid)
                    terminate_pid_file_if_matches "${pid_file}" "pid文件导航节点" 'goGoalNavigation66'
                    ;;
                *01_goGoalNavigation66_tail.pid)
                    terminate_pid_file_if_matches "${pid_file}" "pid文件导航日志 tail" 'tail .*01_goGoalNavigation66\.log'
                    ;;
                *02_g1ArmOfficialActionServer.pid|*01_g1ArmOfficialActionServer.pid)
                    terminate_pid_file_if_matches "${pid_file}" "pid文件手臂动作服务" 'g1ArmOfficialActionServer'
                    ;;
                *03_humble_robot_agent_bridge.pid|*02_humble_robot_agent_bridge.pid)
                    terminate_pid_file_if_matches "${pid_file}" "pid文件 28180 bridge" 'humble_robot_agent_bridge:app'
                    ;;
            esac
        done < <(find "${HOST_NAV_RUN_LOG_DIR}" -maxdepth 2 -type f -name '*.pid' 2>/dev/null | sort)
    else
        log_info "宿主机导航日志目录不存在，跳过 pid 文件清理：${HOST_NAV_RUN_LOG_DIR}"
    fi

    if ss -ltnp 2>/dev/null | grep -q ':28180'; then
        log_warn "28180 端口仍被占用："
        ss -ltnp 2>/dev/null | grep ':28180' >&2 || true
    else
        log_info "28180 端口已释放。"
    fi
}

cleanup_host_nav_arm_bridge

for container in "${UNIFIED_CONTAINERS[@]}"; do
    log_info "清理统一容器服务进程：${container}"
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

log_info "统一容器 workflow 停止流程完成。"
