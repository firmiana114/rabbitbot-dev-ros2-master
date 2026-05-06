#!/bin/bash
# 启动 SenseVoice STT 服务的脚本

# 设置环境变量
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)

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
export STT_MODEL_PATH=${STT_MODEL_PATH:-/data/models/SenseVoiceSmall}
export VAD_MODEL_PATH=${VAD_MODEL_PATH:-/data/models/fsmn_vad}

# 设备名称
DEVICE_NAME="${STT_DEVICE_NAME:-DJI MIC MINI}"

# 查找输入设备。必须在激活虚拟环境后执行，否则默认 python 可能没有 sounddevice。
echo "查找输入设备: ${DEVICE_NAME}"
DEVICE_INFO=$(python - <<'PYDEV'
import os
import sys

preferred_name = os.environ.get("STT_DEVICE_NAME", "DJI MIC MINI")
try:
    import sounddevice as sd
except Exception as exc:
    print(f"sounddevice 不可用，无法按名称查找输入设备: {exc}", file=sys.stderr)
    sys.exit(0)

for idx, dev in enumerate(sd.query_devices()):
    if preferred_name in dev.get("name", "") and dev.get("max_input_channels", 0) > 0:
        print(idx)
        break
PYDEV
)

if [ -n "${DEVICE_INFO}" ]; then
    export INPUT_DEVICE_INDEX="${DEVICE_INFO}"
    echo "使用设备: ${DEVICE_NAME} (index=${DEVICE_INFO})"
elif [ -n "${INPUT_DEVICE_INDEX}" ]; then
    echo "未按名称找到设备 ${DEVICE_NAME}，使用已设置的 INPUT_DEVICE_INDEX=${INPUT_DEVICE_INDEX}"
else
    echo "未找到输入设备 ${DEVICE_NAME}，将以无输入设备模式启动"
    unset INPUT_DEVICE_INDEX
fi

echo "STT 模型路径: ${STT_MODEL_PATH}"
echo "VAD 模型路径: ${VAD_MODEL_PATH}"
echo "STT 设备: ${STT_DEVICE}"
echo "STT 端口: ${STT_PORT}"

# 启动服务
cd "${PROJECT_DIR}"
python stt_app_funasr.py
