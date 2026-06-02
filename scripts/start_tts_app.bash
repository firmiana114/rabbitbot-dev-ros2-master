#!/bin/sh

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
#export HTTPS_PROXY=http://127.0.0.1:7897

#export TTS_CLOUD="http://10.10.30.22:28187"

source /opt/venv/bin/activate

RABBITBOT_TTS_BACKEND="${RABBITBOT_TTS_BACKEND:-unitree}"
case "${RABBITBOT_TTS_BACKEND}" in
    unitree|g1|robot)
        echo "使用 Unitree G1 本体 TTS 后端，跳过 Orin 本地输出声卡扫描。音量=${RABBITBOT_UNITREE_TTS_VOLUME:-100}"
        export OUTPUT_DEVICE_INDEX=""
        ;;
    *)
        # TTS_DEVICE_NAME 只在明确指定时作为最高优先级；默认自动选择稳定出现的外接声卡。
        # TTS 实际播放使用 sounddevice，因此启动前也必须用 sounddevice 同源扫描设备。
        # 默认不回退 Orin/HDMI/APE 内置设备，避免服务“正常播放”但现场无声。
        DEVICE_NAME="${TTS_DEVICE_NAME:-}"
        TTS_DEVICE_WAIT_SECONDS="${TTS_DEVICE_WAIT_SECONDS:-20}"
        TTS_DEVICE_STABLE_COUNT="${TTS_DEVICE_STABLE_COUNT:-3}"
        RABBITBOT_TTS_ALLOW_BUILTIN="${RABBITBOT_TTS_ALLOW_BUILTIN:-0}"

        if [ -d /dev/snd ]; then
    DEVICE_INFO=$(python - <<'PY' 2>/tmp/rabbitbot_tts_sounddevice.err
import os
import sys
import time

preferred_name = os.environ.get("TTS_DEVICE_NAME", "").strip().lower()
wait_seconds = float(os.environ.get("TTS_DEVICE_WAIT_SECONDS", "20"))
stable_count = int(os.environ.get("TTS_DEVICE_STABLE_COUNT", "3"))
allow_builtin = os.environ.get("RABBITBOT_TTS_ALLOW_BUILTIN", "0").strip().lower() in {
    "1", "true", "yes", "on"
}
builtin_keywords = (
    "orin",
    "jetson",
    "tegra",
    "nvidia",
    "hda",
    "hdmi",
    "ape",
    "admaif",
    "tegrasnd",
)


def log(message):
    print(message, file=sys.stderr, flush=True)


def is_builtin_audio(name):
    normalized = name.lower()
    return any(keyword in normalized for keyword in builtin_keywords)


def scan_once():
    try:
        import sounddevice as sd
    except Exception as exc:
        log(f"sounddevice 不可用，无法查找输出设备: {exc}")
        return None, []

    candidates = []
    for index, dev in enumerate(sd.query_devices()):
        output_channels = int(dev.get("max_output_channels", 0))
        if output_channels <= 0:
            continue

        name = dev.get("name", "")
        builtin = is_builtin_audio(name)
        if preferred_name:
            matched = preferred_name in name.lower()
        else:
            matched = not builtin
        if matched or (allow_builtin and not preferred_name):
            candidates.append({
                "index": index,
                "name": name,
                "channels": output_channels,
                "builtin": builtin,
                "matched": matched,
            })

    preferred = [
        item for item in candidates
        if item["matched"] and (allow_builtin or not item["builtin"])
    ]
    fallback = [
        item for item in candidates
        if allow_builtin and item["builtin"]
    ]
    selected = (preferred or fallback or [None])[0]
    return selected, candidates


deadline = time.monotonic() + wait_seconds
last_key = None
stable_seen = 0
last_candidates = []

while True:
    selected, candidates = scan_once()
    last_candidates = candidates
    if selected:
        key = (selected["index"], selected["name"])
        if key == last_key:
            stable_seen += 1
        else:
            last_key = key
            stable_seen = 1

        log(
            "TTS输出设备候选稳定检测: "
            f"index={selected['index']}, name={selected['name']}, "
            f"stable={stable_seen}/{stable_count}"
        )
        if stable_seen >= stable_count:
            print(f"{selected['index']}|{selected['name']}|{selected['channels']}")
            sys.exit(0)
    else:
        stable_seen = 0
        last_key = None
        if preferred_name:
            log(f"未检测到指定 TTS 输出设备: {preferred_name}")
        else:
            log("未检测到外接 TTS 输出设备")

    if time.monotonic() >= deadline:
        break
    time.sleep(1)

if last_candidates:
    log("最后一次输出设备候选:")
    for item in last_candidates:
        log(
            f"  index={item['index']}, name={item['name']}, "
            f"channels={item['channels']}, builtin={item['builtin']}"
        )
else:
    log("最后一次扫描没有发现可用输出设备")

sys.exit(2)
PY
)
    DEVICE_SCAN_STATUS=$?
    DEVICE_INDEX=$(echo "$DEVICE_INFO" | cut -d'|' -f1)
    DEVICE_FOUND_NAME=$(echo "$DEVICE_INFO" | cut -d'|' -f2)
else
    DEVICE_SCAN_STATUS=2
    DEVICE_INDEX=""
    echo "未检测到 /dev/snd，无法启动 TTS 输出"
fi

        if [ "${DEVICE_SCAN_STATUS}" -eq 0 ] && [ -n "$DEVICE_INDEX" ]; then
            export OUTPUT_DEVICE_INDEX=$DEVICE_INDEX
            echo "使用输出音频设备 ${DEVICE_FOUND_NAME}，index=${OUTPUT_DEVICE_INDEX}"
        else
            echo "未找到稳定可用的外接输出音频设备，拒绝启动 TTS。"
            echo "如需临时允许内置声卡回退，请设置 RABBITBOT_TTS_ALLOW_BUILTIN=1。"
            echo "sounddevice 扫描日志: /tmp/rabbitbot_tts_sounddevice.err"
            exit 1
        fi
        ;;
esac

uvicorn tts_app:app --host 0.0.0.0 --port 28185 --log-level debug --workers 1
#python tts_app.py
