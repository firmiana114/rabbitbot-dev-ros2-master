#!/bin/bash

source py310/bin/activate

export PYTHONPATH=$(pwd):${PYTHONPATH}

export REALTIME_STT_BASE_URL=http://localhost:28184/v1
export REALTIME_TTS_BASE_URL=http://localhost:28185/v1

export RABBITBOT_STT_AGENT_URL=${REALTIME_STT_BASE_URL}
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

python tests/vln/test_vln.py
