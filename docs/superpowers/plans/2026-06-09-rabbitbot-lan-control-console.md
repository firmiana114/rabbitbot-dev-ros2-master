# RabbitBot LAN Control Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LAN web console on the Orin that lets customers login, view RabbitBot navigation/workflow status, see the current localization pose, and send only `go`/`back` commands without terminal access.

**Architecture:** Add a focused `rabbitbot.control_console` Python package. Pure status/log parsing and command whitelist logic live in testable modules; FastAPI wires those modules to authenticated JSON endpoints and a single-page HTML UI. The console is deployed separately from the existing navigation workflow loop and uses `NAV_PCD_PATH=/home/unitree/test9.pcd` via environment or service configuration.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, pytest, standard-library pathlib/subprocess/socket/re/json.

---

## File Structure

Create these files:

- `rabbitbot/control_console/__init__.py` - package marker.
- `rabbitbot/control_console/config.py` - environment-backed paths, password, ports, map path.
- `rabbitbot/control_console/status.py` - pure helpers for ANSI stripping, latest-file selection, workflow status, nav readiness, pose parsing, log tailing.
- `rabbitbot/control_console/commands.py` - command whitelist and script invocation wrapper.
- `rabbitbot/control_console/app.py` - FastAPI app, session cookie auth, API routes, HTML UI.
- `rabbitbot/control_console/__main__.py` - `python3 -m rabbitbot.control_console` entrypoint.
- `scripts_1/start_control_console.sh` - shell launcher used by operators/systemd.
- `deploy/rabbitbot-control-console.service` - sample systemd service for the web console.
- `tests/control_console/test_status.py` - parser/status/log unit tests.
- `tests/control_console/test_commands.py` - command whitelist unit tests.
- `tests/control_console/test_app.py` - API auth and command route tests.

Modify:

- `pyproject.toml` - include `rabbitbot*` packages so the new subpackage is included.

Do not modify existing workflow scripts except for adding the separate launcher/service files.

---

### Task 1: Status Parsing And Runtime Inspection

**Files:**
- Create: `rabbitbot/control_console/__init__.py`
- Create: `rabbitbot/control_console/config.py`
- Create: `rabbitbot/control_console/status.py`
- Test: `tests/control_console/test_status.py`

- [ ] **Step 1: Write failing tests for status helpers**

Create `tests/control_console/test_status.py`:

