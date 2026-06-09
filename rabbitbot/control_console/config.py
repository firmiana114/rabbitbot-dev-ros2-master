from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path("/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master")


@dataclass(frozen=True)
class ConsoleConfig:
    project_root: Path
    host: str
    port: int
    nav_port: int
    map_path: str
    command_script: Path
    workflow_control_dir: Path
    nav_log_dir: Path
    workflow_log_dir: Path
    loop_service_name: str
    systemctl_path: Path
    sudo_path: Path | None
    map_env_file: Path

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        project_root = Path(os.environ.get("RABBITBOT_PROJECT_ROOT", str(PROJECT_ROOT)))
        sudo_path_value = os.environ.get("RABBITBOT_CONSOLE_SUDO_PATH", "/usr/bin/sudo")
        sudo_path = None if sudo_path_value.lower() in {"", "none", "0"} else Path(sudo_path_value)
        return cls(
            project_root=project_root,
            host=os.environ.get("RABBITBOT_CONSOLE_HOST", "0.0.0.0"),
            port=int(os.environ.get("RABBITBOT_CONSOLE_PORT", "8080")),
            nav_port=int(os.environ.get("RABBITBOT_NAV_PORT", "28180")),
            map_path=os.environ.get("NAV_PCD_PATH", "/home/unitree/test9.pcd"),
            command_script=project_root / "scripts_1" / "send_nav_workflow_command.sh",
            workflow_control_dir=project_root / "logs" / "nav_workflow_control" / "workflow_control",
            nav_log_dir=project_root / "logs" / "nav_workflow_control",
            workflow_log_dir=project_root / "logs" / "nav_workflow_control",
            loop_service_name=os.environ.get("RABBITBOT_LOOP_SERVICE", "rabbitbot-loop.service"),
            systemctl_path=Path(os.environ.get("RABBITBOT_CONSOLE_SYSTEMCTL_PATH", "/usr/bin/systemctl")),
            sudo_path=sudo_path,
            map_env_file=Path(os.environ.get("RABBITBOT_LOOP_ENV_FILE", str(project_root / "runtime" / "rabbitbot-loop.env"))),
        )
