#!/bin/bash

cd /datanvme/fuchengjia/projects/rabbitbot-dev-ros2-dev
source py38/bin/activate


source /opt/ros/foxy/setup.bash
cd /datanvme/fuchengjia/projects/vln/ros2_ws
rm -rf ./build ./install ./log
colcon build --symlink-install