```python
from pathlib import Path

from rabbitbot.control_console.config import ConsoleConfig
from rabbitbot.control_console.status import (
    get_latest_workflow_status,
    get_tail_lines,
    parse_latest_pose,
    strip_ansi,
)


def test_strip_ansi_removes_terminal_color_sequences():
    assert strip_ansi("\x1b[36m[Pose]\x1b[0m x: 1.0") == "[Pose] x: 1.0"


def test_parse_latest_pose_prefers_last_periodic_pose(tmp_path):
    log = tmp_path / "nav_bridge_20260609.log"
    log.write_text(
        "[INFO] [1] [hybrid_navigation_node_66]: \x1b[32m[Auto-Relocation] Success! Current pose:\x1b[0m
"
        "[INFO] [1] [hybrid_navigation_node_66]:   x: -0.3913  y: 16.9003  z: -0.0693
"
        "[INFO] [1] [hybrid_navigation_node_66]:   ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579
"
        "[INFO] [2] [hybrid_navigation_node_66]: \x1b[36m[Pose]\x1b[0m x: 1.2345  y: -2.3456  z: 0.1000  ox: 0.0100  oy: 0.0200  oz: 0.0300  ow: 0.9990
",
        encoding="utf-8",
    )

    pose = parse_latest_pose(log)

    assert pose.available is True
    assert pose.source == "pose_log"
    assert pose.x == 1.2345
    assert pose.y == -2.3456
    assert pose.z == 0.1
    assert pose.ox == 0.01
    assert pose.oy == 0.02
    assert pose.oz == 0.03
    assert pose.ow == 0.999


def test_parse_latest_pose_uses_relocation_block_when_no_periodic_pose(tmp_path):
    log = tmp_path / "nav_bridge_20260609.log"
    log.write_text(
        "[INFO] [1] [hybrid_navigation_node_66]: [Auto-Relocation] Success! Current pose:
"
        "[INFO] [1] [hybrid_navigation_node_66]:   x: -0.3913  y: 16.9003  z: -0.0693
"
        "[INFO] [1] [hybrid_navigation_node_66]:   ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579
",
        encoding="utf-8",
    )

    pose = parse_latest_pose(log)

    assert pose.available is True
    assert pose.source == "relocation_success"
    assert pose.x == -0.3913
    assert pose.y == 16.9003
    assert pose.z == -0.0693
    assert pose.ox == 0.1253
    assert pose.oy == 0.0844
    assert pose.oz == 0.7378
    assert pose.ow == 0.6579


def test_parse_latest_pose_returns_unavailable_for_missing_log(tmp_path):
    pose = parse_latest_pose(tmp_path / "missing.log")

    assert pose.available is False
    assert pose.message == "暂无定位位姿数据"


def test_get_latest_workflow_status_prefers_newest_run_id(tmp_path):
    control = tmp_path / "workflow_control"
    control.mkdir()
    (control / "20260608_090000.status").write_text("finished
", encoding="utf-8")
    (control / "20260608_090000.exit_code").write_text("0
", encoding="utf-8")
    (control / "20260609_100000.status").write_text("running
", encoding="utf-8")
    (control / "20260609_100000.ready").write_text("ready
", encoding="utf-8")
    (control / "20260609_100000.pid").write_text("1234
", encoding="utf-8")

    workflow = get_latest_workflow_status(control)

    assert workflow.run_id == "20260609_100000"
    assert workflow.status == "waiting_for_go"
    assert workflow.ready is True
    assert workflow.pid == "1234"
    assert workflow.exit_code is None


def test_get_latest_workflow_status_handles_missing_directory(tmp_path):
    workflow = get_latest_workflow_status(tmp_path / "missing")

    assert workflow.run_id is None
    assert workflow.status == "unknown"
    assert workflow.ready is False


def test_get_tail_lines_strips_ansi_and_limits_count(tmp_path):
    log = tmp_path / "nav.log"
    log.write_text("one
\x1b[32mtwo\x1b[0m
three
", encoding="utf-8")

    assert get_tail_lines(log, 2) == ["two", "three"]


def test_console_config_defaults_to_test9_map(monkeypatch):
    monkeypatch.delenv("NAV_PCD_PATH", raising=False)

    config = ConsoleConfig.from_env()

    assert config.map_path == "/home/unitree/test9.pcd"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/control_console/test_status.py -q
```

Expected: FAIL during import because `rabbitbot.control_console` does not exist.

- [ ] **Step 3: Implement config and status helpers**

Create `rabbitbot/control_console/__init__.py`:

```python
"""LAN control console for RabbitBot."""
```

Create `rabbitbot/control_console/config.py`:

```python
from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path("/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master")


@dataclass(frozen=True)
class ConsoleConfig:
    project_root: Path
    password: str
    host: str
    port: int
    nav_port: int
    map_path: str
    command_script: Path
    workflow_control_dir: Path
    nav_log_dir: Path
    workflow_log_dir: Path

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        project_root = Path(os.environ.get("RABBITBOT_PROJECT_ROOT", str(PROJECT_ROOT)))
        return cls(
            project_root=project_root,
            password=os.environ.get("RABBITBOT_CONSOLE_PASSWORD", "123"),
            host=os.environ.get("RABBITBOT_CONSOLE_HOST", "0.0.0.0"),
            port=int(os.environ.get("RABBITBOT_CONSOLE_PORT", "8080")),
            nav_port=int(os.environ.get("RABBITBOT_NAV_PORT", "28180")),
            map_path=os.environ.get("NAV_PCD_PATH", "/home/unitree/test9.pcd"),
            command_script=project_root / "scripts_1" / "send_nav_workflow_command.sh",
            workflow_control_dir=project_root / "logs" / "nav_workflow_control" / "workflow_control",
            nav_log_dir=project_root / "logs" / "nav_workflow_control",
            workflow_log_dir=project_root / "logs" / "nav_workflow_control",
        )
```

Create `rabbitbot/control_console/status.py`:

```python
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
```

- [ ] **Step 4: Run status tests and verify they pass**

Run:

```bash
pytest tests/control_console/test_status.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add rabbitbot/control_console/__init__.py rabbitbot/control_console/config.py rabbitbot/control_console/status.py tests/control_console/test_status.py
git commit -m "feat: add control console status helpers"
```

---

### Task 2: Command Whitelist Wrapper

**Files:**
- Create: `rabbitbot/control_console/commands.py`
- Test: `tests/control_console/test_commands.py`

- [ ] **Step 1: Write failing command tests**

Create `tests/control_console/test_commands.py`:

