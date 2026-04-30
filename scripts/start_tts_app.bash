#!/bin/sh

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
#export HTTPS_PROXY=http://127.0.0.1:7897

#export TTS_CLOUD="http://10.10.30.22:28187"

source /opt/venv/bin/activate

#DEVICE_NAME="USB Audio Device"
DEVICE_NAME="${TTS_DEVICE_NAME:-BT67}"
if [ -d /dev/snd ]; then
    DEVICE_INFO=$(python - <<'PY' 2>/tmp/rabbitbot_tts_pyaudio.err
import os
import pyaudio

preferred_name = os.environ.get("TTS_DEVICE_NAME", "BT67")
p = pyaudio.PyAudio()
fallback = None

try:
    for index in range(p.get_device_count()):
        info = p.get_device_info_by_index(index)
        output_channels = int(info.get("maxOutputChannels", 0))
        if output_channels <= 0:
            continue

        name = info.get("name", "")
        device_info = f"{index}|{name}|{output_channels}"
        if preferred_name and preferred_name in name:
            print(device_info)
            break
        if fallback is None:
            fallback = device_info
    else:
        if fallback is not None:
            print(fallback)
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
    echo "未找到输出音频设备 ${DEVICE_NAME}，将以无输出设备模式启动 TTS"
fi

uvicorn tts_app:app --host 0.0.0.0 --port 28185 --log-level debug --workers 1
#python tts_app.py
