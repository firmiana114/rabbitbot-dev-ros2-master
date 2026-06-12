from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Optional

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rabbitbot.context import AppContext
from rabbitbot.provider import create_general_vlm_openai
from rabbitbot.tools.sound_agno import (
    audio_input_execute,
    audio_input_execute_timeout,
    tts_sound,
    tts_wait,
)


LOGGER = logging.getLogger("rabbitbot.vlm_qa_workflow")


QA_SYSTEM_PROMPT = dedent(
    """\
    你是 RabbitBot 的开放式中文语音问答助手，优先直接回答当前用户的问题。
    你可以回答日常聊天、通用知识、轻量技术解释、机器人能力说明、园区与导览相关问题，以及当前画面相关问题。
    不要把自己描述成“只能回答导览相关问题”的机器人，也不要把回答范围限制在展厅、展品或参观路线内。
    用户问题表达不完整、上下文不足或有多种理解时，不要直接说无法回答；先按最可能的意思给出简短有用的回答，并在结尾补一句澄清问题。
    对实时信息、专业诊断、法律医疗金融等高风险问题，不要编造具体事实；可以说明自己不能确认最新或个案结论，同时给出通用背景、判断思路和安全建议。
    只有在问题明显不可理解、要求泄露隐私或要求执行危险/违法行为时，才简短拒绝，并尽量给出可替代的安全帮助。
    你不是导览 workflow，不负责展厅路线推进或机器人动作控制；如果用户说“开始导览”，由外部流程处理，你不要在回答中模拟导航命令。
    不要输出动作标签、导航指令、工具调用标记或幕后规则，只输出适合直接播报给用户的中文回答正文。
    """
).strip()


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    if str(raw_value).strip() == "":
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        LOGGER.warning("环境变量不是整数，使用默认值：name=%s, value=%s, default=%s", name, raw_value, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        LOGGER.warning("环境变量不是数字，使用默认值：name=%s, value=%s, default=%s", name, raw_value, default)
        return default


def _text_digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def _text_preview(text: str, max_chars: int = 24) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}..."


def _env_csv(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, default)
    values = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return values or tuple(item.strip() for item in default.split(",") if item.strip())


def _normalize_command_text(text: str) -> str:
    return "".join(ch for ch in _normalize_text(text).lower() if ch.isalnum() or "一" <= ch <= "鿿")


def _is_guide_trigger_text(text: str, phrases: tuple[str, ...]) -> bool:
    normalized_text = _normalize_command_text(text)
    if not normalized_text:
        return False
    for phrase in phrases:
        normalized_phrase = _normalize_command_text(phrase)
        if normalized_phrase and normalized_phrase in normalized_text:
            return True
    return False


