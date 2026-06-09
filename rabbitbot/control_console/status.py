from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import socket
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


@dataclass(frozen=True)
class PoseStatus:
    available: bool
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
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def get_tail_lines(path: Path, limit: int = 120) -> list[str]:
    if limit < 1:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [strip_ansi(line) for line in lines[-limit:]]


def parse_latest_pose(path: Path) -> PoseStatus:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return PoseStatus(available=False, message="暂无定位位姿数据")

    clean_lines = [strip_ansi(line) for line in lines]
    latest: PoseStatus | None = None

    for line in clean_lines:
        match = POSE_RE.search(line)
        if match:
            values = [float(value) for value in match.groups()]
            latest = PoseStatus(
                available=True,
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
        return PoseStatus(available=False, message="暂无定位位姿数据")
    return latest


def get_latest_workflow_status(control_dir: Path) -> WorkflowStatus:
    try:
        names = [path.name for path in control_dir.iterdir() if path.is_file()]
    except OSError:
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    run_ids = sorted({match.group(1) for name in names if (match := RUN_ID_RE.match(name))})
    if not run_ids:
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    run_id = run_ids[-1]
    status = _read_text(control_dir / f"{run_id}.status") or "unknown"
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
