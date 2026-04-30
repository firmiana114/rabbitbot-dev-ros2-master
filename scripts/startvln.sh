#!/bin/sh

docker start vln-fast
docker exec -d vln-fast /bin/bash /data/v-fuchengjia/Projects/robot_car/tools/run_navid_app.sh
# docker exec -it vln-fast /bin/bash
# docker stop vln-fast
