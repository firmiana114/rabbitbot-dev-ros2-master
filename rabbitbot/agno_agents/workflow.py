
import time
import json
import random
import asyncio
import threading
import os
import subprocess
import shlex
from pathlib import Path
from datetime import datetime
import difflib
import re
import ast
import atexit
from agno.workflow.v2 import (
    Workflow,
    Loop,
    Router,
    StepInput,
    Step,
    StepOutput,
    Workflow
)
from agno.run.v2.workflow import WorkflowRunResponseEvent
from agno.agent import Agent
from rabbitbot.agno_agents.sound import RealtimeSTT, RealtimeTTS
from rabbitbot.tools.logging import logger as file_logger

from .models import (
    CompletionCheckModel,
    StaticOrDynamicNavigationModel,
    SimpleDelegationTaskModel,
    DelegationTaskModel,
    #ActionModel,
)
from .prompts import (
    get_inst_plan,
    get_inst_navi_check,
    get_inst_chat,
    get_inst_post_docx_chat,
    get_inst_search_check,
    get_inst_ctoe_translate
)
from .chat import ChatQueue
from rabbitbot.robots.constants import MoveType, NavigationStatus
from rabbitbot.tools.navi_agno import NavigationToolkit, NavigationQuery, is_navigating
from rabbitbot.tools.sound_agno import (
    tts_sound, tts_wait, tts_stop, tts_fast, tts_get_wav_count,
    tts_long_text_with_stt_stop,
    tts_long_text,
    action_with_tts, wait_with_tts,
    audio_input_execute,
    audio_input_execute_timeout,
    audio_input_execute_timeout_navi,
    tts_ask_with_early_stt,
    audio_input_yes_or_no,
    audio_input_yes_or_no_ignore_echo,
    audio_input_stop_chat,
    yes_or_no_quick_match,
    identify_think_type,
    build_guide_go_to_text,
    build_stt_prompt_by_list
)
from rabbitbot.tools.detect_agno import DetectToolkit

from typing import Any, List, AsyncIterator, Union
from textwrap import dedent
from rich.console import Console
from rich.pretty import pprint
from rich.prompt import Prompt
from agno.exceptions import StopAgentRun
import numpy as np
import cv2
from rabbitbot.provider import create_general_vlm_openai


class WorkflowTimePoints:
    PLAN_START = -1
    PLAN_END = -1
    NAVI_CHECK_START = -1
    NAVI_CHECK_END = -1
    CHAT_START = -1
    CHAT_FIRST_TEXT_START = -1
    CHAT_END = -1


workflow_configs = {
    "max_chat_history": 5,
    "max_chat_steps": 1
}

PLAN_SESSION_ID = 0
NAVI_CHECK_SESSION_ID = 1
CHAT_SESSION_ID = 2
last_chat_text = ""
chat_queue = ChatQueue(10)
before_text = ""
pending_user_text = ""
_profile_lock = threading.Lock()
_profile_span_id = 0
_profile_summary_lock = threading.RLock()
_profile_summary = {}


def _env_enabled(name, default="0"):
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _workflow_verbose_enabled():
    return _env_enabled("RABBITBOT_WORKFLOW_VERBOSE", "0")


def _workflow_non_integration_enabled():
    return _env_enabled("RABBITBOT_WORKFLOW_NON_INTEGRATION", "0")


def _strict_docx_script_enabled():
    return _env_enabled("RABBITBOT_STRICT_DOCX_SCRIPT", "1")


def _workflow_log(message, verbose=False):
    if verbose and not _workflow_verbose_enabled():
        return
    print(message)


# workflow 运行环境变量速查：
# - RABBITBOT_STRICT_DOCX_SCRIPT：是否启用严格 DOCX 剧本模式，默认启用。
# - RABBITBOT_SCRIPTED_TOUR：是否启用脚本化导览推进，默认启用。
# - RABBITBOT_WORKFLOW_NON_INTEGRATION：是否使用非联调手动确认导航模式。
# - RABBITBOT_WORKFLOW_VERBOSE：是否打印调试级 workflow 过程日志。
# - RABBITBOT_WORKFLOW_PROFILE：是否写入 workflow profile JSONL，默认启用。
# - RABBITBOT_WORKFLOW_PROFILE_LOG：显式指定 workflow profile JSONL 路径。
# - RABBITBOT_LOG_DIR：未指定 profile 路径时的日志目录。
# - RABBITBOT_WORKFLOW_SUMMARY：是否在退出时打印 workflow 耗时汇总，默认启用。
# - RABBITBOT_DIALOGUE_INDEX：选择 conf/dialogue_<序号>.json，未设置时默认 0。
# - RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX：旧版台词序号变量，仅在 RABBITBOT_DIALOGUE_INDEX 未设置时兜底。
# - RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE：直接指定台词 JSON 文件完整路径，优先级高于序号。
# - RABBITBOT_COFFEE_DELIVERY_COMMAND：覆盖“呼叫咖啡车”的后台命令。
# - RABBITBOT_COFFEE_DELIVERY_COMMAND_TIMEOUT：呼叫咖啡车后台命令等待超时时间，单位秒。
# - RABBITBOT_OPENING_MODE：控制开场流程，full 为完整开场，skip/0/false/off 为跳过。
# - RABBITBOT_ENABLE_NAVI：是否真实执行导航，设为 0/false/no/off 时跳过导航。
# - RABBITBOT_HAND_GESTURE_<ACTION>：为指定手臂动作配置灵巧手 ROS 字符串命令。
# - RABBITBOT_HAND_GESTURE_TOPIC：灵巧手命令发布 topic，默认 /gesture_cmd。
# - RABBITBOT_HAND_GESTURE_PUB_TIMEOUT：灵巧手命令发布超时，单位秒。
# - RABBITBOT_HANDSHAKE_BEFORE_RELEASE_DELAY：握手动作收手前等待时间，单位秒。
# - RABBITBOT_ARM_BEFORE_RELEASE_DELAY：其它前置动作收手前默认等待时间，单位秒。
# - RABBITBOT_ARM_AFTER_SPEECH_RELEASE_DELAY：台词后收手动作的等待时间，单位秒。
# - RABBITBOT_ARM_CONCURRENT_RELEASE_DELAY：动作与台词并发时收手前等待时间，单位秒。
# - RABBITBOT_ARM_RELEASE_WAIT_SECONDS：发送 release 后额外等待时间，单位秒。
# - RABBITBOT_VIEW_MODE：视觉问答来源，robot 使用机器人视觉，其它值使用 mock。
# - RABBITBOT_MOCK_IMAGE：mock 视觉问答使用的本地图片路径。
DOCX_GUIDE_DIALOGUE_DIR = Path(__file__).resolve().parents[2] / "conf"
DOCX_GUIDE_DIALOGUE_DEFAULT_INDEX = "0"
_DOCX_GUIDE_DIALOGUE_CACHE = {"path": None, "data": None}


def _docx_guide_dialogue_index():
    raw_index = os.getenv(
        "RABBITBOT_DIALOGUE_INDEX",
        os.getenv("RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX", DOCX_GUIDE_DIALOGUE_DEFAULT_INDEX),
    ).strip()
    if not re.fullmatch(r"[0-9]+", raw_index):
        _workflow_log(f"DOCX 导览台词序号非法: RABBITBOT_DIALOGUE_INDEX={raw_index!r}")
        raise ValueError(f"DOCX 导览台词序号必须是数字: {raw_index!r}")
    return raw_index


def _docx_guide_dialogue_path():
    configured_path = os.getenv("RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE", "").strip()
    if configured_path:
        return Path(configured_path)
    return DOCX_GUIDE_DIALOGUE_DIR / f"dialogue_{_docx_guide_dialogue_index()}.json"


def _load_docx_guide_dialogue():
    dialogue_path = _docx_guide_dialogue_path()
    cache_path = _DOCX_GUIDE_DIALOGUE_CACHE.get("path")
    if cache_path == dialogue_path and _DOCX_GUIDE_DIALOGUE_CACHE.get("data") is not None:
        return _DOCX_GUIDE_DIALOGUE_CACHE["data"]

    start_time = time.perf_counter()
    try:
        raw_text = dialogue_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except FileNotFoundError as exc:
        _workflow_log(f"DOCX 导览台词文件缺失: path={dialogue_path}")
        raise FileNotFoundError(f"DOCX 导览台词文件缺失: {dialogue_path}") from exc
    except json.JSONDecodeError as exc:
        _workflow_log(
            "DOCX 导览台词文件 JSON 解析失败: "
            f"path={dialogue_path}, line={exc.lineno}, column={exc.colno}, message={exc.msg}"
        )
        raise ValueError(f"DOCX 导览台词文件 JSON 解析失败: {dialogue_path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"DOCX 导览台词文件根节点必须是对象: {dialogue_path}")
    variables = data.get("variables", {})
    opening = data.get("opening", {})
    steps = data.get("steps", [])
    if not isinstance(variables, dict):
        raise ValueError(f"DOCX 导览台词 variables 必须是对象: {dialogue_path}")
    if not isinstance(opening, dict):
        raise ValueError(f"DOCX 导览台词 opening 必须是对象: {dialogue_path}")
    if not isinstance(steps, list):
        raise ValueError(f"DOCX 导览台词 steps 必须是数组: {dialogue_path}")

    elapsed_seconds = time.perf_counter() - start_time
    segment_count = sum(len(step.get("segments", []) or []) for step in steps if isinstance(step, dict))
    leader_calling = str(variables.get("leader_calling") or "").strip()
    _DOCX_GUIDE_DIALOGUE_CACHE["path"] = dialogue_path
    _DOCX_GUIDE_DIALOGUE_CACHE["data"] = data
    configured_path = os.getenv("RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE", "").strip()
    dialogue_source = "file_env" if configured_path else f"index={_docx_guide_dialogue_index()}"
    _workflow_log(
        "DOCX 导览台词文件加载完成: "
        f"source={dialogue_source}, path={dialogue_path}, steps={len(steps)}, segments={segment_count}, "
        f"leader_calling={leader_calling or '未配置'}, elapsed={elapsed_seconds:.3f}s"
    )
    return data


def _docx_guide_variables(extra_variables=None):
    data = _load_docx_guide_dialogue()
    variables = dict(data.get("variables", {}) or {})
    if "leader_calling" not in variables or not str(variables.get("leader_calling") or "").strip():
        raise KeyError(f"DOCX 导览台词 variables 缺少必填称呼键: key=leader_calling, path={_docx_guide_dialogue_path()}")
    variables["leader_calling"] = str(variables["leader_calling"]).strip()
    if extra_variables:
        variables.update(extra_variables)
        if "leader_calling" in variables:
            variables["leader_calling"] = str(variables["leader_calling"]).strip()
    return variables


def _docx_guide_leader_calling():
    return _docx_guide_variables()["leader_calling"]


def _format_docx_guide_text(text, variables=None):
    if text is None:
        return ""
    format_variables = _docx_guide_variables(variables)
    try:
        return str(text).format(**format_variables)
    except KeyError as exc:
        _workflow_log(
            "DOCX 导览台词占位符缺少变量: "
            f"missing={exc.args[0]}, available={sorted(format_variables.keys())}"
        )
        raise


def _docx_opening_text(key, variables=None):
    opening = _load_docx_guide_dialogue().get("opening", {}) or {}
    if key not in opening:
        dialogue_path = _docx_guide_dialogue_path()
        raise KeyError(f"DOCX 导览台词 opening 缺少键: key={key}, path={dialogue_path}")
    return _format_docx_guide_text(opening[key], variables)


def _load_docx_script_steps(point_entity):
    data = _load_docx_guide_dialogue()
    raw_steps = data.get("steps", [])
    if not raw_steps:
        raise ValueError(f"DOCX 导览台词 steps 为空: {_docx_guide_dialogue_path()}")

    steps = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"DOCX 导览台词 step 必须是对象: index={index}")
        step = dict(raw_step)
        entity_key = step.pop("entity_key", None)
        if entity_key:
            if entity_key not in point_entity:
                raise KeyError(f"DOCX 导览台词 step entity_key 未定义: index={index}, entity_key={entity_key}")
            step["entity"] = point_entity[entity_key]
        segments = step.get("segments", [])
        if segments is None:
            segments = []
        if not isinstance(segments, list):
            raise ValueError(f"DOCX 导览台词 step segments 必须是数组: index={index}, scene={step.get('scene')}")
        step["segments"] = [dict(segment) for segment in segments]
        steps.append(step)
    return steps


def _workflow_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _format_log_fields(fields):
    return ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)


def _workflow_action_log(stage, action_name=None, **fields):
    field_text = _format_log_fields(fields)
    suffix = f", {field_text}" if field_text else ""
    print(f"[{_workflow_timestamp()}] workflow动作链路: stage={stage}, action={action_name}{suffix}")


def _workflow_profile_enabled():
    return _env_enabled("RABBITBOT_WORKFLOW_PROFILE", "1")


def _workflow_profile_path():
    explicit_path = os.getenv("RABBITBOT_WORKFLOW_PROFILE_LOG", "").strip()
    if explicit_path:
        return Path(explicit_path)
    log_dir = os.getenv("RABBITBOT_LOG_DIR", "").strip()
    if log_dir:
        return Path(log_dir) / "workflow_profile.jsonl"
    return Path.cwd() / "logs" / "workflow_profile.jsonl"


def _profile_json_safe(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _profile_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_profile_json_safe(item) for item in value]
    return str(value)


def _profile_write(record):
    if not _workflow_profile_enabled():
        return
    record = {key: _profile_json_safe(value) for key, value in record.items()}
    record.setdefault("ts", _workflow_timestamp())
    profile_path = _workflow_profile_path()
    try:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with _profile_lock:
            with profile_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"workflow profile 写入失败: path={profile_path}, error={exc}")


def _profile_next_span_id():
    global _profile_span_id
    with _profile_lock:
        _profile_span_id += 1
        return _profile_span_id


def _profile_start(span, **fields):
    _profile_summary_start_if_needed()
    span_token = {
        "span_id": _profile_next_span_id(),
        "span": span,
        "start_perf": time.perf_counter(),
    }
    _profile_write({
        "event": "start",
        "span": span,
        "span_id": span_token["span_id"],
        **fields,
    })
    return span_token


def _profile_end(span_token, **fields):
    if not span_token:
        return
    elapsed_seconds = time.perf_counter() - span_token["start_perf"]
    _profile_write({
        "event": "end",
        "span": span_token["span"],
        "span_id": span_token["span_id"],
        "elapsed": round(elapsed_seconds, 6),
        **fields,
    })
    _profile_summary_record(span_token["span"], elapsed_seconds)


def _profile_instant(name, span=None, **fields):
    record = {
        "event": "instant",
        "name": name,
        **fields,
    }
    if span:
        record["span"] = span
    _profile_write(record)


def _workflow_profile_summary_enabled():
    return _env_enabled("RABBITBOT_WORKFLOW_SUMMARY", "1")


def _profile_summary_reset():
    global _profile_summary
    with _profile_summary_lock:
        _profile_summary = {
            "start_perf": None,
            "printed": False,
            "loop_iterations": 0,
            "stats": {
                "audio_input": {"count": 0, "sum": 0.0},
                "plan_llm": {"count": 0, "sum": 0.0},
                "chat_llm": {"count": 0, "sum": 0.0},
                "chat_tts": {"count": 0, "sum": 0.0},
                "action": {"count": 0, "sum": 0.0},
                "navi_check": {"count": 0, "sum": 0.0},
                "completion_check": {"count": 0, "sum": 0.0},
            },
        }


def _profile_summary_start_if_needed():
    if not _workflow_profile_summary_enabled():
        return
    with _profile_summary_lock:
        if not _profile_summary:
            _profile_summary_reset()
        if _profile_summary["start_perf"] is None:
            _profile_summary["start_perf"] = time.perf_counter()


def _profile_summary_label(span):
    return {
        "audio_input": "audio_input",
        "listen_answer": "audio_input",
        "plan_llm": "plan_llm",
        "chat_llm": "chat_llm",
        "chat_tts": "chat_tts",
        "tts_segment": "chat_tts",
        "arm_action": "action",
        "navi_check": "navi_check",
        "completion_check": "completion_check",
    }.get(span)


def _profile_summary_record(span, elapsed_seconds):
    if not _workflow_profile_summary_enabled():
        return
    _profile_summary_start_if_needed()
    with _profile_summary_lock:
        if span == "loop_iteration":
            _profile_summary["loop_iterations"] += 1
        label = _profile_summary_label(span)
        if not label:
            return
        stat = _profile_summary["stats"][label]
        stat["count"] += 1
        stat["sum"] += float(elapsed_seconds)


def _profile_summary_line(label):
    stat = _profile_summary["stats"].get(label, {"count": 0, "sum": 0.0})
    count = stat["count"]
    avg = stat["sum"] / count if count else 0.0
    return f"{label + ' (avg):':<22}{avg:>9.3f}s  (×{count})"


def _profile_summary_print(reason="finished", force=False):
    if not _workflow_profile_summary_enabled():
        return
    with _profile_summary_lock:
        if not _profile_summary:
            return
        if _profile_summary.get("printed") and not force:
            return
        start_perf = _profile_summary.get("start_perf")
        loop_total = time.perf_counter() - start_perf if start_perf is not None else 0.0
        lines = [
            "========== Workflow Profile Summary ==========",
            f"loop_total:{loop_total:>20.3f}s",
            f"loop_iterations:{_profile_summary['loop_iterations']:>9}",
            _profile_summary_line("audio_input"),
            _profile_summary_line("plan_llm"),
            _profile_summary_line("chat_llm"),
            _profile_summary_line("chat_tts"),
            _profile_summary_line("action"),
            _profile_summary_line("navi_check"),
            _profile_summary_line("completion_check"),
        ]
        _profile_summary["printed"] = True

    print("\n".join(lines))
    _profile_write({
        "event": "instant",
        "name": "workflow_profile_summary_printed",
        "reason": reason,
        "loop_total": round(loop_total, 6),
    })


def _profile_summary_print_at_exit():
    _profile_summary_print(reason="process_exit")


_profile_summary_reset()
atexit.register(_profile_summary_print_at_exit)


ARM_ACTIONS_NEED_RELEASE_BEFORE_SPEECH = {"shake_hand", "face_wave", "high_wave", "hug"}
ARM_ACTIONS_NEED_RELEASE_AFTER_SPEECH = {"right_hand_up", "hands_up"}
ARM_RELEASE_ACTION = "release"
ARM_BEFORE_RELEASE_DELAYS = {
    "shake_hand": 0.0,
}
ARM_BEFORE_RELEASE_DELAY_ENV = {
    "shake_hand": "RABBITBOT_HANDSHAKE_BEFORE_RELEASE_DELAY",
}
HAND_GESTURE_COMMANDS = {}


def _should_speak_with_action(action_name, configured=False):
    if not action_name:
        return False
    return bool(configured) or action_name != "shake_hand"


