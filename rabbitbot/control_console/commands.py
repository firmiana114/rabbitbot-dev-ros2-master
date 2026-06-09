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
