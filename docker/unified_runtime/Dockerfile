# 夸父机器人统一运行时实验镜像。
# 目标是在不删除原有四个镜像的前提下，把 workflow、音频、VLM、Neo4j 的运行时合入一个镜像。

FROM rabbitbot-vllm:20260511 AS vllm
FROM foxy-ros-cam-orb-ubuntu20:rabbitbot-20260511 AS workflow
FROM neo4j:5.26-community AS neo4j
FROM navid-rabbitbot:stt-tts-audio-ct2cuda-20260511 AS runtime

USER root

# VLM 镜像和音频镜像同为 Ubuntu 24.04 / Python 3.12，保留各自 venv，避免依赖互相覆盖。
COPY --from=vllm /opt/venv /opt/rabbitbot-vllm-venv

# workflow/robot 依赖 ROS Foxy 和 Python 3.8；这些来自原 workflow 镜像。
COPY --from=workflow /opt/ros/foxy /opt/ros/foxy
COPY --from=workflow /usr/bin/python3.8 /usr/bin/python3.8
COPY --from=workflow /usr/lib/python3.8 /usr/lib/python3.8
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libpython3.8* /usr/lib/aarch64-linux-gnu/
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libssl.so.1.1 /usr/lib/aarch64-linux-gnu/
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libcrypto.so.1.1 /usr/lib/aarch64-linux-gnu/
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libffi.so.7* /usr/lib/aarch64-linux-gnu/
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libtinyxml2.so.6* /usr/lib/aarch64-linux-gnu/
COPY --from=workflow /usr/lib/aarch64-linux-gnu/libspdlog.so* /usr/lib/aarch64-linux-gnu/

# Neo4j 复制官方镜像内的程序、入口脚本和 Java 运行时。
COPY --from=neo4j /var/lib/neo4j /var/lib/neo4j
COPY --from=neo4j /startup /startup
COPY --from=neo4j /opt/java /opt/java
COPY --from=neo4j /usr/bin/jq /usr/bin/jq
COPY --from=neo4j /usr/bin/su-exec /usr/bin/su-exec
COPY --from=neo4j /usr/lib/aarch64-linux-gnu/libjq.so.1* /usr/lib/aarch64-linux-gnu/
COPY --from=neo4j /usr/lib/aarch64-linux-gnu/libonig.so.5* /usr/lib/aarch64-linux-gnu/

ENV JAVA_HOME=/opt/java/openjdk \
    NEO4J_HOME=/var/lib/neo4j \
    PATH=/var/lib/neo4j/bin:/opt/java/openjdk/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    RABBITBOT_DIR=/workspace/projects/rabbitbot-dev-ros2-master \
    RABBITBOT_MODELS_DIR=/models

COPY scripts_1/unified_runtime/start_unified_container.sh /usr/local/bin/rabbitbot-start-unified
COPY scripts_1/unified_runtime/smoke_check.sh /usr/local/bin/rabbitbot-unified-smoke-check

RUN chmod +x /usr/local/bin/rabbitbot-start-unified /usr/local/bin/rabbitbot-unified-smoke-check \
    && mkdir -p /data /workspace/projects /models /logs /var/lib/neo4j/data /var/lib/neo4j/logs \
    && (getent group neo4j >/dev/null || groupadd -g 7474 neo4j) \
    && (id neo4j >/dev/null 2>&1 || useradd -u 7474 -g neo4j -d /var/lib/neo4j -s /usr/sbin/nologin neo4j) \
    && chown -R neo4j:neo4j /var/lib/neo4j

CMD ["/usr/local/bin/rabbitbot-start-unified"]
