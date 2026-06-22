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

### 补充说明：TTS 卡住的具体原因

- 进一步排查确认，TTS 卡住不是模型生成慢，而是音频播放层阻塞：`tts_index=45` 已完成 `tts_generate_done` 和 `tts_play_start`，但没有 `tts_play_done`。
- 代码路径显示 `tts_play_done` 只有在 `rabbitbot/audio/run_tts_espnet.py` 中 `SDOutputStream.play_and_wait()` 返回后才会记录；该函数内部调用 `sounddevice.OutputStream.write(audio)`，因此卡点在 PortAudio/ALSA 输出流写入阶段。
- 内核日志在 11:33:08 记录 `usb 1-4.2: reset full-speed USB device number 5 using tegra-xusb`，该设备就是 `REDMI Speaker 2-6002` 所在 USB 路径；随后 `pulseaudio` 对该设备报 `Failed to find a working profile` 和 `Failed to load module module-alsa-card`。
- TTS 启动时日志记录 REDMI 输出设备 index 为 5，但 reset 后容器内 `sounddevice.query_devices()` 显示 REDMI 变为 index 4，index 5 变成 Jetson APE 默认设备；说明设备 reset 后 PortAudio 序号/流状态发生变化，TTS 进程仍持有启动时创建的旧 `OutputStream`。
- 直接原因判断：REDMI 外放设备发生 USB reset/重新枚举，TTS 没有重建输出流，也没有播放超时保护，导致下一句音频写入旧输出流时一直阻塞。
- 建议修复方向：启动时不要长期缓存易失效的 PortAudio index 和 `OutputStream`；播放前按设备名重新解析 REDMI；`stream.write()` 外围增加播放超时、错误日志和自动重建输出流；外部恢复层面优先检查 REDMI 音响供电、线缆、USB 口和自动省电/断连问题。

### 修复开始导览口令误识别不触发

- 目标：Aaron 反馈刚刚连续说两次“开始导览”，机器人没有启动导览 workflow。本轮排查并修改 QA 触发逻辑。
- 原因：当前 `guide_state=qa_listening`，导览 workflow 已停在 go 闸门，服务状态正常；但 QA 日志显示 STT 将“开始导览”识别为“开始捣揽”“开始捣览”，另有一次识别为“史捣烂”。旧逻辑只精确包含默认触发词 `开始导览`，因此没有写入 `go` 命令，而是把误识别文本交给大模型回答。
- 修改：在 `rabbitbot/agno_agents/vlm_qa_workflow.py` 增加导览口令容错匹配，将 `捣/倒/到/道/蹈/岛` 归一为 `导`，将 `揽/缆/烂/蓝/栏/兰/懒` 归一为 `览`，将 `史` 归一为 `始`；同时支持短口令 `导览`、动作词加导览词、以及有限编辑距离匹配。
- 日志：导览触发日志新增 `match_reason` 和 `text_preview`，后续可以直接看出是精确匹配、同音归一、短口令还是编辑距离触发。
- 验证：本地导入函数测试确认 `开始导览`、`开始捣揽`、`开始捣览`、`史捣烂`、`导览`、`开始讲解` 均可触发；`苏州有什么好玩的地方`、`导览服务是什么` 不触发。`python3 -m py_compile rabbitbot/agno_agents/vlm_qa_workflow.py` 通过。
- 运行结果：直接 `systemctl restart rabbitbot-loop.service` 因需要交互授权失败；已改用控制台 `/api/restart` 接口重启导航主程序，服务已回到 `qa_listening`，新 QA 监听会加载本次容错逻辑。
- 注意：当前状态为 `qa_listening`，但状态接口显示定位暂未成功，需要现场确认定位后再开始真实导览。

### 只读排查：导览再次失败原因

