# 交接报告

## 背景和目标

本轮目标是在当前 `June6_workflow` 分支中先不启动 VLM 和 Embedding，确认当前六月六日脚本化导览主流程是否可以不依赖这两个模型服务运行。项目主机 `AGX-orin-FX`，路径 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，分支 `June6_workflow`。

## 当前状态

已完成：

- 已核查当前 workflow：
  - VLM 仍在视觉问答工具路径中使用，但六月六日 DOCX 脚本化导览主流程不主动调用视觉问答。
  - Embedding 主要由 Memory Agent 查询路径使用；当前 DOCX 点位导航主流程使用内嵌 `DOCX_SCRIPT_POINTS`，不是 Memory Agent 检索。
  - 开场里查询 `点位1` 的 Memory Agent fallback 有异常捕获，不会阻断严格 DOCX 脚本。
- 已将统一容器入口 `scripts_1/unified_runtime/start_unified_container.sh` 改为默认跳过 VLM 和 Embedding：
  - `RABBITBOT_UNIFIED_START_VLM=0`
  - `RABBITBOT_UNIFIED_START_EMBEDDING=0`
- 已将宿主机启动脚本 `scripts_1/start_unified_integration_workflow.sh` 的等待逻辑同步改为默认不等待 8000/8005。
- 已在容器创建命令中显式执行挂载项目里的 `scripts_1/unified_runtime/start_unified_container.sh`，这样脚本改动无需重建统一镜像即可生效。
- 如果已有统一容器的 VLM/Embedding 启动配置与当前期望不一致，启动脚本会默认重建容器，避免旧容器继续按旧配置启动 VLM/Embedding。

未完成：

- 尚未启动统一容器实测“跳过 VLM/Embedding 后”六月六日 workflow 是否完整可跑。
- 尚未验证 Memory Agent 在没有 Embedding 服务时如果被用户自由问答路径触发会如何降级；当前只确认脚本化导览主流程不应依赖它。

## 已验证的事实

- `scripts_1/unified_runtime/start_unified_container.sh` 语法检查通过。
- `scripts_1/start_unified_integration_workflow.sh` 语法检查通过。
- VLM/Embedding 服务仍可通过环境变量恢复：
  - `RABBITBOT_UNIFIED_START_VLM=1`
  - `RABBITBOT_UNIFIED_START_EMBEDDING=1`
- 当前修改未改剧本文案、点位、动作字段、STT 灵敏度或 TTS 配置。

## 阻塞问题

无代码层面的阻塞。运行层面需要实际启动统一容器验证跳过 VLM/Embedding 后，TTS、STT、Robot Agent、workflow 是否都能按预期工作。

## 建议的下一步

- 运行非联调 workflow，确认不用 VLM/Embedding 时脚本化导览能走完。
- 如果用户在导览中触发视觉问答、自由问答中的视觉工具或 Memory Agent 语义检索，再按需恢复：
  - `RABBITBOT_UNIFIED_START_VLM=1 RABBITBOT_UNIFIED_START_EMBEDDING=1 bash scripts_1/start_unified_integration_workflow.sh`
- 如果只需要 VLM 不需要 Embedding，也可以只设置 `RABBITBOT_UNIFIED_START_VLM=1`。

## 注意事项

- 本轮不是删除 VLM/Embedding 能力，只是默认不启动、不等待。
- 由于容器入口改为执行挂载项目里的脚本，后续修改 `scripts_1/unified_runtime/start_unified_container.sh` 可以不重建镜像生效，但已有容器仍需要在配置变化时重建。
- 旧容器如果已经启动了 VLM/Embedding 进程，需要通过停止脚本或重建容器清理；本轮启动脚本会在配置不匹配时自动重建。

## 其它信息

如需同步到 `feature/unified-runtime-image`，可 cherry-pick 本轮提交。
