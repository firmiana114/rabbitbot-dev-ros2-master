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


def _coordinate_to_editor_text(location: dict) -> str:
    fields = [*COORDINATE_REQUIRED_FIELDS, "mode"]
    payload = {field: location[field] for field in fields if field in location}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _hot_row_id_from_key(point_key: str) -> str:
    if point_key.startswith(CONSOLE_POINT_PREFIX):
        return point_key[len(CONSOLE_POINT_PREFIX):]
    return point_key


def read_dialogue_hot_rows(path: Path) -> dict:
    data = _read_dialogue_data(path)
    points = data.get("points", {}) or {}
    steps = data.get("steps", []) or []
    rows = []
    for step in steps:
        if not isinstance(step, dict) or step.get("source") != CONTROL_CONSOLE_TABLE_SOURCE:
            continue
        point_key = str(step.get("entity_key") or "").strip()
        point = points.get(point_key)
        location_items = point.get("location", []) if isinstance(point, dict) else []
        if not isinstance(location_items, list) or not location_items:
            continue
        segments = step.get("segments", []) or []
        text = ""
        if segments and isinstance(segments[0], dict):
            text = str(segments[0].get("text") or "")
        rows.append({
            "id": str(step.get("row_id") or _hot_row_id_from_key(point_key)),
            "point_key": point_key,
            "coordinate": _coordinate_to_editor_text(location_items[0]),
            "script": text,
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


def _normalize_hot_rows(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        logger.info("导览热更新表格校验失败：reason=rows_not_list")
        raise DialogueError("点位台词表格必须是数组")

    normalized_rows = []
    used_ids = set()
    for index, row in enumerate(rows):
        row_number = index + 1
        if not isinstance(row, dict):
            logger.info("导览热更新表格校验失败：row=%s, reason=row_not_object", row_number)
            raise DialogueError(f"第 {row_number} 行必须是对象")
        script = str(row.get("script") or "").strip()
        if not script:
            logger.info("导览热更新表格校验失败：row=%s, reason=empty_script", row_number)
            raise DialogueError(f"第 {row_number} 行讲解台词不能为空")
        row_id = _normalize_row_id(row.get("id"), index)
        if row_id in used_ids:
            row_id = f"{row_id}_{row_number}"
        used_ids.add(row_id)
        normalized_rows.append({
            "id": row_id,
            "point_key": f"{CONSOLE_POINT_PREFIX}{row_id}",
            "coordinate": _parse_coordinate(row.get("coordinate"), row_number),
            "script": script,
        })
    return normalized_rows


def write_dialogue_hot_rows(path: Path, rows: object) -> dict:
    data = _read_dialogue_data(path)
    normalized_rows = _normalize_hot_rows(rows)
    points = data.get("points", {}) or {}
    steps = data.get("steps", []) or []
    if not isinstance(points, dict):
        raise DialogueError("points 必须是对象")
    if not isinstance(steps, list):
        raise DialogueError("steps 必须是数组")

    removed_point_keys = [key for key, value in points.items() if isinstance(value, dict) and value.get("source") == CONTROL_CONSOLE_TABLE_SOURCE]
    for key in removed_point_keys:
        points.pop(key, None)

    steps = [
        step for step in steps
        if not (isinstance(step, dict) and step.get("source") == CONTROL_CONSOLE_TABLE_SOURCE)
    ]

    for row in normalized_rows:
        points[row["point_key"]] = {
            "name": row["point_key"],
            "summary": row["point_key"],
            "description": "网页控制台热更新点位。",
            "source": CONTROL_CONSOLE_TABLE_SOURCE,
            "row_id": row["id"],
            "location": [row["coordinate"]],
        }
        steps.append({
            "scene": row["point_key"],
            "entity_key": row["point_key"],
            "source": CONTROL_CONSOLE_TABLE_SOURCE,
            "row_id": row["id"],
            "segments": [{"text": row["script"]}],
        })

    data["points"] = points
    data["steps"] = steps
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
        "rows": [
            {
                "id": row["id"],
                "point_key": row["point_key"],
                "coordinate": _coordinate_to_editor_text(row["coordinate"]),
                "script": row["script"],
            }
            for row in normalized_rows
        ],
        "message": "点位台词已保存，下一次导览生效，无需重启",
        "summary": _summary(data, path),
    }
