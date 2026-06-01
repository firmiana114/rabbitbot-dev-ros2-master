#!/bin/bash
# 启动 SenseVoice STT 服务的脚本

# 设置环境变量
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
source "${SCRIPT_DIR}/path_env.sh"

if [ -f /opt/venv/bin/activate ]; then
    source /opt/venv/bin/activate
elif [ -f "${PROJECT_DIR}/py310/bin/activate" ]; then
    source "${PROJECT_DIR}/py310/bin/activate"
else
    echo "未找到 Python 虚拟环境，将使用系统 python"
fi

export STT_DEVICE=${STT_DEVICE:-cuda}
export STT_COMPUTE_TYPE=${STT_COMPUTE_TYPE:-float16}
export STT_PORT=${STT_PORT:-28184}
export STT_MODEL_PATH=${STT_MODEL_PATH:-${RABBITBOT_MODELS_DIR}/SenseVoiceSmall}
export VAD_MODEL_PATH=${VAD_MODEL_PATH:-${RABBITBOT_MODELS_DIR}/fsmn_vad}
export STT_SILENCE_SEC=${STT_SILENCE_SEC:-0.50}
export STT_VAD_WINDOW_SEC=${STT_VAD_WINDOW_SEC:-0.45}
export STT_VAD_KEEP_SEC=${STT_VAD_KEEP_SEC:-0.12}
export STT_VAD_SPEECH_THRES=${STT_VAD_SPEECH_THRES:-0.12}
export STT_VAD_START_HITS=${STT_VAD_START_HITS:-1}
export STT_MIN_RMS=${STT_MIN_RMS:-0.022}
export STT_MIN_UTTERANCE_SEC=${STT_MIN_UTTERANCE_SEC:-0.35}
export STT_INPUT_BLOCK_SEC=${STT_INPUT_BLOCK_SEC:-0.1}
export STT_INPUT_LATENCY=${STT_INPUT_LATENCY:-high}
export STT_AUDIO_QUEUE_MAX_CHUNKS=${STT_AUDIO_QUEUE_MAX_CHUNKS:-160}
export STT_INPUT_GAIN=${STT_INPUT_GAIN:-1.0}
export STT_INPUT_VOLUME_PERCENT=${STT_INPUT_VOLUME_PERCENT:-80}

# STT_DEVICE_NAME 只在明确指定时作为最高优先级；默认自动选择外接麦克风。
DEVICE_NAME="${STT_DEVICE_NAME:-}"

# 查找输入设备。必须在激活虚拟环境后执行，否则默认 python 可能没有 sounddevice。
echo "查找输入设备，指定名称: ${DEVICE_NAME:-未指定}"
DEVICE_INFO=$(python - <<'PYDEV'
import os
import sys

preferred_name = os.environ.get("STT_DEVICE_NAME", "").strip().lower()
builtin_keywords = (
    "orin",
    "jetson",
    "tegra",
    "nvidia",
    "hda",
    "ape",
    "admaif",
    "tegrasnd",
)

def is_builtin_audio(name):
    normalized = name.lower()
    return any(keyword in normalized for keyword in builtin_keywords)

try:
    import sounddevice as sd
except Exception as exc:
    print(f"sounddevice 不可用，无法按名称查找输入设备: {exc}", file=sys.stderr)
    sys.exit(0)

preferred = None
mic_external = None
external = None
builtin = None
mic_keywords = ("mic", "microphone", "dji", "wireless", "rx")
output_like_keywords = ("bt67", "speaker", "monitor", "output")

for idx, dev in enumerate(sd.query_devices()):
    input_channels = int(dev.get("max_input_channels", 0))
    if input_channels <= 0:
        continue

    name = dev.get("name", "")
    normalized_name = name.lower()
    device_info = f"{idx}|{name}|{input_channels}"
    print(
        f"输入设备候选: index={idx}, name={name}, channels={input_channels}",
        file=sys.stderr,
    )
    if preferred_name and preferred_name in normalized_name and preferred is None:
        preferred = device_info
    elif not is_builtin_audio(name):
        if any(keyword in normalized_name for keyword in mic_keywords) and mic_external is None:
            mic_external = device_info
        elif not any(keyword in normalized_name for keyword in output_like_keywords) and external is None:
            external = device_info
    elif builtin is None:
        builtin = device_info

selected = preferred or mic_external or external or builtin
if selected is not None:
    print(selected)
PYDEV
)

if [ -n "${DEVICE_INFO}" ]; then
    DEVICE_INDEX=$(echo "${DEVICE_INFO}" | cut -d'|' -f1)
    DEVICE_FOUND_NAME=$(echo "${DEVICE_INFO}" | cut -d'|' -f2)
    export INPUT_DEVICE_INDEX="${DEVICE_INDEX}"
    echo "使用输入音频设备 ${DEVICE_FOUND_NAME}，index=${INPUT_DEVICE_INDEX}"
    DEVICE_CARD=$(echo "${DEVICE_FOUND_NAME}" | sed -n 's/.*(hw:\([0-9][0-9]*\),[0-9][0-9]*).*/\1/p')
    if [ -n "${DEVICE_CARD}" ] && command -v amixer >/dev/null 2>&1; then
        if amixer -c "${DEVICE_CARD}" sset Mic "${STT_INPUT_VOLUME_PERCENT}%" >/dev/null 2>&1; then
            echo "设置输入麦克风音量: card=${DEVICE_CARD}, volume=${STT_INPUT_VOLUME_PERCENT}%"
        else
            echo "设置输入麦克风音量失败，将继续使用当前系统音量: card=${DEVICE_CARD}, volume=${STT_INPUT_VOLUME_PERCENT}%"
        fi
    else
        echo "未能解析输入声卡 card 或 amixer 不可用，跳过麦克风音量设置"
    fi
elif [ -n "${INPUT_DEVICE_INDEX}" ]; then
    echo "未自动找到输入设备，使用已设置的 INPUT_DEVICE_INDEX=${INPUT_DEVICE_INDEX}"
else
    echo "未找到可用输入设备，将以无输入设备模式启动"
    unset INPUT_DEVICE_INDEX
fi

echo "STT 模型路径: ${STT_MODEL_PATH}"
echo "VAD 模型路径: ${VAD_MODEL_PATH}"
echo "STT 设备: ${STT_DEVICE}"
echo "STT 端口: ${STT_PORT}"
echo "STT 过滤参数: vad_thres=${STT_VAD_SPEECH_THRES}, min_rms=${STT_MIN_RMS}, silence=${STT_SILENCE_SEC}, min_utterance=${STT_MIN_UTTERANCE_SEC}, block_sec=${STT_INPUT_BLOCK_SEC}, latency=${STT_INPUT_LATENCY}, input_gain=${STT_INPUT_GAIN}"

# 启动服务
cd "${PROJECT_DIR}"
python stt_app_funasr.py