def _get_hand_gesture_command(action_name):
    if not action_name:
        return ""
    env_name = f"RABBITBOT_HAND_GESTURE_{action_name.upper()}".replace("-", "_")
    command = os.getenv(env_name, HAND_GESTURE_COMMANDS.get(action_name, ""))
    return command.strip()


def _publish_hand_gesture_for_arm_action(action_name):
    command = _get_hand_gesture_command(action_name)
    if not command:
        _workflow_action_log("hand_gesture_skip", action_name, reason="未配置灵巧手动作")
        return

    topic = os.getenv("RABBITBOT_HAND_GESTURE_TOPIC", "/gesture_cmd")
    timeout = _env_float("RABBITBOT_HAND_GESTURE_PUB_TIMEOUT", 3.0)
    message = f"{{data: '{command}'}}"
    start_time = time.perf_counter()
    _workflow_action_log("hand_gesture_publish_start", action_name, topic=topic, data=command, timeout=timeout)
    try:
        subprocess.run(
            ["ros2", "topic", "pub", "--once", topic, "std_msgs/msg/String", message],
            check=True,
            timeout=timeout,
        )
        elapsed_seconds = time.perf_counter() - start_time
        _workflow_action_log("hand_gesture_publish_done", action_name, topic=topic, data=command, elapsed=f"{elapsed_seconds:.3f}s")
        print(f"已发布灵巧手动作: topic={topic}, data={command}")
    except FileNotFoundError as exc:
        elapsed_seconds = time.perf_counter() - start_time
        _workflow_action_log("hand_gesture_publish_error", action_name, topic=topic, data=command, elapsed=f"{elapsed_seconds:.3f}s", error=exc)
        print("发布灵巧手动作失败: 未找到 ros2 命令")
    except subprocess.TimeoutExpired:
        elapsed_seconds = time.perf_counter() - start_time
        _workflow_action_log("hand_gesture_publish_timeout", action_name, topic=topic, data=command, elapsed=f"{elapsed_seconds:.3f}s", timeout=timeout)
        print(f"发布灵巧手动作超时: topic={topic}, data={command}, timeout={timeout}")
    except subprocess.CalledProcessError as exc:
        elapsed_seconds = time.perf_counter() - start_time
        _workflow_action_log("hand_gesture_publish_error", action_name, topic=topic, data=command, elapsed=f"{elapsed_seconds:.3f}s", returncode=exc.returncode)
        print(f"发布灵巧手动作失败: topic={topic}, data={command}, returncode={exc.returncode}")



DOCX_SCRIPT_POINTS = {
    "点位1": {
        "summary": "点位1",
        "description": "DOCX 剧本起始点位。",
        "location": [
            {"x": 1.9105, "y": -1.6180, "z": 0.0117, "ox": -0.0029, "oy": 0.0265, "oz": -0.2046, "ow": 0.9785, "mode": 1},
        ],
    },
    "1->2过渡点位": {
        "summary": "1->2过渡点位",
        "description": "DOCX 剧本点位1前往点位2路径上的过渡点位；该点位只导航，不播报台词。",
        "location": [
            {"x": 8.6465, "y": -2.5763, "z": -0.0722, "ox": 0.0547, "oy": 0.0907, "oz": 0.5347, "ow": 0.8384, "mode": 1},
        ],
    },
    "点位2": {
        "summary": "点位2",
        "description": "DOCX 剧本问咖啡点位；点咖啡台词只允许在该最终点位播报。",
        "location": [
            {"x": 10.1203, "y": 0.8162, "z": -0.1335, "ox": 0.0904, "oy": 0.0373, "oz": 0.9074, "ow": 0.4087, "mode": 1},
        ],
    },
    "点位3": {
        "summary": "点位3",
        "description": "DOCX 剧本拿取咖啡点位。",
        "location": [
            {"x": 11.1090, "y": 4.3229, "z": -0.1892, "ox": 0.0937, "oy": 0.0170, "oz": 0.9717, "ow": 0.2162, "mode": 1},
        ],
    },
    "点位4": {
        "summary": "点位4",
        "description": "DOCX 剧本点位3前往点位5路径上的中转点位。",
        "location": [
            {"x": 13.9410, "y": -5.1633, "z": 0.0350, "ox": 0.0140, "oy": 0.0335, "oz": -0.9085, "ow": -0.4163, "mode": 1},
        ],
    },
    "3->5过渡点位": {
        "summary": "3->5过渡点位",
        "description": "DOCX 剧本点位3前往点位5路径上的过渡点位；该点位只导航，不播报台词。",
        "location": [
            {"x": 5.5507, "y": 14.4097, "z": -0.1921, "ox": 0.0779, "oy": 0.0578, "oz": 0.7806, "ow": 0.6174, "mode": 1},
        ],
    },
    "点位5": {
        "summary": "点位5",
        "description": "DOCX 剧本告别并指引小巴方向点位；告别台词只允许在该最终点位播报。",
        "location": [
            {"x": 4.7039, "y": 20.4749, "z": -0.2250, "ox": 0.0876, "oy": -0.0269, "oz": 0.9076, "ow": -0.4096, "mode": 1},
        ],
    },
}


def _load_docx_point_entity(name):
    point = DOCX_SCRIPT_POINTS.get(name)
    if not point:
        return None
    return {
        "name": name,
        "summary": point.get("summary", name),
        "description": point.get("description", ""),
        "location": point.get("location", []),
    }


def _env_float(name, default):
    raw_value = os.getenv(name, str(default))
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        print(f"Invalid {name}={raw_value}, use {default}")
        return float(default)


def _format_arm_action_success(result):
    if isinstance(result, dict):
        return result.get("success", "未知")
    if result is None:
        return "无返回"
    return "未知"


def _log_arm_action_latency(action_name, elapsed_seconds, result=None, error=None, call_type="async"):
    if error is not None:
        _workflow_action_log(
            "workflow_do_arm_result",
            action_name,
            success="异常",
            elapsed=f"{elapsed_seconds:.3f}s",
            mode=call_type,
            error=error,
        )
        print(
            f"手臂动作body回执耗时: action={action_name}, success=异常, "
            f"elapsed={elapsed_seconds:.3f}s, mode={call_type}, error={error}"
        )
        return
    success = _format_arm_action_success(result)
    _workflow_action_log(
        "workflow_do_arm_result",
        action_name,
        success=success,
        elapsed=f"{elapsed_seconds:.3f}s",
        mode=call_type,
    )
    print(
        f"手臂动作body回执耗时: action={action_name}, success={success}, "
        f"elapsed={elapsed_seconds:.3f}s, mode={call_type}"
    )


async def _do_arm_async_timed(robot, action_name):
    start_time = time.perf_counter()
    span_token = _profile_start("arm_action", action=action_name, mode="async")
    _workflow_action_log("workflow_do_arm_async_start", action_name)
    try:
        result = await robot.do_arm_async(action_name)
    except Exception as exc:
        elapsed_seconds = time.perf_counter() - start_time
        _log_arm_action_latency(action_name, elapsed_seconds, error=exc, call_type="async")
        _profile_end(span_token, action=action_name, mode="async", success=False, error=exc)
        raise
    elapsed_seconds = time.perf_counter() - start_time
    success = _format_arm_action_success(result)
    _log_arm_action_latency(action_name, elapsed_seconds, result=result, call_type="async")
    _profile_end(span_token, action=action_name, mode="async", success=success)
    return result


async def _send_release_arm(robot):
    span_token = _profile_start("release_arm", action=ARM_RELEASE_ACTION)
    _workflow_action_log("workflow_release_start", ARM_RELEASE_ACTION)
    release_result = await _do_arm_async_timed(robot, ARM_RELEASE_ACTION)
    if isinstance(release_result, dict) and not release_result.get("success", True):
        print(f"收回动作回执失败: action={ARM_RELEASE_ACTION}, result={release_result}")
    release_wait_seconds = _env_float("RABBITBOT_ARM_RELEASE_WAIT_SECONDS", 0.2)
    if release_wait_seconds > 0:
        _workflow_action_log("workflow_release_wait_start", ARM_RELEASE_ACTION, wait=f"{release_wait_seconds:.3f}s")
        await asyncio.sleep(release_wait_seconds)
        _workflow_action_log("workflow_release_wait_done", ARM_RELEASE_ACTION, wait=f"{release_wait_seconds:.3f}s")
    success = _format_arm_action_success(release_result)
    _profile_end(span_token, action=ARM_RELEASE_ACTION, success=success)


def _send_release_arm_sync(robot):
    span_token = _profile_start("release_arm", action=ARM_RELEASE_ACTION, mode="thread")
    _workflow_action_log("workflow_release_thread_start", ARM_RELEASE_ACTION)
    try:
        release_result = _do_arm_sync(robot, ARM_RELEASE_ACTION)
    except Exception as exc:
        _workflow_action_log("workflow_release_thread_error", ARM_RELEASE_ACTION, error=exc)
        _profile_end(span_token, action=ARM_RELEASE_ACTION, mode="thread", success=False, error=exc)
        return
    if isinstance(release_result, dict) and not release_result.get("success", True):
        print(f"收回动作回执失败: action={ARM_RELEASE_ACTION}, result={release_result}")
    release_wait_seconds = _env_float("RABBITBOT_ARM_RELEASE_WAIT_SECONDS", 0.2)
    if release_wait_seconds > 0:
        _workflow_action_log("workflow_release_thread_wait_start", ARM_RELEASE_ACTION, wait=f"{release_wait_seconds:.3f}s")
        time.sleep(release_wait_seconds)
        _workflow_action_log("workflow_release_thread_wait_done", ARM_RELEASE_ACTION, wait=f"{release_wait_seconds:.3f}s")
    success = _format_arm_action_success(release_result)
    _profile_end(span_token, action=ARM_RELEASE_ACTION, mode="thread", success=success)


async def _do_arm_before_speech(robot, action_name):
    _workflow_action_log("workflow_arm_before_speech_start", action_name)
    _publish_hand_gesture_for_arm_action(action_name)
    action_result = await _do_arm_async_timed(robot, action_name)
    if isinstance(action_result, dict) and not action_result.get("success", True):
        print(f"动作回执失败: action={action_name}, result={action_result}")
    if action_name not in ARM_ACTIONS_NEED_RELEASE_BEFORE_SPEECH:
        return

    default_before_release_delay = ARM_BEFORE_RELEASE_DELAYS.get(
        action_name,
        _env_float("RABBITBOT_ARM_BEFORE_RELEASE_DELAY", 0.0),
    )
    before_release_delay = _env_float(
        ARM_BEFORE_RELEASE_DELAY_ENV.get(action_name, "RABBITBOT_ARM_BEFORE_RELEASE_DELAY"),
        default_before_release_delay,
    )
    if before_release_delay > 0:
        _workflow_action_log("workflow_before_release_wait_start", action_name, wait=f"{before_release_delay:.3f}s")
        await asyncio.sleep(before_release_delay)
        _workflow_action_log("workflow_before_release_wait_done", action_name, wait=f"{before_release_delay:.3f}s")
    await _send_release_arm(robot)


def _do_arm_sync(robot, action_name):
    do_arm = getattr(robot, "do_arm", None)
    if callable(do_arm):
        start_time = time.perf_counter()
        span_token = _profile_start("arm_action", action=action_name, mode="sync")
        _workflow_action_log("workflow_do_arm_sync_start", action_name)
        try:
            result = do_arm(action_name)
        except Exception as exc:
            elapsed_seconds = time.perf_counter() - start_time
            _log_arm_action_latency(action_name, elapsed_seconds, error=exc, call_type="sync")
            _profile_end(span_token, action=action_name, mode="sync", success=False, error=exc)
            raise
        elapsed_seconds = time.perf_counter() - start_time
        success = _format_arm_action_success(result)
        _log_arm_action_latency(action_name, elapsed_seconds, result=result, call_type="sync")
        _profile_end(span_token, action=action_name, mode="sync", success=success)
        return result
    raise RuntimeError("robot 不支持同步 do_arm 调用")


async def _do_arm_during_speech(robot, action_name, speech_func, wait_action_before_return=True):
    action_thread = None
    action_result = None
    action_error = None

    def run_action():
        nonlocal action_result, action_error
        try:
            _workflow_action_log("workflow_concurrent_action_thread_start", action_name)
            _publish_hand_gesture_for_arm_action(action_name)
            action_result = _do_arm_sync(robot, action_name)
            _workflow_action_log("workflow_concurrent_action_thread_done", action_name)
        except Exception as exc:
            action_error = exc

    async def finish_action_after_speech():
        _workflow_action_log("workflow_concurrent_action_join_start", action_name)
        await asyncio.to_thread(action_thread.join)
        _workflow_action_log("workflow_concurrent_action_join_done", action_name)
        if action_error is not None:
            print(f"动作执行异常: action={action_name}, error={action_error}")
        else:
            if isinstance(action_result, dict) and not action_result.get("success", True):
                print(f"动作回执失败: action={action_name}, result={action_result}")

        await _release_arm_after_concurrent_speech(robot, action_name)

    def finish_action_after_speech_in_thread():
        _workflow_action_log("workflow_concurrent_action_join_thread_start", action_name)
        action_thread.join()
        _workflow_action_log("workflow_concurrent_action_join_thread_done", action_name)
        if action_error is not None:
            print(f"动作执行异常: action={action_name}, error={action_error}")
        else:
            if isinstance(action_result, dict) and not action_result.get("success", True):
                print(f"动作回执失败: action={action_name}, result={action_result}")

        if action_name not in ARM_ACTIONS_NEED_RELEASE_BEFORE_SPEECH | ARM_ACTIONS_NEED_RELEASE_AFTER_SPEECH:
            return
        release_delay = _env_float("RABBITBOT_ARM_CONCURRENT_RELEASE_DELAY", 0.0)
        if release_delay > 0:
            _workflow_action_log("workflow_concurrent_release_thread_wait_start", action_name, wait=f"{release_delay:.3f}s")
            time.sleep(release_delay)
            _workflow_action_log("workflow_concurrent_release_thread_wait_done", action_name, wait=f"{release_delay:.3f}s")
        _send_release_arm_sync(robot)

    if action_name:
        _workflow_action_log("workflow_concurrent_action_thread_create", action_name)
        action_thread = threading.Thread(target=run_action, daemon=True)
        action_thread.start()

    _workflow_action_log("workflow_concurrent_speech_start", action_name)
    speech_result = speech_func()
    _workflow_action_log("workflow_concurrent_speech_done", action_name)

    if action_thread is None:
        return speech_result

    if wait_action_before_return:
        await finish_action_after_speech()
    else:
        _workflow_action_log("workflow_concurrent_action_join_thread_create", action_name)
        threading.Thread(target=finish_action_after_speech_in_thread, daemon=True).start()
    return speech_result


async def _release_arm_after_concurrent_speech(robot, action_name):
    if action_name not in ARM_ACTIONS_NEED_RELEASE_BEFORE_SPEECH | ARM_ACTIONS_NEED_RELEASE_AFTER_SPEECH:
        return
    release_delay = _env_float("RABBITBOT_ARM_CONCURRENT_RELEASE_DELAY", 0.0)
    if release_delay > 0:
        _workflow_action_log("workflow_concurrent_release_wait_start", action_name, wait=f"{release_delay:.3f}s")
        await asyncio.sleep(release_delay)
        _workflow_action_log("workflow_concurrent_release_wait_done", action_name, wait=f"{release_delay:.3f}s")
    await _send_release_arm(robot)


async def _release_arm_after_speech(robot, action_name):
    if action_name not in ARM_ACTIONS_NEED_RELEASE_AFTER_SPEECH:
        return
    after_speech_delay = _env_float("RABBITBOT_ARM_AFTER_SPEECH_RELEASE_DELAY", 0.0)
    if after_speech_delay > 0:
        _workflow_action_log("workflow_after_speech_release_wait_start", action_name, wait=f"{after_speech_delay:.3f}s")
        await asyncio.sleep(after_speech_delay)
        _workflow_action_log("workflow_after_speech_release_wait_done", action_name, wait=f"{after_speech_delay:.3f}s")
    await _send_release_arm(robot)