- 目标：Aaron 反馈上次导览又失败一次，要求只查看原因，不改代码、不影响现场状态。本轮未发送 `go/back`，未重启服务，未调用会改变导航状态的接口。
- 当前 run：`20260622_115805`，状态文件显示 `guide_running`，状态接口显示主循环和 28180 导航桥接均在运行。
- 触发链路：QA 日志显示“是捣览”被新容错逻辑识别为导览口令，`match_reason=导览意图匹配:短导览口令`，已写入 `go`，并且 `guide_state` 从 `qa_listening` 变为 `guide_running`，因此这次不是开始导览口令未触发。
- TTS 链路：点位6复星创富讲解相关 `tts_index=105` 到 `112` 均有 `tts_play_done`，12:00 到 12:10 之间未看到 REDMI/USB reset 或 ALSA/PulseAudio 音频设备异常，因此这次不是 TTS 卡住。
- 导航链路：点位6导航目标 `x=-8.9294, y=22.5193` 已成功到达并完成讲解；随后进入点位7，发送目标 `x=-9.1327, y=26.7313` 后，当前位置约 `x=-8.9440, y=22.5828`，距离点位7仍约 4.15 米。
- 原因判断：点位6到点位7导航途中，导航桥接持续输出 `There are obstacles nearby, please be careful`，workflow 侧 `go_to_status` 持续为 `NavigationStatus.ACTIVE`，没有到达点位7，也没有失败退出；机器人应是在前往点位7途中被局部避障/障碍检测卡住。
- 建议：现场优先检查点位6到点位7路径上的人员、展板边缘、玻璃、窄通道或雷达误检；若现场空间确实偏窄，应重新采点位7到可安全到达的位置，或在点位6和点位7之间增加绕行过渡点。


### 只读排查：点位10处再次 TTS 卡住

- 目标：Aaron 反馈机器人停止，确认是否又是 TTS 卡死。本轮只读取状态和日志，未重启服务，未下发导航或移动命令。
- 当前状态：状态接口显示主循环和导航桥接仍在运行，`guide_state=guide_running`；机器人位置约 `x=-3.1846, y=34.6751`，接近点位10。
- workflow 进度：点位8宣传片等待已结束，流程已继续经过点位9并到达点位10；12:24:56 开始请求点位10企业服务支持体系相关讲解。
- TTS 结论：`tts_index=169` 文本“依托滨湖产业集团和上海复星的资源优势”已完成生成并进入 `tts_play_start`，但截至 12:25:48 未出现 `tts_play_done`；后续 `tts_index=170/171` 也已生成并排队，说明阻塞点在播放线程，不是模型生成或 workflow 请求失败。
- 音频设备证据：内核日志在 12:24:48 记录 `usb 1-4.2: reset full-speed USB device number 5 using tegra-xusb`，随后 PulseAudio 重新处理该设备；这与此前 REDMI 外放 USB 重置导致 PortAudio 输出流卡住的症状一致。
- 原因判断：机器人停止不是导航问题，而是 TTS 播放层在 USB 音频设备重置后卡在旧输出流，workflow 等待 TTS 队列完成而无法继续。
- 建议：现场优先处理 REDMI 音响 USB 连接、供电和自动省电/断连问题；临时恢复可考虑重启 TTS 服务，但会影响当前播放队列。代码层面仍建议增加播放超时、设备重建和更明确的音频设备重置诊断日志。

### 修复 REDMI 外放重置后的 TTS 播放恢复

