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

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        project_root = Path(os.environ.get("RABBITBOT_PROJECT_ROOT", str(PROJECT_ROOT)))
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
        )
