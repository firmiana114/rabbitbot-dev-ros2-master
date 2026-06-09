import pytest

from rabbitbot.control_console.commands import CommandError, send_workflow_command


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