- 目标：解决 REDMI Speaker USB 重置后 TTS 写入旧音频流卡住的问题，并保证恢复后继续播放同一句，不吞掉已排队台词；同时提交当前已有的点位7坐标调整。
- 修改：`rabbitbot/audio/run_tts_espnet.py` 增加 TTS 播放超时、输出设备按名称重扫、输出流重建和同一句音频重试逻辑；默认优先使用 `TTS_DEVICE_NAME` 或 `RABBITBOT_PREFERRED_LOCAL_TTS_DEVICE` 指定的 REDMI 设备，避免设备重枚举后继续使用旧 index。
- 修改：播放线程只在音频确认播放完成后才减少待播放数量；发生超时、输出流异常或设备重建时，会等待短暂恢复时间后重新解析设备并重试同一个 wav，避免 workflow 误判 TTS 队列已清空。
- 配置：新增可调环境变量 `RABBITBOT_TTS_PLAY_TIMEOUT_GRACE_SECONDS`、`RABBITBOT_TTS_PLAY_TIMEOUT_MIN_SECONDS`、`RABBITBOT_TTS_OUTPUT_RECOVER_WAIT_SECONDS`、`RABBITBOT_TTS_PLAY_RETRY_SLEEP_SECONDS`、`RABBITBOT_TTS_PLAY_RETRY_LIMIT`，默认无限重试，直到新一轮 TTS 生成或服务停止取消旧句。
- 日志：新增或增强 `tts_output_stream_open`、`tts_play_start`、`tts_play_done`、`tts_play_timeout`、`tts_play_error`、`tts_play_recover_start`、`tts_output_device_reselected`、`tts_output_stream_abort_error` 等日志，便于定位播放阶段、设备 id、尝试次数、超时时间、恢复耗时和失败原因。
- 点位：`conf/dialogue_0.json` 保留并提交当前未提交的点位7坐标调整，便于避开点位6到点位7路径上的障碍卡顿风险。
- 验证：远端 Docker 环境内 `/opt/venv/bin/python -m py_compile rabbitbot/audio/run_tts_espnet.py` 和 `py310/bin/python -m py_compile rabbitbot/audio/run_tts_espnet.py` 均通过；`python3 -m json.tool conf/dialogue_0.json` 通过。
- 验证：重启 `rabbitbot-unified-runtime` 后 TTS 使用 `REDMI Speaker 2-6002` 打开输出流，短句“语音恢复测试。”成功完成 `tts_play_start` 到 `tts_play_done`。
- 当前状态：主循环已重新启动并回到 `qa_listening`，workflow 停在 go 闸门；最新状态接口显示定位成功，位姿约为 `x=-2.389, y=-0.6117`。
- 未验证事项：本轮没有人为拔插或强制 reset REDMI 外放，因此实际 USB reset 后的自动恢复路径尚未在现场完整复现；代码已覆盖超时、重扫设备、重建输出流和重试同一句的路径。

### 修复 TTS 底层播放崩溃导致后续不讲话

- 目标：Aaron 反馈多个点位到达后很久才讲话，点位4后直接不讲话，当前站在点位6附近发呆；本轮先排查原因，再修复 TTS 服务因 REDMI/ALSA 异常直接崩溃的问题。
- 现象：`rabbitbot_tts.log` 在 13:13 左右出现大量 PortAudio/ALSA `PaAlsaStreamComponent_RegisterChannels` 断言错误，随后 `uvicorn tts_app:app` 以 `Aborted (core dumped)` 退出；容器内 28185 端口无 TTS 进程。
- 原因：上一轮的 sounddevice 超时和重建逻辑只能处理 Python 层异常；这次是 PortAudio/ALSA 在 C 层直接 abort 进程，Python 无法捕获，导致 TTS API 服务退出，后续 workflow 请求 TTS 只有 `Connection refused`。
- 导览状态：run_id `20260622_130416` 中点位6的复星创富台词请求发生在 TTS 崩溃后，workflow 记录 `workflow_tts_request_invalid_response` 后继续进入点位7；随后点位7导航目标 `(-8.7774, 27.1503, ...)` 一直为 `NavigationStatus.ACTIVE`，因此当前站在点位6附近发呆主要是点位6到点位7导航未完成。
- 修改：`rabbitbot/audio/run_tts_espnet.py` 新增默认 `ffmpeg_alsa` 播放后端，将每句音频写入临时 wav 后交给独立 `ffmpeg -f alsa` 子进程播放，避免 PortAudio/ALSA C 层 abort 直接拖垮 TTS 服务进程；保留 `sounddevice` 后端作为 `RABBITBOT_TTS_PLAYBACK_BACKEND=sounddevice` 的回退选项。
- 日志：新增 `tts_playback_backend_selected`、`tts_ffmpeg_alsa_device_resolved`、`tts_ffmpeg_play_start`、`tts_ffmpeg_play_done`、`tts_ffmpeg_play_error`、`tts_ffmpeg_play_timeout`、`tts_ffmpeg_temp_cleanup_error`，用于定位播放后端、ALSA 设备、播放耗时、子进程返回码和临时文件清理问题。
- 验证：容器内 `/opt/venv/bin/python -m py_compile` 和 `py310/bin/python -m py_compile` 通过；`ffmpeg` 静音打开 `plughw:3,0` 成功；单独恢复 TTS 后日志显示选中 `ffmpeg_alsa`，解析到 `REDMI Speaker 2-6002` 的 `plughw:3,0`，启动自检句均出现 `tts_ffmpeg_play_done` 和 `tts_play_done`。
- 当前状态：TTS 进程已恢复并监听 28185；主 workflow 未重启，仍在 run_id `20260622_130416` 中，导览状态为 `guide_running`，点位7导航仍持续 ACTIVE，状态接口显示定位状态待确认。
- 注意：本次修复解决 TTS 服务被 ALSA abort 拖死的问题；点位6到点位7导航持续 ACTIVE 仍需现场处理障碍、定位状态或重新采点，属于独立导航问题。

