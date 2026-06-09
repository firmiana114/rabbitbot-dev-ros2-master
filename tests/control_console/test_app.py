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
    command_script.write_text("#!/usr/bin/env bash\necho \"已发送命令：$1\"\n", encoding="utf-8")
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
        "[INFO] [2] [hybrid_navigation_node_66]: [Pose] x: 1.0000  y: 2.0000  z: 3.0000  ox: 0.1000  oy: 0.2000  oz: 0.3000  ow: 0.9000\n",
        encoding="utf-8",
    )
    (config.workflow_control_dir / "20260609_100000.status").write_text("running\n", encoding="utf-8")
    (config.workflow_control_dir / "20260609_100000.ready").write_text("ready\n", encoding="utf-8")
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
    (config.nav_log_dir / "nav_bridge_1.log").write_text("old\n", encoding="utf-8")
    latest = config.nav_log_dir / "nav_bridge_2.log"
    latest.write_text("one\ntwo\nthree\n", encoding="utf-8")
    client = TestClient(create_app(config))
    client.post("/api/login", json={"password": "123"})

    response = client.get("/api/logs?target=nav&lines=2")

    assert response.status_code == 200
    assert response.json()["lines"] == ["two", "three"]
