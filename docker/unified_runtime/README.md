# 统一运行时镜像实验

本目录用于实验把 RabbitBot 当前四个运行镜像合并为一个运行时镜像。

当前统一镜像名：

```bash
rabbitbot-unified-runtime:20260518
```

合入来源：

| 来源镜像 | 用途 |
| --- | --- |
| `navid-rabbitbot:stt-tts-audio-ct2cuda-20260511` | 统一镜像基底、STT/TTS 运行时 |
| `rabbitbot-vllm:20260511` | VLM/Embedding vLLM 运行时 |
| `foxy-ros-cam-orb-ubuntu20:rabbitbot-20260511` | ROS Foxy、Robot Agent 所需 Python 3.8 运行时 |
| `neo4j:5.26-community` | Neo4j 程序、Java、入口依赖 |

构建和冒烟检查：

```bash
cd /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master
bash scripts_1/build_unified_runtime_image.sh
```

启动统一联调容器：

```bash
cd /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master
AUTO_START_WORKFLOW=0 \
RABBITBOT_TTS_ALLOW_BUILTIN=1 \
START_AFTER_CREATE=1 \
bash scripts_1/start_unified_integration_workflow.sh
```

当前验证状态：

| 项 | 状态 |
| --- | --- |
| 镜像构建 | 已通过 |
| 冒烟检查 | 已通过 |
| Neo4j | 统一容器内可启动 |
| VLM | 统一容器内可启动，默认降为 `max_model_len=32768` |
| Embedding | 统一容器内可启动 |
| TTS | 统一容器默认使用 CPU 和轻量启动，跳过启动时常用语预生成 |
| STT/Memory/Robot/Workflow | 依赖 TTS 轻量启动后继续验证 |

已知问题：

1. TTS 原实现默认使用 CUDA。单容器内 VLM/Embedding 已占用 GPU 后，TTS CUDA 初始化容易卡住。
3. 统一容器默认把 `RABBITBOT_TTS_DEVICE` 设置为 `cpu`，并设置 `RABBITBOT_TTS_FAST_SOUND_PRELOAD=0`、`RABBITBOT_TTS_STARTUP_SPEECH=0`，避免 CPU 模式在 Uvicorn 监听前同步预生成常用语。
4. 项目目录挂载到 `/workspace/projects`，避免 Neo4j 官方镜像把数据卷挂到 `/data` 时遮蔽项目目录。
6. 轻量启动后，常用语会在首次 `fast_sound_*` 请求时惰性生成并缓存；首次播放可能仍有额外延迟。
7. 因此当前统一镜像还不能替代四容器稳定架构，只能作为继续压缩镜像和排查资源策略的实验基线。

后续优先方向：

1. 继续验证 STT、Memory Agent、Robot Agent 和前台 workflow。
2. 评估首次惰性生成常用语的延迟是否可接受。
3. 或把 VLM/Embedding 的 GPU 资源占用继续下调，让 TTS 保持 CUDA。
