#!/bin/bash
#
# STT 启动后，持续监听并打印语音输入。
#
# 前提：
#   1. STT 服务已经启动，并监听在 28184 端口。
#   2. STT 服务已经识别到输入设备，例如 Wireless Mic。
#
# 用法：
#   bash scripts_1/listen_stt_and_print.sh
#
# 可选环境变量：
#   STT_BASE_URL=http://127.0.0.1:28184   STT 服务地址
#   STT_LANG=zh                           识别语言
#   STT_TIMEOUT=30                        单轮识别超时时间
#   POLL_INTERVAL=0.5                     轮询间隔秒数
#   STT_PROMPT=""                         传给 start_async 的提示词，建议只用普通中文/英文文本

set -e

STT_BASE_URL="${STT_BASE_URL:-http://127.0.0.1:28184}"
STT_LANG="${STT_LANG:-zh}"
STT_TIMEOUT="${STT_TIMEOUT:-30}"
POLL_INTERVAL="${POLL_INTERVAL:-0.5}"
STT_PROMPT="${STT_PROMPT:-}"

STT_BASE_URL="${STT_BASE_URL%/}"
STOPPING=0

json_escape() {
    # 只做 curl 请求中最常见的 JSON 字符转义；提示词请避免复杂引号。
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

extract_json_field() {
    local field="$1"
    sed -n "s/.*\"${field}\":\"\\([^\"]*\\)\".*/\\1/p"
}

post_task() {
    local task="$1"
    local text="${2:-}"
    local escaped_text
    local payload
    local response

    escaped_text="$(json_escape "${text}")"
    payload="{\"task\":\"${task}\",\"lang\":\"${STT_LANG}\",\"text\":\"${escaped_text}\",\"timeout\":${STT_TIMEOUT}}"

    response="$(
        curl -s --max-time "$((STT_TIMEOUT + 5))" \
            -X POST "${STT_BASE_URL}/exec" \
            -F "task=${payload}"
    )"

    if printf '%s' "${response}" | grep -q '"error"'; then
        echo "STT 接口返回错误：${response}" >&2
        return 1
    fi

    printf '%s' "${response}" | extract_json_field "out_text"
}

stop_recording() {
    if [ "${STOPPING}" = "1" ]; then
        exit 0
    fi
    STOPPING=1
    echo ""
    echo "正在停止 STT 异步监听..."
    post_task "stop_async" >/dev/null 2>&1 || true
    exit 0
}

trap stop_recording INT TERM

echo "STT 持续监听已启动：${STT_BASE_URL}"
echo "请对麦克风说话；识别到文本后会打印，并自动进入下一轮监听。"
echo "按 Ctrl+C 退出。"
echo ""

# 先清理可能残留的异步录音状态，再开始第一轮。
post_task "stop_async" >/dev/null 2>&1 || true
post_task "start_async" "${STT_PROMPT}" >/dev/null

while true; do
    text="$(post_task "get_text_async")"
    if [ -n "${text}" ]; then
        echo "[$(date '+%H:%M:%S')] 识别文字：${text}"
        post_task "start_async" "${STT_PROMPT}" >/dev/null
        continue
    fi

    status="$(post_task "get_status_async")"
    if [ "${status}" != "<REC_START>" ]; then
        # 如果一轮录音无结果就结束，自动重新开始，保持持续监听。
        post_task "start_async" "${STT_PROMPT}" >/dev/null
    fi

    sleep "${POLL_INTERVAL}"
done
