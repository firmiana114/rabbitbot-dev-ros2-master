#!/usr/bin/env bash
# 构建 G1 本体 TTS 桥接程序。该程序由 Python TTS 后端调用，通过宇树 SDK2 DDS 接口让机器人本体播报。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECTS_DIR="${RABBITBOT_PROJECTS_DIR:-$(cd "${PROJECT_DIR}/.." && pwd)}"
SOURCE_FILE="${PROJECT_DIR}/scripts/unitree_g1_tts_bridge.cpp"
OUTPUT_FILE="${RABBITBOT_UNITREE_TTS_BINARY:-${PROJECT_DIR}/build/unitree_g1_tts_bridge}"
ARCH="$(uname -m)"

if [ -n "${RABBITBOT_UNITREE_SDK_DIR:-}" ]; then
    SDK_DIR="${RABBITBOT_UNITREE_SDK_DIR}"
elif [ -d /workspace/projects/unitree_sdk2 ]; then
    SDK_DIR="/workspace/projects/unitree_sdk2"
else
    SDK_DIR="${PROJECTS_DIR}/unitree_sdk2"
fi

if [ ! -d "${SDK_DIR}" ]; then
    echo "[ERROR] 未找到宇树 SDK2 目录: ${SDK_DIR}" >&2
    exit 1
fi

SDK_LIB="${SDK_DIR}/lib/${ARCH}/libunitree_sdk2.a"
SDK_THIRDPARTY_LIB="${SDK_DIR}/thirdparty/lib/${ARCH}"
if [ ! -f "${SDK_LIB}" ]; then
    echo "[ERROR] 未找到宇树 SDK2 静态库: ${SDK_LIB}" >&2
    exit 1
fi
if [ ! -d "${SDK_THIRDPARTY_LIB}" ]; then
    echo "[ERROR] 未找到宇树 SDK2 第三方库目录: ${SDK_THIRDPARTY_LIB}" >&2
    exit 1
fi

mkdir -p "$(dirname "${OUTPUT_FILE}")"
echo "[INFO] 构建 Unitree G1 TTS 桥接程序: output=${OUTPUT_FILE}, sdk=${SDK_DIR}, arch=${ARCH}"
g++ -std=c++17 -O2 \
    -I"${SDK_DIR}/include" \
    -I"${SDK_DIR}/thirdparty/include" \
    -I"${SDK_DIR}/thirdparty/include/ddscxx" \
    "${SOURCE_FILE}" \
    -L"${SDK_THIRDPARTY_LIB}" \
    -Wl,-rpath,"${SDK_THIRDPARTY_LIB}" \
    -Wl,--start-group "${SDK_LIB}" -lddsc -lddscxx -Wl,--end-group \
    -lpthread -ldl \
    -o "${OUTPUT_FILE}"

echo "[INFO] Unitree G1 TTS 桥接程序构建完成: ${OUTPUT_FILE}"
