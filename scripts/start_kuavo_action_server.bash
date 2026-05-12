#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

source py38/bin/activate

unset HTTP_PROXY; unset HTTPS_PROXY

export ROS_MASTER_URI=http://kuavo_master:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source "${RABBITBOT_VLN_WS_DIR}/install/setup.bash"

cd "${RABBITBOT_VLN_WS_DIR}/src/custom_action_interfaces/scripts"

python3 kuavo_action_server.py