async def _ensure_start_position(ctx, start_entity_name="点位1"):
    if getattr(ctx, "start_position_confirmed", False):
        return NavigationStatus.SUCCEEDED

    start_entity = _load_docx_point_entity(start_entity_name) or _load_json_entity(start_entity_name)
    start_points = _extract_location_points(start_entity)
    if not start_points:
        print(f"{start_entity_name}缺少可用导航点位: {start_entity}")
        return NavigationStatus.ABORTED

    enable_navi = os.getenv("RABBITBOT_ENABLE_NAVI", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enable_navi:
        ctx.start_position_confirmed = True
        return NavigationStatus.SUCCEEDED

    if _wait_manual_navigation_success(start_entity_name):
        start_navi_status = NavigationStatus.SUCCEEDED
    else:
        navi_tools = NavigationToolkit(ctx)
        navi_query = NavigationQuery()
        x, y, ox, oy, oz, ow = start_points[0]
        await navi_tools.go_to_async(
            x, y, ox, oy, oz, ow, navi_query,
            waypoints=start_points if len(start_points) > 1 else None,
        )
        while await is_navigating(navi_tools):
            await asyncio.sleep(0.5)
        start_navi_status = await navi_tools.go_to_status()
        await navi_tools.reset_go_to_status()

    if start_navi_status == NavigationStatus.SUCCEEDED:
        ctx.start_position_confirmed = True
        ctx.current_entity_name = start_entity_name
        entity_order = getattr(ctx, 'json_entity_order', None) or JSON_ENTITY_ORDER or getattr(ctx, 'entity_lst', [])
        if start_entity_name in entity_order:
            ctx.current_entity_index = entity_order.index(start_entity_name)

    return start_navi_status


def _wait_manual_navigation_success(location_name):
    if not _workflow_non_integration_enabled():
        return False

    prompt = f"[非联调模式] 请在确认到达“{location_name}”后按任意键，workflow 将视为导航成功..."
    print(prompt, flush=True)
    try:
        import sys
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()
    except Exception:
        input(f"[非联调模式] 请在确认到达“{location_name}”后按回车继续...")
    return True


def _load_combined_data():
    data_file = Path(__file__).resolve().parents[2] / "combined_data.json"
    try:
        return json.loads(data_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"加载 combined_data.json 失败: {exc}")
        return []


def _load_json_entity_order():
    return [item.get("name") for item in _load_combined_data() if item.get("name")]


def _load_json_entity(name):
    for item in _load_combined_data():
        if item.get("name") != name:
            continue
        sentences = item.get("sentences") or []
        description = "".join(sentences)
        return {
            "name": name,
            "summary": sentences[0] if sentences else name,
            "description": description,
            "location": item.get("location") or [],
        }
    return None


def _extract_first_location_point(entity):
    points = _extract_location_points(entity)
    return points[0] if points else None


def _extract_location_points(entity):
    if not entity:
        return []
    location = entity.get("location") if isinstance(entity, dict) else entity
    if isinstance(location, str):
        try:
            location = ast.literal_eval(location)
        except (SyntaxError, ValueError):
            return []
    if isinstance(location, dict):
        location = [location]
    if not isinstance(location, (list, tuple)) or not location:
        return []

    if len(location) >= 6 and not isinstance(location[0], (list, tuple, dict)):
        location = [location]

    points = []
    for item in location:
        if isinstance(item, dict):
            point = [
                item.get("x"),
                item.get("y"),
                item.get("ox"),
                item.get("oy"),
                item.get("oz"),
                item.get("ow"),
            ]
        elif isinstance(item, (list, tuple)) and len(item) >= 6:
            point = list(item[:6])
        else:
            continue
        try:
            points.append(tuple(float(value) for value in point))
        except (TypeError, ValueError):
            continue
    return points


def _prefer_json_entity_location(entity):
    if not isinstance(entity, dict):
        return entity
    name = entity.get("name")
    if not name:
        return entity

    json_entity = _load_json_entity(name)
    json_points = _extract_location_points(json_entity)
    if not json_points:
        return entity

    merged_entity = dict(entity)
    merged_entity["location"] = json_entity["location"]
    if not merged_entity.get("description") and json_entity.get("description"):
        merged_entity["description"] = json_entity["description"]
    if not merged_entity.get("summary") and json_entity.get("summary"):
        merged_entity["summary"] = json_entity["summary"]

    memory_points = _extract_location_points(entity)
    if len(json_points) != len(memory_points):
        print(f"使用 combined_data.json 中的完整导航点位: {name}, points={len(json_points)}")
    return merged_entity


JSON_ENTITY_ORDER = _load_json_entity_order()


COMMON_SURNAMES = [
    "欧阳", "司马", "上官", "诸葛", "东方", "夏侯", "皇甫", "尉迟", "公孙", "司徒",
    "赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫", "蒋", "沈",
    "韩", "杨", "朱", "秦", "尤", "许", "何", "吕", "施", "张", "孔", "曹", "严", "华",
    "金", "魏", "陶", "姜", "戚", "谢", "邹", "喻", "柏", "水", "窦", "章", "云", "苏",
    "潘", "葛", "奚", "范", "彭", "郎", "鲁", "韦", "昌", "马", "苗", "凤", "花", "方",
    "俞", "任", "袁", "柳", "鲍", "史", "唐", "费", "廉", "岑", "薛", "雷", "贺", "倪",
    "汤", "滕", "殷", "罗", "毕", "郝", "邬", "安", "常", "乐", "于", "时", "傅", "皮",
    "卞", "齐", "康", "伍", "余", "元", "卜", "顾", "孟", "平", "黄", "和", "穆", "萧",
    "尹", "姚", "邵", "湛", "汪", "祁", "毛", "禹", "狄", "米", "贝", "明", "臧", "计",
    "伏", "成", "戴", "宋", "庞", "熊", "纪", "舒", "屈", "项", "祝", "董", "梁", "杜",
    "阮", "蓝", "闵", "席", "季", "麻", "强", "贾", "路", "娄", "危", "江", "童", "颜",
    "郭", "梅", "盛", "林", "刁", "钟", "徐", "邱", "骆", "高", "夏", "蔡", "田", "胡",
    "凌", "霍", "虞", "万", "支", "柯", "昝", "管", "卢", "莫", "经", "房", "裘", "缪",
    "干", "解", "应", "宗", "丁", "宣", "邓", "郁", "单", "杭", "洪", "包", "左", "石",
    "崔", "吉", "龚", "程", "邢", "裴", "陆", "荣", "翁", "荀", "羊", "於", "惠", "甄",
    "曲", "家", "封", "芮", "储", "靳", "汲", "邴", "糜", "松", "井", "段", "富", "巫",
    "乌", "焦", "巴", "弓", "牧", "隗", "山", "谷", "车", "侯", "宓", "蓬", "全", "郗",
    "班", "仰", "秋", "仲", "伊", "宫", "宁", "仇", "栾", "暴", "甘", "钭", "厉", "戎",
    "祖", "武", "符", "刘", "詹", "龙", "叶", "幸", "司", "黎", "白", "蒲", "邰", "赖",
    "卓", "蔺", "屠", "蒙", "池", "乔", "阴", "胥", "能", "苍", "闻", "莘", "党", "翟",
    "谭", "贡", "劳", "逄", "姬", "申", "扶", "堵", "冉", "宰", "郦", "雍", "郤", "璩",
    "桑", "桂", "濮", "牛", "寿", "通", "边", "扈", "燕", "冀", "郏", "浦", "尚", "农",
    "温", "别", "庄", "晏", "柴", "瞿", "阎", "充", "慕", "连", "茹", "习", "宦", "艾",
    "鱼", "容", "向", "古", "易", "慎", "戈", "廖", "庾", "终", "暨", "居", "衡", "步",
    "都", "耿", "满", "弘", "匡", "国", "文", "寇", "广", "禄", "阙", "东", "殴", "利",
    "师", "巩", "聂", "晁", "勾", "敖", "融", "冷", "訾", "辛", "阚", "那", "简", "饶",
    "空", "曾", "毋", "沙", "乜", "养", "鞠", "须", "丰", "巢", "关", "蒯", "相", "查",
    "后", "荆", "红", "游", "竺", "权", "逯", "盖", "益", "桓", "公",
]


def _find_common_surname(value):
    for surname in COMMON_SURNAMES:
        if value.startswith(surname):
            return surname
    return ""


def _extract_leader_calling(text):
    text = (text or "").strip()
    normalized_text = re.sub(r"[\s，。！？?、,.!]+", "", text)
    title_candidates = [
        "副总经理", "总经理", "董事长", "副主任", "负责人", "主任", "书记", "部长",
        "院长", "局长", "处长", "科长", "总监", "经理", "教授", "博士", "副总", "总",
    ]

    title = ""
    for candidate in title_candidates:
        if candidate in normalized_text:
            title = candidate
            break

    surname = ""
    for marker in ["免贵姓", "我姓", "姓", "我叫", "叫", "我是", "本人是"]:
        index = normalized_text.find(marker)
        if index < 0:
            continue
        surname = _find_common_surname(normalized_text[index + len(marker):])
        if surname:
            break

    if not surname:
        title_pattern = "|".join(re.escape(candidate) for candidate in title_candidates)
        match = re.search(r"([\u4e00-\u9fff]{1,2})(?:" + title_pattern + r")", normalized_text)
        if match:
            surname = _find_common_surname(match.group(1))

    if surname and title:
        return f"{surname}{title}"
    if surname:
        return f"{surname}领导"
    if title:
        return f"{title}"
    return "领导"


def _parse_first_visit_answer(text):
    normalized_text = re.sub(r"[\s，。！？?、,.!]+", "", text or "")
    if normalized_text == "":
        return "unknown"

    repeat_keywords = [
        "不是第一次", "不止一次", "以前来过", "之前来过", "已经来过", "我来过",
        "来过很多次", "来过好多次", "来过几次", "来过多次", "来过一次", "来过",
        "很多次", "好多次", "好几次", "几次了", "多次", "经常来", "常来",
        "第二次", "第三次", "第四次", "第2次", "第3次", "第4次",
        "不是", "不",
    ]
    first_keywords = [
        "第一次", "首次", "头一次", "初次", "第一回来", "头回来", "刚来", "第一次来",
        "没来过", "没有来过", "从没来过", "从来没来过", "没到过", "没去过", "是第一次",
    ]
    yes_words = {"是", "是的", "对", "对的", "没错", "嗯", "嗯嗯"}
    no_words = {"不是", "不是的", "不", "不对", "没有"}

    # 先判断“非第一次”，避免“不是第一次”被“第一次”误判为 first。
    if any(keyword in normalized_text for keyword in repeat_keywords) or normalized_text in no_words:
        return "repeat"
    if any(keyword in normalized_text for keyword in first_keywords) or normalized_text in yes_words:
        return "first"
    return "unknown"


def _is_empty_stt_text(text):
    return text is None or text.strip() in {"", "<REC_TIMEOUT>", "<REC_STOP>", "Timeout"}


def _start_docx_script_elapsed_timer(ctx, reason="speech_start"):
    if getattr(ctx, "docx_script_elapsed_start_perf", None) is not None:
        return
    ctx.docx_script_elapsed_start_perf = time.perf_counter()
    ctx.docx_script_elapsed_start_ts = _workflow_timestamp()
    ctx.docx_script_elapsed_finish_printed = False
    print(f"DOCX 剧本总计时开始: reason={reason}, start={ctx.docx_script_elapsed_start_ts}")


def _finish_docx_script_elapsed_timer(ctx, reason="script_finished"):
    start_perf = getattr(ctx, "docx_script_elapsed_start_perf", None)
    if start_perf is None:
        print(f"DOCX 剧本总计时无法结束: reason={reason}, start_missing=True")
        return
    if getattr(ctx, "docx_script_elapsed_finish_printed", False):
        return
    elapsed_seconds = time.perf_counter() - start_perf
    ctx.docx_script_elapsed_finish_printed = True
    ctx.docx_script_elapsed_seconds = elapsed_seconds
    start_ts = getattr(ctx, "docx_script_elapsed_start_ts", "")
    print(
        "DOCX 剧本总耗时: "
        f"reason={reason}, start={start_ts}, "
        f"end={_workflow_timestamp()}, elapsed={elapsed_seconds:.3f}s"
    )


async def guide_opening_speech(ctx: Any):
    """Run the speech-only opening guide flow before the main workflow."""

    def set_opening_pending_text(text):
        global pending_user_text
        if _is_empty_stt_text(text):
            return False
        pending_user_text = text.strip()
        print("设置导览开场打断后的下一轮用户输入: " + pending_user_text)
        return True

    def say(text, interruptible=True):
        if _strict_docx_script_enabled():
            _start_docx_script_elapsed_timer(ctx, reason="opening_speech")
        if _strict_docx_script_enabled() and interruptible:
            tts_sound(ctx.tts_agent, text, "zh")
            tts_wait(ctx.tts_agent)
            return False
        if interruptible:
            interrupt_text = tts_long_text_with_stt_stop(ctx.tts_agent, text, ctx.stt_agent, ctx.robot, before_text=None)
            return set_opening_pending_text(interrupt_text)
        tts_sound(ctx.tts_agent, text, "zh")
        tts_wait(ctx.tts_agent)
        return False

    if _strict_docx_script_enabled():
        # PDF 剧本的开场发生在点位1现场；严格剧本模式不在开场前额外导航，避免台词被起点导航阻塞。
        ctx.start_position_confirmed = True
        ctx.current_entity_name = "点位1"
        _workflow_log("严格 DOCX 剧本开场：按 PDF 顺序直接在点位1开始台词，不预先执行起点导航")

    opening_mode = os.getenv("RABBITBOT_OPENING_MODE", "full").strip().lower()
    if opening_mode in {"0", "false", "no", "off", "skip"}:
        print(f"跳过导览开场: RABBITBOT_OPENING_MODE={opening_mode}")
        default_leader_calling = _docx_guide_leader_calling()
        return {
            "leader_calling": default_leader_calling,
            "raw_name_text": "",
            "raw_visit_text": "",
            "first_visit": True,
            "start_entity_name": None,
        }

    if opening_mode != "full":
        short_leader_calling = _docx_opening_text("short_mode_leader_calling")
        if say(_docx_opening_text("short_mode_intro", {"leader_calling": short_leader_calling})):
            return {
                "leader_calling": short_leader_calling,
                "raw_name_text": pending_user_text,
                "raw_visit_text": "",
                "first_visit": True,
                "start_entity_name": None,
            }
        say(_docx_opening_text("short_mode_ready", {"leader_calling": short_leader_calling}), interruptible=False)
        leader_info = {
            "leader_calling": short_leader_calling,
            "raw_name_text": "",
            "raw_visit_text": "",
            "first_visit": True,
            "start_entity_name": None,
        }
        ctx.leader_info = leader_info
        return leader_info

    leader_calling = _docx_guide_leader_calling()
    raw_name_text = leader_calling

    def speak_handshake_opening():
        if say(_docx_opening_text("handshake_greeting", {"leader_calling": leader_calling})):
            return True
        return say(_docx_opening_text("handshake_welcome", {"leader_calling": leader_calling}))

    if await _do_arm_during_speech(ctx.robot, "shake_hand", speak_handshake_opening):
        return {"leader_calling": leader_calling, "raw_name_text": raw_name_text, "raw_visit_text": pending_user_text, "first_visit": True, "start_entity_name": None}
    if await _do_arm_during_speech(ctx.robot, "face_wave", lambda: say(_docx_opening_text("group_welcome", {"leader_calling": leader_calling}))):
        return {"leader_calling": leader_calling, "raw_name_text": raw_name_text, "raw_visit_text": pending_user_text, "first_visit": True, "start_entity_name": None}
    raw_visit_text = ""
    first_visit = True
    if say(_docx_opening_text("follow_intro", {"leader_calling": leader_calling})):
        return {"leader_calling": leader_calling, "raw_name_text": raw_name_text, "raw_visit_text": raw_visit_text, "first_visit": first_visit, "start_entity_name": None}

    start_entity_name = "点位1"
    start_description = ""
    start_entity = _load_json_entity(start_entity_name)
    if start_entity is not None:
        start_description = start_entity.get("description", "")
    else:
        try:
            start_nodes = await ctx.memory.query(query=start_entity_name, group_name="展点", limit=1)
        except Exception as exc:
            print(f"查询起始板块失败: {exc}")
            start_nodes = []
        start_node = start_nodes[0] if start_nodes else None
        if start_node is not None:
            start_description = start_node.attributes.get("description", "") or start_node.attributes.get("describtion", "") or start_node.summary or ""

    if not _strict_docx_script_enabled() and say("好的，我们现在去" + start_entity_name):
        return {"leader_calling": leader_calling, "raw_name_text": raw_name_text, "raw_visit_text": raw_visit_text, "first_visit": first_visit, "start_entity_name": start_entity_name}

    start_navi_status = NavigationStatus.SUCCEEDED
    start_points = _extract_location_points(start_entity)
    start_point = start_points[0] if start_points else None
    enable_navi = os.getenv("RABBITBOT_ENABLE_NAVI", "1").strip().lower() not in {"0", "false", "no", "off"}
    _workflow_log(f"开场导航配置: enable_navi={enable_navi}", verbose=True)
    if _strict_docx_script_enabled():
        _workflow_log("严格 DOCX 剧本已在开场前确认起始板块，跳过重复起始点导航", verbose=True)
    elif enable_navi:
        start_navi_status = NavigationStatus.ABORTED
        if start_point is None:
            _workflow_log(f"起始板块缺少可用导航点位: {start_entity}")
        elif _wait_manual_navigation_success(start_entity_name):
            start_navi_status = NavigationStatus.SUCCEEDED
        else:
            navi_tools = NavigationToolkit(ctx)
            navi_query = NavigationQuery()
            x, y, ox, oy, oz, ow = start_point
            await navi_tools.go_to_async(
                x, y, ox, oy, oz, ow, navi_query,
                waypoints=start_points if len(start_points) > 1 else None,
            )
            while await is_navigating(navi_tools):
                await asyncio.sleep(0.5)
            start_navi_status = await navi_tools.go_to_status()
            _workflow_log(f"开场导航完成: status={start_navi_status}")

    ctx.current_entity_name = start_entity_name
    if start_entity_name in getattr(ctx, "entity_lst", []):
        ctx.current_entity_index = ctx.entity_lst.index(start_entity_name)
    if start_navi_status == NavigationStatus.SUCCEEDED and start_description and not _strict_docx_script_enabled():
        interrupt_text = tts_long_text_with_stt_stop(ctx.tts_agent, start_description, ctx.stt_agent, ctx.robot, before_text)
        set_opening_pending_text(interrupt_text)
    elif start_navi_status != NavigationStatus.SUCCEEDED:
        print(f"起始板块导航未完成，跳过开场介绍: {start_navi_status}")

    leader_info = {
        "leader_calling": leader_calling,
        "raw_name_text": raw_name_text,
        "raw_visit_text": raw_visit_text,
        "first_visit": first_visit,
        "start_entity_name": start_entity_name,
    }
    ctx.leader_info = leader_info
    return leader_info


def create_main_workflow(ctx: Any) -> Workflow:
    """
    Create the main workflow for the RabbitBot agents.
    """
    # Initialize toolkits
    navi_tools = NavigationToolkit(ctx)
    detect_tools = DetectToolkit(ctx)
    # Define agents
    model = ctx.agno_model
    quant_model =  ctx.agno_quant_model
    plan_agent = Agent(
        name='Plan Agent',
        role='Planner',
        instructions=get_inst_plan(ctx.entity_lst),
        # instructions=dedent(f"""\
        #     你是智元机器人公司的具身机器人规划智能体。
        #     给定一个任务，你必须规划完成该任务的下一步操作。
        #     每个子任务应该是以下之一：
        #     - navigation: 寻找或前往某个位置/房间/实体
        #     - chat: 与用户聊天对话，特别是介绍智元公司相关信息
        #     如果任务是寻找或前往某个位置/房间/实体或者需要你介绍智元公司相关的信息，你应该输出"navigation"并输出subtask_description："<位置/房间/实体的名称>"。
        #     如果任务是与用户聊天、询问问题，你应该输出"chat"。
        #     如果子任务无法由任何智能体完成，你应该向用户寻求帮助。
        #     """),
        #response_model=SimpleDelegationTaskModel,
        model=model,
        debug_mode=False,
        add_history_to_messages=False,
        num_history_runs=4,
    )

    navi_check_agent = Agent(
        name='Navigation Plan Agent',
        role='Planner',
        instructions=get_inst_navi_check(ctx.entity_lst),
        model=model,
        debug_mode=False,
        add_history_to_messages=True,
        num_history_runs=5,
    )

    entity_check_agent = Agent(
        name='Entity Check Agent',
        role='Entity checker',
        instructions=dedent("""\
            你是一个实体检查智能体。请根据用户给定的查询请求，从实体列表中选择最相关的实体。实体列表是一个字典类型的数据，包含"""),
        model=model,
    )

    location_name="教育场景"
    node_names= ctx.education_entity_lst
    node_summary=ctx.education_summary_lst
    search_check_agent = Agent(
        name='Search Check Agent',
        role='Search Checker',
        instructions=get_inst_search_check(node_names,node_summary),
        model=model,
        debug_mode=True,
    )

    ctoe_translate_agent = Agent(
        name='English to Chinese Translate Agent',
        role='Translator',
        instructions=get_inst_ctoe_translate(),
        model=model,
        debug_mode=False,
    )

    entity_reranker_agent = Agent(
        name='Entity Reranker Agent',
        role='Entity reranker',
        instructions=dedent("""\
            You are an entity reranker agent.
            Given a task and a list of entities:
                - if there is not any relevant entity, you should output "nothing relevant".
                - if there are multiple relevant entities, you should output the name of the most relevant one.
            Taken the name and description of the entity into account."""),
        model=model,
    )

    task_completion_check_agent = Agent(
        name='Task Completion Check Agent',
        role='Task completion checker',
        instructions=dedent("""\
            You are a task completion checker agent.
            Given the task and all previous step outputs, you must determine if the task is completed"""),
        response_model=CompletionCheckModel,
        model=model,
    )

    #stt_agent = Agent(
    #    name="STT Agent",
    #    model=RealtimeSTT(id="base", modalities=["text"]),
    #)
    #stt_agent = None

    stt_agent = ctx.stt_agent

    #tts_agent = Agent(
    #    name="TTS Agent",
    #    model=RealtimeTTS(id="base", modalities=["text"]),
    #)
    tts_agent = ctx.tts_agent

    chat_bot_name = "机二机器人"

    max_chat_history = workflow_configs["max_chat_history"]
    chat_agent = Agent(
        name='Chat Agent',
        role='Assistant',
        instructions=get_inst_chat(ctx.entity_lst),
        model=model,
        #model=quant_model,
        read_chat_history=False,
        add_history_to_messages=True,
        num_history_runs=max_chat_history,
    )
    post_docx_chat_agent = Agent(
        name='Post DOCX Chat Agent',
        role='Assistant',
        instructions=get_inst_post_docx_chat(),
        model=model,
        read_chat_history=False,
        add_history_to_messages=True,
        num_history_runs=max_chat_history,
    )
    general_vlm_openai = create_general_vlm_openai()

    DOCX_SCRIPT_CONTINUE_TEXTS = {
        "好", "好的", "好啊", "好呀", "嗯", "嗯嗯", "可以", "行", "行的",
        "继续", "继续吧", "接着讲", "接着说", "往下讲", "往下说",
        "收到", "知道了", "明白", "明白了", "没问题",
    }

    def normalize_docx_script_control_text(text):
        return re.sub(r"[\s，。！？?、,.!；;：:\"'“”‘’（）()\[\]【】]+", "", text or "").lower()

    def is_docx_script_continue_text(text):
        return normalize_docx_script_control_text(text) in {
            normalize_docx_script_control_text(item)
            for item in DOCX_SCRIPT_CONTINUE_TEXTS
        }

    def docx_script_in_progress():
        return (
            _strict_docx_script_enabled()
            and hasattr(ctx, "docx_script_step_index")
            and not getattr(ctx, "docx_script_done", False)
        )

    def set_pending_user_text(text):
        global pending_user_text
        if text is None:
            return False
        text = text.strip()
        if text == "":
            return False
        if docx_script_in_progress() and is_docx_script_continue_text(text):
            print(f"忽略剧本继续确认词: {text}")
            return False
        pending_user_text = text
        print(f"设置打断后的下一轮用户输入: {pending_user_text}")
        return True

    def pop_pending_user_text():
        global pending_user_text
        text = pending_user_text
        pending_user_text = ""
        return text

    def set_current_entity_name(name):
        if not name:
            return
        ctx.current_entity_name = name
        entity_order = getattr(ctx, 'json_entity_order', None) or JSON_ENTITY_ORDER or getattr(ctx, 'entity_lst', [])
        if name in entity_order:
            ctx.current_entity_index = entity_order.index(name)
        elif hasattr(ctx, 'entity_lst') and name in ctx.entity_lst:
            ctx.current_entity_index = ctx.entity_lst.index(name)

    def get_next_entity_name():
        entity_order = getattr(ctx, 'json_entity_order', None) or JSON_ENTITY_ORDER or getattr(ctx, 'entity_lst', [])
        if not entity_order:
            return None
        current_name = getattr(ctx, 'current_entity_name', None)
        current_index = getattr(ctx, 'current_entity_index', None)
        if current_index is None:
            if current_name not in entity_order:
                return None
            current_index = entity_order.index(current_name)
        next_index = current_index + 1
        if next_index >= len(entity_order):
            return None
        return entity_order[next_index]

    SCRIPTED_TOUR_STEP_DONE = "<SCRIPTED_TOUR_STEP_DONE>"
    SCRIPTED_TOUR_FINISHED = "<SCRIPTED_TOUR_FINISHED>"
    SCRIPTED_TOUR_ORDER = [
        "起始板块",
        "多功能展示区",
        "园区历史板块",
        "复星集团板块",
        "园区布局板块",
        "园区介绍板块",
        "园区企业介绍板块",
        "智慧园区板块",
        "合影板块",
    ]
    SCRIPTED_TOUR_ACTIONS = {
        "起始板块": "face_wave",
        "多功能展示区": "right_hand_up",
        "园区历史板块": "right_hand_up",
        "复星集团板块": "right_hand_up",
        "园区布局板块": "right_hand_up",
        "园区介绍板块": "right_hand_up",
        "园区企业介绍板块": "right_hand_up",
        "智慧园区板块": "right_hand_up",
        "合影板块": "high_wave",
    }
    DOCX_SCRIPT_POINT_ENTITY = {
        "point_1_to_2_transition": "1->2过渡点位",
        "point_2": "点位2",
        "point_3": "点位3",
        "point_4": "点位4",
        "point_3_to_5_transition": "3->5过渡点位",
        "point_5": "点位5",
    }
    DOCX_SCRIPT_STEPS = _load_docx_script_steps(DOCX_SCRIPT_POINT_ENTITY)

    def scripted_tour_enabled():
        value = os.getenv("RABBITBOT_SCRIPTED_TOUR", "1").strip().lower()
        return value not in {"0", "false", "no", "off", "skip"}

    def init_scripted_tour_state():
        if hasattr(ctx, "scripted_tour_index"):
            return
        entity_order = [name for name in SCRIPTED_TOUR_ORDER if _load_json_entity(name) is not None]
        if not entity_order:
            entity_order = getattr(ctx, "json_entity_order", None) or JSON_ENTITY_ORDER or getattr(ctx, "entity_lst", [])
        ctx.scripted_tour_order = list(entity_order)
        current_name = getattr(ctx, "current_entity_name", None)
        if current_name in ctx.scripted_tour_order:
            ctx.scripted_tour_index = ctx.scripted_tour_order.index(current_name) + 1
        else:
            ctx.scripted_tour_index = 0
        ctx.scripted_tour_arrived_index = None
        ctx.scripted_tour_done = False
        _workflow_log(f"初始化剧本导览状态: index={ctx.scripted_tour_index}, order={ctx.scripted_tour_order}", verbose=True)

    def build_scripted_intro(entity_name):
        leader_info = getattr(ctx, "leader_info", {}) or {}
        leader_calling = leader_info.get("leader_calling") or _docx_guide_leader_calling()
        if entity_name == "合影板块":
            return f"{leader_calling}，请各位移步合影区。"
        return f"{leader_calling}，下面请随我来到{entity_name}。"

    def init_docx_script_state():
        if hasattr(ctx, "docx_script_step_index"):
            return
        ctx.docx_script_step_index = 0
        ctx.docx_script_segment_index = 0
        ctx.docx_script_nav_done_step = None
        ctx.docx_script_done = False
        ctx.docx_script_answers = {}
        ctx.docx_background_commands_started = set()
        if not hasattr(ctx, "docx_script_elapsed_start_perf"):
            ctx.docx_script_elapsed_start_perf = None
            ctx.docx_script_elapsed_start_ts = ""
            ctx.docx_script_elapsed_finish_printed = False
            ctx.docx_script_elapsed_seconds = None
        ctx.docx_total_profile_span = _profile_start("docx_total")
        _workflow_log("初始化 DOCX 剧本演出状态", verbose=True)

    def format_docx_script_text(text):
        leader_info = getattr(ctx, "leader_info", {}) or {}
        leader_calling = leader_info.get("leader_calling") or _docx_guide_leader_calling()
        coffee_order = getattr(ctx, "docx_script_answers", {}).get("coffee_order", "")
        return _format_docx_guide_text(text, {"leader_calling": leader_calling, "coffee_order": coffee_order})

    def _format_command_for_log(command):
        try:
            return shlex.join([str(item) for item in command])
        except Exception:
            return " ".join(str(item) for item in command)

    def _resolve_coffee_delivery_command():
        configured_command = os.getenv("RABBITBOT_COFFEE_DELIVERY_COMMAND", "").strip()
        if configured_command:
            return shlex.split(configured_command), "env"

        candidates = [
            Path("/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/send_delivery_task.py"),
            Path("/workspace/projects/rabbitbot-dev-ros2-master/send_delivery_task.py"),
        ]
        for script_path in candidates:
            if script_path.exists():
                return ["python3", str(script_path), "run"], str(script_path)

        return ["python3", str(candidates[0]), "run"], "host_default_missing"

    def _resolve_docx_background_command(command_spec):
        if command_spec == "coffee_delivery_run":
            return _resolve_coffee_delivery_command()
        if isinstance(command_spec, (list, tuple)):
            return [str(item) for item in command_spec], "segment_list"
        if isinstance(command_spec, str):
            return shlex.split(command_spec), "segment_string"
        raise ValueError(f"不支持的后台命令配置: {command_spec!r}")

    def start_docx_segment_background_command(segment, scene, segment_index, formatted_text):
        command_spec = segment.get("background_command")
        if not command_spec:
            return

        command_name = segment.get("background_command_name") or str(command_spec)
        once_key = segment.get("background_command_once_key")
        started_commands = getattr(ctx, "docx_background_commands_started", set())
        if once_key and once_key in started_commands:
            print(f"DOCX 后台命令跳过重复启动: name={command_name}, scene={scene}, segment={segment_index}, once_key={once_key}")
            return

        try:
            command, source = _resolve_docx_background_command(command_spec)
        except Exception as exc:
            print(f"DOCX 后台命令解析失败: name={command_name}, scene={scene}, segment={segment_index}, error={type(exc).__name__}: {exc}")
            _profile_instant(
                "docx_background_command_resolve_error",
                span="docx_background_command",
                name=command_name,
                scene=scene,
                segment=segment_index,
                error=f"{type(exc).__name__}: {exc}",
            )
            return

        command_timeout = float(segment.get("background_command_timeout") or os.getenv("RABBITBOT_COFFEE_DELIVERY_COMMAND_TIMEOUT", "15"))
        command_text = _format_command_for_log(command)
        span_token = _profile_start(
            "docx_background_command",
            name=command_name,
            scene=scene,
            segment=segment_index,
            command=command_text,
            source=source,
            timeout=command_timeout,
        )
        start_time = time.perf_counter()
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            elapsed_seconds = time.perf_counter() - start_time
            print(f"DOCX 后台命令启动失败: name={command_name}, scene={scene}, segment={segment_index}, command={command_text}, error={type(exc).__name__}: {exc}")
            _profile_end(
                span_token,
                name=command_name,
                scene=scene,
                segment=segment_index,
                status="start_error",
                elapsed=round(elapsed_seconds, 6),
                error=f"{type(exc).__name__}: {exc}",
            )
            return

        if once_key:
            started_commands.add(once_key)
            ctx.docx_background_commands_started = started_commands

        print(f"DOCX 后台命令已启动: name={command_name}, scene={scene}, segment={segment_index}, pid={process.pid}, command={command_text}, source={source}, timeout={command_timeout}")

        def wait_background_command():
            try:
                stdout, stderr = process.communicate(timeout=command_timeout)
                status = "success" if process.returncode == 0 else "error"
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                status = "timeout"
            elapsed_seconds = time.perf_counter() - start_time
            stdout_tail = (stdout or "")[-1000:]
            stderr_tail = (stderr or "")[-1000:]
            print(
                "DOCX 后台命令结束: "
                f"name={command_name}, scene={scene}, segment={segment_index}, "
                f"pid={process.pid}, status={status}, returncode={process.returncode}, "
                f"elapsed={elapsed_seconds:.3f}s, stdout={stdout_tail!r}, stderr={stderr_tail!r}"
            )
            _profile_end(
                span_token,
                name=command_name,
                scene=scene,
                segment=segment_index,
                status=status,
                returncode=process.returncode,
                elapsed=round(elapsed_seconds, 6),
                stdout=stdout_tail,
                stderr=stderr_tail,
            )

        threading.Thread(target=wait_background_command, daemon=True).start()

    def make_docx_interaction_trace(listen_key, scene, segment_index, trace_id=None):
        trace_id = trace_id or f"{listen_key}-{scene}-{segment_index}-{int(time.time() * 1000)}"

        def emit_trace(**fields):
            fields = dict(fields)
            fields.pop("trace_id", None)
            phase = fields.get("phase")
            _profile_instant(
                "interaction_latency",
                span="interaction_latency",
                trace_id=trace_id,
                listen_key=listen_key,
                scene=scene,
                segment=segment_index,
                **fields,
            )
            print(
                f"[{_workflow_timestamp()}] 用户到TTS链路: "
                f"trace_id={trace_id}, listen_key={listen_key}, "
                f"scene={scene}, segment={segment_index}, "
                f"phase={phase}, elapsed_from_listen_start={fields.get('elapsed_from_listen_start')}, "
                f"text={fields.get('text')}, status={fields.get('status')}, "
                f"tts_index={fields.get('tts_index')}"
            )

        return trace_id, emit_trace

    def mark_docx_answer_received(listen_key, scene, segment_index, answer, trace_id=None):
        span_token = _profile_start(
            "answer_to_feedback",
            listen_key=listen_key,
            answer_scene=scene,
            answer_segment=segment_index,
            answer=answer,
            trace_id=trace_id,
        )
        pending_latency = {
            "listen_key": listen_key,
            "scene": scene,
            "segment": segment_index,
            "answer": answer,
            "trace_id": trace_id,
            "received_perf": time.perf_counter(),
            "received_at": _workflow_timestamp(),
            "profile_span": span_token,
        }
        ctx.docx_pending_answer_latency = pending_latency
        _profile_instant(
            "human_answer_received",
            span="listen_answer",
            listen_key=listen_key,
            scene=scene,
            segment=segment_index,
            answer=answer,
            trace_id=trace_id,
        )
        _profile_instant(
            "interaction_latency",
            span="interaction_latency",
            phase="human_answer_accepted",
            trace_id=trace_id,
            listen_key=listen_key,
            scene=scene,
            segment=segment_index,
            answer=answer,
        )
        print(
            f"[{pending_latency['received_at']}] DOCX应答延迟: "
            f"stage=human_answer_received, trace_id={trace_id}, listen_key={listen_key}, "
            f"scene={scene}, segment={segment_index}, answer={answer}"
        )

    def log_docx_feedback_start(scene, segment_index, text):
        pending_latency = getattr(ctx, "docx_pending_answer_latency", None)
        if not pending_latency:
            return
        elapsed_seconds = time.perf_counter() - pending_latency["received_perf"]
        feedback_at = _workflow_timestamp()
        print(
            f"[{feedback_at}] DOCX应答延迟: stage=robot_feedback_tts_start, "
            f"trace_id={pending_latency.get('trace_id')}, "
            f"listen_key={pending_latency['listen_key']}, "
            f"answer_scene={pending_latency['scene']}, answer_segment={pending_latency['segment']}, "
            f"feedback_scene={scene}, feedback_segment={segment_index}, "
            f"elapsed={elapsed_seconds:.3f}s, answer={pending_latency['answer']}, feedback_text={text}"
        )
        _profile_instant(
            "interaction_latency",
            span="interaction_latency",
            phase="feedback_tts_start",
            trace_id=pending_latency.get("trace_id"),
            listen_key=pending_latency["listen_key"],
            answer_scene=pending_latency["scene"],
            answer_segment=pending_latency["segment"],
            feedback_scene=scene,
            feedback_segment=segment_index,
            elapsed_from_answer=round(elapsed_seconds, 6),
            answer=pending_latency["answer"],
            feedback_text=text,
        )
        _profile_end(
            pending_latency.get("profile_span"),
            listen_key=pending_latency["listen_key"],
            answer_scene=pending_latency["scene"],
            answer_segment=pending_latency["segment"],
            feedback_scene=scene,
            feedback_segment=segment_index,
            answer=pending_latency["answer"],
            feedback_text=text,
            trace_id=pending_latency.get("trace_id"),
        )
        ctx.docx_pending_answer_latency = None

    def normalize_coffee_answer(text):
        answer = (text or "").strip()
        for wrong_text in ["老铁", "拿贴", "拿帖", "拿跌"]:
            answer = answer.replace(wrong_text, "拿铁")
        return answer

    def is_valid_coffee_answer(text):
        normalized_text = re.sub(r"[\s，。！？?、,.!；;：:\"'“”‘’（）()\[\]【】]+", "", text or "").lower()
        if normalized_text == "":
            return False

        coffee_keywords = [
            "咖啡", "拿铁", "美式", "热拿铁", "冰拿铁", "热美式", "冰美式",
            "老铁", "拿贴", "拿帖", "拿跌",
            "都可以", "随便", "任选", "一样", "都行", "可以",
        ]
        no_coffee_keywords = [
            "不喝", "不用", "不要", "不需要", "免了", "算了", "不用了", "不要了",
        ]
        return any(keyword in normalized_text for keyword in coffee_keywords + no_coffee_keywords)

    def accept_docx_listen_answer(listen_key, scene, segment_index, answer, trace_id=None):
        if _is_empty_stt_text(answer):
            return False

        answer = answer.strip()
        if listen_key == "coffee_order":
            answer = normalize_coffee_answer(answer)
        elif listen_key == "dog_show_confirmation" and not is_valid_dog_show_confirmation(answer):
            print(f"忽略非机器狗表演确认回答: {answer}")
            return False

        ctx.docx_script_answers[listen_key] = answer
        mark_docx_answer_received(listen_key, scene, segment_index, answer, trace_id=trace_id)
        return True

    def is_valid_dog_show_confirmation(text):
        normalized_text = normalize_docx_script_control_text(text)
        if normalized_text == "":
            return False

        negative_keywords = [
            "不看", "不用", "不要", "不需要", "算了", "别", "先不", "不等",
            "不表演", "不用表演", "别表演", "不可以", "不行", "不是",
        ]
        if any(keyword in normalized_text for keyword in negative_keywords):
            return False

        positive_keywords = [
            "是", "是的", "对", "对的", "好", "好的", "好啊", "好呀",
            "可以", "行", "行的", "没问题", "看", "看看", "看吧",
            "看个节目", "表演", "动起来", "开始吧", "来吧",
        ]
        return any(keyword in normalized_text for keyword in positive_keywords)

    def load_docx_script_entity(entity_name):
        return _load_docx_point_entity(entity_name) or _load_json_entity(entity_name)

    async def speak_docx_script_navigation_segments(step, scene):
        if not step.get("speak_during_navigation"):
            return None

        segments = step.get("segments", [])
        segment_index = getattr(ctx, "docx_script_segment_index", 0)
        segment_count = int(step.get("speak_during_navigation_segments", 0) or 0)
        end_index = min(segment_index + segment_count, len(segments))
        while segment_index < end_index:
            segment = segments[segment_index]
            action_name = segment.get("action")
            speak_with_action = _should_speak_with_action(action_name, segment.get("speak_with_action"))
            if action_name and not speak_with_action:
                await _do_arm_before_speech(ctx.robot, action_name)

            text = segment.get("text", "")
            listen_key = segment.get("listen_key")
            listen_timeout = int(segment.get("listen_timeout", 8))
            early_listen = bool(segment.get("early_listen")) and listen_key
            interrupt_text = None
            listen_answer_handled = False
            if text:
                def speak_segment():
                    _start_docx_script_elapsed_timer(ctx, reason="docx_segment_speech")
                    formatted_text = format_docx_script_text(text)
                    start_docx_segment_background_command(segment, scene, segment_index, formatted_text)
                    log_docx_feedback_start(scene, segment_index, formatted_text)
                    span_token = _profile_start("tts_segment", scene=scene, segment=segment_index, text=formatted_text)
                    try:
                        if early_listen:
                            listen_span = _profile_start("listen_answer", listen_key=listen_key, scene=scene, segment=segment_index, timeout=listen_timeout, early=True)
                            answer = ""
                            trace_id, trace_event = make_docx_interaction_trace(listen_key, scene, segment_index)
                            try:
                                answer = tts_ask_with_early_stt(
                                    tts_agent,
                                    formatted_text,
                                    stt_agent,
                                    timeout=listen_timeout,
                                    stop_tts_on_answer=True,
                                    trace_event=trace_event,
                                    trace_id=trace_id,
                                )
                            finally:
                                _profile_end(listen_span, listen_key=listen_key, scene=scene, segment=segment_index, early=True, answer=answer, trace_id=trace_id)
                            return ("__DOCX_LISTEN_ANSWER__", answer, trace_id)
                        return tts_long_text_with_stt_stop(
                            tts_agent,
                            formatted_text,
                            stt_agent,
                            ctx.robot,
                            before_text,
                            ignored_interrupt_texts=DOCX_SCRIPT_CONTINUE_TEXTS,
                            ignore_unlisted_interrupts=True,
                        )
                    finally:
                        _profile_end(span_token, scene=scene, segment=segment_index, text=formatted_text)

                if speak_with_action:
                    interrupt_text = await _do_arm_during_speech(ctx.robot, action_name, speak_segment)
                else:
                    interrupt_text = speak_segment()

                if isinstance(interrupt_text, tuple) and interrupt_text[0] == "__DOCX_LISTEN_ANSWER__":
                    listen_answer_handled = True
                    accept_docx_listen_answer(
                        listen_key,
                        scene,
                        segment_index,
                        interrupt_text[1],
                        trace_id=interrupt_text[2] if len(interrupt_text) > 2 else None,
                    )
                    interrupt_text = None

            if not speak_with_action:
                await _release_arm_after_speech(ctx.robot, action_name)
            if not _is_empty_stt_text(interrupt_text):
                if is_docx_script_continue_text(interrupt_text):
                    print(f"忽略剧本继续确认词: {interrupt_text}")
                else:
                    print(f"DOCX 剧本被用户打断: scene={scene}, segment={segment_index}, text={interrupt_text}")
                    ctx.docx_script_segment_index = segment_index
                    return "interrupt", interrupt_text.strip()

            segment_index += 1
            ctx.docx_script_segment_index = segment_index
        return None

    async def navigate_docx_script_step(step, step_index):
        entity_name = step.get("entity")
        scene = step.get("scene", entity_name)
        span_token = _profile_start("navigation", step_index=step_index, scene=scene, entity=entity_name)
        if not entity_name:
            _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status=NavigationStatus.SUCCEEDED)
            return NavigationStatus.SUCCEEDED

        if step.get("skip_navigation_if_current") and getattr(ctx, "current_entity_name", None) == entity_name:
            _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status=NavigationStatus.SUCCEEDED, skipped=True)
            return NavigationStatus.SUCCEEDED

        entity = load_docx_script_entity(entity_name)
        if entity is None:
            print(f"DOCX 剧本展点不存在或缺少点位配置: {entity_name}")
            _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status=NavigationStatus.ABORTED, error="entity_missing")
            return NavigationStatus.ABORTED

        location_points = _extract_location_points(entity)
        if not location_points:
            print(f"DOCX 剧本展点缺少可用导航点位: {entity_name}")
            _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status=NavigationStatus.ABORTED, error="location_missing")
            return NavigationStatus.ABORTED
        _workflow_log(f"DOCX 剧本导航目标: step={step_index}, scene={scene}, entity={entity_name}, points={len(location_points)}")

        guide_text = step.get("guide")
        if guide_text:
            formatted_guide_text = format_docx_script_text(guide_text)
            guide_span = _profile_start("tts_segment", scene=step.get("scene", entity_name), segment="guide", text=formatted_guide_text)
            interrupt_text = tts_long_text_with_stt_stop(
                tts_agent,
                formatted_guide_text,
                stt_agent,
                ctx.robot,
                before_text,
                ignored_interrupt_texts=DOCX_SCRIPT_CONTINUE_TEXTS,
                ignore_unlisted_interrupts=True,
            )
            _profile_end(guide_span, scene=step.get("scene", entity_name), segment="guide", text=formatted_guide_text)
            if not _is_empty_stt_text(interrupt_text):
                _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status="interrupt")
                return ("interrupt", interrupt_text.strip())

        enable_navi = os.getenv("RABBITBOT_ENABLE_NAVI", "1").strip().lower() not in {"0", "false", "no", "off"}
        navi_status = NavigationStatus.SUCCEEDED
        if enable_navi:
            if _workflow_non_integration_enabled():
                speech_result = await speak_docx_script_navigation_segments(step, step.get("scene", entity_name))
                if speech_result:
                    _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status="interrupt")
                    return speech_result
                if _wait_manual_navigation_success(entity_name):
                    navi_status = NavigationStatus.SUCCEEDED
            else:
                navi_query = NavigationQuery()
                x, y, ox, oy, oz, ow = location_points[0]
                await navi_tools.go_to_async(
                    x, y, ox, oy, oz, ow, navi_query,
                    waypoints=location_points if len(location_points) > 1 else None,
                )
                speech_result = await speak_docx_script_navigation_segments(step, step.get("scene", entity_name))
                if speech_result:
                    _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status="interrupt")
                    return speech_result
                while await is_navigating(navi_tools):
                    await asyncio.sleep(0.5)
                navi_status = await navi_tools.go_to_status()
                await navi_tools.reset_go_to_status()

        if navi_status == NavigationStatus.SUCCEEDED:
            set_current_entity_name(entity_name)
            ctx.docx_script_nav_done_step = step_index
        _profile_end(span_token, step_index=step_index, scene=scene, entity=entity_name, status=navi_status)
        return navi_status

    async def run_docx_scripted_tour_next_step():
        if pending_user_text:
            return None, None

        init_docx_script_state()
        if getattr(ctx, "docx_script_done", False):
            return None, None

        step_index = getattr(ctx, "docx_script_step_index", 0)
        if step_index >= len(DOCX_SCRIPT_STEPS):
            ctx.docx_script_done = True
            _profile_end(getattr(ctx, "docx_total_profile_span", None), status="finished")
            ctx.docx_total_profile_span = None
            _finish_docx_script_elapsed_timer(ctx, reason="script_index_finished")
            return "done", SCRIPTED_TOUR_FINISHED

        step = DOCX_SCRIPT_STEPS[step_index]
        scene = step.get("scene", f"步骤{step_index + 1}")
        step_span = _profile_start("docx_step", step_index=step_index, scene=scene)
        _workflow_log(f"DOCX 剧本步骤开始: index={step_index}, scene={scene}")

        if getattr(ctx, "docx_script_nav_done_step", None) != step_index:
            nav_result = await navigate_docx_script_step(step, step_index)
            if isinstance(nav_result, tuple) and nav_result[0] == "interrupt":
                _profile_end(step_span, step_index=step_index, scene=scene, status="interrupt")
                return nav_result
            if nav_result != NavigationStatus.SUCCEEDED:
                tts_sound(tts_agent, f"{before_text}很抱歉，我暂时无法到达{step.get('entity', scene)}。", "zh")
                tts_wait(tts_agent)
                ctx.docx_script_step_index = step_index + 1
                ctx.docx_script_segment_index = 0
                ctx.docx_script_nav_done_step = None
                _profile_end(step_span, step_index=step_index, scene=scene, status=nav_result)
                return "done", SCRIPTED_TOUR_STEP_DONE

        segments = step.get("segments", [])
        segment_index = getattr(ctx, "docx_script_segment_index", 0)
        while segment_index < len(segments):
            segment = segments[segment_index]
            action_name = segment.get("action")
            speak_with_action = _should_speak_with_action(action_name, segment.get("speak_with_action"))
            if action_name and not speak_with_action:
                await _do_arm_before_speech(ctx.robot, action_name)

            text = segment.get("text", "")
            listen_key = segment.get("listen_key")
            listen_timeout = int(segment.get("listen_timeout", 8))
            early_listen = bool(segment.get("early_listen")) and listen_key
            interrupt_text = None
            listen_answer_handled = False
            if text:
                def speak_segment():
                    _start_docx_script_elapsed_timer(ctx, reason="docx_segment_speech")
                    formatted_text = format_docx_script_text(text)
                    start_docx_segment_background_command(segment, scene, segment_index, formatted_text)
                    log_docx_feedback_start(scene, segment_index, formatted_text)
                    span_token = _profile_start("tts_segment", scene=scene, segment=segment_index, text=formatted_text)
                    try:
                        if early_listen:
                            listen_span = _profile_start("listen_answer", listen_key=listen_key, scene=scene, segment=segment_index, timeout=listen_timeout, early=True)
                            answer = ""
                            trace_id, trace_event = make_docx_interaction_trace(listen_key, scene, segment_index)
                            try:
                                answer = tts_ask_with_early_stt(
                                    tts_agent,
                                    formatted_text,
                                    stt_agent,
                                    timeout=listen_timeout,
                                    stop_tts_on_answer=True,
                                    trace_event=trace_event,
                                    trace_id=trace_id,
                                )
                            finally:
                                _profile_end(listen_span, listen_key=listen_key, scene=scene, segment=segment_index, early=True, answer=answer, trace_id=trace_id)
                            return ("__DOCX_LISTEN_ANSWER__", answer, trace_id)
                        return tts_long_text_with_stt_stop(
                            tts_agent,
                            formatted_text,
                            stt_agent,
                            ctx.robot,
                            before_text,
                            ignored_interrupt_texts=DOCX_SCRIPT_CONTINUE_TEXTS,
                            ignore_unlisted_interrupts=True,
                        )
                    finally:
                        _profile_end(span_token, scene=scene, segment=segment_index, text=formatted_text)

                if speak_with_action:
                    interrupt_text = await _do_arm_during_speech(ctx.robot, action_name, speak_segment)
                else:
                    interrupt_text = speak_segment()

                if isinstance(interrupt_text, tuple) and interrupt_text[0] == "__DOCX_LISTEN_ANSWER__":
                    listen_answer_handled = True
                    accept_docx_listen_answer(
                        listen_key,
                        scene,
                        segment_index,
                        interrupt_text[1],
                        trace_id=interrupt_text[2] if len(interrupt_text) > 2 else None,
                    )
                    interrupt_text = None

            if not speak_with_action:
                await _release_arm_after_speech(ctx.robot, action_name)
            if not _is_empty_stt_text(interrupt_text):
                if is_docx_script_continue_text(interrupt_text):
                    print(f"忽略剧本继续确认词: {interrupt_text}")
                    segment_index += 1
                    ctx.docx_script_segment_index = segment_index
                    continue
                print(f"DOCX 剧本被用户打断: scene={scene}, segment={segment_index}, text={interrupt_text}")
                ctx.docx_script_segment_index = segment_index
                _profile_end(step_span, step_index=step_index, scene=scene, status="interrupt")
                return "interrupt", interrupt_text.strip()

            if listen_key and not listen_answer_handled:
                listen_span = _profile_start("listen_answer", listen_key=listen_key, scene=scene, segment=segment_index, timeout=listen_timeout)
                answer = audio_input_execute_timeout(stt_agent, timeout=listen_timeout, text="")
                _profile_end(listen_span, listen_key=listen_key, scene=scene, segment=segment_index, answer=answer)
                accept_docx_listen_answer(listen_key, scene, segment_index, answer)

            post_wait_seconds = float(segment.get("post_wait_seconds", 0) or 0)
            if post_wait_seconds > 0:
                await asyncio.sleep(post_wait_seconds)

            segment_index += 1
            ctx.docx_script_segment_index = segment_index

        ctx.docx_script_step_index = step_index + 1
        ctx.docx_script_segment_index = 0
        ctx.docx_script_nav_done_step = None
        _profile_end(step_span, step_index=step_index, scene=scene, status="done")
        _workflow_log(f"DOCX 剧本步骤完成: scene={scene}, next_index={ctx.docx_script_step_index}")
        if ctx.docx_script_step_index >= len(DOCX_SCRIPT_STEPS):
            ctx.docx_script_done = True
            ctx.post_docx_chat_mode = False
            _profile_end(getattr(ctx, "docx_total_profile_span", None), status="finished")
            ctx.docx_total_profile_span = None
            _finish_docx_script_elapsed_timer(ctx, reason="script_finished")
            _workflow_log("DOCX 剧本全部完成，结束 workflow，不进入剧本后问答")
            return "done", SCRIPTED_TOUR_FINISHED
        return "done", SCRIPTED_TOUR_STEP_DONE

    async def run_scripted_tour_next_step():
        if not scripted_tour_enabled():
            return None, None
        if pending_user_text:
            return None, None
        if _strict_docx_script_enabled():
            return await run_docx_scripted_tour_next_step()

        init_scripted_tour_state()
        if getattr(ctx, "scripted_tour_done", False):
            return None, None

        entity_order = getattr(ctx, "scripted_tour_order", [])
        index = getattr(ctx, "scripted_tour_index", 0)
        if index >= len(entity_order):
            ctx.scripted_tour_done = True
            await _do_arm_async_timed(ctx.robot, "high_wave")
            leader_info = getattr(ctx, "leader_info", {}) or {}
            leader_calling = leader_info.get("leader_calling") or _docx_guide_leader_calling()
            tts_sound(tts_agent, f"{before_text}{leader_calling}、各位领导再会，欢迎您再次来到我们人形机器人产业园。", "zh")
            tts_wait(tts_agent)
            return "done", SCRIPTED_TOUR_FINISHED

        entity_name = entity_order[index]
        entity = _load_json_entity(entity_name)
        if entity is None:
            print(f"剧本导览跳过未知展点: {entity_name}")
            ctx.scripted_tour_index = index + 1
            return "done", SCRIPTED_TOUR_STEP_DONE

        _workflow_log(f"剧本导览步骤开始: index={index}, entity={entity_name}")
        already_arrived = (
            getattr(ctx, "scripted_tour_arrived_index", None) == index
            and getattr(ctx, "current_entity_name", None) == entity_name
        )
        if not already_arrived:
            guide_text = build_scripted_intro(entity_name)
            tts_sound(tts_agent, f"{before_text}{guide_text}", "zh")
            tts_wait(tts_agent)

            location_points = _extract_location_points(entity)
            if not location_points:
                print(f"剧本导览展点缺少可用导航点位: {entity}")
                ctx.scripted_tour_index = index + 1
                return "done", SCRIPTED_TOUR_STEP_DONE

            enable_navi = os.getenv("RABBITBOT_ENABLE_NAVI", "1").strip().lower() not in {"0", "false", "no", "off"}
            navi_status = NavigationStatus.SUCCEEDED
            if enable_navi:
                if _wait_manual_navigation_success(entity_name):
                    navi_status = NavigationStatus.SUCCEEDED
                else:
                    navi_query = NavigationQuery()
                    x, y, ox, oy, oz, ow = location_points[0]
                    await navi_tools.go_to_async(
                        x, y, ox, oy, oz, ow, navi_query,
                        waypoints=location_points if len(location_points) > 1 else None,
                    )
                    while await is_navigating(navi_tools):
                        await asyncio.sleep(0.5)
                    navi_status = await navi_tools.go_to_status()
                    await navi_tools.reset_go_to_status()
                _workflow_log(f"剧本导览导航完成: entity={entity_name}, status={navi_status}")

            if navi_status != NavigationStatus.SUCCEEDED:
                tts_sound(tts_agent, f"{before_text}很抱歉，我暂时无法到达{entity_name}。", "zh")
                tts_wait(tts_agent)
                return "done", SCRIPTED_TOUR_STEP_DONE

            set_current_entity_name(entity_name)
            ctx.scripted_tour_arrived_index = index
        else:
            tts_sound(tts_agent, f"{before_text}我们继续刚才的介绍。", "zh")
            tts_wait(tts_agent)

        action_name = SCRIPTED_TOUR_ACTIONS.get(entity_name)
        interrupt_text = None
        description = entity.get("description", "")
        if description:
            def speak_entity_description():
                return tts_long_text_with_stt_stop(tts_agent, description, stt_agent, ctx.robot, before_text)

            if _should_speak_with_action(action_name):
                interrupt_text = await _do_arm_during_speech(ctx.robot, action_name, speak_entity_description)
            else:
                if action_name:
                    await _do_arm_before_speech(ctx.robot, action_name)
                interrupt_text = speak_entity_description()
                await _release_arm_after_speech(ctx.robot, action_name)
        elif action_name:
            await _do_arm_before_speech(ctx.robot, action_name)
            await _release_arm_after_speech(ctx.robot, action_name)
        if not _is_empty_stt_text(interrupt_text):
            print(f"剧本导览被用户打断: entity={entity_name}, text={interrupt_text}")
            return "interrupt", interrupt_text.strip()

        ctx.scripted_tour_index = index + 1
        ctx.scripted_tour_arrived_index = None
        _workflow_log(f"剧本导览步骤完成: entity={entity_name}, next_index={ctx.scripted_tour_index}")
        return "done", SCRIPTED_TOUR_STEP_DONE

    async def audio_input_executor(step_input):
        original_task = step_input.message or ''
        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"original_task: {original_task}", verbose=True)
        _workflow_log(f"previous_steps: {previous_steps}", verbose=True)

        loop_span = _profile_start("loop_iteration", step="audio_input_step")
        text = original_task
        #text = previous_steps.split("===")[-1]
        #text = text[1:]
        _workflow_log(f"text: {text}", verbose=True)

        #tts_sound(tts_agent, f"{before_text}我准备好了，您需要帮助吗？", "zh")
        #tts_sound(tts_agent, "You can chat with me now", "en")
        #tts_fast(tts_agent, "ready")

        text = "请介绍一下深圳这座城市"
        pending_text = pop_pending_user_text()
        if pending_text and docx_script_in_progress() and is_docx_script_continue_text(pending_text):
            print(f"忽略剧本继续确认词: {pending_text}")
            pending_text = ""
        if pending_text:
            out_text = pending_text
            print(f"使用打断输入作为下一轮用户输入: {out_text}")
        else:
            script_kind, script_text = await run_scripted_tour_next_step()
            if script_kind == "done":
                WorkflowTimePoints.PLAN_START = time.time()
                _profile_end(loop_span, step="audio_input_step", result="script_done")
                if script_text == SCRIPTED_TOUR_FINISHED:
                    _profile_summary_print(reason="docx_finished")
                return StepOutput(content=f"{script_text}")
            if script_kind == "interrupt":
                out_text = script_text
                print(f"使用剧本导览打断输入作为用户输入: {out_text}")
            else:
                time.sleep(1)
                #out_text = audio_input_execute(stt_agent, "speech_to_text", timeout=300)
                audio_span = _profile_start("audio_input", source="main_loop", timeout=30)
                try:
                    out_text = audio_input_execute_timeout(stt_agent, timeout=30, text="")
                finally:
                    _profile_end(audio_span, source="main_loop", timeout=30)
                while out_text == "<REC_TIMEOUT>" or out_text == "<REC_DUPLICATE>":
                    tts_sound(tts_agent, f"{before_text}你好，请问你需要我做什么吗？", "zh")
                    audio_span = _profile_start("audio_input", source="main_loop_retry", timeout=30)
                    try:
                        out_text = audio_input_execute_timeout(stt_agent, timeout=30, text="")
                    finally:
                        _profile_end(audio_span, source="main_loop_retry", timeout=30)
        chat_queue.put(out_text, "用户")

        #tts_sound(tts_agent, f"{before_text}我听到了，但是可能要思考一会。请稍等片刻", "zh")
        think_type = identify_think_type(out_text)
        tts_fast(tts_agent, think_type)

        WorkflowTimePoints.PLAN_START = time.time()

        _profile_end(loop_span, step="audio_input_step", result="user_input")
        return StepOutput(content=f"{out_text}")

    audio_input_step = Step(
        name='audio_input_step',
        description='Audio input from the user.',
        executor=audio_input_executor,
    )

    plan_step = Step(
        name='plan_step',
        agent=plan_agent,
        description='Plan the next step to complete the task.',
    )

    async def plan_executor(step_input):
        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"previous_steps: {previous_steps}", verbose=True)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")

        _workflow_log(f"in_text: {text}", verbose=True)
        if text in {SCRIPTED_TOUR_STEP_DONE, SCRIPTED_TOUR_FINISHED}:
            _workflow_log(f"plan_executor: scripted tour control token {text}, skip planner", verbose=True)
            return StepOutput(content=text)
        if getattr(ctx, "post_docx_chat_mode", False):
            _workflow_log("plan_executor: post DOCX chat mode, skip guide planner", verbose=True)
            return await chat_executor(step_input)
        history_text = chat_queue.build_history()
        text =  history_text
        _workflow_log(f"in_text: {text}", verbose=True)
        rule_task = classify_task_by_rule(text_lst[2].replace("\n", ""))
        if rule_task == "C":
            _workflow_log("plan_executor: rule classified as chat", verbose=True)
            return await chat_executor(step_input)
        if rule_task == "N":
            _workflow_log("plan_executor: rule classified as navigation", verbose=True)
            return await navi_check_executor(step_input)
        if rule_task == "V":
            _workflow_log("plan_executor: rule classified as view", verbose=True)
            return await view_executor(step_input)

        start_time = time.time()
        plan_llm_span = _profile_start("plan_llm")
        #run_response = plan_agent.run(text, session_id=str(PLAN_SESSION_ID))
        #out_text = run_response.content
        response_stream = plan_agent.run(
            text, stream=True, stream_intermediate_steps=False,
            session_id=str(PLAN_SESSION_ID)
        )
        out_text = ""
        for event in response_stream:
            if event.event == "RunResponseContent":
                #print(f"Content: {event.content}")
                out_text += event.content
            elif event.event == "ToolCallStarted":
                _workflow_log(f"Tool call started: {event.tool}", verbose=True)
            elif event.event == "ReasoningStep":
                _workflow_log(f"Reasoning step: {event.content}", verbose=True)
            if len(out_text) > 0:
                break
        duration  = time.time() - start_time
        _workflow_log(f"out_text: {out_text}", verbose=True)
        log_text = f"plan_executor: plan_duration {duration:.3f}, text {out_text}"
        _workflow_log(log_text, verbose=True)
        file_logger.debug(log_text)
        _profile_end(plan_llm_span, output=out_text)

        planner_choice = (out_text or "").strip()[:1].upper()
        if planner_choice == "C":
            response = await chat_executor(step_input)
        elif planner_choice == "N":
            response = await navi_check_executor(step_input)
        elif planner_choice == "V":
            response = await view_executor(step_input)
        else:
            # The planner is intentionally conservative: ordinary dialogue should
            # remain usable even if the routing model returns an empty or noisy token.
            print(f"plan_executor: invalid planner output {out_text!r}, fallback to chat")
            response = await chat_executor(step_input)

        return response

    plan_step_v2 = Step(
        name='plan_step',
        description='Plan the next step to complete the task.',
        executor=plan_executor,
    )

    def is_chinese(s):
        #return all('\u4e00' <= ch <= '\u9fff' for ch in s)
        return '\u4e00' <= s[0] <= '\u9fff'

    def is_english(s):
        #return all('a' <= ch.lower() <= 'z' for ch in s if ch.isalpha())
        return 'a' <= s[0].lower() <= 'z'

    async def chat_execute(text, sess_idx=None, navi_tools=None):
        _workflow_log(f"chat_execute: text {text}", verbose=True)
        if is_chinese(text): lang = "zh"
        elif is_english(text): lang = "en"
        else:
            lang = "zh"
            #print(f"Unkown lanugage")
            #out_text = "<CHAT_UNKOWN_LANG>"
            #return StepOutput(content=f"{out_text}")
        _workflow_log(f"lang: {lang}", verbose=True)
        if text == "<REC_TIMEOUT>":
            out_text = text
            return StepOutput(content=f"{out_text}")

        tts_wait(tts_agent)

        WorkflowTimePoints.CHAT_START = time.time()
        chat_llm_span = _profile_start("chat_llm")
        chat_tts_span = None
        active_chat_agent = post_docx_chat_agent if getattr(ctx, "post_docx_chat_mode", False) else chat_agent
        if sess_idx is not None:
            _workflow_log(f"chat_agent: session_id {str(sess_idx)}", verbose=True)
            _workflow_log(f"chat_agent: text {text}", verbose=True)
            response_stream = active_chat_agent.run(
                text, stream=True, stream_intermediate_steps=False,
                session_id=str(sess_idx)
            )
        else:
            response_stream = active_chat_agent.run(
                text, stream=True, stream_intermediate_steps=False,
            )

        speecher_start_event = threading.Event()
        speecher_stop_event = threading.Event()
        listener_stop_event = threading.Event()
        interrupt_text_holder = {"text": ""}

        def stop_task():
            while True:
                time.sleep(1)
                while not speecher_start_event.is_set():
                    time.sleep(1)
                print("聊天正式开始，可以输入停止命令了") if lang == "zh" else print("You can say stop now")
                if False:
                    #text = "停止说话"
                    #input_dict = {"task": "speech_to_text_async", "lang": lang, "text": "", "timeout": 60}

                    #run_response = stt_agent.run(
                    #   json.dumps(input_dict), stream=False, stream_intermediate_steps=False,
                    #)
                    #out_text = run_response.content

                    #out_text = stt_agent.run(json.dumps(input_dict))

                    out_text = audio_input_execute_timeout(stt_agent, timeout=30)
                    #out_text = ""

                    print("收到命令：", out_text) if lang == "zh" else print("Got command:", out_text)
                    if out_text.startswith("停止") or "停" in out_text or "stop" in out_text.lower():
                        speecher_stop_event.set()
                        break
                if listener_stop_event.is_set():
                    _workflow_log("监听线程收到信号量，退出", verbose=True)
                    break
                if True:
                    resp_msg = audio_input_stop_chat(stt_agent)
                    if resp_msg == "<STOP_CHAT>":
                        print("收到停止口令，退出")
                        speecher_stop_event.set()
                        break
                    elif resp_msg != "<UNKNOWN_MSG>":
                        print("收到用户打断输入，退出当前回答：", resp_msg)
                        interrupt_text_holder["text"] = resp_msg
                        speecher_stop_event.set()
                        break
                if listener_stop_event.is_set():
                    _workflow_log("监听线程收到信号量，退出", verbose=True)
                    break

        speecher_stop_thread = threading.Thread(target=stop_task)
        speecher_stop_thread.start()

        global last_chat_text
        out_text = ""
        last_chat_text = ""
        num_setence = 0
        for event in response_stream:
            if event.event == "RunResponseContent":
                #print(f"Content: {event.content}")
                out_text += event.content
            elif event.event == "ToolCallStarted":
                _workflow_log(f"Tool call started: {event.tool}", verbose=True)
            elif event.event == "ReasoningStep":
                _workflow_log(f"Reasoning step: {event.content}", verbose=True)

            if speecher_stop_event.is_set():
                tts_stop(tts_agent)
                time.sleep(0.5)
                _workflow_log("已经停止说话了" if lang == "zh" else "Chatting stopped", verbose=True)
                break
            if navi_tools is not None:
                if not await is_navigating(navi_tools):
                    _workflow_log("导航达到，停止生成文本", verbose=True)
                    break

            #print(f"OutText: {out_text}")
            out_text = out_text
            if out_text.endswith("，") or out_text.endswith("；") or \
                out_text.endswith("。") or out_text.endswith("？") or out_text.endswith("！") or \
                out_text.endswith(".") or out_text.endswith("!") or out_text.endswith("\n"):
                _workflow_log(f"out_text: {out_text}", verbose=True)
                action_name = None

                if out_text.startswith("[A:"):
                    ei = out_text.index("]")
                    text_len = len(out_text[ei+1:])
                else:
                    text_len = len(out_text)

                _workflow_log(f"text_len: {text_len}", verbose=True)
                if text_len < 8:
                    continue

                if out_text.startswith("[A:"):
                    ei = out_text.index("]")
                    _workflow_log(f"ei: {ei}", verbose=True)
                    action_name = out_text[3:ei]
                    _workflow_log(f"action_name: {action_name}", verbose=True)
                    out_text = out_text[ei+1:]
                    _workflow_log(f"out_text: {out_text}", verbose=True)
                #time.sleep(10)

                if is_chinese(out_text):
                    lang = "zh"
                elif is_english(out_text):
                    lang = "en"
                else:
                    lang = "zh"
                    print(f"Unkown lanugage: {lang}")
                WorkflowTimePoints.CHAT_FIRST_TEXT_START = time.time()
                first_infer_time = WorkflowTimePoints.CHAT_FIRST_TEXT_START - WorkflowTimePoints.CHAT_START
                WorkflowTimePoints.CHAT_START = WorkflowTimePoints.CHAT_FIRST_TEXT_START
                log_text = f"chat_executor: seq_idx {num_setence}, infer_time {first_infer_time:.3f}, text {out_text}"
                _workflow_log(log_text, verbose=True)
                file_logger.debug(log_text)
                #tts_index = tts_sound(tts_agent, f"{before_text}" + out_text.strip(), lang)
                if chat_tts_span is None:
                    chat_tts_span = _profile_start("chat_tts")
                tts_index = tts_sound(tts_agent, out_text.strip(), lang)
                speecher_start_event.set()
                if navi_tools is not None:
                    go_to_status = await navi_tools.go_to_status()
                    if go_to_status == NavigationStatus.PENDING or go_to_status == NavigationStatus.SUCCEEDED:
                        if action_name is not None:
                            if action_name == "shake_hand":
                                #await handshake_execute_v2(ctx)
                                action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                            else:
                                action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                else:
                    if action_name is not None:
                        if action_name == "shake_hand":
                            #await handshake_execute_v2(ctx)
                            action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                        else:
                            action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                last_chat_text += out_text
                out_text = ""
                num_setence += 1
                #if num_setence > 3:
                #    break

        _profile_end(chat_llm_span, sentence_count=num_setence)

        remaining_text = out_text.strip()
        if remaining_text and not speecher_stop_event.is_set():
            _workflow_log(f"remaining out_text: {remaining_text}", verbose=True)
            action_name = None
            if remaining_text.startswith("[A:") and "]" in remaining_text:
                ei = remaining_text.index("]")
                action_name = remaining_text[3:ei]
                remaining_text = remaining_text[ei+1:].strip()
                _workflow_log(f"remaining action_name: {action_name}", verbose=True)

            if remaining_text:
                if is_chinese(remaining_text):
                    lang = "zh"
                elif is_english(remaining_text):
                    lang = "en"
                else:
                    lang = "zh"
                    print(f"Unkown lanugage: {lang}")
                WorkflowTimePoints.CHAT_FIRST_TEXT_START = time.time()
                first_infer_time = WorkflowTimePoints.CHAT_FIRST_TEXT_START - WorkflowTimePoints.CHAT_START
                WorkflowTimePoints.CHAT_START = WorkflowTimePoints.CHAT_FIRST_TEXT_START
                log_text = f"chat_executor: seq_idx {num_setence}, infer_time {first_infer_time:.3f}, text {remaining_text}"
                _workflow_log(log_text, verbose=True)
                file_logger.debug(log_text)
                if chat_tts_span is None:
                    chat_tts_span = _profile_start("chat_tts")
                tts_index = tts_sound(tts_agent, remaining_text, lang)
                speecher_start_event.set()
                if action_name is not None:
                    action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                last_chat_text += remaining_text
                num_setence += 1

        if False:
            go_to_status = await navi_tools.go_to_status()
            if go_to_status == NavigationStatus.PENDING or go_to_status == NavigationStatus.SUCCEEDED:
                if "自我介绍" in text or "你好" in text or "您好" in text:
                    time.sleep(0.6)
                    await _do_arm_async_timed(ctx.robot, "face_wave")

        #out_text = run_response.content
        chat_queue.put(last_chat_text, "机器人")
        out_text = ""
        #print(f"OutText: {out_text}")

        #tts_wait(tts_agent)
        while True:
            time.sleep(0.5)
            if speecher_stop_event.is_set():
                _workflow_log("收到停止或打断命令，准备退出聊天", verbose=True)
                tts_stop(tts_agent)
                break
            if navi_tools is not None:
                if not await is_navigating(navi_tools):
                    _workflow_log("导航达到，停止等待语音", verbose=True)
                    break
            if tts_get_wav_count(tts_agent) == 0:
                _workflow_log("WAV播完，退出聊天", verbose=True)
                break
        if chat_tts_span is not None:
            _profile_end(chat_tts_span, sentence_count=num_setence)
        listener_stop_event.set()
        speecher_start_event.set()
        #audio_input_execute(stt_agent, "stop")
        audio_input_execute(stt_agent, "stop_async")
        speecher_stop_thread.join()

        return interrupt_text_holder["text"]

    class ChatSessionInfo:
        sess_idx: int = CHAT_SESSION_ID

    async def chat_loop_execute(text, navi_tools=None):
        max_chat_steps = workflow_configs["max_chat_steps"]
        for i in range(max_chat_steps):
            if text is None:
                if navi_tools is None:
                    text = audio_input_execute_timeout(stt_agent, timeout=60)
                else:
                    text = await audio_input_execute_timeout_navi(stt_agent, 60, navi_tools)
            if text == "<REC_TIMEOUT>" or text == "<NAVI_REACH>" or text == "<REC_DUPLICATE>":
                break
            if "停止聊天" in text:
                break
            #if i > 0:
            #    think_type = identify_think_type(text)
            #    tts_fast(tts_agent, think_type)
            interrupt_text = await chat_execute(text, ChatSessionInfo.sess_idx, navi_tools)
            if set_pending_user_text(interrupt_text):
                break
            text = None
        out_text = "Chat loop finish"
        #ChatSessionInfo.sess_idx += 1
        return out_text

    async def chat_executor(step_input):
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        _workflow_log(f"chat_executor: plan_time: {plan_time:.3f}", verbose=True)
        original_task = step_input.message or ''
        previous_step = step_input.get_last_step_content()
        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"original_task: {original_task}", verbose=True)
        _workflow_log(f"previous_step: {previous_step}", verbose=True)
        _workflow_log(f"previous_steps: {previous_steps}", verbose=True)

        #text = previous_step.split("=")[2][1:-1]
        #text = previous_step.subtask_description
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")
        _workflow_log(f"chat_input_text: {text}", verbose=True)
        #text = str(previous_step)
        #text = text.split("=")[2][1:-1]
        #text = str(original_task)
        #text = ""
        #print("text:", text)

        #out_text = await chat_execute(text)
        out_text = await chat_loop_execute(text)

        return StepOutput(content=f"{out_text}")

    async def vln_execute(ctx):
        tts_sound(tts_agent, f"{before_text}下面我将展示我的动态导航功能", "zh")
        while True:
            tts_sound(tts_agent, f"{before_text}请告诉我你想让我找什么？", "zh")
            audio_input_text = audio_input_execute_timeout(stt_agent, 300)
            task = audio_input_text
            _workflow_log(f"task: {task}", verbose=True)

            run_response = ctoe_translate_agent.run(task)
            out_text = run_response.content
            _workflow_log(f"out_text: {out_text}", verbose=True)

            task = out_text
            _workflow_log(f"task: {task}", verbose=True)
            await ctx.robot.vln(task)

    def load_mock_view_image():
        image_path = os.getenv(
            "RABBITBOT_MOCK_IMAGE",
            str(Path(__file__).resolve().parents[2] / "tests" / "tasks" / "resources" / "frig.jpg"),
        )
        image = cv2.imread(image_path)
        if image is not None:
            print(f"使用 mock 视觉图片: {image_path}")
            return image

        print(f"mock 视觉图片不存在或无法读取: {image_path}，使用内置测试图")
        image = np.full((720, 1280, 3), 245, dtype=np.uint8)
        cv2.rectangle(image, (120, 180), (520, 520), (80, 160, 240), -1)
        cv2.rectangle(image, (700, 220), (1080, 500), (80, 190, 120), -1)
        cv2.putText(image, "orange display board", (150, 560), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2)
        cv2.putText(image, "green robot area", (720, 540), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2)
        return image

    async def view_execute(ctx, task):
        _workflow_log(f"view task: {task}", verbose=True)
        view_mode = os.getenv("RABBITBOT_VIEW_MODE", "mock").strip().lower()
        if view_mode == "robot":
            out_text = await ctx.robot.view(task)
        else:
            image = load_mock_view_image()
            prompt = dedent(f"""\
                你是机二机器人的视觉问答模块。请根据图片内容回答用户问题。
                用户问题：{task}

                要求：
                - 用中文回答。
                - 回答要简短、自然，适合机器人直接说出来。
                - 如果图片中看不清或无法确定，请明确说明。
            """)
            messages, extra_body = general_vlm_openai.prepare_message_for_vllm([image], prompt)
            out_text = general_vlm_openai.get_chat_response(messages, extra_body)
        _workflow_log(f"view out_text: {out_text}", verbose=True)
        chat_queue.put(out_text, "机器人")
        tts_sound(tts_agent, f"{before_text}{out_text}", "zh")
        return out_text

    async def move_execute(ctx):
        tts_sound(tts_agent, f"{before_text}下面我将展示我的转向能力", "zh")
        while True:
            tts_sound(tts_agent, f"{before_text}请按回车键向左转", "zh")
            input("请按回车键继续")
            out_text = await ctx.robot.move(2)
            tts_sound(tts_agent, f"{before_text}请按回车键向右转", "zh")
            input("请按回车键继续")
            out_text = await ctx.robot.move(3)

    async def sound_execute(ctx):
        tts_sound(tts_agent, f"下面我将展示我的语音说话功能，我会重复你说的话", "zh")
        while True:
            audio_input_text = audio_input_execute_timeout(stt_agent, 300)
            tts_sound(tts_agent, f"{audio_input_text}", "zh")

    async def vln_executor(step_input):
        await vln_execute(ctx)
        response = 'VLN completed.'
        yield StepOutput(
            content=response,
        )

    async def view_executor(step_input):
        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"view previous_steps: {previous_steps}", verbose=True)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        task = text_lst[2].replace("\n", "")
        await view_execute(ctx, task)
        response = 'VLM completed.'
        return StepOutput(
            content=response,
        )

    async def move_executor(step_input):
        await move_execute(ctx)
        response = 'Move completed.'
        yield StepOutput(
            content=response,
        )

    async def sound_executor(step_input):
        await sound_execute(ctx)
        response = 'Sound completed.'
        yield StepOutput(
            content=response,
        )

    async def unknown_executor(step_input):
        #tts_fast(tts_agent, "sorry")
        arm_lst = ["否定拒绝", "双手平摊开掌心向上"]
        n = len(arm_lst)
        rand_n = random.randint(0, n-1)
        await _do_arm_async_timed(ctx.robot, arm_lst[rand_n])
        tts_fast(tts_agent, "unknown")
        out_text = "<WORKFLOW_UNKOWN>"
        return StepOutput(content=f"{out_text}")

    navigation_routines = {
        'slam_vln': dedent("""\
            1. call go_to with the (x, y) of the target entity
            2. call dynamic_navigation to get close and face the target entity"""),
        'vln': dedent("""\
            1. call dynamic_navigation to complete the task"""),
    }
    navigation_agents: dict[str, Agent] = {}
    for routine, instruction in navigation_routines.items():
        navigation_agents[routine] = Agent(
            name='Navigation Agent ({})'.format(routine),
            role='Navigator',
            instructions=dedent("""\
                You are a navigation agent of a embodied robot.
                Given a task, you must use the navigation tool to complete.
                Routine:
                """ + instruction),
            tools=[navi_tools],
            model=model,
            show_tool_calls=True,
        )

    def _normalize_nav_text(text):
        text = (text or "").strip()
        replacements = {
            "复新": "复星",
            "负星": "复星",
            "福星": "复星",
            "合营": "合影",
            "合迎": "合影",
            "和影": "合影",
            "合映": "合影",
            "合应": "合影",
            "合英": "合影",
            "和迎": "合影",
            "合音": "合影",
            "资源": "智元",
            "自原": "智元",
            "自愿": "智元",
            "原区": "园区",
            "骑石": "起始",
            "骑士": "起始",
            "骑是": "起始",
            "奇石": "起始",
            "奇士": "起始",
            "启示": "起始",
            "其实": "起始",
            "其是": "起始",
            "起事": "起始",
            "趣奇石": "去起始",
            "趣骑士": "去起始",
            "趣起始": "去起始",
            "去骑石": "去起始",
            "去骑士": "去起始",
            "去奇石": "去起始",
            "骑石板块": "起始板块",
            "骑士板块": "起始板块",
            "骑是板块": "起始板块",
            "奇石板块": "起始板块",
            "奇士板块": "起始板块",
            "启示板块": "起始板块",
            "其实板块": "起始板块",
            "其是板块": "起始板块",
            "起事板块": "起始板块",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return re.sub(r"[\s，。！？?、,.!]+", "", text)

    def _has_any(text, keywords):
        return any(keyword in text for keyword in keywords)

    def is_chat_info_request(text):
        text = _normalize_nav_text(text)
        chat_keywords = ["介绍", "讲讲", "说明", "了解", "是什么", "有什么", "内容", "功能", "特色", "怎么样"]
        return _has_any(text, chat_keywords) and not has_navigation_action(text)

    def has_navigation_action(text):
        text = _normalize_nav_text(text)
        direct_keywords = [
            "我要去", "我想去", "带我去", "带我们去", "带着我去", "带着我们去",
            "去", "前往", "过去", "导航到", "走到", "参观", "逛一下",
        ]
        return _has_any(text, direct_keywords)

    def is_visual_request(text):
        text = _normalize_nav_text(text)
        visual_keywords = [
            "你看到了什么", "你看到什么", "你现在看到什么", "前面有什么",
            "画面里有什么", "图片里有什么", "桌子上有什么", "桌上有什么",
            "帮我看一下", "看一下前面", "看看前面", "看一下画面", "看看画面",
            "识别一下", "视觉理解",
        ]
        return _has_any(text, visual_keywords)

    def is_direct_navigation_request(text):
        return has_navigation_action(text)

    def is_next_board_request(text):
        text = _normalize_nav_text(text)
        next_keywords = [
            "去下一个板块", "下一个板块", "下一板块", "下个板块",
            "去下一个展点", "下一个展点", "下一展点",
            "下一站", "去下一站", "继续下一个", "下一个地方",
        ]
        return _has_any(text, next_keywords)

    def classify_task_by_rule(text):
        if is_visual_request(text):
            return "V"
        if is_chat_info_request(text):
            return "C"
        if has_navigation_action(text):
            return "N"
        return None

    def resolve_navigation_entity_by_fuzzy(text, entity_lst):
        normalized_text = _normalize_nav_text(text)
        if normalized_text == "":
            return None, 0.0

        remove_words = [
            "我要去", "我想去", "带我去", "带我们去", "带着我去", "带着我们去",
            "请", "帮我", "导航到", "走到", "前往", "过去", "去", "参观", "看看", "看一看", "看一下", "逛一下",
        ]
        target_text = normalized_text
        for word in remove_words:
            target_text = target_text.replace(word, "")

        best_entity = None
        best_score = 0.0
        for entity_name in entity_lst:
            normalized_entity = _normalize_nav_text(entity_name)
            if not normalized_entity:
                continue
            if normalized_entity in normalized_text or normalized_entity in target_text:
                return entity_name, 1.0
            if target_text and target_text in normalized_entity:
                score = max(0.85, len(target_text) / max(len(normalized_entity), 1))
            else:
                score = max(
                    difflib.SequenceMatcher(None, normalized_text, normalized_entity).ratio(),
                    difflib.SequenceMatcher(None, target_text, normalized_entity).ratio() if target_text else 0.0,
                )
            if score > best_score:
                best_entity = entity_name
                best_score = score

        if best_score >= 0.62:
            return best_entity, best_score
        return None, best_score

    async def navi_execute(
        subtask_description,
        skip_confirm=False,
    ):
        nodes = await ctx.memory.query(query=subtask_description, group_name="展点", limit=5)
        _workflow_log(f"nodes: {nodes}", verbose=True)
        #import pdb; pdb.set_trace()
        entities = [
            _prefer_json_entity_location({
                'name': node.name,
                'summary': node.summary,
                'location': node.attributes.get('location', ''),
                'description': node.attributes.get('description', ''),
            })
            for node in nodes
        ]

        rerank_prompt = dedent("""\
            Task: "{task_description}"
            Entities: {entities}""").format(
            task_description=subtask_description,
            entities=entities,
        )
        _workflow_log(f"rerank_prompt: {rerank_prompt}", verbose=True)
        # response_iterator = await entity_reranker_agent.arun(
        #     rerank_prompt, stream=True, stream_intermediate_steps=True,
        # )
        # async for event in response_iterator:
        #     yield event

        # response = entity_reranker_agent.run_response
        # entity_name = response.content.strip()
        entity_name = nodes[0].name
        _workflow_log(f"entity_name: {entity_name}", verbose=True)
        entity = next(
            (e for e in entities if e['name'] == entity_name), None
        )
        if entity:
            entity = {
                'name': entity['name'],
                'summary': entity['summary'],
                'location': entity['location'],
                'description': entity['description']
            }
            navigation_prompt = dedent("""\
                Task: "{task_description}"
                Target: {entity}""").format(
                task_description=subtask_description,
                entity=entity,
            )
            #import pdb; pdb.set_trace()
            console = ctx.console
            # Get the live display instance from the console
            #live = console._live

            # Stop the live display temporarily so we can ask for user confirmation
            #live.stop()  # type: ignore

            # Ask for confirmation only when the user's navigation intent is ambiguous.
            if skip_confirm:
                print(f"用户已明确要求前往，跳过导航确认: {entity['name']}")
                tts_sound(tts_agent, f"好的，我们现在去{entity['name']}", "zh")
                tts_wait(tts_agent)
                message = "y"
            else:
                #tts_sound(tts_agent, f"{before_text}你是否想去往{entity['name']}", "zh")
                #tts_sound(tts_agent, f"{before_text}要不要我带你去{entity['name']}看看吧", "zh")
                guide_go_to_text = build_guide_go_to_text(entity['name'])
                tts_sound(tts_agent, guide_go_to_text, "zh")
                tts_wait(tts_agent)
                #message = (
                #    Prompt.ask("Do you want to go to the {}?".format(entity['name']), choices=["y", "n"], default="y")
                #    .strip()
                #    .lower()
                #)
                #live.start()
                message = audio_input_yes_or_no_ignore_echo(stt_agent, guide_go_to_text, entity['name'])
                #message = input("请输入 y/n 来开启或取消导航：")
                while message != "y" and message != "n":
                    #tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你是否想去往{entity['name']}", "zh")
                    tts_fast(tts_agent, "sorry")
                    tts_sound(tts_agent, guide_go_to_text, "zh")
                    tts_wait(tts_agent)
                    message = audio_input_yes_or_no_ignore_echo(stt_agent, guide_go_to_text, entity['name'])

            #import pdb; pdb.set_trace()
            # If the user does not want to continue, raise a StopExecution exception
            if message != "y":
                #live.stop()
                # Ask for confirmation
                #message = (
                #    Prompt.ask("I cannot find the target in my memory. Do you want to go to the target by dynamic navigation?", choices=["y", "n"], default="y")
                #    .strip()
                #    .lower()
                #)
                chat_queue.put("不用了。", "用户")
                tts_fast(tts_agent, "cancel")
                #tts_sound(tts_agent, f"{before_text}那需要我动态寻找{entity['name']}吗", "zh")
                #message = audio_input_yes_or_no(stt_agent)
                message = "n"
                while message != "y" and message != "n":
                    tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。我不知道{entity['name']}在哪里，需要我动态寻找吗", "zh")
                    message = audio_input_yes_or_no(stt_agent)
                if message == "y":
                    navigation_prompt = subtask_description
                    #response = await navigation_tools.dynamic_navigation(navigation_prompt)
                    response = 'Dynamic navigation completed.'
                    tts_sound(tts_agent, f"{before_text}动态寻找已完成", "zh")
                    #live.start()
                else:
                    response = "Unable to reach the place the user wants to go!"
            else:
                entity_name = entity['name']
                set_current_entity_name(entity_name)
                #tts_sound(tts_agent, f"{before_text}好的，我即将前往{entity_name}", "zh")
                #tts_sound(tts_agent, f"{before_text}我已经知道了{entity_name}在哪里了，下面我带你去", "zh")
                #tts_sound(tts_agent, f"{before_text}好的，下面我带你去{entity_name}", "zh")
                tts_fast(tts_agent, "naviguide")
                _workflow_log(f"entity location: {entity['location']}", verbose=True)
                location_points = _extract_location_points(entity)
                if not location_points:
                    print(f"展点缺少可用导航点位: {entity}")
                    return "Unable to reach the place the user wants to go!"
                x, y, ox, oy, oz, ow = location_points[0]
                enable_navi = os.getenv("RABBITBOT_ENABLE_NAVI", "1").strip().lower() not in {"0", "false", "no", "off"}
                _workflow_log(f"workflow enable_navi: {enable_navi}", verbose=True)
                if enable_navi:
                    if _wait_manual_navigation_success(entity_name):
                        navi_status = NavigationStatus.SUCCEEDED
                    else:
                        # v1
                        #response = await navigation_tools.go_to(x, y, yaw)
                        # v2
                        navi_query = NavigationQuery()
                        await navi_tools.go_to_async(
                            x, y, ox, oy, oz, ow, navi_query,
                            waypoints=location_points if len(location_points) > 1 else None,
                        )
                        # v3
                        #await navigation_tools.go_to(x, y, ox, oy, oz, ow)

                        #navi_status = navi_query.get_status()
                        enable_chat = False
                        while await is_navigating(navi_tools):
                            if enable_chat:
                                #tts_sound(tts_agent, f"{before_text}现在你可以和我聊天哟", "zh")
                                tts_fast(tts_agent, "navichat")
                                #audio_input_text = audio_input_execute(stt_agent, "speech_to_text_async", timeout=30)
                                audio_input_text = await audio_input_execute_timeout_navi(stt_agent, 30, navi_tools)
                                if audio_input_text != "<REC_TIMEOUT>" and audio_input_text != "<NAVI_REACH>":
                                    #tts_sound(tts_agent, f"{before_text}我听到了，让我想一想", "zh")
                                    think_type = identify_think_type(audio_input_text)
                                    tts_fast(tts_agent, think_type)
                                    #await chat_execute(audio_input_text)
                                    await chat_loop_execute(audio_input_text, navi_tools)
                            #navi_status = navi_query.get_status()

                        navi_status = await navi_tools.go_to_status()
                else:
                    #time.sleep(10.0)
                    navi_status = NavigationStatus.SUCCEEDED
                if navi_status == NavigationStatus.SUCCEEDED and "礼品" not in entity['name']:
                    enable_intro_description = True
                    if enable_intro_description:
                        #tts_sound(tts_agent, f"{before_text}我已经到达了，一会再聊", "zh")
                        #tts_sound(tts_agent, f"{before_text}下面我为你介绍{entity_name}", "zh")
                        time.sleep(0.1)
                        #tts_index = tts_sound(tts_agent, f"{before_text}请往这边看", "zh")
                        time.sleep(0.5)
                        #tts_sound(tts_agent, f"{before_text}{entity['description']}", "zh")
                        #action_with_tts(ctx.robot, "右手摆动（先内向后向外）", tts_agent, tts_index)
                        #text = f"{before_text}{entity['description']}"
                        text = f"{entity['description']}"
                        interrupt_text = tts_long_text_with_stt_stop(tts_agent, text, stt_agent, ctx.robot, before_text)
                        if set_pending_user_text(interrupt_text):
                            response = f"Interrupted by user: {interrupt_text}"
                            return response
                        #time.sleep(4.0)
                        #await ctx.robot.do_arm_async("右手摆动（先内向后向外）")

                        #tts_sound(tts_agent, f"{before_text}我介绍完了", "zh")

                    #target_group_name = "教育场景"
                    target_group_name = "人形机器人科研场景"
                    enable_game_execute = True
                    if target_group_name in entity['name'] and enable_game_execute:
                        location_name = target_group_name
                        entity_lst = await ctx.memory.get_group_names(location_name)
                        summary_lst= await ctx.memory.get_group_summary(location_name)
                        #recommand_entity_lst = random.sample(entity_lst, 3)
                        recommand_entity_lst = random.sample(entity_lst, 2)
                        entity_prompt = build_stt_prompt_by_list(recommand_entity_lst)
                        #tts_sound(tts_agent, f"{before_text}除了我刚才的介绍，这里还有{entity_prompt}等具体板块，需要我为再做详细的介绍吗？", "zh")
                        #message = audio_input_yes_or_no(stt_agent)
                        message = "y"
                        while message != "y" and message != "n":
                            #tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你是否想去往{entity['name']}", "zh")
                            tts_fast(tts_agent, "sorry")
                            tts_sound(tts_agent, f"{before_text}还需要我为您详细介绍这个地方吗？", "zh")
                            message = audio_input_yes_or_no(stt_agent)
                        if message == "y":
                            #tts_sound(tts_agent, f"{before_text}下面我和你玩个小游戏", "zh")
                            await game_execute(ctx, target_group_name)
                            await thank_chat_execute(ctx)
                            input("请按回车键带用户去礼品处")
                            tts_sound(tts_agent, f"{before_text}好啊，没问题，跟我来", "zh")

                    #tts_sound(tts_agent, f"{before_text}我可以带你继续参观，你有想去的地方吗？或者和我聊天也可以。", "zh")
                    #tts_sound(tts_agent, f"{before_text}我们继续吧", "zh")

                    response = 'Navigation to ({}, {}) successful.'.format(x, y)
                    await navi_tools.reset_go_to_status()
                elif navi_status == NavigationStatus.SUCCEEDED and "礼品" in entity['name']:
                    tts_sound(tts_agent, f"{before_text}我马上到达了，一会再聊", "zh")
                    #await grab_execute(ctx)
                    response = 'Navigation to ({}, {}) successful.'.format(x, y)
                    await navi_tools.reset_go_to_status()
                else:
                    tts_sound(tts_agent, f"{before_text}很抱歉，我无法到达目的地", "zh")
                    response = 'Navigation to ({}, {}) failed.'.format(x, y)
            _workflow_log(f"response: {response}", verbose=True)
        else:
            console = ctx.console
            # Get the live display instance from the console
            #live = console._live

            # Stop the live display temporarily so we can ask for user confirmation
            #live.stop()  # type: ignore

            # Ask for confirmation
            #message = (
            #    Prompt.ask("Do you want to go to the target by dynamic navigation?", choices=["y", "n"], default="y")
            #    .strip()
            #    .lower()
            #)
            #live.start()
            #tts_sound(tts_agent, f"{before_text}你需要我去动态寻找吗", "zh")
            #message = audio_input_yes_or_no(stt_agent)
            message = "n"
            while message != "y" and message != "n":
                tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你需要我去动态寻找吗", "zh")
                message = audio_input_yes_or_no(stt_agent)

            # If the user does not want to continue, raise a StopExecution exception
            if message != "y":
                response = "Unable to reach the place the user wants to go!"
            else:
                navigation_prompt = task.subtask_description
                #response = await navigation_tools.dynamic_navigation(navigation_prompt)
                response = 'Dynamic navigation completed.'
                tts_sound(tts_agent, f"{before_text}动态寻找已完成", "zh")
        return response

    async def navi_executor(
        step_input: StepInput,
    ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        #task: DelegationTaskModel = step_input.previous_step_content
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        _workflow_log(f"chat_executor: plan_time: {plan_time:.3f}", verbose=True)

        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"previous_steps: {previous_steps}", verbose=True)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")
        #subtask_description = task.subtask_description
        subtask_description = text

        response = await navi_execute(subtask_description)

        yield StepOutput(
            content=response,
        )

    async def navi_check_execute(input_text):
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        _workflow_log(f"chat_executor: plan_time: {plan_time:.3f}", verbose=True)

        global last_chat_text
        _workflow_log(f"last_chat_text: {last_chat_text}", verbose=True)
        #print("input_text:", "机器人："  + last_chat_text + "用户："  + input_text)
        #input_text_with_chat = "机器人："  + last_chat_text + "用户："  + input_text
        history_text = chat_queue.build_history(max_count=4)
        input_text_with_chat = history_text
        _workflow_log(f"input_text_with_chat: {input_text_with_chat}", verbose=True)
        navi_check_span = _profile_start("navi_check")
        run_response = navi_check_agent.run(input_text_with_chat, session_id=str(NAVI_CHECK_SESSION_ID))
        _profile_end(navi_check_span)
        out_text = run_response.content
        _workflow_log(f"out_text: {out_text}", verbose=True)
        out_text = out_text.split("\n")[0]
        WorkflowTimePoints.NAVI_CHECK_END = time.time()
        navi_check_time = WorkflowTimePoints.NAVI_CHECK_END - WorkflowTimePoints.NAVI_CHECK_START
        _workflow_log(f"navi_check_execute: navi_check_time: {navi_check_time:.3f}", verbose=True)

        num_entity = 1
        recommand_entity_lst = random.sample(ctx.entity_lst, num_entity)

        if out_text[0] == "A":
            try:
                if len(out_text) > 1:
                    out_text = out_text[1:]
                    if out_text[0].isdigit():
                        entity_idx = int(out_text)
                        # 添加边界检查
                        if entity_idx < len(ctx.entity_lst):
                            out_text = ctx.entity_lst[entity_idx]
                            # 注意：不在这里放入队列，navi_execute 会处理确认询问
                        else:
                            out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
                else:
                    out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
            except (ValueError, IndexError) as exc:
                out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
        elif out_text[0].isdigit():
            entity_idx = int(out_text)
            if entity_idx < len(ctx.entity_lst):
                out_text = ctx.entity_lst[entity_idx]
            else:
                out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
        elif out_text[0] == "B":
            out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
            chat_queue.put(out_text, "机器人")
        elif out_text[0] == "D":
            out_text = f"{before_text}请告诉我你想去什么地方？这里有 {recommand_entity_lst} 等板块可以参观"
            chat_queue.put(out_text, "机器人")
        elif out_text[0] == "C":
            n = len(ctx.entity_lst)
            rand_n = random.randint(0, n-1)
            out_text = ctx.entity_lst[rand_n]
            # 注意：不在这里放入队列，navi_execute 会处理确认询问
        _workflow_log(f"out_text: {out_text}", verbose=True)

        if is_next_board_request(input_text):
            next_entity_name = get_next_entity_name()
            if next_entity_name is not None:
                _workflow_log(f"next board request resolved to: {next_entity_name}", verbose=True)
                out_text = next_entity_name
                response = await navi_execute(out_text, skip_confirm=True)
                return response
            out_text = f"{before_text}已经是最后一个板块了"
            tts_sound(tts_agent, f"{out_text}", "zh")
            return out_text

        fuzzy_entity = None
        fuzzy_score = 0.0
        if out_text not in ctx.entity_lst and is_direct_navigation_request(input_text):
            fuzzy_entity, fuzzy_score = resolve_navigation_entity_by_fuzzy(input_text, ctx.entity_lst)
            if fuzzy_entity is not None:
                _workflow_log(f"导航目标模糊匹配: input={input_text}, entity={fuzzy_entity}, score={fuzzy_score:.3f}", verbose=True)
                out_text = fuzzy_entity

        if out_text in ctx.entity_lst:
            response = await navi_execute(out_text, skip_confirm=is_direct_navigation_request(input_text))
        else:
            if is_direct_navigation_request(input_text):
                out_text = f"{before_text}抱歉，我没听清你想去哪里，可以再说一遍吗？"
            tts_sound(tts_agent, f"{out_text}", "zh")
            response = out_text

        return response

    async def navi_check_executor(step_input):
        WorkflowTimePoints.NAVI_CHECK_START = time.time()
        previous_steps = step_input.get_all_previous_content()
        _workflow_log(f"previous_steps: {previous_steps}", verbose=True)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")

        #think_type = identify_think_type(text)
        #tts_fast(tts_agent, think_type)
        out_text = await navi_check_execute(text)

        return StepOutput(content=f"{out_text}")

    async def game_execute(ctx: Any, location_name: str, entity_name = None):
        # TODO: Navigate to the game location
        entity_lst = await ctx.memory.get_group_names(location_name)
        summary_lst= await ctx.memory.get_group_summary(location_name)
        entity_prompt = build_stt_prompt_by_list(entity_lst)

        # TODO: while循环等待用户提问
        tts_index = -1
        while True:
            # TODO: 语音等待用户提问
            #tts_sound(tts_agent, f"{before_text}请告诉我你想要找什么", "zh")
            if tts_index >= 0:
                wait_with_tts(tts_agent, tts_index)
            if entity_name is None:
                tts_fast(tts_agent, "introguide")
                tts_sound(tts_agent, f"{before_text}您还需要我介绍什么吗？", "zh")
                audio_input_text = audio_input_execute_timeout(stt_agent, 30, entity_prompt)
            else:
                audio_input_text = entity_name
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                continue
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                break
            # TODO: 如果用户结束游戏，则退出循环
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            audio_input_text = audio_input_text.replace("原", "圆")
            print(audio_input_text)

            # 异步调用语音：例如：“我听到了，让我来找一找”、“我听到了，让我来想一想”
            answer_templates = [
                f"{before_text}好嘞，我听到了，让我来介绍一下",
                f"{before_text}好呀，请往这里看，我来给你讲讲",
                f"{before_text}明白了，我来给你介绍这个",
                f"{before_text}没问题，我来详细介绍一下",
                f"{before_text}明白，我来给你讲解一下这个"
            ]
            answer_template = np.random.choice(answer_templates)
            tts_sound(tts_agent, f"{answer_template}", "zh")

            # 添加查询检查
            search_response = search_check_agent.run(audio_input_text)

            search_response_text = search_response.content
            print(f"Agent判断的名称为：{search_response_text}")

            # 根据用户提问调用detect_tool.detect_location，并返回结果
            # audio_input_text = ctx.vlm_openai.prepare_correction_text_message_for_vllm(audio_input_text)
            # 异步执行memory查询
            memory_query_task = asyncio.create_task(ctx.memory.query(query=search_response_text, group_name=location_name, limit=1))
            # 在do_finger之前同步等待memory查询结果
            nodes = await memory_query_task
            memory_node = nodes[0]
            if memory_node.name == '异常结点':
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我无法找到你想要找的物品", "zh")
                continue

            #{round(location[0], 1)}, {round(location[1], 1)}, {round(location[2], 1)}
            #tts_index = tts_sound(tts_agent, f"{before_text}太好了，我找到了！下面我给你介绍{memory_node.name}", "zh")
            description = memory_node.attributes.get('description', '')
            #tts_sound(tts_agent, f"找到了哦，我指给你看，{description}", "zh")
            interrupt_text = tts_long_text_with_stt_stop(tts_agent, description, stt_agent, ctx.robot, before_text)
            if set_pending_user_text(interrupt_text):
                return
            #tts_index = tts_sound(tts_agent, f"{before_text}我介绍完了", "zh")

            summary = memory_node.summary
            print("summary", summary)
            location = detect_tools.detect_location({'task': summary})
            # 判断是否没有识别到或者识别到多个物品
            if location[0] == 0 or location[1] == 0 or location[2] == 0:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我无法找到你想要找的物品", "zh")
                continue
            elif location[0] == -1 or location[1] == -1 or location[2] == -1:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找到了多个相似物品，可以再描述一下吗", "zh")
                continue
            # TODO: 根据location[0], location[1], location[2]，调用ctx.robot.do_finger
            ctx.robot.do_finger(location[0], location[1], location[2])
            do_finger_check = False
            if do_finger_check:
                time.sleep(0.5)
                finger_status = await ctx.robot.do_finger_status_async()
                print(f"finger_status: {finger_status}")
                while finger_status == -1:
                    time.sleep(0.5)
                    finger_status = await ctx.robot.do_finger_status_async()
                    print(f"finger_status: {finger_status}")
                if finger_status == 1:
                    tts_index = tts_sound(tts_agent, f"{before_text}太好了，逆解成功了！", "zh")
                elif finger_status == 0:
                    tts_index = tts_sound(tts_agent, f"{before_text}糟糕，逆解失败了。", "zh")

            if entity_name is not None:
                break

            #input("请按回车键描述衣服")
            #time.sleep(1)
            #tts_index = tts_sound(tts_agent, f"{before_text}您穿的是青色衣服，显得很有活力！", "zh")

            #message = input("请按 y/n 开启或退出下一轮识别：")
            message = "y"
            if message == "y":
                break

    async def game_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await game_execute(ctx, "人形机器人科研场景")
        response = 'Game completed.'
        yield StepOutput(
            content=response,
        )

    navigation_check_step = Step(
        name='navigation_check_step',
        description='Check navigation goal.',
        executor=navi_check_executor,
    )

    navigation_check_step = Step(
        name='navigation_check_step',
        description='Check navigation goal.',
        executor=navi_check_executor,
    )

    async def grab_execute(ctx: Any, yaw=0, pitch=25):
        while True:
            # tts_fast(tts_agent, "introguide")
            #tts_sound(tts_agent, f"{before_text}下面我来展示抓篮子功能，我准备好了！请按回车键继续", "zh")
            #audio_input_text = audio_input_execute_timeout(stt_agent, 120)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            audio_input_text = input("按回车键继续")
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                return
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                return
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            # tts_sound(tts_agent, f"{before_text}有的，请您挑选", "zh")
            await ctx.robot.do_head_async(yaw=0, pitch=25)
            # time.sleep(5)
            await asyncio.sleep(2)
            locations = detect_tools.detect_key_point_pixel({'task': ''})
            #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

            await ctx.robot.do_grab_async(locations[0], locations[1], locations[2])
            # Wait and monitor location changes for 5 seconds
            start_time = time.time()
            old_location = locations
            threshold = 0.2  # Distance threshold for location change detection

            catch_status = await ctx.robot.do_grab_status_async()
            while time.time() - start_time < 30 and catch_status != 1:
                await asyncio.sleep(1)

                new_location = detect_tools.detect_key_point_pixel({'task': ''})
                print(time.time(), new_location[1], old_location[1])
                # Calculate distance between old and new locations
                distance = abs(new_location[1] - old_location[1])
                print(f"distance: {distance}, threshold: {threshold}, new_location: {new_location}, old_location: {old_location}")
                if distance > threshold and new_location[2] - old_location[2] < 0.2 and new_location[0] - old_location[0] > -0.2:
                    print(f"Location changed significantly (distance: {distance}), re-grabbing...")
                    #tts_sound(tts_agent, f"{before_text}唉,有人在捣乱，让我重新定位并抓取一下", "zh")
                    tts_sound(tts_agent, f"{before_text}唉，有人在捣乱！", "zh")
                    # TODO: 发送停止指令
                    await ctx.robot.do_grab_cancel_async()
                    await asyncio.sleep(4)

                    new_location = detect_tools.detect_key_point_pixel({'task': ''})
                    await ctx.robot.do_grab_async(new_location[0], new_location[1], new_location[2])
                    old_location = new_location
                    await asyncio.sleep(4)
                    break
                catch_status = await ctx.robot.do_grab_status_async()
            # tts_sound(tts_agent, f"{before_text}我要开抓", "zh")
            tts_sound(tts_agent, f"{before_text}这是给您的小礼物 ，欢迎您再次来智元参观", "zh")
            await asyncio.sleep(1)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            await asyncio.sleep(1)
            await ctx.robot.do_head_async(yaw=30, pitch=0)
            await asyncio.sleep(3)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            input("请按回车键开启下一轮抓取测试")

    async def grab_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await grab_execute(ctx)
        response = 'Grab completed.'
        yield StepOutput(
            content=response,
        )

    grab_step = Step(
        name='grab_step',
        description='Grab the object.',
        executor=grab_executor,
    )

    async def handshake_execute(ctx: Any, yaw=0, pitch=25):
        while True:
            # tts_fast(tts_agent, "introguide")
            tts_sound(tts_agent, f"{before_text}下面我来展示握手功能，我准备好了！我等你的命令", "zh")
            audio_input_text = audio_input_execute_timeout(stt_agent, 120)
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                return
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                return
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            tts_sound(tts_agent, f"{before_text}好的", "zh")
            # await ctx.robot.do_head_async(yaw=yaw, pitch=pitch)
            # time.sleep(5)
            locations = detect_tools.detect_hand_location()
            #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

            if locations[0] == 0 or locations[1] == 0 or locations[2] == 0:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找不到你的手呢", "zh")
                continue

            await ctx.robot.do_handshake_async(locations[0], locations[1], locations[2] + 0.1)
            input("请按回车键开启下一轮握手测试")

    async def handshake_execute_v2(ctx: Any, yaw=0, pitch=25):
        # await ctx.robot.do_head_async(yaw=yaw, pitch=pitch)
        # time.sleep(5)
        locations = detect_tools.detect_hand_location()
        #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

        if locations[0] == 0 or locations[1] == 0 or locations[2] == 0:
            tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找不到你的手呢", "zh")
        else:
            await ctx.robot.do_handshake_async(locations[0], locations[1], locations[2] + 0.1)

    async def handshake_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await handshake_execute(ctx)
        response = 'Handshake completed.'
        yield StepOutput(
            content=response,
        )

    handshake_step = Step(
        name='handshake_step',
        description='Handshake with man.',
        executor=handshake_executor,
    )

    navigation_step = Step(
        name='navigation_step',
        description='Use static or dynamic navigation to complete the task.',
        executor=navi_executor,
    )

    game_step = Step(
        name='game_step',
        description='Play a game with the user.',
        executor=game_executor,
    )

    chat_step = Step(
        name='chat_step',
        description='Chat with the user.',
        executor=chat_executor,
    )

    vln_step = Step(
        name='vln_step',
        description='Navigation with VLN.',
        executor=vln_executor,
    )

    view_step = Step(
        name='view_step',
        description='View.',
        executor=view_executor,
    )

    move_step = Step(
        name='move_step',
        description='Move.',
        executor=move_executor,
    )

    sound_step = Step(
        name='sound_step',
        description='Sound.',
        executor=sound_executor,
    )

    unknown_step = Step(
        name='unknown_step',
        description='Unkown what to do.',
        executor=unknown_executor,
    )

    async def thank_chat_execute(ctx):
        input("请按回车键夸奖用户")
        await _do_arm_async_timed(ctx.robot, "比耶")
        tts_sound(tts_agent, f"{before_text}感谢你的夸奖！很高兴能为你导览。", "zh")
        tts_sound(tts_agent, f"{before_text}您今天的青色衣服也太帅了！", "zh")

    async def thank_chat_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await thank_chat_execute(ctx)
        response = 'Chat completed.'
        yield StepOutput(
            content=response,
        )

    thank_chat_step = Step(
        name='thank_chat_step',
        description='Chat with the user.',
        executor=thank_chat_executor,
    )

    def simple_delegate_task(step_input: StepInput) -> List[Step]:
        task: SimpleDelegationTaskModel = step_input.previous_step_content

        if task.t == 'N':
            #return [navigation_step]
            return [navigation_check_step]
        # elif task.t == 'vision':
        #     return [vision_step]
        elif task.t == 'C':
            return [chat_step]
        elif task.t == 'V':
            return [view_step]
        elif task.t == 'G':
            return [game_step]
        elif task.t == 'O':
            return [unknown_step]

    def delegate_task(step_input: StepInput) -> List[Step]:
        task: DelegationTaskModel = step_input.previous_step_content

        if task.agent_name == 'navigation':
            return [navigation_step]
        # elif task.agent_name == 'vision':
        #     return [vision_step]
        elif task.agent_name == 'chat':
            return [chat_step]
        elif task.agent_name == 'game':
            return [game_step]

    router_step = Router(
        name='task_router',
        selector=simple_delegate_task,
        choices=[navigation_step, chat_step, view_step, game_step],
        description="Delegate the task to the appropriate agent based on the task description.",
    )

    async def task_completion_check(
        step_input: StepInput,
    ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        completion_span = _profile_start("completion_check")
        original_task = step_input.message or ''
        previous_steps = step_input.get_all_previous_content()

        if getattr(ctx, "post_docx_chat_mode", False):
            result = StepOutput(content=CompletionCheckModel(task_completed=False))
            _profile_end(completion_span, skipped=True)
            return result
        if SCRIPTED_TOUR_FINISHED in previous_steps:
            result = StepOutput(content=CompletionCheckModel(task_completed=True))
            _profile_summary_print(reason="docx_finished_loop_breaker")
            _profile_end(completion_span, skipped=True, task_completed=True)
            return result
        if SCRIPTED_TOUR_STEP_DONE in previous_steps:
            result = StepOutput(content=CompletionCheckModel(task_completed=False))
            _profile_end(completion_span, skipped=True)
            return result

        prompt = dedent("""\
            Task: "{task_description}"
            Previous Steps: {previous_steps}""").format(
            task_description=original_task,
            previous_steps=previous_steps,
        )

        result = await task_completion_check_agent.arun(
            prompt, stream=True, stream_intermediate_steps=True,
        )
        _profile_end(completion_span)
        return result

    def loop_breaker(outputs: List[StepOutput]) -> bool:
        if not outputs:
            return False

        for output in outputs:
            if isinstance(output.content, CompletionCheckModel):
                if output.content.task_completed:
                    _profile_summary_print(reason="loop_breaker_completed")
                    return True

        return False

    return Workflow(
        name='RabbitBot Main Workflow',
        description='Workflow for general tasks',
        steps=[
            Loop(
                name='Task Loop',
                steps=[
                    #vln_step,
                    #game_step,
                    #grab_step,
                    #view_step,
                    #handshake_step,
                    #move_step,
                    #sound_step,
                    #thank_chat_step,
                    audio_input_step,
                    #plan_step,
                    #router_step,
                    plan_step_v2,
                    task_completion_check,
                ],
                max_iterations=100,
                end_condition=loop_breaker,
            )
        ],
    )

    # - action: If the prompt mentions "action", to perform an action such as wavehands, greet, ask a question, etc.
    # If the task is to perform an action such as wavehands, greet, ask a question, etc, you should output "action".
    # action_chooser_agent = Agent(
    #     name='Action Chooser Agent',
    #     role='Action chooser',
    #     instructions=dedent("""\
    #         You are an action chooser agent.
    #         Given the action task, you must choose whether to use action such as wavehands, greet to complete the task."""),
    #     response_model=ActionModel,
    #     model=model,
    # )

    # async def action_executor(
    #     step_input: StepInput,
    # ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
    #     task: DelegationTaskModel = step_input.previous_step_content
    #     await action_chooser_agent.arun(task.subtask_description)
    #     response = action_chooser_agent.run_response
    #     choice: ActionModel = action_chooser_agent.run_response.content
    #     print(choice.choice)
    #     if choice.choice == 'wavehands':
    #         pass
    #         return StepOutput(
    #             content=choice.choice,
    #             response=response,
    #         )
    #     elif choice.choice == 'greet':
    #         pass
    #         return StepOutput(
    #             content=choice.choice,
    #             response=response,
    #         )

    # action_step = Step(
    #     name='action_step',
    #     description='Use action executor to complete the task.',
    #     executor=action_executor,
    # )