```python
from pathlib import Path

import pytest

from rabbitbot.control_console.commands import CommandError, send_workflow_command


def test_send_workflow_command_allows_go_and_invokes_script(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash
"
        "echo "$1" > "$2"
"
        "echo "已发送命令：$1"
",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("go", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "go"
    assert result["message"] == "已发送命令：go"
    assert record.read_text(encoding="utf-8").strip() == "go"


def test_send_workflow_command_allows_back(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash
"
        "echo "$1" > "$2"
"
        "echo "已发送命令：$1"
",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("back", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "back"
    assert record.read_text(encoding="utf-8").strip() == "back"


@pytest.mark.parametrize("command", ["quit", "exit", "restart", "go; rm -rf /", ""])
def test_send_workflow_command_rejects_non_whitelisted_commands(tmp_path, command):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash
exit 0
", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command(command, script)

    assert "不支持的命令" in str(excinfo.value)


def test_send_workflow_command_reports_script_failure(tmp_path):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash
echo failure >&2
exit 7
", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command("go", script)

    assert "failure" in str(excinfo.value)
```

- [ ] **Step 2: Run command tests and verify they fail**

Run:

```bash
pytest tests/control_console/test_commands.py -q
```

Expected: FAIL because `rabbitbot.control_console.commands` does not exist.

- [ ] **Step 3: Implement command wrapper**

Create `rabbitbot/control_console/commands.py`:

```python
from __future__ import annotations

from pathlib import Path
import subprocess


ALLOWED_COMMANDS = {"go", "back"}


class CommandError(RuntimeError):
    """Raised when a console command cannot be sent."""


def send_workflow_command(command: str, script: Path, extra_args: list[str] | None = None) -> dict:
    if command not in ALLOWED_COMMANDS:
        raise CommandError(f"不支持的命令：{command}")
    if not script.exists():
        raise CommandError(f"命令脚本不存在：{script}")

    args = ["bash", str(script), command]
    if extra_args:
        args.extend(extra_args)

    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise CommandError(output or f"命令执行失败，退出码：{result.returncode}")

    return {"ok": True, "command": command, "message": output or f"已发送命令：{command}"}
```

- [ ] **Step 4: Run command tests and verify they pass**

Run:

```bash
pytest tests/control_console/test_commands.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add rabbitbot/control_console/commands.py tests/control_console/test_commands.py
git commit -m "feat: whitelist workflow console commands"
```

---

### Task 3: FastAPI Routes And API Auth

**Files:**
- Create: `rabbitbot/control_console/app.py`
- Test: `tests/control_console/test_app.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/control_console/test_app.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from rabbitbot.control_console.app import create_app
from rabbitbot.control_console.config import ConsoleConfig


def make_config(tmp_path):
    project_root = tmp_path / "project"
    command_script = project_root / "scripts_1" / "send_nav_workflow_command.sh"
    workflow_control_dir = project_root / "logs" / "nav_workflow_control" / "workflow_control"
    nav_log_dir = project_root / "logs" / "nav_workflow_control"
    workflow_log_dir = project_root / "logs" / "nav_workflow_control"
    command_script.parent.mkdir(parents=True)
    workflow_control_dir.mkdir(parents=True)
    nav_log_dir.mkdir(parents=True, exist_ok=True)
    workflow_log_dir.mkdir(parents=True, exist_ok=True)
    command_script.write_text("#!/usr/bin/env bash
echo "已发送命令：$1"
", encoding="utf-8")
    command_script.chmod(0o755)
    return ConsoleConfig(
        project_root=project_root,
        password="123",
        host="127.0.0.1",
        port=8080,
        nav_port=9,
        map_path="/home/unitree/test9.pcd",
        command_script=command_script,
        workflow_control_dir=workflow_control_dir,
        nav_log_dir=nav_log_dir,
        workflow_log_dir=workflow_log_dir,
    )


def test_status_requires_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/api/status")

    assert response.status_code == 401


def test_login_sets_cookie_and_status_returns_map_and_pose(tmp_path):
    config = make_config(tmp_path)
    nav_log = config.nav_log_dir / "nav_bridge_20260609.log"
    nav_log.write_text(
        "[INFO] [2] [hybrid_navigation_node_66]: [Pose] x: 1.0000  y: 2.0000  z: 3.0000  ox: 0.1000  oy: 0.2000  oz: 0.3000  ow: 0.9000
",
        encoding="utf-8",
    )
    (config.workflow_control_dir / "20260609_100000.status").write_text("running
", encoding="utf-8")
    (config.workflow_control_dir / "20260609_100000.ready").write_text("ready
", encoding="utf-8")
    client = TestClient(create_app(config))

    login = client.post("/api/login", json={"password": "123"})
    response = client.get("/api/status")

    assert login.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["map_path"] == "/home/unitree/test9.pcd"
    assert body["workflow"]["status"] == "waiting_for_go"
    assert body["pose"]["available"] is True
    assert body["pose"]["x"] == 1.0


def test_login_rejects_wrong_password(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/login", json={"password": "bad"})

    assert response.status_code == 401


def test_command_rejects_quit_even_after_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))
    client.post("/api/login", json={"password": "123"})

    response = client.post("/api/command", json={"command": "quit"})

    assert response.status_code == 400
    assert "不支持的命令" in response.json()["detail"]


def test_command_sends_go_after_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))
    client.post("/api/login", json={"password": "123"})

    response = client.post("/api/command", json={"command": "go"})

    assert response.status_code == 200
    assert response.json()["command"] == "go"


def test_logs_return_latest_nav_log_lines(tmp_path):
    config = make_config(tmp_path)
    (config.nav_log_dir / "nav_bridge_1.log").write_text("old
", encoding="utf-8")
    latest = config.nav_log_dir / "nav_bridge_2.log"
    latest.write_text("one
two
three
", encoding="utf-8")
    client = TestClient(create_app(config))
    client.post("/api/login", json={"password": "123"})

    response = client.get("/api/logs?target=nav&lines=2")

    assert response.status_code == 200
    assert response.json()["lines"] == ["two", "three"]
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
pytest tests/control_console/test_app.py -q
```

