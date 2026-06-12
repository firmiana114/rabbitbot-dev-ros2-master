from __future__ import annotations

from pathlib import Path
import logging
import socket
import subprocess
import time


ALLOWED_COMMANDS = {"go", "back"}
TASK_LABELS = {"guide": "导览", "dialogue": "对话", "vision": "视觉导航"}
PLACEHOLDER_TASKS = {"dialogue", "vision"}
LOOP_SERVICE_NAME = "rabbitbot-loop.service"
MAP_ENV_KEY = "NAV_PCD_PATH"
NAV_BRIDGE_PORT = 28180
logger = logging.getLogger(__name__)


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



def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _cleanup_tcp_port_occupants(
    port: int,
    sudo_path: Path | None,
    fuser_path: Path = Path("/usr/bin/fuser"),
    wait_seconds: float = 5.0,
) -> None:
    started_at = time.monotonic()
    if not fuser_path.exists():
        logger.warning("端口清理跳过：fuser 不存在，port=%s, fuser=%s", port, fuser_path)
        return

    logger.info("端口清理开始：port=%s, fuser=%s, sudo=%s, wait_seconds=%.1f", port, fuser_path, sudo_path, wait_seconds)
    attempts: list[list[str]] = []
    if sudo_path is not None and sudo_path.exists():
        attempts.append([str(sudo_path), "-n", str(fuser_path), "-k", f"{port}/tcp"])
    attempts.append([str(fuser_path), "-k", f"{port}/tcp"])

    last_result = None
    for args in attempts:
        logger.debug("端口清理执行：port=%s, command=%s", port, args)
        last_result = subprocess.run(
            args,
            check=False,
            text=True,
            capture_output=True,
        )
        output = (last_result.stdout or last_result.stderr or "").strip()
        if "password is required" in output or "not allowed" in output:
            logger.warning("端口清理命令无权限，尝试降级执行：port=%s, exit_code=%s, output_summary=%s", port, last_result.returncode, output[:200])
            continue
        if last_result.returncode in (0, 1):
            logger.info("端口清理命令完成：port=%s, exit_code=%s, output_summary=%s", port, last_result.returncode, output[:200])
            break
        logger.error("端口清理命令失败：port=%s, exit_code=%s, output_summary=%s", port, last_result.returncode, output[:200])
        raise CommandError(output or f"释放 {port} 端口占用失败，退出码：{last_result.returncode}")
    if last_result is None:
        return

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not _port_open("127.0.0.1", port):
            logger.info("端口清理完成：port=%s, elapsed=%.3fs", port, time.monotonic() - started_at)
            return
        time.sleep(0.2)

    logger.error("端口清理超时：port=%s, elapsed=%.3fs", port, time.monotonic() - started_at)
    raise CommandError(f"{port} 端口占用未释放，请检查旧导航桥接进程")


def _run_loop_service_action(
    action: str,
    service_name: str,
    systemctl_path: Path,
    sudo_path: Path | None,
    failure_label: str,
) -> str:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持操作的服务：{service_name}")
    if action not in {"start", "restart", "stop"}:
        raise CommandError(f"不支持的服务操作：{action}")
    if not systemctl_path.exists():
        raise CommandError(f"systemctl 不存在：{systemctl_path}")
    if sudo_path is not None and not sudo_path.exists():
        raise CommandError(f"sudo 不存在：{sudo_path}")

    args: list[str] = []
    if sudo_path is not None:
        args.extend([str(sudo_path), "-n"])
    args.extend([str(systemctl_path), action, service_name])

    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise CommandError(output or f"{failure_label}失败，退出码：{result.returncode}")
    return output


def start_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持启动的服务：{service_name}")
    output = _run_loop_service_action("start", service_name, systemctl_path, sudo_path, "启动")
    return {"ok": True, "service": service_name, "message": output or "已启动导航主程序"}


def restart_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    map_path: str | None = None,
    map_env_file: Path | None = None,
    cleanup_port: bool = True,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持重启的服务：{service_name}")

    active_map_path = None
    if map_path is not None:
        if map_env_file is None:
            raise CommandError("缺少地图配置文件路径")
        active_map_path = write_map_path(map_env_file, map_path)

    logger.info("导航主程序重启开始：service=%s, map_path=%s, cleanup_port=%s", service_name, active_map_path, cleanup_port)
    _run_loop_service_action("stop", service_name, systemctl_path, sudo_path, "关闭")
    if cleanup_port:
        _cleanup_tcp_port_occupants(NAV_BRIDGE_PORT, sudo_path)
    output = _run_loop_service_action("start", service_name, systemctl_path, sudo_path, "启动")
    logger.info("导航主程序重启完成：service=%s, map_path=%s", service_name, active_map_path)

    response = {"ok": True, "service": service_name, "message": output or "已重新启动导航主程序"}
    if active_map_path is not None:
        response["map_path"] = active_map_path
        response["message"] = f"已使用地图 {active_map_path} 重新启动导航主程序"
    return response


def stop_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    cleanup_port: bool = True,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持关闭的服务：{service_name}")
    logger.info("导航主程序关闭开始：service=%s, cleanup_port=%s", service_name, cleanup_port)
    output = _run_loop_service_action("stop", service_name, systemctl_path, sudo_path, "关闭")
    if cleanup_port:
        _cleanup_tcp_port_occupants(NAV_BRIDGE_PORT, sudo_path)
    logger.info("导航主程序关闭完成：service=%s", service_name)
    return {"ok": True, "service": service_name, "message": output or "已关闭导航主程序"}
