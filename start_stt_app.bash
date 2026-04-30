#!/bin/sh

export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libgomp.so.1
export LD_LIBRARY_PATH=/opt/ctranslate2-cuda/lib:/usr/local/cuda/lib64:/usr/local/cuda/targets/aarch64-linux/lib:/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH}
# export LD_LIBRARY_PATH=/opt/ctranslate2/lib

export HF_ENDPOINT=https://hf-mirror.com

#export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

export REALTIME_TTS_BASE_URL=http://localhost:28185/v1
#export REALTIME_TTS_BASE_URL=http://10.10.30.19:28185/v1
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

#export STT_CLOUD="http://10.10.30.22:28186"

source py310/bin/activate

#DEVICE_NAME="USB Audio Device"
DEVICE_NAME="Wireless Mic Rx"
DEVICE_STR=$(bash scripts/start_pyaudio_test.bash | grep "${DEVICE_NAME}")
DEVICE_INDEX=$(echo "$DEVICE_STR" | cut -d':' -f1)

export INPUT_DEVICE_INDEX=$DEVICE_INDEX

export TORCH_HUB_DISABLE_NETWORK=1

uvicorn stt_app:app --host 0.0.0.0 --port 28184 --log-level debug --workers 1
#python stt_app.py