def _read_state_file(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("state="):
                return line.split("=", 1)[1].strip()
    except OSError:
        return ""
    return ""


def _write_atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def _normalize_text(text: str) -> str:
    return (text or "").strip()


def _is_valid_user_text(text: str) -> bool:
    text = _normalize_text(text)
    if text == "":
        return False
    return text not in {"<REC_TIMEOUT>", "<REC_STOP>", "<REC_DUPLICATE>", "Timeout", "Started", "Stopped"}


def _is_exit_text(text: str, exit_words: set[str]) -> bool:
    normalized = "".join(ch for ch in _normalize_text(text).lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return normalized in exit_words


SENTENCE_ENDINGS = {"。", "！", "？", "!", "?", "；", ";", "\n"}
SENTENCE_TAIL_CHARS = {"”", "’", "\"", "'", "）", ")", "】", "]", "》", ">"}


def _pop_stream_tts_segment(buffer: str, force: bool = False) -> tuple[Optional[str], str]:
    """从当前 VLM 流式缓冲中取出一段适合提交 TTS 的文本。"""
    if not buffer:
        return None, ""

    for index, char in enumerate(buffer):
        if char not in SENTENCE_ENDINGS:
            continue
        end_index = index + 1
        while end_index < len(buffer) and buffer[end_index] in SENTENCE_TAIL_CHARS:
            end_index += 1
        segment = _normalize_text(buffer[:end_index])
        remainder = buffer[end_index:]
        if segment:
            return segment, remainder

    if force:
        segment = _normalize_text(buffer)
        if segment:
            return segment, ""
    return None, buffer


def _split_dialogue_sentences(text: str) -> list[str]:
    """将问答文本切成带句末标点的短句，便于逐句记录时间戳。"""
    sentences: list[str] = []
    pending_text = text or ""
    while pending_text:
        sentence, pending_text = _pop_stream_tts_segment(pending_text, force=True)
        if sentence is None:
            break
        sentences.append(sentence)
    return sentences


def _dialogue_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@dataclass
class QAWorkflowConfig:
    listen_timeout: int
    idle_sleep_seconds: float
    include_image: bool
    image_width: int
    image_height: int
    answer_max_chars: int
    vlm_max_tokens: int
    vlm_stream: bool
    thinking_speech: str
    speak_thinking_speech: bool
    startup_speech: str
    stream_tts: bool
    dialogue_log_path: str
    exit_words: set[str]
    guide_trigger_phrases: tuple[str, ...]
    guide_command_file: str
    guide_state_file: str
    guide_start_timeout_seconds: float
    guide_finish_timeout_seconds: float
    guide_resume_speech: str
    guide_unavailable_speech: str

    @classmethod
    def from_env(cls) -> "QAWorkflowConfig":
        raw_exit_words = os.getenv("RABBITBOT_QA_EXIT_WORDS", "退出,停止,结束,再见,quit,exit")
        answer_max_chars = _env_int("RABBITBOT_QA_MAX_ANSWER_CHARS", 180)
        return cls(
            listen_timeout=_env_int("RABBITBOT_QA_LISTEN_TIMEOUT", 30),
            idle_sleep_seconds=_env_float("RABBITBOT_QA_IDLE_SLEEP_SECONDS", 0.2),
            include_image=_env_bool("RABBITBOT_QA_INCLUDE_IMAGE", "0"),
            image_width=_env_int("RABBITBOT_QA_IMAGE_WIDTH", 1280),
            image_height=_env_int("RABBITBOT_QA_IMAGE_HEIGHT", 720),
            answer_max_chars=answer_max_chars,
            vlm_max_tokens=_env_int("RABBITBOT_QA_VLM_MAX_TOKENS", min(256, max(64, answer_max_chars))),
            vlm_stream=_env_bool("RABBITBOT_QA_VLM_STREAM", "0"),
            thinking_speech=os.getenv("RABBITBOT_QA_THINKING_SPEECH", "我听到了，让我想一想。"),
            speak_thinking_speech=_env_bool("RABBITBOT_QA_SPEAK_THINKING_SPEECH", "0"),
            startup_speech=os.getenv("RABBITBOT_QA_STARTUP_SPEECH", "你好，请问需要我做些什么吗？"),
            stream_tts=_env_bool("RABBITBOT_QA_STREAM_TTS", "1"),
            dialogue_log_path=os.getenv("RABBITBOT_QA_DIALOGUE_LOG", "").strip(),
            exit_words={word.strip().lower() for word in raw_exit_words.split(",") if word.strip()},
            guide_trigger_phrases=_env_csv("RABBITBOT_QA_GUIDE_TRIGGER_PHRASES", "开始导览"),
            guide_command_file=os.getenv(
                "RABBITBOT_QA_GUIDE_COMMAND_FILE",
                str(PROJECT_ROOT / "runtime" / "nav_workflow_control" / "command"),
            ).strip(),
            guide_state_file=os.getenv(
                "RABBITBOT_QA_GUIDE_STATE_FILE",
                str(PROJECT_ROOT / "runtime" / "nav_workflow_control" / "guide_state"),
            ).strip(),
            guide_start_timeout_seconds=_env_float("RABBITBOT_QA_GUIDE_START_TIMEOUT_SECONDS", 90.0),
            guide_finish_timeout_seconds=_env_float("RABBITBOT_QA_GUIDE_FINISH_TIMEOUT_SECONDS", 1200.0),
            guide_resume_speech=os.getenv("RABBITBOT_QA_GUIDE_RESUME_SPEECH", "").strip(),
            guide_unavailable_speech=os.getenv(
                "RABBITBOT_QA_GUIDE_UNAVAILABLE_SPEECH",
                "导览流程正在准备或尚未返航，请稍后再试。",
            ).strip(),
        )


class VLMQAWorkflow:
    def __init__(self, ctx: AppContext, config: QAWorkflowConfig):
        self.ctx = ctx
        self.config = config
        self.vlm = create_general_vlm_openai()
        self.stop_requested = False
        self.turn_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.guide_trigger_count = 0
        self.start_time = time.perf_counter()
        self.dialogue_log_path = self._init_dialogue_log()

    def _init_dialogue_log(self) -> Optional[Path]:
        raw_path = self.config.dialogue_log_path
        if raw_path:
            log_path = Path(raw_path).expanduser()
        else:
            log_dir = Path(os.getenv("RABBITBOT_LOG_DIR", str(PROJECT_ROOT / "logs" / "vlm_qa_workflow")))
            log_path = log_dir / f"vlm_qa_dialogue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        if not log_path.is_absolute():
            log_path = (PROJECT_ROOT / log_path).resolve()

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch(exist_ok=True)
            latest_path = log_path.parent / "vlm_qa_dialogue_latest.log"
            try:
                if latest_path.exists() or latest_path.is_symlink():
                    latest_path.unlink()
                latest_path.symlink_to(log_path.name)
            except OSError as exc:
                LOGGER.warning("问答日志 latest 软链更新失败：path=%s, type=%s, error=%s", latest_path, type(exc).__name__, exc)
            LOGGER.info("问答日志已启用：path=%s", log_path)
            return log_path
        except OSError as exc:
            LOGGER.exception("问答日志初始化失败：path=%s, type=%s", log_path, type(exc).__name__)
            return None

    def _write_dialogue_log(self, role: str, text: str) -> None:
        if self.dialogue_log_path is None:
            return

        sentences = _split_dialogue_sentences(text)
        if not sentences:
            return

        try:
            with self.dialogue_log_path.open("a", encoding="utf-8") as file:
                for sentence in sentences:
                    file.write(f"{_dialogue_timestamp()} {role}：{sentence}\n")
                file.flush()
        except OSError as exc:
            LOGGER.exception(
                "问答日志写入失败：path=%s, role=%s, text_len=%s, type=%s",
                self.dialogue_log_path,
                role,
                len(text or ""),
                type(exc).__name__,
            )

    def request_stop(self, *_args) -> None:
        self.stop_requested = True
        LOGGER.info("收到退出信号，准备停止问答 workflow")
        try:
            audio_input_execute(self.ctx.stt_agent, "stop_async")
        except Exception as exc:
            LOGGER.warning("停止 STT 异步监听失败：type=%s, error=%s", type(exc).__name__, exc)

    def _current_guide_state(self) -> str:
        if not self.config.guide_state_file:
            return ""
        return _read_state_file(Path(self.config.guide_state_file))

    def _send_guide_start_command(self, user_text: str) -> bool:
        command_path = Path(self.config.guide_command_file)
        state = self._current_guide_state()
        allowed_states = {"", "qa_listening", "waiting_go"}
        if state not in allowed_states:
            LOGGER.warning(
                "导览触发被拒绝：turn=%s, state=%s, command_file=%s, state_file=%s",
                self.turn_count,
                state or "未设置",
                command_path,
                self.config.guide_state_file,
            )
            if self.config.guide_unavailable_speech:
                tts_sound(self.ctx.tts_agent, self.config.guide_unavailable_speech, "zh")
                tts_wait(self.ctx.tts_agent)
                self._write_dialogue_log("回答", self.config.guide_unavailable_speech)
            return False

        started_at = time.perf_counter()
        try:
            _write_atomic_text(command_path, "go\n")
        except OSError as exc:
            elapsed = time.perf_counter() - started_at
            LOGGER.exception(
                "导览触发命令写入失败：turn=%s, command_file=%s, type=%s, elapsed=%.3fs",
                self.turn_count,
                command_path,
                type(exc).__name__,
                elapsed,
            )
            raise
        elapsed = time.perf_counter() - started_at
        LOGGER.info(
            "导览触发命令已写入：turn=%s, command_file=%s, state=%s, text_hash=%s, elapsed=%.3fs",
            self.turn_count,
            command_path,
            state or "未设置",
            _text_digest(user_text),
            elapsed,
        )
        return True

    def _wait_for_guide_completion(self) -> None:
        started_at = time.perf_counter()
        start_deadline = started_at + self.config.guide_start_timeout_seconds
        finish_deadline = started_at + self.config.guide_finish_timeout_seconds
        last_state: Optional[str] = None
        saw_running = False
        LOGGER.info(
            "暂停问答并等待导览完成：turn=%s, state_file=%s, start_timeout=%.1fs, finish_timeout=%.1fs",
            self.turn_count,
            self.config.guide_state_file,
            self.config.guide_start_timeout_seconds,
            self.config.guide_finish_timeout_seconds,
        )
        while time.perf_counter() < finish_deadline and not self.stop_requested:
            state = self._current_guide_state()
            if state != last_state:
                LOGGER.info(
                    "导览状态变化：turn=%s, previous=%s, current=%s, elapsed=%.3fs",
                    self.turn_count,
                    last_state or "未设置",
                    state or "未设置",
                    time.perf_counter() - started_at,
                )
                last_state = state
            if state == "guide_running":
                saw_running = True
            if saw_running and state in {"guide_finished_waiting_back", "qa_listening"}:
                elapsed = time.perf_counter() - started_at
                LOGGER.info("导览已完成，恢复问答监听：turn=%s, final_state=%s, elapsed=%.3fs", self.turn_count, state, elapsed)
                if self.config.guide_resume_speech:
                    tts_sound(self.ctx.tts_agent, self.config.guide_resume_speech, "zh")
                    tts_wait(self.ctx.tts_agent)
                    self._write_dialogue_log("回答", self.config.guide_resume_speech)
                return
            if not saw_running and time.perf_counter() >= start_deadline:
                LOGGER.error(
                    "导览启动等待超时，恢复问答监听：turn=%s, last_state=%s, elapsed=%.3fs",
                    self.turn_count,
                    state or "未设置",
                    time.perf_counter() - started_at,
                )
                if self.config.guide_unavailable_speech:
                    tts_sound(self.ctx.tts_agent, self.config.guide_unavailable_speech, "zh")
                    tts_wait(self.ctx.tts_agent)
                    self._write_dialogue_log("回答", self.config.guide_unavailable_speech)
                return
            time.sleep(0.5)

        LOGGER.error(
            "导览完成等待超时，恢复问答监听：turn=%s, last_state=%s, elapsed=%.3fs",
            self.turn_count,
            last_state or "未设置",
            time.perf_counter() - started_at,
        )

    def _handle_guide_trigger(self, user_text: str) -> None:
        self.guide_trigger_count += 1
        self._write_dialogue_log("系统", "收到开始导览口令，暂停问答并启动导览。")
        if not self._send_guide_start_command(user_text):
            return
        self._wait_for_guide_completion()

    def _capture_image(self) -> Optional[np.ndarray]:
        if not self.config.include_image:
            return None

        source = os.getenv("RABBITBOT_QA_IMAGE_SOURCE", "robot").strip().lower()
        started_at = time.perf_counter()
        if source == "mock":
            image_path = os.getenv(
                "RABBITBOT_QA_MOCK_IMAGE",
                str(PROJECT_ROOT / "tests" / "tasks" / "resources" / "frig.jpg"),
            )
            image = cv2.imread(image_path)
            elapsed = time.perf_counter() - started_at
            if image is None:
                LOGGER.warning("mock 图像读取失败，将改为纯文本问答：path=%s, elapsed=%.3fs", image_path, elapsed)
                return None
            LOGGER.info("已读取 mock 图像：path=%s, shape=%s, elapsed=%.3fs", image_path, image.shape, elapsed)
            return image

        try:
            image = self.ctx.robot.get_camera_info(
                "view_2d",
                {"frame_size": (self.config.image_width, self.config.image_height)},
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started_at
            LOGGER.exception(
                "机器人图像读取异常，将改为纯文本问答：type=%s, elapsed=%.3fs",
                type(exc).__name__,
                elapsed,
            )
            return None

        elapsed = time.perf_counter() - started_at
        if image is None:
            LOGGER.warning("机器人图像为空，将改为纯文本问答：elapsed=%.3fs", elapsed)
            return None
        image = np.asarray(image, dtype=np.uint8)
        LOGGER.info("已读取机器人图像：shape=%s, elapsed=%.3fs", image.shape, elapsed)
        return image

    def _build_visual_prompt(self, user_text: str) -> str:
        return dedent(f"""\
            {QA_SYSTEM_PROMPT}

            请结合当前画面直接回答用户问题，不要复述问题或规则。
            用户问题：{user_text}
        """)

    def _build_text_messages(self, user_text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

    def _create_vlm_completion(self, user_text: str, image: Optional[np.ndarray], stream: bool):
        has_image = image is not None
        if has_image:
            prompt = self._build_visual_prompt(user_text)
            messages, extra_body = self.vlm.prepare_message_for_vllm([image], prompt)
            return self.vlm.client.chat.completions.create(
                model=self.vlm.model,
                messages=messages,
                extra_body=extra_body,
                temperature=0.2,
                max_tokens=self.config.vlm_max_tokens,
                stream=stream,
            )
        return self.vlm.client.chat.completions.create(
            model=self.vlm.model,
            messages=self._build_text_messages(user_text),
            temperature=0.2,
            max_tokens=self.config.vlm_max_tokens,
            stream=stream,
        )

    def _call_vlm(self, user_text: str, image: Optional[np.ndarray]) -> str:
        has_image = image is not None
        request_started_at = time.perf_counter()
        LOGGER.info(
            "VLM 推理开始：turn=%s, question_len=%s, question_hash=%s, has_image=%s, stream=%s, max_tokens=%s, prompt_profile=%s",
            self.turn_count,
            len(user_text),
            _text_digest(user_text),
            has_image,
            False,
            self.config.vlm_max_tokens,
            "qa_broad",
        )

        response = self._create_vlm_completion(user_text, image, stream=False)
        answer = getattr(response.choices[0].message, "content", "") or ""
        print(answer, flush=True)

        elapsed = time.perf_counter() - request_started_at
        answer = _normalize_text(answer)
        LOGGER.info(
            "VLM 推理完成：turn=%s, answer_len=%s, answer_hash=%s, elapsed=%.3fs",
            self.turn_count,
            len(answer),
            _text_digest(answer),
            elapsed,
        )
        return answer

    def _submit_stream_tts_segment(self, segment: str, segment_index: int, spoken_chars: int) -> tuple[int, int]:
        remaining_chars = max(0, self.config.answer_max_chars - spoken_chars)
        if remaining_chars <= 0:
            LOGGER.warning(
                "跳过流式 TTS 分段：turn=%s, segment_index=%s, reason=answer_max_chars_reached, segment_len=%s",
                self.turn_count,
                segment_index,
                len(segment),
            )
            return -1, spoken_chars

        tts_text = segment
        if len(tts_text) > remaining_chars:
            LOGGER.info(
                "流式 TTS 分段超过剩余长度，将截断：turn=%s, segment_index=%s, segment_len=%s, remaining=%s",
                self.turn_count,
                segment_index,
                len(tts_text),
                remaining_chars,
            )
            tts_text = tts_text[:remaining_chars].rstrip()
            if tts_text and tts_text[-1] not in SENTENCE_ENDINGS:
                tts_text += "。"

        if not tts_text:
            return -1, spoken_chars

        tts_started_at = time.perf_counter()
        tts_index = tts_sound(self.ctx.tts_agent, tts_text, "zh")
        self._write_dialogue_log("回答", tts_text)
        elapsed = time.perf_counter() - tts_started_at
        LOGGER.info(
            "流式 TTS 分段已提交：turn=%s, segment_index=%s, tts_index=%s, segment_len=%s, segment_hash=%s, elapsed=%.3fs",
            self.turn_count,
            segment_index,
            tts_index,
            len(tts_text),
            _text_digest(tts_text),
            elapsed,
        )
        return tts_index, spoken_chars + len(tts_text)

    def _call_vlm_with_stream_tts(self, user_text: str, image: Optional[np.ndarray]) -> str:
        if not self.config.vlm_stream:
            LOGGER.info(
                "VLM 输出流式已关闭，改为完整回答后分段播报：turn=%s, stream_tts=%s, max_tokens=%s",
                self.turn_count,
                self.config.stream_tts,
                self.config.vlm_max_tokens,
            )
            answer = self._call_vlm(user_text, image)
            segments = _split_dialogue_sentences(answer)
            if not segments:
                self._speak_answer(answer)
                return answer

            segment_count = 0
            spoken_chars = 0
            for segment in segments:
                if spoken_chars >= self.config.answer_max_chars:
                    break
                segment_count += 1
                _, spoken_chars = self._submit_stream_tts_segment(segment, segment_count, spoken_chars)

            tts_wait_started_at = time.perf_counter()
            tts_wait(self.ctx.tts_agent)
            LOGGER.info(
                "完整回答分段 TTS 等待完成：turn=%s, segment_count=%s, spoken_chars=%s, elapsed=%.3fs",
                self.turn_count,
                segment_count,
                spoken_chars,
                time.perf_counter() - tts_wait_started_at,
            )
            return answer

        has_image = image is not None
        request_started_at = time.perf_counter()
        LOGGER.info(
            "VLM 流式问答开始：turn=%s, question_len=%s, question_hash=%s, has_image=%s, stream_tts=%s, max_tokens=%s, prompt_profile=%s",
            self.turn_count,
            len(user_text),
            _text_digest(user_text),
            has_image,
            self.config.stream_tts,
            self.config.vlm_max_tokens,
            "qa_broad",
        )

        response = self._create_vlm_completion(user_text, image, stream=True)
        chunks: list[str] = []
        pending_text = ""
        segment_index = 0
        spoken_chars = 0
        first_token_elapsed: Optional[float] = None
        first_tts_elapsed: Optional[float] = None

        for chunk in response:
            content = getattr(chunk.choices[0].delta, "content", None)
            if not content:
                continue
            if first_token_elapsed is None:
                first_token_elapsed = time.perf_counter() - request_started_at
                LOGGER.info(
                    "VLM 首 token 到达：turn=%s, elapsed=%.3fs",
                    self.turn_count,
                    first_token_elapsed,
                )
            print(content, end="", flush=True)
            chunks.append(content)
            pending_text += content

            while True:
                segment, pending_text = _pop_stream_tts_segment(pending_text)
                if segment is None:
                    break
                segment_index += 1
                _, spoken_chars = self._submit_stream_tts_segment(segment, segment_index, spoken_chars)
                if first_tts_elapsed is None:
                    first_tts_elapsed = time.perf_counter() - request_started_at

        print("", flush=True)
        final_segment, _ = _pop_stream_tts_segment(pending_text, force=True)
        if final_segment:
            segment_index += 1
            _, spoken_chars = self._submit_stream_tts_segment(final_segment, segment_index, spoken_chars)
            if first_tts_elapsed is None:
                first_tts_elapsed = time.perf_counter() - request_started_at

        answer = _normalize_text("".join(chunks))
        if segment_index == 0:
            self._speak_answer(answer)
            first_tts_elapsed = time.perf_counter() - request_started_at
        else:
            tts_wait_started_at = time.perf_counter()
            tts_wait(self.ctx.tts_agent)
            LOGGER.info(
                "流式 TTS 等待完成：turn=%s, segment_count=%s, elapsed=%.3fs",
                self.turn_count,
                segment_index,
                time.perf_counter() - tts_wait_started_at,
            )

        elapsed = time.perf_counter() - request_started_at
        LOGGER.info(
            "VLM 流式问答完成：turn=%s, answer_len=%s, answer_hash=%s, segment_count=%s, "
            "first_token_elapsed=%s, first_tts_elapsed=%s, elapsed=%.3fs",
            self.turn_count,
            len(answer),
            _text_digest(answer),
            segment_index,
            f"{first_token_elapsed:.3f}s" if first_token_elapsed is not None else None,
            f"{first_tts_elapsed:.3f}s" if first_tts_elapsed is not None else None,
            elapsed,
        )
        return answer

    def _speak_answer(self, answer: str) -> None:
        if not answer:
            answer = "抱歉，我刚才没有生成有效回答，请您再问一遍。"
        if len(answer) > self.config.answer_max_chars:
            LOGGER.info("回答超过长度限制，将截断播报：answer_len=%s, max=%s", len(answer), self.config.answer_max_chars)
            answer = answer[: self.config.answer_max_chars].rstrip() + "。"
        tts_index = tts_sound(self.ctx.tts_agent, answer, "zh")
        self._write_dialogue_log("回答", answer)
        LOGGER.info("TTS 播报已提交：turn=%s, tts_index=%s, answer_len=%s", self.turn_count, tts_index, len(answer))
        tts_wait(self.ctx.tts_agent)

    async def run(self) -> None:
        LOGGER.info(
            "问答 workflow 启动：listen_timeout=%ss, include_image=%s, image_size=%sx%s, stream_tts=%s, vlm_stream=%s, vlm_max_tokens=%s, prompt_profile=%s",
            self.config.listen_timeout,
            self.config.include_image,
            self.config.image_width,
            self.config.image_height,
            self.config.stream_tts,
            self.config.vlm_stream,
            self.config.vlm_max_tokens,
            "qa_broad",
        )
        if self.config.startup_speech:
            tts_sound(self.ctx.tts_agent, self.config.startup_speech, "zh")

        while not self.stop_requested:
            self.turn_count += 1
            LOGGER.info("开始监听用户问题：turn=%s, timeout=%ss", self.turn_count, self.config.listen_timeout)
            listen_started_at = time.perf_counter()
            try:
                user_text = audio_input_execute_timeout(self.ctx.stt_agent, timeout=self.config.listen_timeout, text="")
            except Exception as exc:
                self.failure_count += 1
                LOGGER.exception("STT 监听异常：turn=%s, type=%s", self.turn_count, type(exc).__name__)
                await asyncio.sleep(self.config.idle_sleep_seconds)
                continue

            listen_elapsed = time.perf_counter() - listen_started_at
            user_text = _normalize_text(user_text)
            if not _is_valid_user_text(user_text):
                LOGGER.debug("本轮没有有效语音输入：turn=%s, raw=%s, elapsed=%.3fs", self.turn_count, user_text, listen_elapsed)
                await asyncio.sleep(self.config.idle_sleep_seconds)
                continue

            LOGGER.info(
                "收到用户问题：turn=%s, text_len=%s, text_hash=%s, text_preview=%s, elapsed=%.3fs",
                self.turn_count,
                len(user_text),
                _text_digest(user_text),
                _text_preview(user_text),
                listen_elapsed,
            )
            self._write_dialogue_log("用户", user_text)
            if _is_exit_text(user_text, self.config.exit_words):
                LOGGER.info("收到退出口令：turn=%s, text_hash=%s", self.turn_count, _text_digest(user_text))
                exit_answer = "问答测试已结束。"
                tts_sound(self.ctx.tts_agent, exit_answer, "zh")
                self._write_dialogue_log("回答", exit_answer)
                break

            if _is_guide_trigger_text(user_text, self.config.guide_trigger_phrases):
                LOGGER.info(
                    "收到开始导览口令：turn=%s, trigger_count=%s, phrases=%s, text_hash=%s",
                    self.turn_count,
                    self.guide_trigger_count + 1,
                    ";".join(self.config.guide_trigger_phrases),
                    _text_digest(user_text),
                )
                try:
                    self._handle_guide_trigger(user_text)
                    self.success_count += 1
                except Exception as exc:
                    self.failure_count += 1
                    LOGGER.exception("导览触发流程失败：turn=%s, type=%s", self.turn_count, type(exc).__name__)
                    error_answer = "抱歉，导览启动失败，请稍后再试。"
                    tts_sound(self.ctx.tts_agent, error_answer, "zh")
                    self._write_dialogue_log("回答", error_answer)
                await asyncio.sleep(self.config.idle_sleep_seconds)
                continue

            try:
                if self.config.thinking_speech:
                    LOGGER.info(
                        "收到用户问题后的思考提示：turn=%s, speak=%s, text=%s",
                        self.turn_count,
                        self.config.speak_thinking_speech,
                        self.config.thinking_speech,
                    )
                    if self.config.speak_thinking_speech:
                        tts_sound(self.ctx.tts_agent, self.config.thinking_speech, "zh")
                image = self._capture_image()
                if self.config.stream_tts:
                    self._call_vlm_with_stream_tts(user_text, image)
                else:
                    answer = self._call_vlm(user_text, image)
                    self._speak_answer(answer)
                self.success_count += 1
            except Exception as exc:
                self.failure_count += 1
                LOGGER.exception("问答轮次失败：turn=%s, type=%s", self.turn_count, type(exc).__name__)
                error_answer = "抱歉，我刚才处理问题时遇到异常，请您稍后再试。"
                tts_sound(self.ctx.tts_agent, error_answer, "zh")
                self._write_dialogue_log("回答", error_answer)

        total_elapsed = time.perf_counter() - self.start_time
        LOGGER.info(
            "问答 workflow 结束：turns=%s, success=%s, failure=%s, guide_triggers=%s, elapsed=%.3fs",
            self.turn_count,
            self.success_count,
            self.failure_count,
            self.guide_trigger_count,
            total_elapsed,
        )


async def main(args: argparse.Namespace) -> None:
    _setup_logging(args.verbose or _env_bool("RABBITBOT_QA_VERBOSE", "0"))
    config = QAWorkflowConfig.from_env()
    if args.include_image:
        config.include_image = True
    if args.text_only:
        config.include_image = False

    async with AppContext(with_memory=False) as ctx:
        workflow = VLMQAWorkflow(ctx, config)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, workflow.request_stop)
            except NotImplementedError:
                signal.signal(sig, workflow.request_stop)
        await workflow.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="持续监听语音并通过 VLM 回答的问答测试 workflow。")
    parser.add_argument("--include-image", action="store_true", help="每轮问题同时抓取一帧图像传给 VLM。")
    parser.add_argument("--text-only", action="store_true", help="强制只使用语音文字，不抓取图像。")
    parser.add_argument("--verbose", action="store_true", help="输出 DEBUG 级别诊断日志。")
    return parser


if __name__ == "__main__":
    asyncio.run(main(build_parser().parse_args()))
