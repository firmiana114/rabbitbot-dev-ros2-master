#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RABBITBOT_PROJECT_ROOT="${RABBITBOT_PROJECT_ROOT:-${PROJECT_DIR}}"
export RABBITBOT_CONSOLE_HOST="${RABBITBOT_CONSOLE_HOST:-0.0.0.0}"
export RABBITBOT_CONSOLE_PORT="${RABBITBOT_CONSOLE_PORT:-8080}"
export NAV_PCD_PATH="${NAV_PCD_PATH:-/home/unitree/test9.pcd}"

cd "${PROJECT_DIR}"
exec python3 -m rabbitbot.control_console
