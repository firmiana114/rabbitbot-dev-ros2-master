import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path


def _unitree_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _unitree_log(stage, text=None, **fields):
    field_text = ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    suffix = f", {field_text}" if field_text else ""
    print(f"[{_unitree_timestamp()}] Unitree本体TTS: stage={stage}, text={text}{suffix}")


def _env_enabled(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class UnitreeG1TTS:
    supports_wav_output = False

    def __init__(self, lang="zh"):
        self.lang = lang
        self.network_interface = os.getenv("RABBITBOT_UNITREE_TTS_INTERFACE", "eno1").strip() or "eno1"
        self.speaker_id = int(os.getenv("RABBITBOT_UNITREE_TTS_SPEAKER_ID", "0"))
        self.timeout = float(os.getenv("RABBITBOT_UNITREE_TTS_TIMEOUT", "10"))
        self.command_timeout = float(os.getenv("RABBITBOT_UNITREE_TTS_COMMAND_TIMEOUT", str(self.timeout + 5.0)))
        volume_text = os.getenv("RABBITBOT_UNITREE_TTS_VOLUME", "100").strip()
        self.volume = int(volume_text) if volume_text else -1
        self.binary_path = Path(os.getenv("RABBITBOT_UNITREE_TTS_BINARY", "build/unitree_g1_tts_bridge"))
        self.build_script = Path(os.getenv("RABBITBOT_UNITREE_TTS_BUILD_SCRIPT", "scripts/build_unitree_g1_tts_bridge.sh"))
        self.sdk_dir = Path(os.getenv("RABBITBOT_UNITREE_SDK_DIR") or self._default_sdk_dir())
        self.sdk_thirdparty_lib = self.sdk_dir / "thirdparty" / "lib" / os.uname().machine
        self.auto_build = _env_enabled("RABBITBOT_UNITREE_TTS_AUTO_BUILD", True)
        self.dry_run = _env_enabled("RABBITBOT_UNITREE_TTS_DRY_RUN", False)
        self.tts_index = 0
        self.pending_until = time.monotonic()
        self.lock = threading.Lock()
        _unitree_log(
            "init",
            backend="unitree",
            network=self.network_interface,
            speaker=self.speaker_id,
            volume=self.volume,
            timeout=self.timeout,
            binary=self.binary_path,
            sdk=self.sdk_dir,
            thirdparty_lib=self.sdk_thirdparty_lib,
            dry_run=self.dry_run,
        )
        if not self.dry_run:
            self._ensure_binary()

    def _default_sdk_dir(self):
        for candidate in ("/workspace/projects/unitree_sdk2", "/mnt/ssd/navgation/projects/unitree_sdk2"):
            if Path(candidate).exists():
                return candidate
        return "/mnt/ssd/navgation/projects/unitree_sdk2"

    def _subprocess_env(self):
        env = os.environ.copy()
        lib_path = str(self.sdk_thirdparty_lib)
        previous = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = lib_path if not previous else f"{lib_path}:{previous}"
        return env

    def set_lang(self, lang):
        self.lang = lang
        _unitree_log("set_lang", lang=lang)

    def init_async_workers(self):
        _unitree_log("init_async_workers_skip", reason="Unitree本体TTS同步调用机器人语音服务")

    def warmup(self, text="你好，欢迎参观。"):
        _unitree_log("warmup_skip", text=text, reason="Unitree本体TTS不需要本地合成预热")

    def _ensure_binary(self):
        if self.binary_path.exists() and os.access(self.binary_path, os.X_OK):
            _unitree_log("bridge_binary_ready", binary=self.binary_path)
            return
        if not self.auto_build:
            raise FileNotFoundError(f"Unitree G1 TTS 桥接程序不存在: {self.binary_path}")
        if not self.build_script.exists():
            raise FileNotFoundError(f"Unitree G1 TTS 构建脚本不存在: {self.build_script}")
        build_timeout = float(os.getenv("RABBITBOT_UNITREE_TTS_BUILD_TIMEOUT", "60"))
        _unitree_log("bridge_build_start", script=self.build_script, binary=self.binary_path, timeout=build_timeout)
        start = time.perf_counter()
        result = subprocess.run(
            ["bash", str(self.build_script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=build_timeout,
            check=False,
            env=self._subprocess_env(),
        )
        elapsed = time.perf_counter() - start
        if result.returncode != 0:
            _unitree_log(
                "bridge_build_error",
                returncode=result.returncode,
                elapsed=f"{elapsed:.3f}s",
                stdout=result.stdout[-1000:],
                stderr=result.stderr[-1000:],
            )
            raise RuntimeError(f"Unitree G1 TTS 桥接程序构建失败: returncode={result.returncode}")
        _unitree_log("bridge_build_done", elapsed=f"{elapsed:.3f}s", stdout=result.stdout[-1000:])

    def _estimate_duration(self, text):
        visible_chars = len("".join(ch for ch in (text or "") if not ch.isspace()))
        # 机器人端 TtsMaker 只返回接收状态，没有播放完成回调；这里用于 wait_speech 的保守等待。
        return max(1.0, min(30.0, visible_chars / 5.0 + 0.8))

    def put_text(self, text):
        tts_index = self.tts_index
        self.tts_index += 1
        if text is None:
            _unitree_log("enqueue_close", tts_index=tts_index)
            return tts_index
        clean_text = str(text).strip()
        if not clean_text:
            _unitree_log("skip_empty_text", tts_index=tts_index)
            return tts_index

        duration = self._estimate_duration(clean_text)
        start = time.perf_counter()
        _unitree_log(
            "tts_request_start",
            text=clean_text,
            tts_index=tts_index,
            network=self.network_interface,
            speaker=self.speaker_id,
            volume=self.volume,
            estimated_duration=f"{duration:.3f}s",
        )
        if self.dry_run:
            returncode = 0
            stdout = "dry_run"
            stderr = ""
        else:
            command = [
                str(self.binary_path),
                "--network", self.network_interface,
                "--speaker", str(self.speaker_id),
                "--timeout", str(self.timeout),
                "--text", clean_text,
            ]
            if self.volume >= 0:
                command.extend(["--volume", str(self.volume)])
            result = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.command_timeout,
                check=False,
                env=self._subprocess_env(),
            )
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        elapsed = time.perf_counter() - start
        if returncode != 0:
            _unitree_log(
                "tts_request_error",
                text=clean_text,
                tts_index=tts_index,
                returncode=returncode,
                elapsed=f"{elapsed:.3f}s",
                stdout=stdout[-1000:],
                stderr=stderr[-1000:],
            )
            raise RuntimeError(f"Unitree G1 TTS 请求失败: returncode={returncode}")
        with self.lock:
            now = time.monotonic()
            self.pending_until = max(now, self.pending_until) + duration
        _unitree_log(
            "tts_request_done",
            text=clean_text,
            tts_index=tts_index,
            elapsed=f"{elapsed:.3f}s",
            estimated_duration=f"{duration:.3f}s",
            stdout=stdout[-1000:],
        )
        return tts_index

    def get_wav_count(self):
        with self.lock:
            return 1 if time.monotonic() < self.pending_until else 0

    def get_play(self, tts_index):
        return 0 if self.get_wav_count() else 1

    def wait_wav_queue(self):
        while True:
            with self.lock:
                remaining = self.pending_until - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.2, remaining))
        _unitree_log("wait_done")

    def stop_wait_restart(self, soft_stop):
        with self.lock:
            self.pending_until = time.monotonic()
        _unitree_log("stop", soft_stop=soft_stop, note="Unitree TtsMaker 暂无明确停止接口，仅清空本地等待状态")

    def text_to_wav(self, text, speed=1.0):
        raise RuntimeError("Unitree 本体 TTS 后端不支持本地 WAV 生成")

    def put_wav(self, wav):
        _unitree_log("put_wav_skip", reason="Unitree 本体 TTS 后端不接收本地 wav 队列")

    def sound_wav(self, wav_data, orig_sr):
        _unitree_log("sound_wav_skip", reason="Unitree 本体 TTS 后端不播放本地 wav")