Expected: FAIL because `rabbitbot.control_console.app` does not exist.

- [ ] **Step 3: Implement FastAPI app**

Create `rabbitbot/control_console/app.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import secrets

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .commands import CommandError, send_workflow_command
from .config import ConsoleConfig
from .status import (
    detect_main_loop_running,
    get_latest_workflow_status,
    get_tail_lines,
    is_port_open,
    latest_file,
    parse_latest_pose,
)


SESSION_COOKIE = "rabbitbot_console_session"


class LoginRequest(BaseModel):
    password: str


class CommandRequest(BaseModel):
    command: str


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RabbitBot 控制台</title>
  <style>
    :root{font-family:Arial,'Noto Sans SC',sans-serif;color:#172033;background:#eef2f6}body{margin:0}.wrap{max-width:1180px;margin:0 auto;padding:20px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.panel{background:white;border:1px solid #d7dde8;border-radius:8px;padding:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:#f7f9fc;border-radius:6px;padding:12px}.label{font-size:12px;color:#667085;text-transform:uppercase}.value{font-size:18px;font-weight:700;margin-top:4px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}button{border:0;border-radius:6px;color:white;padding:11px 16px;font-size:15px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.go{background:#137333}.back{background:#b3261e}.refresh{background:#334155}.login{max-width:360px;margin:12vh auto}.input{width:100%;box-sizing:border-box;padding:11px;border:1px solid #cbd5e1;border-radius:6px;margin:10px 0 12px}.log{font-family:ui-monospace,Menlo,monospace;background:#111827;color:#d1d5db;border-radius:6px;padding:12px;line-height:1.5;font-size:12px;min-height:220px;overflow:auto}.error{color:#b3261e}.ok{color:#137333}@media(max-width:820px){.grid,.cards{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}</style>
</head>
<body>
  <div class="wrap">
    <div id="login" class="panel login">
      <h2>RabbitBot 控制台</h2>
      <div class="label">请输入访问密码</div>
      <input id="password" class="input" type="password" autocomplete="current-password" placeholder="密码">
      <button class="refresh" onclick="login()">登录</button>
      <p id="loginError" class="error"></p>
    </div>
    <div id="app" style="display:none">
      <div class="top">
        <div><h2>RabbitBot 控制台</h2><div id="map" class="label">地图：-</div></div>
        <div id="overall" class="value">读取中</div>
      </div>
      <div class="grid">
        <section class="panel">
          <div class="cards">
            <div class="card"><div class="label">主循环</div><div id="mainLoop" class="value">-</div></div>
            <div class="card"><div class="label">导航桥接</div><div id="navBridge" class="value">-</div></div>
            <div class="card"><div class="label">Workflow</div><div id="workflow" class="value">-</div></div>
          </div>
          <div class="actions">
            <button id="goBtn" class="go" onclick="sendCommand('go')">开始任务</button>
            <button class="back" onclick="sendCommand('back')">返航</button>
            <button class="refresh" onclick="refresh()">刷新状态</button>
          </div>
          <p id="message"></p>
        </section>
        <section class="panel">
          <div class="label">定位位姿</div>
          <div id="pose" class="value">暂无定位位姿数据</div>
        </section>
      </div>
      <section class="panel" style="margin-top:16px">
        <div class="label">最近日志</div>
        <pre id="logs" class="log">读取中...</pre>
      </section>
    </div>
  </div>
<script>
async function login(){
  const password=document.getElementById('password').value;
  const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(!res.ok){document.getElementById('loginError').textContent='密码错误';return;}
  document.getElementById('login').style.display='none';
  document.getElementById('app').style.display='block';
  refresh();
}
function setText(id,text){document.getElementById(id).textContent=text;}
async function refresh(){
  const res=await fetch('/api/status');
  if(res.status===401){document.getElementById('login').style.display='block';document.getElementById('app').style.display='none';return;}
  const data=await res.json();
  setText('map','地图：'+data.map_path);
  setText('overall',data.nav_bridge.ready?'在线':'导航未就绪');
  setText('mainLoop',data.main_loop);
  setText('navBridge',data.nav_bridge.ready?'28180 就绪':'未就绪');
  setText('workflow',data.workflow.status || 'unknown');
  document.getElementById('goBtn').disabled=!data.nav_bridge.ready;
  if(data.pose && data.pose.available){setText('pose',`x ${data.pose.x} / y ${data.pose.y} / z ${data.pose.z}
