#!/bin/bash

#source py38/bin/activate
source py310/bin/activate

export PYTHONPATH=/usr/local/lib:$(pwd):${PYTHONPATH}

echo ${PYTHONPATH}

export RABBITBOT_MODEL_SERVER=http://127.0.0.1:8000/v1
#export RABBITBOT_MODEL_SERVER=http://10.10.30.22:8000/v1
#export RABBITBOT_VLN_URL=http://127.0.0.1:28181
export RABBITBOT_VLN_URL=http://127.0.0.1:8001

export RABBITBOT_MEMORY_AGENT_URL=http://127.0.0.1:28182

export RABBITBOT_ROBOT_AGENT_URL=http://localhost:28180

export REALTIME_STT_BASE_URL=http://localhost:28184/v1
export REALTIME_TTS_BASE_URL=http://localhost:28185/v1

export RABBITBOT_STT_AGENT_URL=${REALTIME_STT_BASE_URL}
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

#export OUTPUT_DEVICE_INDEX=25

#export HTTP_PROXY="http://127.0.0.1:7897"; export HTTPS_PROXY="http://127.0.0.1:7897"

#python3 tests/tasks/test_error.py

#python3 tests/audio/test_long_chat_stop.py

python3 examples/run_kuavo_agno.py --patch

#ros2 action send_goal /navi_arm custom_action_interfaces/action/NaviArm "{action_name: '点赞'}"
#ros2 action send_goal /navi_arm custom_action_interfaces/action/NaviArm "{action_name: '打招呼'}"
#ros2 action send_goal /navi_head custom_action_interfaces/action/NaviHead "{yaw: xxx, pitch: xxx}"
