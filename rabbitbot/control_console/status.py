from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import socket
import time
from typing import Iterable


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
FLOAT = r"([-+]?\d+(?:\.\d+)?)"
POSE_RE = re.compile(
    rf"\[Pose\].*?x:\s*{FLOAT}\s+y:\s*{FLOAT}\s+z:\s*{FLOAT}\s+"
    rf"ox:\s*{FLOAT}\s+oy:\s*{FLOAT}\s+oz:\s*{FLOAT}\s+ow:\s*{FLOAT}"
)
POSITION_RE = re.compile(rf"x:\s*{FLOAT}\s+y:\s*{FLOAT}\s+z:\s*{FLOAT}")
ORIENTATION_RE = re.compile(rf"ox:\s*{FLOAT}\s+oy:\s*{FLOAT}\s+oz:\s*{FLOAT}\s+ow:\s*{FLOAT}")
RUN_ID_RE = re.compile(r"^(\d{8}_\d{6})\.(status|pid|ready|exit_code|finished_at)$")
LOCALIZATION_SUCCESS_MESSAGE = "定位成功"
LOCALIZATION_HELP_MESSAGE = "定位未成功：程序会持续重定位，需要遥控机器人的位姿，帮助机器人完成定位"
LOCALIZATION_UNKNOWN_MESSAGE = "当前位姿已读取，定位状态待确认"
LOCALIZATION_STATE_WINDOW_LINES = 300


@dataclass(frozen=True)
class PoseStatus:
    available: bool
    localized: bool = False
    status_message: str = LOCALIZATION_HELP_MESSAGE
    x: float | None = None
    y: float | None = None
    z: float | None = None
    ox: float | None = None
    oy: float | None = None
    oz: float | None = None
    ow: float | None = None
    source: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowStatus:
    run_id: str | None
    status: str
    ready: bool
    pid: str | None = None
    exit_code: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def latest_file(directory: Path, pattern: str) -> Path | None:
    try:
        matches = [path for path in directory.glob(pattern) if path.is_file()]
    except OSError:
        return None
    candidates: list[tuple[float, str, Path]] = []
    for path in matches:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path.name, path))
    if not candidates:
        return None

    now = time.time()
    non_future_candidates = [item for item in candidates if item[0] <= now + 300]
    if non_future_candidates:
        candidates = non_future_candidates
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def get_tail_lines(path: Path, limit: int = 120) -> list[str]:
    if limit < 1:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [strip_ansi(line) for line in lines[-limit:]]


def _localization_state(lines: list[str]) -> tuple[bool, str]:
    localized = False
    message = LOCALIZATION_UNKNOWN_MESSAGE
    recent_lines = lines[-LOCALIZATION_STATE_WINDOW_LINES:]
    for line in recent_lines:
        if "Waiting for localization" in line or "start relocation with map" in line:
            localized = False
            message = LOCALIZATION_HELP_MESSAGE
        if "[Auto-Relocation] Success! Current pose:" in line:
            localized = True
            message = LOCALIZATION_SUCCESS_MESSAGE
    return localized, message


def parse_latest_pose(path: Path) -> PoseStatus:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return PoseStatus(available=False, localized=False, status_message=LOCALIZATION_HELP_MESSAGE, message="暂无定位位姿数据")

    clean_lines = [strip_ansi(line) for line in lines]
    localized, status_message = _localization_state(clean_lines)
    latest: PoseStatus | None = None

    for line in clean_lines:
        match = POSE_RE.search(line)
        if match:
            values = [float(value) for value in match.groups()]
            latest = PoseStatus(
                available=True,
                localized=localized,
                status_message=status_message,
                x=values[0],
                y=values[1],
                z=values[2],
                ox=values[3],
                oy=values[4],
                oz=values[5],
                ow=values[6],
                source="pose_log",
            )

    if latest is not None:
        return latest

    for index, line in enumerate(clean_lines):
        if "[Auto-Relocation] Success! Current pose:" not in line:
            continue
        if index + 2 >= len(clean_lines):
            continue
        position = POSITION_RE.search(clean_lines[index + 1])
        orientation = ORIENTATION_RE.search(clean_lines[index + 2])
        if not position or not orientation:
            continue
        pos_values = [float(value) for value in position.groups()]
        orient_values = [float(value) for value in orientation.groups()]
        latest = PoseStatus(
            available=True,
            localized=localized,
            status_message=status_message,
            x=pos_values[0],
            y=pos_values[1],
            z=pos_values[2],
            ox=orient_values[0],
            oy=orient_values[1],
            oz=orient_values[2],
            ow=orient_values[3],
            source="relocation_success",
        )

    if latest is None:
        return PoseStatus(available=False, localized=localized, status_message=status_message, message="暂无定位位姿数据")
    return latest


def get_latest_workflow_status(control_dir: Path) -> WorkflowStatus:
    try:
        files = [path for path in control_dir.iterdir() if path.is_file()]
    except OSError:
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    candidates: list[tuple[int, float, str, str]] = []
    for path in files:
        match = RUN_ID_RE.match(path.name)
        if not match or match.group(2) != "status":
            continue
        run_id = match.group(1)
        status = _read_text(path) or "unknown"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        running_rank = 1 if status == "running" else 0
        candidates.append((running_rank, mtime, run_id, status))

    if not candidates:
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    now = time.time()
    non_future_candidates = [item for item in candidates if item[1] <= now + 300]
    if non_future_candidates:
        candidates = non_future_candidates

    _, _, run_id, status = max(candidates, key=lambda item: (item[0], item[1], item[2]))
    ready = (control_dir / f"{run_id}.ready").exists()
    if status == "running" and ready:
        status = "waiting_for_go"

    return WorkflowStatus(
        run_id=run_id,
        status=status,
        ready=ready,
        pid=_read_text(control_dir / f"{run_id}.pid"),
        exit_code=_read_text(control_dir / f"{run_id}.exit_code"),
        finished_at=_read_text(control_dir / f"{run_id}.finished_at"),
    )


def is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_main_loop_running() -> str:
    proc_root = Path("/proc")
    try:
        proc_dirs: Iterable[Path] = proc_root.iterdir()
    except OSError:
        return "unknown"

    needle = "start_nav_bridge_workflow_loop.sh"
    for proc_dir in proc_dirs:
        if not proc_dir.name.isdigit():
            continue
        cmdline_path = proc_dir / "cmdline"
        try:
            cmdline = cmdline_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", " ")
        except OSError:
            continue
        if needle in cmdline:
            return "running"
    return "not_detected"
