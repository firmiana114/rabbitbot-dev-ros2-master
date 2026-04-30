#!/bin/bash
#
# 在音频 Docker 容器中枚举 PyAudio 可见的输入/输出设备。
# 用途：确认 TTS 输出设备 BT67、STT 输入设备 Wireless Mic 是否已经被容器识别。

set -e

# 音频服务所在容器名；如后续容器名变化，可通过环境变量覆盖：
#   AUDIO_CONTAINER=your-container bash scripts_1/check_audio_devices_in_container.sh
AUDIO_CONTAINER="${AUDIO_CONTAINER:-navid-vllm-cuda-mic-audio}"

echo "正在检查容器 ${AUDIO_CONTAINER} 内的音频设备..."
echo "重点关注设备名是否包含：BT67 / Wireless Mic"
echo ""

docker exec -it "${AUDIO_CONTAINER}" bash -lc '
source /opt/venv/bin/activate
python - <<'"'"'PY'"'"'
import pyaudio

p = pyaudio.PyAudio()
try:
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        print(
            i,
            d.get("name"),
            "in",
            d.get("maxInputChannels"),
            "out",
            d.get("maxOutputChannels"),
        )
finally:
    p.terminate()
PY
'

echo ""
echo "如果列表中能看到 BT67，说明 TTS 输出设备可见。"
echo "如果列表中能看到 Wireless Mic，说明 STT 输入设备可见。"
