#!/bin/bash
#
# 查看 STT 语音识别服务日志。
# 默认日志位置来自 scripts/start_all_services.sh:
#   容器 navid-vllm-cuda-mic-audio:/tmp/rabbitbot_stt.log

set -e

# 音频服务所在容器名；如后续容器名变化，可通过环境变量覆盖：
#   AUDIO_CONTAINER=your-container bash scripts_1/view_stt_log.sh
AUDIO_CONTAINER="${AUDIO_CONTAINER:-navid-vllm-cuda-mic-audio}"
LOG_FILE="${STT_LOG_FILE:-/tmp/rabbitbot_stt.log}"

echo "正在查看 STT 日志：${AUDIO_CONTAINER}:${LOG_FILE}"
echo "按 Ctrl+C 退出日志跟踪。"
echo ""

docker exec -it "${AUDIO_CONTAINER}" bash -lc "tail -n 200 -f '${LOG_FILE}'"
