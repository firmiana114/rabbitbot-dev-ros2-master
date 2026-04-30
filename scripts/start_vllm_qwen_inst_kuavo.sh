#!/bin/sh

#uv pip install pandas

#vllm serve /data/Qwen3-Reranker-0.6B --served-model-name Qwen3-Reranker-0.6B --port 8004 > /data/qwen3-reranker-0.6b.log 2>& 1 &
#vllm serve /data/Qwen3-Embedding-0.6B --served-model-name Qwen3-Embedding-0.6B --task embed --port 8005 > /data/qwen3-embedding-0.6b.log 2>&1 &

export CUDA_VISIBLE_DEVICES=1

QWEN_MODEL_PATH=/media/dodo/FE88E35388E308CB/fuchengjia/Downloads/models/Qwen2.5-VL-7B-Instruct

vllm serve ${QWEN_MODEL_PATH} \
    --seed 42 \
    --gpu-memory-utilization 0.9 \
    --max-num-seqs 2 \
    --limit-mm-per-prompt "image=2,video=1" \
    --max-num-batched-tokens 2048 \
    --enable-chunked-prefill \
    --mm-processor-kwargs '{"max_pixels": 802816, "fps": 1}' \
    --max-model-len 65536 \
    --served-model-name Qwen2.5-VL-7B-Instruct \
    --port 28014
