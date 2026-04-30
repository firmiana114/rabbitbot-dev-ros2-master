#!/bin/sh

#export HTTP_PROXY="http://127.0.0.1:7897"
#export HTTPS_PROXY="http://127.0.0.1:7897"

#curl -v https://registry-1.docker.io/v2/

#docker pull neo4j:5.26-community

export NEO4J_PASS=neo4j_pass

docker run \
    --name neo4j-community \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/${NEO4J_PASS} \
    -e NEO4J_PLUGINS='["apoc"]' \
    neo4j:5.26-community
