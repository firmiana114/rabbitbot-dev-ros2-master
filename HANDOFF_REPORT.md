# 交接报告

## 背景和目标

本项目是 AGX-orin 上的 RabbitBot ROS2/导览 workflow 项目，路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，当前主要工作集中在统一容器、导航桥接、QA 问答模式、STT 触发导览、TTS 播报、网页控制台状态展示和现场导览台词配置。

Aaron 本轮要求撤销此前为“每前往一个地点”增加的导览引导词，即去掉各 step 的 `guide` 前往提示，保留正式讲解内容、点位路线、ABCD 中文近似读音和最近调整过的 STT 阈值。

## 当前状态

已完成：

- 已从 `conf/dialogue_0.json` 的 `steps` 中删除 17 条 `guide` 字段，包括点位间过渡、各主要讲解点位和告别点位的“前往某板块/请跟随/请靠近”等提示。
- 已保留各点位 `segments` 正式讲解文本，未改动点位坐标、地图文件、返航点位或导航流程结构。
- 已保留点位7功能布局讲解中的中文近似读音：`埃区域`、`毙区域`、`锡区域`、`第区域`。
- 已保留上一轮移除 `post_wait_seconds=277` 的结果，点位7讲解后不再等待 277 秒。
- 已保留上一轮 STT 更保守的默认参数：`STT_VAD_SPEECH_THRES=0.20`、`STT_VAD_START_HITS=2`、`STT_MIN_RMS=0.045`、`STT_MIN_UTTERANCE_SEC=0.55`、`STT_INPUT_GAIN=0.75`。
- 已在点位8“请各位领导一同观看宣传片”台词后增加 `post_wait_seconds=277`，等待结束后新增播报“请各位领导随我一同参观企业展示墙。”，后续流程保持不变。

未完成：

- 本轮没有重启 `rabbitbot-loop.service`，没有发送导航命令，没有移动机器人。
- 删除 `guide` 后尚未做现场完整导览验证，需要重启或重新进入导览流程后才能确认实际播报顺序。
- 点位8新增的 277 秒宣传片停留和后续提示尚未现场播放验证。

## 已验证的事实

- 当前分支为 `June6_workflow`。
- `python3 -m json.tool conf/dialogue_0.json` 已通过，台词 JSON 格式有效。
- 已检查点位8台词顺序：宣传片提示段带 `post_wait_seconds=277`，下一段为“请各位领导随我一同参观企业展示墙。”。
- 检查确认 `conf/dialogue_0.json` 中已不再存在 `guide` 字段。
- 本轮只修改台词配置和交接报告，不涉及 Python/脚本执行逻辑。
- 最近服务端口曾确认 `28184`、`28185`、`28180`、`28182`、`8000`、`8080` 均在监听；本轮删除台词字段未改变服务运行状态。

## 阻塞问题

代码和配置修改无阻塞。运行验证层面的主要风险是：workflow 只会在重新加载台词 JSON 后使用删除 `guide` 后的配置，因此如果当前导览进程已经加载旧配置，需要重启相关导览流程或服务后再验收。

## 建议的下一步

- 现场安全确认后，重新启动或重新进入导览流程，听取各点位之间是否已不再播报“前往某板块”的引导词。
- 如果希望过渡点完全静默，重点观察 `segments=[]` 的过渡 step 是否只执行导航、不播报任何内容。
- 如果后续仍听到类似引导词，优先确认是否运行的是已重启后的新 workflow，以及是否加载了 `conf/dialogue_0.json`。

## 注意事项

- 修改 `conf/dialogue_0.json` 后，正在运行的 workflow 不一定自动热更新，需要重启或重新进入流程。
- `guide` 字段是导航前播报提示，本轮删除它们不会删除正式讲解 `segments`。
- 本轮没有新增或调整代码日志；当前可用于排查的关键日志仍是 `logs/unified_runtime/rabbitbot_stt.log`、`logs/unified_runtime/rabbitbot_tts.log`、`logs/nav_workflow_control/*.log` 和 `journalctl -u rabbitbot-loop.service`。
- STT 阈值调整不是声源定位；如果旁人距离麦克风很近或音量很大，仍可能被识别。

## 历史摘要

- 早期围绕 6 月 6 日 DOCX/PDF 剧本做了多轮对齐：开场逻辑、步骤顺序、过渡点、点位坐标、称呼变量、台词 JSON 抽离和严格剧本结束逻辑均已落地。
- TTS 先后经历本地外接音响、Unitree G1 本体 TTS、`SetVolume` 重试、TTS 失败不终止 workflow、桥接进程保活和 ShuHao TTS/STT 逻辑同步；当前仍需按现场设备确认最终使用 local 还是 Unitree。
- 导航 loop 曾修复 go/back 控制、返航路径、预启动闸门、日志目录权限、地图与台词文件 `map_file` 一致性、系统服务注册/禁用和健康检查恢复逻辑。
- QA workflow 已与导览 workflow 整合：默认进入 QA 问答，识别“开始导览”后写入 go 命令并进入导览运行态，导览期间不继续监听 QA。
- 网页控制台 ready 口径已改为以 `guide_state.state=qa_listening` 为准，旧 workflow ready 仅作为诊断信息。
- 曾新增“前往某板块”类 `guide` 引导词、点位7等待 277 秒和 ABCD 中文近似读音；后续已先移除 277 秒等待，本轮又移除全部 `guide` 引导词，仅保留 ABCD 中文近似读音。

