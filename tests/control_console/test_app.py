from fastapi.testclient import TestClient

from rabbitbot.control_console.app import create_app
from rabbitbot.control_console.config import ConsoleConfig


def make_config(tmp_path):
    project_root = tmp_path / "project"
    command_script = project_root / "scripts_1" / "send_nav_workflow_command.sh"
    systemctl_path = project_root / "bin" / "systemctl"
    systemctl_record = project_root / "systemctl_args.txt"
    map_env_file = project_root / "runtime" / "rabbitbot-loop.env"
    workflow_control_dir = project_root / "logs" / "nav_workflow_control" / "workflow_control"
    nav_log_dir = project_root / "logs" / "nav_workflow_control"
    workflow_log_dir = project_root / "logs" / "nav_workflow_control"
    dialogue_dir = project_root / "conf"
    command_script.parent.mkdir(parents=True)
    systemctl_path.parent.mkdir(parents=True)
    workflow_control_dir.mkdir(parents=True)
    nav_log_dir.mkdir(parents=True, exist_ok=True)
    workflow_log_dir.mkdir(parents=True, exist_ok=True)
    dialogue_dir.mkdir(parents=True, exist_ok=True)
    (dialogue_dir / "dialogue_0.json").write_text(
        '{"variables":{"leader_calling":"各位领导"},"opening":{},"steps":[{"segments":[{"text":"欢迎"}]}],"map_file":"test9.pcd","points":{}}\n',
        encoding="utf-8",
    )
    command_script.write_text("#!/usr/bin/env bash\necho \"已发送命令：$1\"\n", encoding="utf-8")
    command_script.chmod(0o755)
    systemctl_path.write_text(f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {systemctl_record}\n", encoding="utf-8")
    systemctl_path.chmod(0o755)
    return ConsoleConfig(
        project_root=project_root,
        host="127.0.0.1",
        port=8080,
        nav_port=9,
        map_path="/home/unitree/test9.pcd",
        command_script=command_script,
        workflow_control_dir=workflow_control_dir,
        nav_log_dir=nav_log_dir,
        workflow_log_dir=workflow_log_dir,
        loop_service_name="rabbitbot-loop.service",
        systemctl_path=systemctl_path,
        sudo_path=None,
        map_env_file=map_env_file,
        dialogue_dir=dialogue_dir,
        dialogue_index="0",
        dialogue_file=None,
    )


def test_status_does_not_require_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["map_path"] == "/home/unitree/test9.pcd"


def test_status_prefers_runtime_map_env_file(tmp_path):
    config = make_config(tmp_path)
    config.map_env_file.parent.mkdir(parents=True)
    config.map_env_file.write_text('NAV_PCD_PATH="/home/unitree/new_map.pcd"\n', encoding="utf-8")
    client = TestClient(create_app(config))

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["map_path"] == "/home/unitree/new_map.pcd"


def test_status_returns_map_and_pose_without_login(tmp_path):
    config = make_config(tmp_path)
    nav_log = config.nav_log_dir / "nav_bridge_20260609.log"
    nav_log.write_text(
        "[INFO] [2] [hybrid_navigation_node_66]: [Pose] x: 1.0000  y: 2.0000  z: 3.0000  ox: 0.1000  oy: 0.2000  oz: 0.3000  ow: 0.9000\n",
        encoding="utf-8",
    )
    (config.workflow_control_dir / "20260609_100000.status").write_text("running\n", encoding="utf-8")
    (config.workflow_control_dir / "20260609_100000.ready").write_text("ready\n", encoding="utf-8")
    client = TestClient(create_app(config))

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["map_path"] == "/home/unitree/test9.pcd"
    assert body["workflow"]["status"] == "waiting_for_go"
    assert body["pose"]["available"] is True
    assert body["pose"]["localized"] is False
    assert body["pose"]["status_message"] == "当前位姿已读取，定位状态待确认"
    assert body["pose"]["x"] == 1.0


def test_command_rejects_quit_without_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/command", json={"command": "quit"})

    assert response.status_code == 400
    assert "不支持的命令" in response.json()["detail"]


def test_command_sends_go_without_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/command", json={"command": "go"})

    assert response.status_code == 200
    assert response.json()["command"] == "go"


def test_task_guide_sends_go_without_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/task", json={"task": "guide"})

    assert response.status_code == 200
    assert response.json()["task"] == "guide"
    assert response.json()["command"] == "go"
    assert response.json()["message"] == "导览任务已启动"


def test_task_placeholders_return_message_without_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    dialogue = client.post("/api/task", json={"task": "dialogue"})
    vision = client.post("/api/task", json={"task": "vision"})

    assert dialogue.status_code == 200
    assert dialogue.json()["placeholder"] is True
    assert dialogue.json()["message"] == "对话任务暂未接入"
    assert vision.status_code == 200
    assert vision.json()["placeholder"] is True
    assert vision.json()["message"] == "视觉导航任务暂未接入"


def test_start_starts_loop_service_without_login(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    response = client.post("/api/start")

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["message"] == "已启动导航主程序"
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["start", "rabbitbot-loop.service"]


def test_restart_restarts_loop_service_without_login(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    response = client.post("/api/restart", json={"map_path": "/home/unitree/test10.pcd"})

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["map_path"] == "/home/unitree/test10.pcd"
    assert config.map_env_file.read_text(encoding="utf-8") == 'NAV_PCD_PATH="/home/unitree/test10.pcd"\n'
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["restart", "rabbitbot-loop.service"]


def test_stop_stops_loop_service_without_login(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    response = client.post("/api/stop")

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["message"] == "已关闭导航主程序"
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["stop", "rabbitbot-loop.service"]


def test_dialogue_loads_current_config(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/api/dialogue")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["summary"]["leader_calling"] == "各位领导"
    assert body["summary"]["map_file"] == "test9.pcd"
    assert '"text": "欢迎"' in body["content"]


def test_dialogue_save_validates_and_writes_config(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))
    content = '{"variables":{"leader_calling":"客户"},"opening":{},"steps":[{"segments":[{"text":"新的讲解词"}]}],"map_file":"test10.pcd","points":{}}'

    response = client.post("/api/dialogue", json={"content": content})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["leader_calling"] == "客户"
    saved = (config.dialogue_dir / "dialogue_0.json").read_text(encoding="utf-8")
    assert "新的讲解词" in saved
    assert list(config.dialogue_dir.glob("dialogue_0.json.*.bak"))


def test_dialogue_save_rejects_invalid_json(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/dialogue", json={"content": "{"})

    assert response.status_code == 400
    assert "JSON 解析失败" in response.json()["detail"]


def test_dialogue_save_rejects_invalid_structure(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/dialogue", json={"content": "[]"})

    assert response.status_code == 400
    assert "根节点必须是对象" in response.json()["detail"]


def test_logs_return_latest_nav_log_lines(tmp_path):
    config = make_config(tmp_path)
    (config.nav_log_dir / "nav_bridge_1.log").write_text("old\n", encoding="utf-8")
    latest = config.nav_log_dir / "nav_bridge_2.log"
    latest.write_text("one\ntwo\nthree\n", encoding="utf-8")
    client = TestClient(create_app(config))

    response = client.get("/api/logs?target=nav&lines=2")

    assert response.status_code == 200
    assert response.json()["lines"] == ["two", "three"]



def test_main_module_exposes_run_function():
    from rabbitbot.control_console.__main__ import run

    assert callable(run)



def test_page_shows_console_without_login_form(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'id="app"' in response.text
    assert 'style="display:none"' not in response.text
    assert 'id="loginForm"' not in response.text
    assert 'password' not in response.text.lower()
    assert '/api/login' not in response.text
    assert '开始任务' in response.text
    assert '导览' in response.text
    assert '对话' in response.text
    assert '视觉导航' in response.text
    assert '/api/task' in response.text
    assert '返航' in response.text
    assert '定位状态' in response.text
    assert '当前位姿' in response.text
    assert '开始程序' in response.text
    assert '一键重启' in response.text
    assert '关闭程序' in response.text
    assert '/api/start' in response.text
    assert 'startProgram' in response.text
    assert 'waitForServicesReady' in response.text
    assert '所有服务已加载成功，可执行相关操作' in response.text
    assert '服务仍未全部就绪，请查看状态或打开日志排查' in response.text
    assert '/api/stop' in response.text
    assert 'stopProgram' in response.text
    assert '/api/restart' in response.text
    assert '重启地图' in response.text
    assert 'mapPathInput' in response.text
    assert 'map_path' in response.text
    assert '导览讲解词' in response.text
    assert '加载讲解词' in response.text
    assert '保存讲解词' in response.text
    assert '折叠讲解词' in response.text
    assert '展开讲解词' in response.text
    assert 'dialogueToggleBtn' in response.text
    assert 'toggleDialogueEditor' in response.text
    assert 'dialogueEditor' in response.text
    assert '/api/dialogue' in response.text
    assert '显示日志' in response.text
    assert '关闭日志' in response.text
    assert 'logsVisible=false' in response.text
    assert '<pre id="logs" class="log" hidden>' in response.text
