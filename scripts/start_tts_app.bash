#!/bin/sh

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
#export HTTPS_PROXY=http://127.0.0.1:7897

#export TTS_CLOUD="http://10.10.30.22:28187"

source /opt/venv/bin/activate

# TTS_DEVICE_NAME 只在明确指定时作为最高优先级；默认自动选择外接声卡。
DEVICE_NAME="${TTS_DEVICE_NAME:-}"
if [ -d /dev/snd ]; then
    DEVICE_INFO=$(python - <<'PY' 2>/tmp/rabbitbot_tts_pyaudio.err
import os
import pyaudio

preferred_name = os.environ.get("TTS_DEVICE_NAME", "").strip().lower()
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

p = pyaudio.PyAudio()
preferred = None
external = None
builtin = None

try:
    for index in range(p.get_device_count()):
        info = p.get_device_info_by_index(index)
        output_channels = int(info.get("maxOutputChannels", 0))
        if output_channels <= 0:
            continue

        name = info.get("name", "")
        device_info = f"{index}|{name}|{output_channels}"
        if preferred_name and preferred_name in name.lower() and preferred is None:
            preferred = device_info
        elif not is_builtin_audio(name) and external is None:
            external = device_info
        elif builtin is None:
            builtin = device_info
    else:
        selected = preferred or external or builtin
        if selected is not None:
            print(selected)
finally:
    p.terminate()
PY
)
    DEVICE_INDEX=$(echo "$DEVICE_INFO" | cut -d'|' -f1)
    DEVICE_FOUND_NAME=$(echo "$DEVICE_INFO" | cut -d'|' -f2)
else
    DEVICE_INDEX=""
    echo "未检测到 /dev/snd，跳过 PyAudio 输出设备扫描"
fi

if [ -n "$DEVICE_INDEX" ]; then
    export OUTPUT_DEVICE_INDEX=$DEVICE_INDEX
    echo "使用输出音频设备 ${DEVICE_FOUND_NAME}，index=${OUTPUT_DEVICE_INDEX}"
else
    unset OUTPUT_DEVICE_INDEX
    echo "未找到可用输出音频设备，将以无输出设备模式启动 TTS"
fi

uvicorn tts_app:app --host 0.0.0.0 --port 28185 --log-level debug --workers 1
#python tts_app.py
