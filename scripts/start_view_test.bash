#!/bin/bash

#source py310/bin/activate

export PYTHONPATH=$(pwd):${PYTHONPATH}

export REALTIME_STT_BASE_URL=http://localhost:28184/v1
export REALTIME_TTS_BASE_URL=http://localhost:28185/v1

export RABBITBOT_STT_AGENT_URL=${REALTIME_STT_BASE_URL}
export RABBITBOT_TTS_AGENT_URL=${REALTIME_TTS_BASE_URL}

export RABBITBOT_MODEL="Qwen3-VL-8B-Instruct"
export RABBITBOT_MODEL_SERVER="http://192.168.20.76:8000/v1"
#python tests/view/test_subway_view.py
#python tests/view/test_subway_view_yolo_pipeline.py

#python tests/view/test_load_h265.py
#rm -f workspace/tools/vision_tools/video_3/h265_*.jpg
python tests/view/test_subway_view_yolo_pipeline_v2.py

#python tests/view/covert_csv.py
#python tests/view/calc_accuracy.py
# python tests/view/calc_accuracy_v2.py workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3_1/四类检测表（2060309最新2）_sim.csv
#python tests/view/simpfile_csv.py workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3_1/四类检测表（2060309最新2）.csv workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3_1/四类检测表（2060309最新2）_sim.csv