ox ${data.pose.ox} / oy ${data.pose.oy} / oz ${data.pose.oz} / ow ${data.pose.ow}`);}else{setText('pose',(data.pose&&data.pose.message)||'暂无定位位姿数据');}
  const logs=await fetch('/api/logs?target=nav&lines=120');
  if(logs.ok){const body=await logs.json();setText('logs',body.lines.join('
') || '暂无日志');}
}
async function sendCommand(command){
  const res=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command})});
  const body=await res.json();
  setText('message',res.ok?body.message:body.detail);
  refresh();
}
setInterval(()=>{if(document.getElementById('app').style.display!=='none')refresh();},2000);
</script>
</body>
</html>"""


def create_app(config: ConsoleConfig | None = None) -> FastAPI:
    config = config or ConsoleConfig.from_env()
    app = FastAPI(title="RabbitBot Control Console")
    session_token = secrets.token_urlsafe(32)

    def require_auth(rabbitbot_console_session: str | None = Cookie(default=None)) -> None:
        if rabbitbot_console_session != session_token:
            raise HTTPException(status_code=401, detail="未登录")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _html()

    @app.post("/api/login")
    def login(payload: LoginRequest, response: Response) -> dict:
        if payload.password != config.password:
            raise HTTPException(status_code=401, detail="密码错误")
        response.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="lax")
        return {"ok": True}

    @app.get("/api/status")
    def status(_: None = Depends(require_auth)) -> dict:
        nav_log = latest_file(config.nav_log_dir, "nav_bridge_*.log")
        pose = parse_latest_pose(nav_log) if nav_log else parse_latest_pose(Path("/missing-nav-log"))
        workflow = get_latest_workflow_status(config.workflow_control_dir)
        return {
            "ok": True,
            "map_path": config.map_path,
            "main_loop": detect_main_loop_running(),
            "nav_bridge": {"ready": is_port_open("127.0.0.1", config.nav_port), "port": config.nav_port},
            "workflow": workflow.to_dict(),
            "pose": pose.to_dict(),
        }

    @app.post("/api/command")
    def command(payload: CommandRequest, _: None = Depends(require_auth)) -> dict:
        try:
            return send_workflow_command(payload.command, config.command_script)
        except CommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/logs")
    def logs(target: str = "nav", lines: int = 120, _: None = Depends(require_auth)) -> dict:
        bounded_lines = max(1, min(lines, 400))
        if target == "nav":
            path = latest_file(config.nav_log_dir, "nav_bridge_*.log")
        elif target == "workflow":
            path = latest_file(config.workflow_log_dir, "rabbitbot_workflow_*.log")
        else:
            raise HTTPException(status_code=400, detail="不支持的日志目标")
        return {
            "ok": True,
            "target": target,
            "path": str(path) if path else None,
            "lines": get_tail_lines(path, bounded_lines) if path else [],
        }

    return app


app = create_app()
```

