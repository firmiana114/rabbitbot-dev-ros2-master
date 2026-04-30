#!/bin/sh

source py310/bin/activate

export PYTHONPATH=$(pwd):${PYTHONPATH}

export NEO4J_PASSWORD="your_password"
export RABBITBOT_MODEL_SERVER="http://127.0.0.1:8000/v1"
export GRAPHITI_RERANK_MODEL_URL=${RABBITBOT_MODEL_SERVER}
export GRAPHITI_EMBD_MODEL_URL="http://127.0.0.1:8005/v1"

python tests/memory/test_memory.py
