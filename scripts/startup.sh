#!/bin/sh

#screen -dmS bridge bash -c "ssh -t nuc 'bash system_with_domain_bridge.sh'"

docker start vlm
docker exec -d vlm /bin/bash /data/start_vllm_v2_quant.sh

# docker exec -it vlm /bin/bash
# bash /data/start_vllm_v2.sh
# docker stop vlm
