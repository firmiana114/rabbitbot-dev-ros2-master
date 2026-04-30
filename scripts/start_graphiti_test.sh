#!/bin/sh

export PYTHONPATH=$(pwd):${PYTHONPATH}

export NEO4J_PASSWORD="neo4j_pass"
export GRAPHITI_RERANK_MODEL_URL="http://127.0.0.1:28014/v1"
export GRAPHITI_EMBD_MODEL_URL="http://127.0.0.1:28015/v1"

#python examples/memory/test_graphiti.py
python examples/memory/test_graphiti_v2.py
