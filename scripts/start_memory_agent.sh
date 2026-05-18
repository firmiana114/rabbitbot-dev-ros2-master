#!/bin/sh

source py310/bin/activate

export PYTHONPATH=$(pwd):${PYTHONPATH}

export NEO4J_PASSWORD="${NEO4J_PASSWORD:-neo4j_pass}"
export RABBITBOT_MODEL_SERVER="http://127.0.0.1:8000/v1"
export GRAPHITI_RERANK_MODEL_URL=${RABBITBOT_MODEL_SERVER}
export GRAPHITI_EMBD_MODEL_URL="http://127.0.0.1:8005/v1"

#export CUR_DIR=$(pwd)
#cd ~/workspace/rabbitbot && source ./.venv/bin/activate
#cd ${CUR_DIR}

py310/bin/python -m uvicorn memory_app:app --host 0.0.0.0 --port 28182 --reload --log-level debug
