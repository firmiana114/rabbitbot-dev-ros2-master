#!/usr/bin/env bash
# 向导航 + workflow 编排脚本发送控制命令。
# 支持命令：go、back、quit。

set -euo pipefail

COMMAND="${1:-}"
CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTROL_DIR:-/tmp/rabbitbot_nav_workflow_control}"
COMMAND_FILE="${RABBITBOT_NAV_WORKFLOW_COMMAND_FILE:-${CONTROL_DIR}/command}"

case "${COMMAND}" in
    go|back|quit|exit)
        ;;
    *)
        echo "用法：$0 {go|back|quit}" >&2
        exit 2
        ;;
esac

mkdir -p "${CONTROL_DIR}"
tmp_file="${COMMAND_FILE}.$$"
printf '%s\n' "${COMMAND}" >"${tmp_file}"
mv "${tmp_file}" "${COMMAND_FILE}"
echo "已发送命令：${COMMAND} -> ${COMMAND_FILE}"
