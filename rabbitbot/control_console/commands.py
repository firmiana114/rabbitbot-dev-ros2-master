from __future__ import annotations

from pathlib import Path
import subprocess


ALLOWED_COMMANDS = {"go", "back"}
LOOP_SERVICE_NAME = "rabbitbot-loop.service"


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


def restart_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持重启的服务：{service_name}")
    if not systemctl_path.exists():
        raise CommandError(f"systemctl 不存在：{systemctl_path}")
    if sudo_path is not None and not sudo_path.exists():
        raise CommandError(f"sudo 不存在：{sudo_path}")

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

    return {"ok": True, "service": service_name, "message": output or "已重新启动导航主程序"}
