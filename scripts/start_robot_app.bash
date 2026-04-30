#!/bin/bash

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1

export ROS_MASTER_URI=http://192.168.26.1:11311
export ROS_IP=192.168.26.13
export ROS_HOSTNAME=${ROS_IP}

source py38/bin/activate

source /opt/ros/noetic/setup.bash
source /opt/ros/foxy/setup.bash

source /data/vln/ros2_ws/install/setup.bash

export CUR_DIR=$(pwd)

cd /data/pyorbbecsdk-v2-py310

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

export DEBUG_PROPAGATE_EXCEPTIONS=True

uvicorn robot_app:app --host 0.0.0.0 --port 28180 --log-level debug

#python3 robot_app.py
