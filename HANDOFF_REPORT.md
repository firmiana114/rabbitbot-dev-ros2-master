# 交接报告

## 背景和目标

本轮目标是调整当前 `June6_workflow` 分支中的动作执行策略：除 `shake_hand` 握手外，其它动作都应与说话同步执行，并且不能阻塞或延后 TTS 说话。项目运行主机为 `AGX-orin-FX`，项目路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`。

## 当前状态

已完成：

- 新增统一判断 `_should_speak_with_action(action_name, configured=False)`：
  - 无动作时不并发。
  - 显式配置 `speak_with_action` 时并发。
  - 动作不是 `shake_hand` 时默认并发。
- 已将两个 DOCX 剧本执行循环改为使用统一判断，避免段落漏写 `speak_with_action` 时退回“先动作、再说话”。
- 已将旧的实体导览路径也改为非握手动作与介绍文本并发执行。
- 现有动作链路日志继续保留，会记录新动作字段的开始、回执、释放和并发执行阶段。
- 已保留此前的新动作字段改造、单容器双模式 unified 启动改造和 STT 灵敏度改造。

未完成：

- 尚未在真实机器人上验证所有非握手动作与 TTS 并发时的体感效果。
- `shake_hand` 仍允许按调用点显式决定是否与说话并发；本轮只保证非握手动作默认并发。

## 已验证的事实

- 当前分支为 `June6_workflow`。
- `rabbitbot/agno_agents/workflow.py` 可以通过 Python 编译检查。
- 现有六月六日剧本动作字段仍使用新字段名：`shake_hand`、`face_wave`、`right_hand_up`、`high_wave`。

## 阻塞问题

当前没有代码层面的阻塞。运行层面仍需真实机器人动作服务验证并发执行是否稳定。

## 建议的下一步

- 先运行非联调 workflow，确认文本流程和 STT 打断不受影响。
- 再运行联调 workflow，重点观察 `face_wave`、`right_hand_up`、`high_wave` 是否在说话期间同时执行。
- 如某个动作时间过长或释放过早，可继续调整对应释放延迟环境变量。

## 注意事项

- 本轮没有修改六月六日剧本文案。
- 本轮没有改变 `release` 字段名。
- 如果后续希望 `shake_hand` 也统一不与说话并发，需要单独调整当前开场握手调用点。

## 其它信息

本轮修改集中在 `rabbitbot/agno_agents/workflow.py`。如后续需要同步到其它分支，可 cherry-pick 本轮提交。
