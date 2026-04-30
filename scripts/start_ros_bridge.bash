#!/bin/bash

unset HTTP_PROXY; unset HTTPS_PROXY

export ROS_MASTER_URI=http://kuavo_master:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

ros2 run ros1_bridge dynamic_bridge --bridge-all-topics
