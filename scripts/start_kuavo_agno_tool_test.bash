#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

#source py38/bin/activate
source py310/bin/activate

#export PATH=${HOME}/workspace/rabbitbot/.venv/bin:${PATH}

export ROS_MASTER_URI=http://kuavo_master:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source "${RABBITBOT_VLN_WS_DIR}/install/setup.bash"

export CUR_DIR=$(pwd)

cd "${RABBITBOT_PYORBBEC_DIR}"

export PYTHONPATH=$PYTHONPATH:$(pwd)/install/lib/

#./install_udev_rules.sh

cd ${CUR_DIR}

export PYTHONPATH=/usr/local/lib:$(pwd):${PYTHONPATH}

echo ${PYTHONPATH}

export RABBITBOT_MODEL_SERVER=http://127.0.0.1:8000/v1
#export RABBITBOT_MODEL_SERVER=http://10.10.30.15:8000/v1
#export RABBITBOT_VLN_URL=http://127.0.0.1:28181
export RABBITBOT_VLN_URL=http://127.0.0.1:8001

export RABBITBOT_MEMORY_AGENT_URL=http://127.0.0.1:28182

export RABBITBOT_ROBOT_AGENT_URL=http://localhost:28180

export REALTIME_STT_BASE_URL=http://localhost:28184/v1
export REALTIME_TTS_BASE_URL=http://localhost:28185/v1

export RABBITBOT_STT_AGENT_URL=${REALTIME_STT_BASE_URL}
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

export OUTPUT_DEVICE_INDEX=25

#export HTTP_PROXY="http://127.0.0.1:7897"; export HTTPS_PROXY="http://127.0.0.1:7897"

#python3 tests/tasks/test_error.py
#python3 tests/audio/test_long_chat_stop.py

#python3 examples/run_kuavo_agno_tool.py
#python3 examples/run_kuavo_agno_agent.py


#ros2 action list

# position_x: 0.8279, position_y: 0.4392
# position_x: 0.7806, position_y: 0.2126
# position_x: 0.7014, position_y: -0.1322
# position_x: 0.7215, position_y: -0.3167
#ros2 action send_goal /navi_ik_arm custom_action_interfaces/action/NaviIkArm \
#  "{position_x: 1.0939, position_y: -0.4394, position_z: -0.4020, orientation_x: 0.0, orientation_y: 0.0, orientation_z: 0.0, orientation_w: 0.0}"

#ros2 action send_goal /navi_grab custom_action_interfaces/action/NaviGrab \
#   "{position_x: 0.7451, position_y: 0.1735, position_z: -0.1960, orientation_x: 0.0, orientation_y: 0.0, orientation_z: 0.0, orientation_w: 0.0}"

ros2 action send_goal /navi_head custom_action_interfaces/action/NaviHead "{yaw: 0.0, pitch: 25.0}"

ros2 topic echo /catch