### 只读排查：定位坐标完全不变与异常跳变

- 目标：Aaron 指出机器人本体即使原地晃动也应有细微位姿变化，连续完全不变更像定位或导航丢失；本轮只读取状态和日志，未下发移动、停止、重启或导览控制命令。
- 当前状态：最新状态接口显示 run_id `20260622_145657`，`guide_state=guide_running`，导航桥接就绪，pose 被标记为 `localized=true`，但位姿为 `x=-113.3204, y=20.9846, z=-5.2644`，明显超出正常展厅地图范围。
- 关键证据：最新 `nav_bridge_20260622_145645.log` 中自动重定位前两次失败，第三次成功后位姿先后跳到 `(-0.9929, 0.9543)`、`(-8.5851, -2.3710)`、`(-5.7693, 4.2980)`、`(-15.0300, 56.1782)`，随后出现 SLAM 提示 `Exceeding the maximum speed, relocation is invalid.`。
- 时间线：坐标不是从导航桥启动一开始就异常；14:57 左右第三次自动重定位成功时位姿仍在正常范围 `x=-0.9929, y=0.9543`，但在 14:59:24 导览 go 闸门释放前已跳飞并冻结到 `x=-113.3204, y=20.9846, z=-5.2644`。
- 关键证据：之后位姿固定为 `x=-113.3204, y=20.9846, z=-5.2644` 并连续多次完全相同；导航到点位1目标时底层返回 `statusCode:4`、`Failed to obtain the current pose information.`。
- 结论：这次不是普通的“导航 ACTIVE 但底盘不动”，而是定位/重定位链路已经异常，pose 输出跳变后冻结；上层仍把 `localized=true` 和 `go_to_status=ACTIVE` 暴露给 workflow，导致导览一直等待。
- 建议：现场应先停止当前导览并重新做定位/重定位，必要时重启导航桥接或底层 SLAM/导航进程；代码层面建议增加位姿合理性校验、pose 新鲜度检查、异常跳变检测，以及底层 `Failed to obtain current pose` 时向 workflow 返回失败而不是持续 ACTIVE。

### 只读分析：根据点位推断 XY 坐标系

- 目标：Aaron 询问能否通过现有点位坐标判断 XY 坐标系。本轮只读取 `conf/dialogue_0.json`，未修改现场状态。
- 结论：可推断相对坐标系，但不能仅凭点位确定绝对东南西北；Y 轴基本对应导览主通道纵深方向，点位1到点位13整体从 `y=-0.2571` 增加到 `y=32.9859`，X 轴基本对应横向跨展区方向。
- 证据：点位5到6、6到7、9到10 都主要是 `y` 增加且 `x` 变化很小；点位3到4、点位7到7->8过渡点主要是 `x` 大幅变化且 `y` 变化很小。
- 注意：最新异常定位 `x=-113.3204, y=20.9846, z=-5.2644` 中，`y` 落在导览纵深范围附近，但 `x` 和 `z` 明显远超正常点位范围，进一步支持该 pose 为定位跳飞结果。

## 其它信息

- 本轮新增 QA 导览触发日志字段 `match_reason` 和 `text_preview`，用于判断口令是精确命中、同音归一、短口令还是编辑距离触发；本次排查同时依靠 `vlm_qa_workflow_20260622_114516.log`、`vlm_qa_dialogue_20260622_034518.log`、STT 日志和 `/api/status` 确认未触发原因。
- 生成时间：2026-06-22
