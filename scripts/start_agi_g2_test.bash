#!/bin/bash

export PYTHONPATH=$(pwd):${PYTHONPATH}

export NEO4J_PASSWORD="your_password"
export RABBITBOT_MODEL_SERVER="http://127.0.0.1:8000/v1"
export GRAPHITI_RERANK_MODEL_URL=${RABBITBOT_MODEL_SERVER}
export GRAPHITI_EMBD_MODEL_URL="http://127.0.0.1:8005/v1"

export PYTHONPATH=$PYTHONPATH:$(pwd)

export RABBITBOT_ROBOT_AGENT_URL=http://10.42.1.101:28180

python tests/slam/test_slam.py
