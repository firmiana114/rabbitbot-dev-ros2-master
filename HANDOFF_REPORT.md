# 交接报告

## 背景和目标

本轮目标是让统一容器的联调和非联调 workflow 共用同一个容器实例，避免 `rabbitbot-unified-runtime` 与 `rabbitbot-unified-runtime-non-integration` 两套容器状态互相分叉。当前工作分支为 `June6_workflow`，项目运行主机为 `AGX-orin-FX`，项目路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`。

## 当前状态

已完成：

- 已将统一容器启动模型改为“基础服务常驻容器 + workflow 按需前台执行”。
- `scripts_1/start_unified_integration_workflow.sh` 创建容器时固定设置 `AUTO_START_WORKFLOW=0`，容器入口只启动 Neo4j、VLM、Embedding、TTS、STT、Memory Agent、Robot Agent，并保持容器运行。
- 联调 workflow 现在由宿主机脚本通过 `docker exec` 在 `rabbitbot-unified-runtime` 内前台启动，默认传入 `RABBITBOT_WORKFLOW_NON_INTEGRATION=0`。
- `scripts_1/start_unified_non_integration_workflow.sh` 现在也默认使用 `rabbitbot-unified-runtime`，并在本次 `docker exec` 中传入 `RABBITBOT_WORKFLOW_NON_INTEGRATION=1`。
- 非联调模式仍默认启用终端输入转发，导航点位可通过终端回车确认成功。
- 启动脚本会等待基础服务端口就绪，再启动 workflow，避免 workflow 早于服务可用。
- 如果发现已有统一容器仍是旧的自启动 workflow 模式，脚本默认会重建为基础服务模式，避免旧环境变量残留。

未完成：

- 尚未在真实统一容器中启动一轮联调和非联调 workflow 做完整运行验证。
- 尚未删除历史遗留的 `rabbitbot-unified-runtime-non-integration` 容器；停止脚本仍会兼容清理这个旧容器。

## 已验证的事实

- 当前脚本语法检查通过。
- 单容器双模式的关键环境变量已经改为每次 workflow 启动时传入，而不是依赖 `docker create` 时固化。
- workflow 日志仍会同步写入 `${RABBITBOT_DIR}/logs/unified_runtime/rabbitbot_workflow_latest.log`。
- `RUN_WORKFLOW_AFTER_START=0` 可用于只启动基础服务，不启动 workflow。
- `START_AFTER_CREATE=0` 可用于只创建或复用容器，不启动基础服务和 workflow。

## 阻塞问题

当前没有代码层面的阻塞。运行验证仍依赖 Orin 上 Docker、统一镜像、音频设备和模型服务可正常启动。

## 建议的下一步

- 先运行 `bash scripts_1/start_unified_integration_workflow.sh`，确认基础服务和联调 workflow 前台输出正常。
- 再运行 `bash scripts_1/start_unified_non_integration_workflow.sh`，确认仍使用同一个 `rabbitbot-unified-runtime` 容器，并且回车模拟导航成功可用。
- 如首次运行遇到旧容器被重建，属于预期行为；后续同一个容器会被复用。
- 如只想提前拉起基础服务，可运行 `RUN_WORKFLOW_AFTER_START=0 bash scripts_1/start_unified_integration_workflow.sh`。

## 注意事项

- 现在 `AUTO_START_WORKFLOW` 不再作为容器内自启动 workflow 的开关使用。为了兼容旧习惯，脚本会把 `AUTO_START_WORKFLOW=0` 映射为 `RUN_WORKFLOW_AFTER_START=0`。
- `RABBITBOT_WORKFLOW_NON_INTEGRATION` 现在由 `docker exec` 本次执行注入，因此同一个容器可以在联调和非联调之间切换。
- 旧的 `rabbitbot-unified-runtime-non-integration` 容器不再由启动脚本使用，但停止脚本仍可清理它。

## 其它信息

本轮修改集中在 `scripts_1/start_unified_integration_workflow.sh` 和 `scripts_1/start_unified_non_integration_workflow.sh`。本轮保持此前 STT 灵敏度修改不变。
