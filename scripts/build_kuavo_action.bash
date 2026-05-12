#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

cd "${RABBITBOT_REPO_DIR}"
source py38/bin/activate


source /opt/ros/foxy/setup.bash
cd "${RABBITBOT_VLN_WS_DIR}"
rm -rf ./build ./install ./log
colcon build --symlink-install