## 最近工作记录

### 排查控制台服务未就绪提示

- 目标：解释前端显示“服务仍未全部就绪，请查看状态或打开日志排查”的原因。
- 结论：TTS 28185 当时未稳定启动，日志显示本地 TTS 后端找不到稳定外放设备，且 `RABBITBOT_TTS_ALLOW_BUILTIN=0` 禁止退回内置声卡。
- 验证：VLM、STT、Memory 等服务逐步恢复，但 TTS 因音频设备问题阻塞 ready。
- 后续：优先确认 REDMI 音响连接和 `/tmp/rabbitbot_tts_sounddevice.err`。

### 手动重启 TTS 并恢复导览链路

- 目标：按 Aaron 要求重启 TTS 试试。
- 结果：在 `rabbitbot-unified-runtime` 容器内手动拉起 TTS，28185 恢复监听，随后 STT/Memory/VLM 状态可用。
- 观察：STT 识别到现场“开始导览”后，系统进入 `guide_running`。
- 注意：TTS 是手动拉起；后续容器或服务重启后仍需确认音频设备。

### 分析复星创富板块后停止原因

- 目标：分析点位6复星创富讲解后机器人走几步停下的原因，不发送导航命令。
- 结论：workflow 已发送点位7目标，但机器人实际停在约 `x=-9.13, y=23.13`，距离点位7仍约 3.6 米，导航状态保持 `ACTIVE`，不是到达成功。
- 关键日志：导航桥接持续输出 `There are obstacles nearby, please be careful`，随后 `rabbitbot-loop.service` 被停止，28180 断开。
- 建议：现场确认障碍物、通道宽度、雷达误检和地图膨胀；必要时重新采点或增加过渡点。

### 移除点位7等待并收紧 STT 阈值

- 目标：去掉点位7讲解后的 277 秒等待，并减少 STT 误收旁人说话。
- 修改：从 `conf/dialogue_0.json` 移除 `post_wait_seconds=277`；收紧 STT VAD/RMS/最短语音时长/连续命中次数，并降低输入增益。
- 验证：JSON 校验、Python 编译、脚本语法和 diff 检查均通过；容器内 STT 已重启，28184 监听，新参数已写入日志。
- 注意：阈值更保守后可能降低远距离或小声命令识别率，需要现场平衡误触发和漏触发。

### 删除各点位前往引导词

- 目标：撤销此前新增的“每前往一个地点”的引导词。
- 修改：删除 `conf/dialogue_0.json` 中 17 条 `guide` 字段，覆盖所有主要前往提示和到点前提示。
- 验证：JSON 校验通过，文件中已无 `guide` 字段。
- 注意：需要重新加载导览配置后才会体现在实际播报中。

### 点位8增加宣传片停留和企业展示墙提示

- 目标：点位8配套设施讲解后需要观看宣传片，停留 277 秒，停留结束后提示继续参观企业展示墙。
- 修改：在 `conf/dialogue_0.json` 的 `point_8` 第三段台词上增加 `post_wait_seconds=277`，并在其后新增台词“请各位领导随我一同参观企业展示墙。”。
- 验证：JSON 校验通过，点位8段落顺序已检查；代码逻辑确认 `post_wait_seconds` 会在当前段播报完成后等待，再继续下一段。
- 注意：正在运行的 workflow 需要重新加载台词配置后才会使用本次改动。

### 排查导览中机器人停止不动

- 目标：Aaron 反馈机器人导览中停止不动，本轮只读取状态和日志，不发送导航、返航、重启或移动命令。
- 当前状态：`rabbitbot-loop.service`、控制台和 Docker 均为 active，关键端口 `28180/28182/28184/28185/8000/8080` 均在监听，`guide_state` 显示 `guide_running`，run_id 为 `20260622_112905`。
- 导航结论：导航桥接日志显示机器人已到达当前目标点，`/go_to_status` 最终为空闲状态 `status=0`，当前位置约 `x=-4.5769, y=11.6135`，没有看到这次卡住是导航 ACTIVE 或避障未到达导致。
- TTS 结论：workflow 在 11:33:42 请求播报“现在我们所在位置是园区一站式企业服务和交流路演中心”，TTS 返回 `tts_index=45`；TTS 日志显示该音频已生成并进入 `tts_play_start`，但一直没有对应的 `tts_play_done`。
- 原因判断：workflow 正在等待 TTS 播放队列完成，TTS 播放线程卡住或外放设备阻塞，导致导览不进入下一段台词，也不会继续后续导航。
- 建议：现场先确认是否仍在播放或外放设备是否断连；若确认无声音且流程不前进，可优先重启 TTS 或恢复外接音响，再视需要重启导览流程。后续代码层面建议给 TTS 播放等待增加超时和更明确的阻塞日志。

## 其它信息

- 本轮没有新增或调整代码日志点；本次排查主要依靠 `rabbitbot_workflow_20260622_112905.log`、`nav_bridge_20260622_112853.log`、`rabbitbot_tts.log`、`/api/status` 和 `/go_to_status`。日志已足够确认当前卡点在 TTS 播放未完成，而不是导航未到达。
- 生成时间：2026-06-22
