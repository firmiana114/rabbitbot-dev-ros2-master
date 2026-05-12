#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

source py38/bin/activate

#export PATH=${HOME}/workspace/rabbitbot/.venv/bin:${PATH}

export ROS_MASTER_URI=http://192.168.26.1:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source "${RABBITBOT_VLN_WS_DIR}/install/setup.bash"

export CUR_DIR=$(pwd)

cd "${RABBITBOT_PYORBBEC_LEGACY_DIR}"

export PYTHONPATH=$PYTHONPATH:$(pwd)/install/lib/

#./install_udev_rules.sh

cd ${CUR_DIR}

export PYTHONPATH=/usr/local/lib:$(pwd):${PYTHONPATH}

echo ${PYTHONPATH}

export RABBITBOT_MODEL_SERVER=http://127.0.0.1:8000/v1
#export RABBITBOT_VLN_URL=http://127.0.0.1:28181
export RABBITBOT_VLN_URL=http://127.0.0.1:8001

export RABBITBOT_MEMORY_AGENT_URL=http://127.0.0.1:28182

export OUTPUT_DEVICE_INDEX=25

#export HTTP_PROXY="http://127.0.0.1:7897"; export HTTPS_PROXY="http://127.0.0.1:7897"

#python3 tests/tasks/test_error.py

python3 examples/multi_agents_kuavo.py
