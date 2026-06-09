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
        "[INFO] [1] [hybrid_navigation_node_66]: \x1b[32m[Auto-Relocation] Success! Current pose:\x1b[0m\n"
        "[INFO] [1] [hybrid_navigation_node_66]:   x: -0.3913  y: 16.9003  z: -0.0693\n"
        "[INFO] [1] [hybrid_navigation_node_66]:   ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579\n"
        "[INFO] [2] [hybrid_navigation_node_66]: \x1b[36m[Pose]\x1b[0m x: 1.2345  y: -2.3456  z: 0.1000  ox: 0.0100  oy: 0.0200  oz: 0.0300  ow: 0.9990\n",
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
        "[INFO] [1] [hybrid_navigation_node_66]: [Auto-Relocation] Success! Current pose:\n"
        "[INFO] [1] [hybrid_navigation_node_66]:   x: -0.3913  y: 16.9003  z: -0.0693\n"
        "[INFO] [1] [hybrid_navigation_node_66]:   ox: 0.1253  oy: 0.0844  oz: 0.7378  ow: 0.6579\n",
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
    (control / "20260608_090000.status").write_text("finished\n", encoding="utf-8")
    (control / "20260608_090000.exit_code").write_text("0\n", encoding="utf-8")
    (control / "20260609_100000.status").write_text("running\n", encoding="utf-8")
    (control / "20260609_100000.ready").write_text("ready\n", encoding="utf-8")
    (control / "20260609_100000.pid").write_text("1234\n", encoding="utf-8")

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
    log.write_text("one\n\x1b[32mtwo\x1b[0m\nthree\n", encoding="utf-8")

    assert get_tail_lines(log, 2) == ["two", "three"]


def test_console_config_defaults_to_test9_map(monkeypatch):
    monkeypatch.delenv("NAV_PCD_PATH", raising=False)

    config = ConsoleConfig.from_env()

    assert config.map_path == "/home/unitree/test9.pcd"
