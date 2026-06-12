#!/usr/bin/env bash

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
#export HTTPS_PROXY=http://127.0.0.1:7897

#export TTS_CLOUD="http://10.10.30.22:28187"

source /opt/venv/bin/activate

RABBITBOT_TTS_BACKEND="${RABBITBOT_TTS_BACKEND:-auto}"
RABBITBOT_UNITREE_TTS_INTERFACE="${RABBITBOT_UNITREE_TTS_INTERFACE:-eno1}"
RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER="${RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER:-1}"
RABBITBOT_UNITREE_TTS_REQUIRE_IPV4="${RABBITBOT_UNITREE_TTS_REQUIRE_IPV4:-1}"
RABBITBOT_UNITREE_TTS_AUTO_PROBE="${RABBITBOT_UNITREE_TTS_AUTO_PROBE:-1}"
RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT="${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT:-3}"
RABBITBOT_UNITREE_TTS_BINARY="${RABBITBOT_UNITREE_TTS_BINARY:-build/unitree_g1_tts_bridge}"
RABBITBOT_UNITREE_TTS_BUILD_SCRIPT="${RABBITBOT_UNITREE_TTS_BUILD_SCRIPT:-scripts/build_unitree_g1_tts_bridge.sh}"

tts_start_log() {
    printf '[%s] TTS启动检查: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

env_enabled() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

unitree_ipv4_address() {
    python - "${RABBITBOT_UNITREE_TTS_INTERFACE}" <<'PY'
import fcntl
import socket
import struct
import sys

iface = sys.argv[1].encode("utf-8")[:15]
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    packed = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack("256s", iface))
except OSError:
    sys.exit(2)
print(socket.inet_ntoa(packed[20:24]))
PY
}

unitree_interface_healthcheck() {
    iface="${RABBITBOT_UNITREE_TTS_INTERFACE}"
    sys_iface="/sys/class/net/${iface}"
    if [ ! -e "${sys_iface}" ] && ! grep -q "^ *${iface}:" /proc/net/dev 2>/dev/null; then
        tts_start_log "Unitree接口检查失败：interface=${iface}, reason=接口不存在"
        return 1
    fi

    operstate="unknown"
    if [ -r "${sys_iface}/operstate" ]; then
        operstate="$(cat "${sys_iface}/operstate" 2>/dev/null || echo unknown)"
    fi
    carrier="unknown"
    if [ -r "${sys_iface}/carrier" ]; then
        carrier="$(cat "${sys_iface}/carrier" 2>/dev/null || echo unknown)"
    fi
    tts_start_log "Unitree接口状态：interface=${iface}, operstate=${operstate}, carrier=${carrier}"

    if env_enabled "${RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER}"; then
        if [ "${carrier}" = "0" ] || [ "${operstate}" = "down" ]; then
            tts_start_log "Unitree链路检查失败：interface=${iface}, operstate=${operstate}, carrier=${carrier}, reason=无物理载波或接口未 UP"
            return 1
        fi
        if [ "${carrier}" = "unknown" ] && [ "${operstate}" != "up" ]; then
            tts_start_log "Unitree链路检查失败：interface=${iface}, operstate=${operstate}, carrier=${carrier}, reason=无法确认链路可用"
            return 1
        fi
    fi

    ipv4="$(unitree_ipv4_address 2>/dev/null || true)"
    if [ -n "${ipv4}" ]; then
        tts_start_log "Unitree IPv4检查通过：interface=${iface}, ipv4=${ipv4}"
    elif env_enabled "${RABBITBOT_UNITREE_TTS_REQUIRE_IPV4}"; then
        tts_start_log "Unitree IPv4检查失败：interface=${iface}, reason=未读取到 IPv4 地址"
        return 1
    else
        tts_start_log "Unitree IPv4检查跳过：interface=${iface}, reason=未读取到 IPv4 地址但未强制要求"
    fi
    return 0
}

