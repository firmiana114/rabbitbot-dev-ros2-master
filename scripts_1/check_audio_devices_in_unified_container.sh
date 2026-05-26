#!/usr/bin/env bash
#
# 在统一 Docker 容器中枚举 ALSA 和 PyAudio 可见的输入/输出设备。
# 用途：确认统一容器里的 TTS 输出设备、STT 输入设备是否已经被容器识别。
#
# 使用示例：
#   bash scripts_1/check_audio_devices_in_unified_container.sh
#   CONTAINER_NAME=rabbitbot-unified-runtime-non-integration bash scripts_1/check_audio_devices_in_unified_container.sh

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"

if ! docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "[ERROR] 容器不存在：${CONTAINER_NAME}" >&2
    echo "[INFO] 当前统一容器候选：" >&2
    docker ps -a --format '  {{.Names}}\t{{.Status}}' | grep 'rabbitbot-unified' >&2 || true
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "[ERROR] 容器未运行：${CONTAINER_NAME}" >&2
    echo "[INFO] 请先启动统一容器，或换一个正在运行的 CONTAINER_NAME。" >&2
    exit 1
fi

echo "正在检查统一容器 ${CONTAINER_NAME} 内的音频设备..."
echo "重点关注外接输出设备和外接输入设备，例如 BT67、DJI MIC MINI、Wireless Mic。"
echo ""

echo "===== 宿主机 /dev/snd/by-id ====="
ls -l /dev/snd/by-id 2>/dev/null || true
echo ""

echo "===== 宿主机 /proc/asound/cards ====="
cat /proc/asound/cards 2>/dev/null || true
echo ""

echo "===== 宿主机音频设备占用 ====="
if command -v fuser >/dev/null 2>&1; then
    fuser -v /dev/snd/* 2>&1 || true
else
    echo "[WARN] fuser 不存在，跳过。"
fi
echo ""

echo "===== 容器挂载配置 ====="
docker inspect "${CONTAINER_NAME}" --format 'Binds={{json .HostConfig.Binds}}
Devices={{json .HostConfig.Devices}}
DeviceCgroupRules={{json .HostConfig.DeviceCgroupRules}}'
echo ""

DOCKER_EXEC_ARGS=()
if [ -t 0 ] && [ -t 1 ]; then
    DOCKER_EXEC_ARGS=(-it)
fi

docker exec "${DOCKER_EXEC_ARGS[@]}" "${CONTAINER_NAME}" bash -lc '
set -e

echo "===== 容器用户和 audio 组 ====="
id
getent group audio || true
echo ""

echo "===== 容器 /dev/snd ====="
ls -l /dev/snd 2>/dev/null || true
echo ""

echo "===== 容器 /dev/snd/by-id ====="
ls -l /dev/snd/by-id 2>/dev/null || true
echo ""

echo "===== 容器 /dev/snd/by-path ====="
ls -l /dev/snd/by-path 2>/dev/null || true
echo ""

echo "===== 容器 /proc/asound/cards ====="
if [ -s /proc/asound/cards ]; then
    cat /proc/asound/cards
else
    echo "[WARN] /proc/asound/cards 为空或不可见。"
    echo "[WARN] 统一容器可能只挂载了 /dev/snd；此时 PyAudio 仍可能通过设备节点枚举到声卡。"
fi
echo ""

echo "===== 容器 /proc/asound/devices ====="
if [ -s /proc/asound/devices ]; then
    cat /proc/asound/devices
else
    echo "[WARN] /proc/asound/devices 为空或不可见。"
fi
echo ""

echo "===== 容器 aplay -l ====="
if command -v aplay >/dev/null 2>&1; then
    aplay -l 2>/dev/null || true
else
    echo "[WARN] aplay 不存在，跳过。"
fi
echo ""

echo "===== 容器 arecord -l ====="
if command -v arecord >/dev/null 2>&1; then
    arecord -l 2>/dev/null || true
else
    echo "[WARN] arecord 不存在，跳过。"
fi
echo ""

echo "===== 容器 PyAudio ====="
AUDIO_PYTHON=""
for py in "${RABBITBOT_AUDIO_PYTHON:-}" python3 python /opt/venv/bin/python \
    "${RABBITBOT_DIR:-/workspace/projects/rabbitbot-dev-ros2-master}/py310/bin/python" \
    "${RABBITBOT_DIR:-/workspace/projects/rabbitbot-dev-ros2-master}/py38/bin/python" \
    /usr/bin/python3.8; do
    if [ -z "${py}" ]; then
        continue
    fi
    if command -v "${py}" >/dev/null 2>&1 || [ -x "${py}" ]; then
        if "${py}" -c "import pyaudio" >/dev/null 2>&1; then
            AUDIO_PYTHON="${py}"
            break
        fi
    fi
done

if [ -z "${AUDIO_PYTHON}" ]; then
    echo "[ERROR] 未找到可 import pyaudio 的 Python。"
else
    echo "[INFO] 使用 Python：${AUDIO_PYTHON}"
    PYAUDIO_ERR="/tmp/rabbitbot_unified_audio_pyaudio.err"
    rm -f "${PYAUDIO_ERR}"
    "${AUDIO_PYTHON}" - <<'"'"'PY'"'"' 2>"${PYAUDIO_ERR}"
import pyaudio

p = pyaudio.PyAudio()
try:
    print("device_count", p.get_device_count())
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        print(
            i,
            d.get("name"),
            "in",
            d.get("maxInputChannels"),
            "out",
            d.get("maxOutputChannels"),
            "rate",
            d.get("defaultSampleRate"),
        )
finally:
    p.terminate()
PY
    if [ -s "${PYAUDIO_ERR}" ]; then
        echo ""
        echo "===== PyAudio/ALSA 警告 ====="
        sed -n "1,80p" "${PYAUDIO_ERR}"
        total_lines=$(wc -l < "${PYAUDIO_ERR}" | tr -d " ")
        if [ "${total_lines}" -gt 80 ]; then
            echo "[INFO] 仅显示前 80 行警告，完整内容：${PYAUDIO_ERR}"
        fi
    fi
fi
'

echo ""
echo "如果输出设备出现在 PyAudio 的 out 通道中，说明 TTS 输出设备可见。"
echo "如果输入设备出现在 PyAudio 的 in 通道中，说明 STT 输入设备可见。"
echo "如果 /proc/asound 为空，但 PyAudio 能列出 BT67、DJI MIC MINI 等设备，优先以 PyAudio 结果判断统一容器音频可用性。"
