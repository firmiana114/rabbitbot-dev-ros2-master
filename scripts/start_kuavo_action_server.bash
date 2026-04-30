#!/bin/bash

source py38/bin/activate

unset HTTP_PROXY; unset HTTPS_PROXY

export ROS_MASTER_URI=http://kuavo_master:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source /data/vln/ros2_ws/install/setup.bash

cd /data/vln/ros2_ws/src/custom_action_interfaces/scripts

python3 kuavo_action_server.py
