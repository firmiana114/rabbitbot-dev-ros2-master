import json

from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch

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
    guide_state_file = project_root / "runtime" / "nav_workflow_control" / "guide_state"
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
        guide_state_file=guide_state_file,
        loop_service_name="rabbitbot-loop.service",
        systemctl_path=systemctl_path,
        sudo_path=None,
        map_env_file=map_env_file,
        dialogue_dir=dialogue_dir,
        dialogue_index="0",
        dialogue_file=None,
    )




def write_guide_state(config, state, run_id="20260617_010000", detail="测试状态", time="2026-06-17 01:00:00"):
    config.guide_state_file.parent.mkdir(parents=True, exist_ok=True)
    config.guide_state_file.write_text(
        f"state={state}\n"
        f"run_id={run_id}\n"
        f"detail={detail}\n"
        f"time={time}\n",
        encoding="utf-8",
    )


def test_status_does_not_require_login(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["map_path"] == "/home/unitree/test9.pcd"
    assert response.json()["autostart"]["enabled"] is False


def test_status_prefers_runtime_map_env_file(tmp_path):
    config = make_config(tmp_path)
    config.map_env_file.parent.mkdir(parents=True)
    config.map_env_file.write_text('NAV_PCD_PATH="/home/unitree/new_map.pcd"\n', encoding="utf-8")
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"):
        response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["map_path"] == "/home/unitree/new_map.pcd"




def test_status_marks_services_not_ready_when_main_loop_missing(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="not_detected"):
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["main_loop"] == "not_detected"
    assert body["nav_bridge"]["ready"] is False
    assert body["workflow"]["status"] == "loop_not_running"
    assert body["workflow"]["ready"] is False


def test_status_returns_unknown_guide_state_when_file_missing(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"),          patch("rabbitbot.control_console.app.is_port_open", return_value=True):
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["guide_state"] == {"state": "unknown", "run_id": "", "detail": "", "time": ""}


def test_status_returns_starting_guide_state_not_ready_semantics(tmp_path):
    config = make_config(tmp_path)
    write_guide_state(config, "starting", detail="启动中")
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"),          patch("rabbitbot.control_console.app.is_port_open", return_value=True):
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["main_loop"] == "running"
    assert body["nav_bridge"]["ready"] is True
    assert body["guide_state"]["state"] == "starting"
    assert body["guide_state"]["detail"] == "启动中"


def test_status_returns_qa_listening_as_ready_source(tmp_path):
    config = make_config(tmp_path)
    write_guide_state(config, "qa_listening", detail="导览 workflow 已停在 go 闸门")
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"),          patch("rabbitbot.control_console.app.is_port_open", return_value=True):
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["main_loop"] == "running"
    assert body["nav_bridge"]["ready"] is True
    assert body["guide_state"]["state"] == "qa_listening"


def test_status_returns_guide_running_state_for_disabled_guide_button(tmp_path):
    config = make_config(tmp_path)
    write_guide_state(config, "guide_running", detail="导览中")
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"),          patch("rabbitbot.control_console.app.is_port_open", return_value=True):
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["nav_bridge"]["ready"] is True
    assert body["guide_state"]["state"] == "guide_running"


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

    with patch("rabbitbot.control_console.app.detect_main_loop_running", return_value="running"):
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

    with patch("rabbitbot.control_console.commands._cleanup_tcp_port_occupants"):
        response = client.post("/api/restart", json={"map_path": "/home/unitree/test10.pcd"})

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["map_path"] == "/home/unitree/test10.pcd"
    assert config.map_env_file.read_text(encoding="utf-8") == 'NAV_PCD_PATH="/home/unitree/test10.pcd"\n'
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["start", "rabbitbot-loop.service"]


def test_stop_stops_loop_service_without_login(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    with patch("rabbitbot.control_console.commands._cleanup_tcp_port_occupants"):
        response = client.post("/api/stop")

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["message"] == "已关闭导航主程序"
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["stop", "rabbitbot-loop.service"]


def test_autostart_toggles_loop_service_without_login(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    response = client.post("/api/autostart", json={"enabled": True})

    assert response.status_code == 200
    assert response.json()["service"] == "rabbitbot-loop.service"
    assert response.json()["enabled"] is True
    record = config.project_root / "systemctl_args.txt"
    assert record.read_text(encoding="utf-8").splitlines() == ["enable", "rabbitbot-loop.service"]


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


def test_dialogue_hot_rows_loads_empty_table(tmp_path):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.get("/api/dialogue/hot-rows")

    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert body["message"] == "当前暂无表格新增点位，请点击 + 添加"


def test_dialogue_hot_rows_reads_existing_table_rows(tmp_path):
    config = make_config(tmp_path)
    (config.dialogue_dir / "dialogue_0.json").write_text(
        json.dumps(
            {
                "variables": {"leader_calling": "各位领导"},
                "opening": {},
                "steps": [
                    {
                        "scene": "console_point_1",
                        "entity_key": "console_point_1",
                        "source": "control_console_table",
                        "row_id": "1",
                        "segments": [{"text": "新增讲解"}],
                    }
                ],
                "map_file": "test9.pcd",
                "points": {
                    "console_point_1": {
                        "name": "console_point_1",
                        "source": "control_console_table",
                        "row_id": "1",
                        "location": [{"x": 1, "y": 2, "z": 3, "ox": 0, "oy": 0, "oz": 0, "ow": 1, "mode": 1}],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(config))

    response = client.get("/api/dialogue/hot-rows")

    assert response.status_code == 200
    assert response.json()["rows"] == [
        {
            "id": "1",
            "point_key": "console_point_1",
            "coordinate": '{"x":1,"y":2,"z":3,"ox":0,"oy":0,"oz":0,"ow":1,"mode":1}',
            "script": "新增讲解",
        }
    ]


def test_dialogue_hot_rows_save_appends_rows_and_backup(tmp_path):
    config = make_config(tmp_path)
    client = TestClient(create_app(config))

    response = client.post(
        "/api/dialogue/hot-rows",
        json={
            "rows": [
                {
                    "coordinate": '{"x":1,"y":2,"z":3,"ox":0,"oy":0,"oz":0,"ow":1}',
                    "script": "新增点位讲解",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "点位台词已保存，下一次导览生效，无需重启"
    saved = json.loads((config.dialogue_dir / "dialogue_0.json").read_text(encoding="utf-8"))
    assert saved["points"]["console_point_1"]["source"] == "control_console_table"
    assert saved["points"]["console_point_1"]["location"][0]["mode"] == 1
    assert saved["steps"][-1]["entity_key"] == "console_point_1"
    assert saved["steps"][-1]["segments"][0]["text"] == "新增点位讲解"
    assert saved["steps"][0]["segments"][0]["text"] == "欢迎"
    assert list(config.dialogue_dir.glob("dialogue_0.json.*.bak"))


def test_dialogue_hot_rows_save_replaces_only_managed_rows(tmp_path):
    config = make_config(tmp_path)
    original = {
        "variables": {"leader_calling": "各位领导"},
        "opening": {},
        "steps": [
            {"scene": "原始点位", "entity_key": "point_1", "segments": [{"text": "原始讲解"}]},
            {
                "scene": "console_point_old",
                "entity_key": "console_point_old",
                "source": "control_console_table",
                "row_id": "old",
                "segments": [{"text": "旧讲解"}],
            },
        ],
        "map_file": "test9.pcd",
        "points": {
            "point_1": {"name": "点位1", "location": [{"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 0, "ow": 1, "mode": 1}]},
            "console_point_old": {
                "name": "console_point_old",
                "source": "control_console_table",
                "location": [{"x": 9, "y": 9, "z": 0, "ox": 0, "oy": 0, "oz": 0, "ow": 1, "mode": 1}],
            },
        },
        "back_points": [{"name": "返航点", "location": [{"x": 0, "y": 1, "z": 0, "ox": 0, "oy": 0, "oz": 0, "ow": 1, "mode": 1}]}],
    }
    (config.dialogue_dir / "dialogue_0.json").write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    client = TestClient(create_app(config))

    response = client.post(
        "/api/dialogue/hot-rows",
        json={
            "rows": [
                {
                    "id": "fresh",
                    "coordinate": '{"x":2,"y":3,"z":0,"ox":0,"oy":0,"oz":0,"ow":1,"mode":1}',
                    "script": "新讲解",
                }
            ]
        },
    )

    assert response.status_code == 200
    saved = json.loads((config.dialogue_dir / "dialogue_0.json").read_text(encoding="utf-8"))
    assert "point_1" in saved["points"]
    assert "console_point_old" not in saved["points"]
    assert saved["back_points"] == original["back_points"]
    assert saved["steps"][0]["scene"] == "原始点位"
    assert saved["steps"][1]["entity_key"] == "console_point_fresh"


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([{"coordinate": "{", "script": "讲解"}], "不是有效 JSON 对象"),
        ([{"coordinate": '{"x":1}', "script": "讲解"}], "缺少字段"),
        ([{"coordinate": '{"x":"bad","y":0,"z":0,"ox":0,"oy":0,"oz":0,"ow":1}', "script": "讲解"}], "必须是数字"),
        ([{"coordinate": '{"x":1,"y":0,"z":0,"ox":0,"oy":0,"oz":0,"ow":1}', "script": ""}], "讲解台词不能为空"),
    ],
)
def test_dialogue_hot_rows_save_rejects_invalid_rows(tmp_path, rows, message):
    client = TestClient(create_app(make_config(tmp_path)))

    response = client.post("/api/dialogue/hot-rows", json={"rows": rows})

    assert response.status_code == 400
    assert message in response.json()["detail"]


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
    assert "data.guide_state.state==='qa_listening'" in response.text
    assert "function canStartGuide(data)" in response.text
    assert "guide_running:'导览中'" in response.text
    assert '视觉导航' in response.text
    assert '/api/task' in response.text
    assert '返航' in response.text
    assert '定位状态' in response.text
    assert '当前位姿' in response.text
    assert '开始程序' in response.text
    assert '一键重启' in response.text
    assert '关闭程序' in response.text
    assert '开机自启动' in response.text
    assert 'autostartBtn' in response.text
    assert 'toggleAutostart' in response.text
    assert '/api/autostart' in response.text
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
    assert '点位坐标' in response.text
    assert '讲解台词' in response.text
    assert '保存点位台词' in response.text
    assert '>+<' in response.text
    assert 'if(rows.length===0){addHotRow();}' in response.text
    assert '/api/dialogue/hot-rows' in response.text
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
