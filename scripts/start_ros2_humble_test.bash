#!/bin/bash

source /opt/ros/humble/setup.bash

echo "Pkg List"
ros2 pkg list

echo "Topic List"
ros2 topic list
