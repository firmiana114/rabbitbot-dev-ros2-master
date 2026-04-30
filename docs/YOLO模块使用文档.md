
## 1. 启动 YOLO App

### 1-1. 启动容器

```shell
docker start yolo
```

### 1-2. 启动 App

```shell
cd /datanvme/fuchengjia/projects/rabbitbot-dev-ros2-dev
bash scripts/start_yolo_app.bash
```

## 2. 单元测试 YOLO App

```shell
# 启动另外一个 docker 容器
docker start navid-vllm-cuda-mic
docker exec -it navid-vllm-cuda-mic /bin/bash
cd /datanvme/fuchengjia/projects/rabbitbot-dev-ros2-dev

# 运行测试脚本
bash scripts/start_yolo_test.bash
```

正常应该能看到如下输出：

```shell
yolo_time: 0.260
bbox: [297, 182, 578, 776]
bbox: [553, 177, 781, 926]
BBOX 图片已保存到： workspace/yolo/无包识别_bbox.png
```

## 3. 单元测试 YOLO+Qwen Pipeline

```shell
# 启动另外一个 docker 容器
docker start navid-vllm-cuda-mic
docker exec -it navid-vllm-cuda-mic /bin/bash
cd /datanvme/fuchengjia/projects/rabbitbot-dev-ros2-dev

# 运行测试脚本
bash scripts/start_view_test.bash
```

正常应该能看到如下输出：

```shell
# YOLO 输出
yolo_time: 0.258
num_bboxes: 2
bboxes: [[150, 247, 366, 758], [365, 224, 463, 500]]

# Qwen 大模型输出
agent_time: 0.651
out_text:
1  # 是否带液体
0  # 是否交互
0  # 是否为特殊人群
1  # 是否带包
```
