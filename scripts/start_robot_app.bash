#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export ROS_MASTER_URI=http://192.168.26.1:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source py38/bin/activate

ROBOT_PYTHON=py38/bin/python
if [ "${RABBITBOT_ROBOT_USE_SYSTEM_PY38:-0}" = "1" ]; then
    ROBOT_PYTHON=/usr/bin/python3.8
    export PYTHONPATH=$(pwd)/py38/lib/python3.8/site-packages:${PYTHONPATH:-}
fi

# source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source "${RABBITBOT_VLN_WS_DIR}/install/setup.bash"

export CUR_DIR=$(pwd)

cd "${RABBITBOT_PYORBBEC_DIR}"

export PYTHONPATH=$PYTHONPATH:$(pwd)/install/lib/

cd ${CUR_DIR}

export PYTHONPATH=/usr/local/lib:$(pwd):${PYTHONPATH}

export RABBITBOT_MODEL_SERVER=http://127.0.0.1:8000/v1
#export RABBITBOT_VLN_URL=http://127.0.0.1:28181
export RABBITBOT_VLN_URL=http://127.0.0.1:8001

export RABBITBOT_MEMORY_AGENT_URL=http://127.0.0.1:28182

export REALTIME_STT_BASE_URL=http://localhost:28184/v1
export REALTIME_TTS_BASE_URL=http://localhost:28185/v1

export RABBITBOT_STT_AGENT_URL=${REALTIME_STT_BASE_URL}
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

# 可选值：gemini 或 null。不设置时使用 kuavo_configs.json。
export RABBITBOT_ROBOT_CAMERA="${RABBITBOT_ROBOT_CAMERA:-}"

export DEBUG_PROPAGATE_EXCEPTIONS=True

${ROBOT_PYTHON} -m uvicorn robot_app:app --host 0.0.0.0 --port 28180 --log-level debug

#python3 robot_app.py
