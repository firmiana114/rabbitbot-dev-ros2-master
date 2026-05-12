#!/bin/sh

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1
export LD_LIBRARY_PATH=/opt/ctranslate2-cuda/lib:/usr/local/cuda/lib64:/usr/local/cuda/targets/aarch64-linux/lib:/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH}
export STT_DEVICE=${STT_DEVICE:-cuda}
export STT_COMPUTE_TYPE=${STT_COMPUTE_TYPE:-float16}

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

export REALTIME_TTS_BASE_URL=http://localhost:28185/v1
#export REALTIME_TTS_BASE_URL=http://10.10.30.19:28185/v1
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

#export STT_CLOUD="http://10.10.30.22:28186"

source /opt/venv/bin/activate

# DJI MIC MINI 当前只接受 48000Hz 录音。RealtimeSTT 的模型和 VAD 仍按 16000Hz
# 处理音频，因此这里在启动前给已安装的 RealtimeSTT 打一个最小补丁：
# 用 48000Hz 打开硬件设备，再交给 RealtimeSTT 内部已有的重采样逻辑转回 16000Hz。
python - <<'PY'
from pathlib import Path

path = Path("/opt/venv/lib/python3.12/site-packages/RealtimeSTT/audio_recorder.py")
text = path.read_text()
replacements = {
    "rate=target_sample_rate,": "rate=sample_rate,",
    "sample_rates_to_try = [16000]": "sample_rates_to_try = [48000]",
    "if highest_rate != 16000:": "if highest_rate != 48000:",
}

changed = False
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new, 1)
        changed = True

if changed:
    path.write_text(text)
    print("已应用 RealtimeSTT 麦克风 48000Hz 兼容补丁")
else:
    print("RealtimeSTT 麦克风 48000Hz 兼容补丁已存在")
PY

# STT_DEVICE_NAME 只在明确指定时作为最高优先级；默认自动选择外接麦克风。
DEVICE_NAME="${STT_DEVICE_NAME:-}"

DEVICE_INDEX=""
DEVICE_FOUND_NAME=""

DEVICE_INFO=$(python - <<'PY' 2>/tmp/rabbitbot_stt_pyaudio.err
import os
import pyaudio

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

p = pyaudio.PyAudio()
preferred = None
external = None
builtin = None

for index in range(p.get_device_count()):
    info = p.get_device_info_by_index(index)
    input_channels = int(info.get("maxInputChannels", 0))
    if input_channels <= 0:
        continue
    
    name = info.get("name", "")
    device_info = f"{index}|{name}|{input_channels}"
    if preferred_name and preferred_name in name.lower() and preferred is None:
        preferred = device_info
    elif not is_builtin_audio(name) and external is None:
        external = device_info
    elif builtin is None:
        builtin = device_info

selected = preferred or external or builtin
if selected:
    print(selected)
p.terminate()
PY
)

if [ -n "$DEVICE_INFO" ]; then
    DEVICE_INDEX=$(echo "$DEVICE_INFO" | cut -d'|' -f1)
    DEVICE_FOUND_NAME=$(echo "$DEVICE_INFO" | cut -d'|' -f2)
    export INPUT_DEVICE_INDEX=$DEVICE_INDEX
    echo "使用输入音频设备 ${DEVICE_FOUND_NAME}，index=${INPUT_DEVICE_INDEX}"
else
    unset INPUT_DEVICE_INDEX
    echo "未找到可用输入音频设备，将以无输入设备模式启动 STT"
fi

export TORCH_HUB_DISABLE_NETWORK=1

uvicorn stt_app:app --host 0.0.0.0 --port 28184 --log-level debug --workers 1
#python stt_app.py
