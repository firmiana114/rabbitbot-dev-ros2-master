from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil


class DialogueError(RuntimeError):
    """Raised when a dialogue file cannot be loaded or saved."""


def resolve_dialogue_path(dialogue_dir: Path, dialogue_index: str, dialogue_file: Path | None = None) -> Path:
    if dialogue_file is not None:
        return dialogue_file
    index = str(dialogue_index).strip() or "0"
    if not index.isdigit():
        raise DialogueError(f"导览台词序号必须是数字：{index}")
    return dialogue_dir / f"dialogue_{index}.json"


def _summary(data: dict, path: Path) -> dict:
    variables = data.get("variables", {}) or {}
    steps = data.get("steps", []) or []
    points = data.get("points", {}) or {}
    segment_count = 0
    for step in steps:
        if isinstance(step, dict):
            segments = step.get("segments", []) or []
            if isinstance(segments, list):
                segment_count += len(segments)
    return {
        "path": str(path),
        "leader_calling": str(variables.get("leader_calling") or "").strip(),
        "map_file": str(data.get("map_file") or "").strip(),
        "steps": len(steps) if isinstance(steps, list) else 0,
        "segments": segment_count,
        "points": len(points) if isinstance(points, dict) else 0,
    }


def validate_dialogue_data(data: object, path: Path) -> dict:
    if not isinstance(data, dict):
        raise DialogueError(f"导览台词 JSON 根节点必须是对象：{path}")
    variables = data.get("variables", {})
    opening = data.get("opening", {})
    steps = data.get("steps", [])
    map_file = data.get("map_file", "")
    points = data.get("points", {})
    back_points = data.get("back_points", [])
    if not isinstance(variables, dict):
        raise DialogueError("variables 必须是对象")
    if not isinstance(opening, dict):
        raise DialogueError("opening 必须是对象")
    if not isinstance(steps, list):
        raise DialogueError("steps 必须是数组")
    if map_file is not None and not isinstance(map_file, str):
        raise DialogueError("map_file 必须是字符串")
    if points is not None and not isinstance(points, dict):
        raise DialogueError("points 必须是对象")
    if back_points is not None and back_points != [] and not isinstance(back_points, list):
        raise DialogueError("back_points 必须是数组")
    for step_index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise DialogueError(f"steps[{step_index}] 必须是对象")
        segments = step.get("segments", [])
        if segments is None:
            continue
        if not isinstance(segments, list):
            raise DialogueError(f"steps[{step_index}].segments 必须是数组")
        for segment_index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                raise DialogueError(f"steps[{step_index}].segments[{segment_index}] 必须是对象")
            text = segment.get("text")
            if text is not None and not isinstance(text, str):
                raise DialogueError(f"steps[{step_index}].segments[{segment_index}].text 必须是字符串")
    return data


def _format_dialogue(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def read_dialogue_editor(path: Path) -> dict:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DialogueError(f"读取导览台词失败：{path}") from exc

    try:
        data = json.loads(raw_text)
        validate_dialogue_data(data, path)
    except json.JSONDecodeError as exc:
        return {
            "ok": True,
            "valid": False,
            "path": str(path),
            "content": raw_text,
            "message": f"JSON 解析失败：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}",
            "summary": {},
        }
    except DialogueError as exc:
        return {
            "ok": True,
            "valid": False,
            "path": str(path),
            "content": raw_text,
            "message": str(exc),
            "summary": {},
        }

    return {
        "ok": True,
        "valid": True,
        "path": str(path),
        "content": _format_dialogue(data),
        "message": "导览台词已加载",
        "summary": _summary(data, path),
    }


def write_dialogue_config(path: Path, content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DialogueError(f"JSON 解析失败：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}") from exc
    data = validate_dialogue_data(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
        shutil.copy2(path, backup_path)
    path.write_text(_format_dialogue(data), encoding="utf-8")
    return {
        "ok": True,
        "valid": True,
        "path": str(path),
        "content": _format_dialogue(data),
        "message": "导览台词已保存，重启导航主程序后生效",
        "summary": _summary(data, path),
    }
