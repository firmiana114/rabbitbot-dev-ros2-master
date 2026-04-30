#!/bin/sh

#uv pip install pandas

#vllm serve /data/Qwen3-Reranker-0.6B --served-model-name Qwen3-Reranker-0.6B --port 8004 > /data/qwen3-reranker-0.6b.log 2>& 1 &
#vllm serve /data/Qwen3-Embedding-0.6B --served-model-name Qwen3-Embedding-0.6B --task embed --port 8005 > /data/qwen3-embedding-0.6b.log 2>&1 &

export CUDA_VISIBLE_DEVICES=0

QWEN_MODEL_PATH=/media/dodo/FE88E35388E308CB/fuchengjia/Downloads/models/Qwen3-Embedding-0.6B

vllm serve ${QWEN_MODEL_PATH} \
    --served-model-name Qwen3-Embedding-0.6B \
    --gpu-memory-utilization 0.2 \
    --task embed \
    --port 28015