ensure_unitree_probe_binary() {
    if [ -x "${RABBITBOT_UNITREE_TTS_BINARY}" ]; then
        tts_start_log "Unitree桥接程序可用：binary=${RABBITBOT_UNITREE_TTS_BINARY}"
        return 0
    fi
    if [ ! -f "${RABBITBOT_UNITREE_TTS_BUILD_SCRIPT}" ]; then
        tts_start_log "Unitree桥接程序检查失败：binary=${RABBITBOT_UNITREE_TTS_BINARY}, build_script=${RABBITBOT_UNITREE_TTS_BUILD_SCRIPT}, reason=构建脚本不存在"
        return 1
    fi

    build_log="/tmp/rabbitbot_unitree_tts_probe_build.log"
    tts_start_log "Unitree桥接程序缺失，开始构建：binary=${RABBITBOT_UNITREE_TTS_BINARY}, build_script=${RABBITBOT_UNITREE_TTS_BUILD_SCRIPT}"
    if bash "${RABBITBOT_UNITREE_TTS_BUILD_SCRIPT}" >"${build_log}" 2>&1; then
        tts_start_log "Unitree桥接程序构建完成：binary=${RABBITBOT_UNITREE_TTS_BINARY}"
        return 0
    fi
    build_rc=$?
    tts_start_log "Unitree桥接程序构建失败：returncode=${build_rc}, log=${build_log}, tail=$(tail -20 "${build_log}" 2>/dev/null | tr '\n' ';')"
    return 1
}

unitree_audio_probe() {
    if ! env_enabled "${RABBITBOT_UNITREE_TTS_AUTO_PROBE}"; then
        tts_start_log "Unitree音频服务探测跳过：reason=RABBITBOT_UNITREE_TTS_AUTO_PROBE=${RABBITBOT_UNITREE_TTS_AUTO_PROBE}"
        return 0
    fi
    if ! ensure_unitree_probe_binary; then
        return 1
    fi

    probe_stdout="/tmp/rabbitbot_unitree_tts_probe.stdout"
    probe_stderr="/tmp/rabbitbot_unitree_tts_probe.stderr"
    timeout_seconds="$(python - "${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT}" <<'PY'
import math
import sys
try:
    value = float(sys.argv[1])
except (TypeError, ValueError):
    value = 3.0
print(max(1, int(math.ceil(value + 2.0))))
PY
)"
    tts_start_log "Unitree音频服务探测开始：interface=${RABBITBOT_UNITREE_TTS_INTERFACE}, probe=get_volume, timeout=${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT}s"
    if command -v timeout >/dev/null 2>&1; then
        timeout "${timeout_seconds}s" "${RABBITBOT_UNITREE_TTS_BINARY}" \
            --network "${RABBITBOT_UNITREE_TTS_INTERFACE}" \
            --timeout "${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT}" \
            --probe get_volume >"${probe_stdout}" 2>"${probe_stderr}"
        probe_rc=$?
    else
        "${RABBITBOT_UNITREE_TTS_BINARY}" \
            --network "${RABBITBOT_UNITREE_TTS_INTERFACE}" \
            --timeout "${RABBITBOT_UNITREE_TTS_PROBE_TIMEOUT}" \
            --probe get_volume >"${probe_stdout}" 2>"${probe_stderr}"
        probe_rc=$?
    fi

    probe_out="$(tail -20 "${probe_stdout}" 2>/dev/null | tr '\n' ';')"
    probe_err="$(tail -20 "${probe_stderr}" 2>/dev/null | tr '\n' ';')"
    if [ "${probe_rc}" -eq 0 ]; then
        tts_start_log "Unitree音频服务探测通过：returncode=0, stdout=${probe_out}, stderr=${probe_err}"
        return 0
    fi
    tts_start_log "Unitree音频服务探测失败：returncode=${probe_rc}, stdout=${probe_out}, stderr=${probe_err}"
    return 1
}

if [ "${RABBITBOT_TTS_BACKEND}" = "auto" ]; then
    tts_start_log "TTS后端自动选择开始：interface=${RABBITBOT_UNITREE_TTS_INTERFACE}, require_carrier=${RABBITBOT_UNITREE_TTS_REQUIRE_CARRIER}, require_ipv4=${RABBITBOT_UNITREE_TTS_REQUIRE_IPV4}, auto_probe=${RABBITBOT_UNITREE_TTS_AUTO_PROBE}"
    if unitree_interface_healthcheck && unitree_audio_probe; then
        tts_start_log "TTS后端自动选择完成：effective=unitree, reason=Unitree接口、链路、IPv4与音频服务探测通过"
        RABBITBOT_TTS_BACKEND="unitree"
    else
        tts_start_log "TTS后端自动选择完成：effective=local, reason=Unitree健康检查失败，回退本地外接输出设备"
        RABBITBOT_TTS_BACKEND="local"
        export TTS_DEVICE_NAME="${TTS_DEVICE_NAME:-BT67}"
    fi
    export RABBITBOT_TTS_BACKEND
fi

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
