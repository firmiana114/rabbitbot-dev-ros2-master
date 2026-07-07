from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import shutil


logger = logging.getLogger(__name__)
CONTROL_CONSOLE_TABLE_SOURCE = "control_console_table"
CONSOLE_POINT_PREFIX = "console_point_"
COORDINATE_REQUIRED_FIELDS = ("x", "y", "z", "ox", "oy", "oz", "ow")
COORDINATE_FLOAT_FIELDS = COORDINATE_REQUIRED_FIELDS


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


def _read_dialogue_data(path: Path) -> dict:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("读取导览台词失败：path=%s, error_type=%s", path, type(exc).__name__)
        raise DialogueError(f"读取导览台词失败：{path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("导览台词 JSON 解析失败：path=%s, line=%s, column=%s", path, exc.lineno, exc.colno)
        raise DialogueError(f"JSON 解析失败：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}") from exc
    return validate_dialogue_data(data, path)


def _backup_dialogue_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    try:
        shutil.copy2(path, backup_path)
    except OSError as exc:
        logger.error("导览台词备份失败：path=%s, backup=%s, error_type=%s", path, backup_path, type(exc).__name__)
        raise DialogueError(f"备份导览台词失败：{path}") from exc
    logger.info("导览台词已备份：path=%s, backup=%s", path, backup_path)
    return backup_path


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
        logger.error("导览台词保存校验失败：path=%s, reason=json_decode, line=%s, column=%s", path, exc.lineno, exc.colno)
        raise DialogueError(f"JSON 解析失败：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}") from exc
    data = validate_dialogue_data(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_dialogue_file(path)
    try:
        path.write_text(_format_dialogue(data), encoding="utf-8")
    except OSError as exc:
        logger.error("导览台词写入失败：path=%s, error_type=%s", path, type(exc).__name__)
        raise DialogueError(f"写入导览台词失败：{path}") from exc
    logger.info("导览台词已保存：path=%s, steps=%s, points=%s", path, len(data.get("steps", []) or []), len(data.get("points", {}) or {}))
    return {
        "ok": True,
        "valid": True,
        "path": str(path),
        "content": _format_dialogue(data),
        "message": "导览台词已保存，重启导航主程序后生效",
        "summary": _summary(data, path),
    }


def read_dialogue_leader_calling(path: Path) -> dict:
    data = _read_dialogue_data(path)
    variables = data.get("variables", {}) or {}
    leader_calling = str(variables.get("leader_calling") or "").strip()
    logger.info("导览嘉宾称呼已读取：path=%s, value_length=%s", path, len(leader_calling))
    return {
        "ok": True,
        "path": str(path),
        "leader_calling": leader_calling,
        "message": "嘉宾称呼已加载",
        "summary": _summary(data, path),
    }


def write_dialogue_leader_calling(path: Path, leader_calling: object) -> dict:
    data = _read_dialogue_data(path)
    value = str(leader_calling or "").strip()
    if not value:
        logger.info("导览嘉宾称呼校验失败：path=%s, reason=empty", path)
        raise DialogueError("嘉宾称呼不能为空")
    if "\n" in value or "\r" in value or "\x00" in value:
        logger.info("导览嘉宾称呼校验失败：path=%s, reason=illegal_character", path)
        raise DialogueError("嘉宾称呼不能包含换行或非法字符")
    if len(value) > 80:
        logger.info("导览嘉宾称呼校验失败：path=%s, reason=too_long, value_length=%s", path, len(value))
        raise DialogueError("嘉宾称呼不能超过 80 个字符")

    variables = data.get("variables", {}) or {}
    old_value = str(variables.get("leader_calling") or "").strip()
    if old_value == value:
        logger.info("导览嘉宾称呼未变化：path=%s, value_length=%s", path, len(value))
        return {
            "ok": True,
            "path": str(path),
            "leader_calling": value,
            "message": "嘉宾称呼未变化",
            "summary": _summary(data, path),
        }

    variables["leader_calling"] = value
    data["variables"] = variables
    validate_dialogue_data(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_dialogue_file(path)
    try:
        path.write_text(_format_dialogue(data), encoding="utf-8")
    except OSError as exc:
        logger.error("导览嘉宾称呼写入失败：path=%s, error_type=%s", path, type(exc).__name__)
        raise DialogueError(f"写入导览台词失败：{path}") from exc
    logger.info("导览嘉宾称呼已保存：path=%s, value_length=%s", path, len(value))
    return {
        "ok": True,
        "path": str(path),
        "leader_calling": value,
        "message": "嘉宾称呼已保存，下一次导览生效，无需重启",
        "summary": _summary(data, path),
    }


def _coordinate_to_editor_text(location: dict) -> str:
    fields = [*COORDINATE_REQUIRED_FIELDS, "mode"]
    payload = {field: location[field] for field in fields if field in location}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _opening_to_editor_text(opening: dict) -> str:
    return json.dumps(opening, ensure_ascii=False, indent=2)


def _segments_to_editor_text(segments: list) -> str:
    texts = []
    for segment in segments:
        if isinstance(segment, dict):
            text = str(segment.get("text") or "").strip()
            if text:
                texts.append(text)
    return "\n\n".join(texts)


def read_dialogue_hot_rows(path: Path) -> dict:
    data = _read_dialogue_data(path)
    points = data.get("points", {}) or {}
    steps = data.get("steps", []) or []
    rows = [{
        "id": "opening",
        "row_type": "opening",
        "point_name": "opening",
        "point_key": "",
        "coordinate": "",
        "script": _opening_to_editor_text(data.get("opening", {}) or {}),
    }]
    for step_index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        point_key = str(step.get("entity_key") or "").strip()
        point = points.get(point_key)
        location_items = point.get("location", []) if isinstance(point, dict) else []
        coordinate = ""
        if isinstance(location_items, list) and location_items:
            coordinate = _coordinate_to_editor_text(location_items[0])
        segments = step.get("segments", []) or []
        rows.append({
            "id": f"step_{step_index}",
            "row_type": "step",
            "step_index": step_index,
            "point_name": str(step.get("scene") or point_key or f"步骤{step_index + 1}"),
            "point_key": point_key,
            "coordinate": coordinate,
            "script": _segments_to_editor_text(segments),
        })
    logger.info("导览热更新表格已读取：path=%s, rows=%s", path, len(rows))
    return {
        "ok": True,
        "path": str(path),
        "rows": rows,
        "message": "点位台词已加载",
        "summary": _summary(data, path),
    }


def _normalize_row_id(raw_id: object, index: int) -> str:
    value = str(raw_id or "").strip()
    if not value:
        return str(index + 1)
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    value = value.strip("_")
    return value or str(index + 1)


def _parse_coordinate(raw_coordinate: object, row_number: int) -> dict:
    if isinstance(raw_coordinate, dict):
        coordinate = dict(raw_coordinate)
    elif isinstance(raw_coordinate, str):
        text = raw_coordinate.strip()
        if not text:
            logger.info("导览热更新表格校验失败：row=%s, reason=empty_coordinate", row_number)
            raise DialogueError(f"第 {row_number} 行点位坐标不能为空")
        try:
            coordinate = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.info("导览热更新表格校验失败：row=%s, reason=json_decode, line=%s, column=%s", row_number, exc.lineno, exc.colno)
            raise DialogueError(f"第 {row_number} 行点位坐标不是有效 JSON 对象") from exc
    else:
        logger.info("导览热更新表格校验失败：row=%s, reason=coordinate_type", row_number)
        raise DialogueError(f"第 {row_number} 行点位坐标必须是 JSON 对象")

    if not isinstance(coordinate, dict):
        logger.info("导览热更新表格校验失败：row=%s, reason=coordinate_not_object", row_number)
        raise DialogueError(f"第 {row_number} 行点位坐标必须是 JSON 对象")

    missing = [field for field in COORDINATE_REQUIRED_FIELDS if field not in coordinate]
    if missing:
        logger.info("导览热更新表格校验失败：row=%s, reason=missing_fields, missing=%s", row_number, missing)
        raise DialogueError(f"第 {row_number} 行点位坐标缺少字段：{', '.join(missing)}")

    normalized = {}
    for field in COORDINATE_FLOAT_FIELDS:
        try:
            normalized[field] = float(coordinate[field])
        except (TypeError, ValueError) as exc:
            logger.info("导览热更新表格校验失败：row=%s, reason=field_not_number, field=%s", row_number, field)
            raise DialogueError(f"第 {row_number} 行点位坐标字段 {field} 必须是数字") from exc
    try:
        normalized["mode"] = int(coordinate.get("mode", 1))
    except (TypeError, ValueError) as exc:
        logger.info("导览热更新表格校验失败：row=%s, reason=mode_not_int", row_number)
        raise DialogueError(f"第 {row_number} 行点位坐标字段 mode 必须是整数") from exc
    return normalized


def _split_script_parts(script: str) -> list[str]:
    text = str(script or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]


def _script_to_segments(script: str, original_segments: list) -> list[dict]:
    parts = _split_script_parts(script)
    if not parts:
        return []
    if len(parts) == len(original_segments) and all(isinstance(segment, dict) for segment in original_segments):
        updated_segments = []
        for segment, text in zip(original_segments, parts):
            updated_segment = dict(segment)
            updated_segment["text"] = text
            updated_segments.append(updated_segment)
        return updated_segments
    return [{"text": part} for part in parts]


def _parse_opening_script(script: object, row_number: int) -> dict:
    text = str(script or "").strip()
    if not text:
        logger.info("导览热更新表格校验失败：row=%s, reason=empty_opening", row_number)
        raise DialogueError("opening 讲解台词不能为空")
    try:
        opening = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.info("导览热更新表格校验失败：row=%s, reason=opening_json_decode, line=%s, column=%s", row_number, exc.lineno, exc.colno)
        raise DialogueError("opening 讲解台词必须是 JSON 对象") from exc
    if not isinstance(opening, dict):
        logger.info("导览热更新表格校验失败：row=%s, reason=opening_not_object", row_number)
        raise DialogueError("opening 讲解台词必须是 JSON 对象")
    for key, value in opening.items():
        if not isinstance(key, str) or not isinstance(value, str):
            logger.info("导览热更新表格校验失败：row=%s, reason=opening_value_type, key=%s", row_number, key)
            raise DialogueError("opening 讲解台词键和值都必须是字符串")
    return opening


def _generated_point_key(point_name: str, index: int, points: dict) -> str:
    base = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", point_name).strip("_")
    if not base:
        base = str(index + 1)
    key = f"{CONSOLE_POINT_PREFIX}{base}"
    if key not in points:
        return key
    suffix = 2
    while f"{key}_{suffix}" in points:
        suffix += 1
    return f"{key}_{suffix}"


def _row_index_from_id(row_id: object) -> int | None:
    match = re.fullmatch(r"step_([0-9]+)", str(row_id or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _normalize_hot_rows(rows: object, data: dict) -> tuple[dict, list[dict]]:
    if not isinstance(rows, list):
        logger.info("导览热更新表格校验失败：reason=rows_not_list")
        raise DialogueError("点位台词表格必须是数组")

    opening = None
    normalized_steps = []
    original_steps = data.get("steps", []) or []
    points = data.get("points", {}) or {}
    for index, row in enumerate(rows):
        row_number = index + 1
        if not isinstance(row, dict):
            logger.info("导览热更新表格校验失败：row=%s, reason=row_not_object", row_number)
            raise DialogueError(f"第 {row_number} 行必须是对象")
        point_name = str(row.get("point_name") or "").strip()
        row_type = str(row.get("row_type") or "").strip()
        if point_name.lower() == "opening" or row_type == "opening":
            opening = _parse_opening_script(row.get("script"), row_number)
            continue
        if not point_name:
            logger.info("导览热更新表格校验失败：row=%s, reason=empty_point_name", row_number)
            raise DialogueError(f"第 {row_number} 行点位名字不能为空")

        step_index = _row_index_from_id(row.get("id"))
        original_step = {}
        if step_index is not None and 0 <= step_index < len(original_steps) and isinstance(original_steps[step_index], dict):
            original_step = dict(original_steps[step_index])
        step = dict(original_step)
        point_key = str(row.get("point_key") or step.get("entity_key") or "").strip()
        if not point_key:
            point_key = _generated_point_key(point_name, index, points)
        script = str(row.get("script") or "").strip()
        original_segments = original_step.get("segments", []) if isinstance(original_step.get("segments", []), list) else []
        step["scene"] = point_name
        step["entity_key"] = point_key
        step["segments"] = _script_to_segments(script, original_segments)
        normalized_steps.append({
            "step": step,
            "point_key": point_key,
            "point_name": point_name,
            "coordinate": _parse_coordinate(row.get("coordinate"), row_number),
        })
    if opening is None:
        opening = data.get("opening", {}) or {}
    return opening, normalized_steps


def write_dialogue_hot_rows(path: Path, rows: object) -> dict:
    data = _read_dialogue_data(path)
    opening, normalized_rows = _normalize_hot_rows(rows, data)
    points = data.get("points", {}) or {}
    if not isinstance(points, dict):
        raise DialogueError("points 必须是对象")

    for row in normalized_rows:
        existing_point = points.get(row["point_key"], {})
        point = dict(existing_point) if isinstance(existing_point, dict) else {}
        point["name"] = row["point_name"]
        point["summary"] = str(point.get("summary") or row["point_name"])
        point.setdefault("description", "网页控制台编辑点位。")
        point["location"] = [row["coordinate"]]
        if row["step"].get("source") == CONTROL_CONSOLE_TABLE_SOURCE or row["point_key"].startswith(CONSOLE_POINT_PREFIX):
            point["source"] = CONTROL_CONSOLE_TABLE_SOURCE
        points[row["point_key"]] = point

    data["opening"] = opening
    data["points"] = points
    data["steps"] = [row["step"] for row in normalized_rows]
    validate_dialogue_data(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_dialogue_file(path)
    try:
        path.write_text(_format_dialogue(data), encoding="utf-8")
    except OSError as exc:
        logger.error("导览热更新表格写入失败：path=%s, rows=%s, error_type=%s", path, len(normalized_rows), type(exc).__name__)
        raise DialogueError(f"写入导览台词失败：{path}") from exc

    logger.info(
        "导览热更新表格已保存：path=%s, rows=%s, point_keys=%s",
        path,
        len(normalized_rows),
        [row["point_key"] for row in normalized_rows],
    )
    return {
        "ok": True,
        "valid": True,
        "path": str(path),
        "rows": read_dialogue_hot_rows(path)["rows"],
        "message": "点位台词已保存，下一次导览生效，无需重启",
        "summary": _summary(data, path),
    }
