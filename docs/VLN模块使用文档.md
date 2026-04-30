
## 1. 启动 VLN App

```shell
docker start vln
docker exec -d vln /bin/bash /data/v-fuchengjia/Projects/robot_car/tools/run_navid_app.sh
```

建议：使用 `jtop` 观察 GPU 显存，等待 2 分钟左右，显存不再增加说明 VLN 模型初始化加载完毕。

## 2. VLN App 单元测试

```shell
# 启动另外一个 docker 容器
docker start navid-vllm-cuda-mic
docker exec -it navid-vllm-cuda-mic /bin/bash
cd /datanvme/fuchengjia/projects/rabbitbot-dev-ros2-dev

# 运行测试脚本
bash scripts/start_vln_test.bash
```

正常应该能看到如下输出：

```shell
# VLN 使用 8001 端口
VLNAgent: http://127.0.0.1:8001/act

# task 表示 VLN 的输入任务，比如去找穿着紫色衣服的人
task: Walk to the person in purple and then stop
# image_path 表示输入给 VLN 的图像路径
image_path: workspace/tools/navigation_tools/navi.png

# VLN 输出下一步动作
action: MoveType.STOP
```

## 3. 在 Workflow 中启用 VLN

目前在 Workflow 中默认没有启动 VLN，代码好像被注释掉了，要打开某些注释的 Code，Fucheng 还得回忆一下。
