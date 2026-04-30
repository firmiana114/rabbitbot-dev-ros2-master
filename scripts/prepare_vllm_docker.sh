#!/bin/sh

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path_to_store_models>"
    exit 1
fi

cp $(dirname "$0")/start_vllm.sh $1/start_vllm.sh

huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct --local-dir $1/Qwen2.5-VL-7B-Instruct
huggingface-cli download Qwen/Qwen3-Reranker-0.6B --local-dir $1/Qwen3-Reranker-0.6B
# huggingface-cli download Qwen/Qwen3-Embedding-0.6B --local-dir $1/Qwen3-Embedding-0.6B

docker run --runtime nvidia --gpus all --ipc=host --net=host -v $1:/data --entrypoint /bin/bash dustynv/vllm:0.9.2-r36.4-cu128-24.04 /data/start_vllm.sh