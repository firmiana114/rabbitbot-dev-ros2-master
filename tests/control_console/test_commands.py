import pytest

from rabbitbot.control_console.commands import CommandError, restart_loop_service, send_workflow_command, start_task


def test_send_workflow_command_allows_go_and_invokes_script(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("go", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "go"
    assert result["message"] == "已发送命令：go"
    assert record.read_text(encoding="utf-8").strip() == "go"


def test_send_workflow_command_allows_back(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("back", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "back"
    assert record.read_text(encoding="utf-8").strip() == "back"


@pytest.mark.parametrize("command", ["quit", "exit", "restart", "go; rm -rf /", ""])
def test_send_workflow_command_rejects_non_whitelisted_commands(tmp_path, command):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command(command, script)

    assert "不支持的命令" in str(excinfo.value)


def test_send_workflow_command_reports_script_failure(tmp_path):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\necho failure >&2\nexit 7\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command("go", script)

    assert "failure" in str(excinfo.value)


def test_restart_loop_service_invokes_systemctl_restart(tmp_path):
    systemctl = tmp_path / "systemctl"
    record = tmp_path / "record.txt"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    result = restart_loop_service(systemctl_path=systemctl, sudo_path=None)

    assert result["ok"] is True
    assert result["service"] == "rabbitbot-loop.service"
    assert record.read_text(encoding="utf-8").splitlines() == ["restart", "rabbitbot-loop.service"]


def test_restart_loop_service_rejects_other_services(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        restart_loop_service("ssh.service", systemctl_path=systemctl, sudo_path=None)

    assert "不支持重启的服务" in str(excinfo.value)


def test_restart_loop_service_reports_failure(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\necho restart failed >&2\nexit 9\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        restart_loop_service(systemctl_path=systemctl, sudo_path=None)

    assert "restart failed" in str(excinfo.value)


def test_start_task_guide_sends_go(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = start_task("guide", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["task"] == "guide"
    assert result["task_label"] == "导览"
    assert result["placeholder"] is False
    assert result["command"] == "go"
    assert result["message"] == "导览任务已启动"
    assert record.read_text(encoding="utf-8").strip() == "go"


def test_start_task_placeholders_do_not_invoke_script(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        f"#!/usr/bin/env bash\necho called > {record}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    dialogue = start_task("dialogue", script)
    vision = start_task("vision", script)

    assert dialogue["placeholder"] is True
    assert dialogue["message"] == "对话任务暂未接入"
    assert vision["placeholder"] is True
    assert vision["message"] == "视觉导航任务暂未接入"
    assert not record.exists()


def test_start_task_rejects_unknown_task(tmp_path):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        start_task("bad", script)

    assert "不支持的任务" in str(excinfo.value)
