#!/usr/bin/env bash
# 统一镜像冒烟检查：只验证运行时和导入能力，不启动完整 workflow。

set -Eeuo pipefail

PROJECT_DIR="${RABBITBOT_DIR:-/data/rabbitbot-dev-ros2-master}"

/opt/venv/bin/python - <<'PY'
import fastapi
import sounddevice
import uvicorn
print("audio_runtime_ok")
PY

/opt/rabbitbot-vllm-venv/bin/python - <<'PY'
import vllm
print("vllm_runtime_ok")
PY

if [ -d "${PROJECT_DIR}" ]; then
    cd "${PROJECT_DIR}"
    py310/bin/python - <<'PY'
import agno
from rabbitbot.agno_agents.workflow import create_main_workflow
print("workflow_runtime_ok")
PY
    PYTHONPATH="${PROJECT_DIR}/py38/lib/python3.8/site-packages:${PROJECT_DIR}:${PYTHONPATH:-}" /usr/bin/python3.8 - <<'PY'
import uvicorn
print("robot_python38_runtime_ok")
PY
else
    echo "未挂载项目目录，跳过项目导入检查：${PROJECT_DIR}"
fi

JAVA_HOME=/opt/java/openjdk /opt/java/openjdk/bin/java -version >/tmp/rabbitbot_unified_java_version 2>&1
head -1 /tmp/rabbitbot_unified_java_version
echo "neo4j_java_runtime_ok"