- [ ] **Step 4: Run API tests and verify they pass**

Run:

```bash
pytest tests/control_console/test_app.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add rabbitbot/control_console/app.py tests/control_console/test_app.py
git commit -m "feat: add rabbitbot control console api"
```

---

### Task 4: Entrypoint, Packaging, And Service Artifacts

**Files:**
- Create: `rabbitbot/control_console/__main__.py`
- Create: `scripts_1/start_control_console.sh`
- Create: `deploy/rabbitbot-control-console.service`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing import/packaging test**

Append this test to `tests/control_console/test_app.py`:

```python

def test_main_module_exposes_run_function():
    from rabbitbot.control_console.__main__ import run

    assert callable(run)
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
pytest tests/control_console/test_app.py::test_main_module_exposes_run_function -q
```

Expected: FAIL because `rabbitbot.control_console.__main__` does not exist.

- [ ] **Step 3: Add entrypoint and deployment files**

Create `rabbitbot/control_console/__main__.py`:

```python
from __future__ import annotations

import uvicorn

from .app import create_app
from .config import ConsoleConfig


def run() -> None:
    config = ConsoleConfig.from_env()
    uvicorn.run(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    run()
```

Create `scripts_1/start_control_console.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RABBITBOT_PROJECT_ROOT="${RABBITBOT_PROJECT_ROOT:-${PROJECT_DIR}}"
export RABBITBOT_CONSOLE_PASSWORD="${RABBITBOT_CONSOLE_PASSWORD:-123}"
export RABBITBOT_CONSOLE_HOST="${RABBITBOT_CONSOLE_HOST:-0.0.0.0}"
export RABBITBOT_CONSOLE_PORT="${RABBITBOT_CONSOLE_PORT:-8080}"
export NAV_PCD_PATH="${NAV_PCD_PATH:-/home/unitree/test9.pcd}"

cd "${PROJECT_DIR}"
exec python3 -m rabbitbot.control_console
```

Make it executable:

```bash
chmod +x scripts_1/start_control_console.sh
```

Create `deploy/rabbitbot-control-console.service`:

```ini
[Unit]
Description=RabbitBot LAN Control Console
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pc
WorkingDirectory=/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master
Environment=RABBITBOT_CONSOLE_PASSWORD=123
Environment=RABBITBOT_CONSOLE_HOST=0.0.0.0
Environment=RABBITBOT_CONSOLE_PORT=8080
Environment=NAV_PCD_PATH=/home/unitree/test9.pcd
ExecStart=/bin/bash /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/scripts_1/start_control_console.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Modify `[tool.setuptools.packages.find]` in `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["rabbitbot*"]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/control_console -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add pyproject.toml rabbitbot/control_console/__main__.py scripts_1/start_control_console.sh deploy/rabbitbot-control-console.service tests/control_console/test_app.py
git commit -m "feat: add control console service entrypoint"
```

---

### Task 5: Runtime Smoke Test

**Files:**
- No code files expected unless smoke test reveals a defect.

- [ ] **Step 1: Run all focused tests**

```bash
pytest tests/control_console -q
```

Expected: PASS.

- [ ] **Step 2: Start console locally on a non-default port**

Run:

```bash
RABBITBOT_CONSOLE_HOST=127.0.0.1 RABBITBOT_CONSOLE_PORT=18080 NAV_PCD_PATH=/home/unitree/test9.pcd bash scripts_1/start_control_console.sh
```

Expected: uvicorn starts on `http://127.0.0.1:18080`.

- [ ] **Step 3: Verify HTTP login and status in another shell**

Run:

```bash
curl -i -c /tmp/rabbitbot-console.cookies -H 'Content-Type: application/json' -d '{"password":"123"}' http://127.0.0.1:18080/api/login
curl -s -b /tmp/rabbitbot-console.cookies http://127.0.0.1:18080/api/status
```

Expected: login returns HTTP 200; status JSON includes `/home/unitree/test9.pcd`, `nav_bridge`, `workflow`, and `pose` keys.

- [ ] **Step 4: Stop smoke-test server**

Stop the uvicorn process with Ctrl+C in the server shell.

- [ ] **Step 5: Commit any smoke-test fixes**

If changes were required:

```bash
git add <changed-files>
git commit -m "fix: stabilize control console smoke test"
```

If no changes were required, do not create an empty commit.
