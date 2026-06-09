from __future__ import annotations

from pathlib import Path
import subprocess


ALLOWED_COMMANDS = {"go", "back"}
TASK_LABELS = {"guide": "导览", "dialogue": "对话", "vision": "视觉导航"}
PLACEHOLDER_TASKS = {"dialogue", "vision"}
LOOP_SERVICE_NAME = "rabbitbot-loop.service"
MAP_ENV_KEY = "NAV_PCD_PATH"


class CommandError(RuntimeError):
    """Raised when a console command cannot be sent."""


def validate_map_path(map_path: str) -> str:
    value = map_path.strip()
    if not value:
        raise CommandError("地图路径不能为空")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise CommandError("地图路径包含非法字符")
    if not value.startswith("/"):
        raise CommandError("地图路径必须是绝对路径")
    return value


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
        return value.replace('\\"', '"').replace('\\\\', '\\')
    return value


def read_map_path(map_env_file: Path, default_map_path: str) -> str:
    try:
        lines = map_env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return default_map_path

    current = default_map_path
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == MAP_ENV_KEY:
            current = _unquote_env_value(value) or default_map_path
    return current


def write_map_path(map_env_file: Path, map_path: str) -> str:
    value = validate_map_path(map_path)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    map_env_file.parent.mkdir(parents=True, exist_ok=True)
    map_env_file.write_text(f'{MAP_ENV_KEY}="{escaped}"\n', encoding="utf-8")
    return value


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


def start_task(task: str, script: Path, extra_args: list[str] | None = None) -> dict:
    if task not in TASK_LABELS:
        raise CommandError(f"不支持的任务：{task}")

    label = TASK_LABELS[task]
    if task in PLACEHOLDER_TASKS:
        return {"ok": True, "task": task, "task_label": label, "placeholder": True, "message": f"{label}任务暂未接入"}

    result = send_workflow_command("go", script, extra_args=extra_args)
    return {
        "ok": True,
        "task": task,
        "task_label": label,
        "placeholder": False,
        "command": result["command"],
        "message": f"{label}任务已启动",
    }


def restart_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    map_path: str | None = None,
    map_env_file: Path | None = None,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持重启的服务：{service_name}")
    if not systemctl_path.exists():
        raise CommandError(f"systemctl 不存在：{systemctl_path}")
    if sudo_path is not None and not sudo_path.exists():
        raise CommandError(f"sudo 不存在：{sudo_path}")

    active_map_path = None
    if map_path is not None:
        if map_env_file is None:
            raise CommandError("缺少地图配置文件路径")
        active_map_path = write_map_path(map_env_file, map_path)

    args: list[str] = []
    if sudo_path is not None:
        args.extend([str(sudo_path), "-n"])
    args.extend([str(systemctl_path), "restart", service_name])

    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise CommandError(output or f"重启失败，退出码：{result.returncode}")

    response = {"ok": True, "service": service_name, "message": output or "已重新启动导航主程序"}
    if active_map_path is not None:
        response["map_path"] = active_map_path
        response["message"] = f"已使用地图 {active_map_path} 重新启动导航主程序"
    return response
