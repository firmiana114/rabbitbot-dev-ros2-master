# 交接报告

## 背景和目标

本项目是 AGX-orin 上的 RabbitBot ROS2/导览 workflow 项目，路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，当前主要工作集中在统一容器、导航桥接、QA 问答模式、STT 触发导览、TTS 播报和网页控制台状态展示。本文已压缩旧记录：早期细节只保留结论，最近 QA/导览整合、控制台 ready 状态、端口清理和启动测试保留完整记录。

## 当前状态

已完成：

- 导览 workflow 已切到严格 DOCX 剧本路线，台词主要维护在 `conf/dialogue_<序号>.json`，点位、地图和返航点位也支持从台词 JSON 读取。
- 导航 loop 脚本支持预启动 workflow、go 闸门、back 返航、健康检查、端口清理、systemd 启动方式和项目内共享控制目录。
- 统一容器可按需启动 Neo4j、VLM、STT、TTS、Memory 和 Robot Agent；当前 QA/导览模式需要 VLM、STT、TTS、Memory 和 28180 导航桥接协同。
- QA workflow 已与导览 workflow 整合：默认进入 QA 问答，识别“开始导览”后写入 go 命令并进入导览运行态，导览期间不继续监听 QA。
- 网页控制台 ready 口径已改为以 `guide_state.state=qa_listening` 为准，旧 workflow ready 仅作为诊断信息。
- 控制台关闭/重启导航主程序会先停止服务、清理 28180 端口，再启动服务；相关流程已补充日志和测试。
- 最近一轮测试已验证：全部关键服务可用，QA 普通问题可由大模型回答并 TTS 播报，通过 STT 注入“开始导览”可触发导览 workflow 进入 `guide_running`。

未完成：

- 最近测试没有以机器人真实行走或导航到点作为成败标准；如果要验收完整导览，需要现场确认机器人行走模式已开启。
- 最近测试观察到 `点咖啡` 台词段后本地 TTS 播放队列可能卡住：`tts_index=7` 只有 `tts_play_start`，未看到 `tts_play_done`。这不影响“开始导览”触发成功的结论，但会影响完整导览闭环。
- 当前运行状态可能仍为 `guide_running`，本轮压缩报告不改变服务状态，也不执行 `back` 或 stop。

## 历史摘要

- 早期围绕 6 月 6 日 DOCX/PDF 剧本做了多轮对齐：开场逻辑、步骤顺序、过渡点、点位坐标、称呼变量、台词 JSON 抽离和严格剧本结束逻辑均已落地。
- TTS 先后经历本地外接音响、Unitree G1 本体 TTS、`SetVolume` 重试、TTS 失败不终止 workflow、桥接进程 `--hold-seconds` 保活和 ShuHao TTS/STT 逻辑同步；当前仍需按现场设备确认最终使用 local 还是 Unitree。
- 导航 loop 曾修复 go/back 控制、返航路径、预启动闸门、日志目录权限、地图与台词文件 `map_file` 一致性、系统服务注册/禁用和健康检查恢复逻辑。
- 台词 JSON 已支持 `map_file`、`points`、`back_points`，`dialogue_1.json` 曾切到 test9 点位；`dialogue_fuxing.json` 记录了显式返航路线。
- 迁移工作曾生成 AGX 到 HaiSong-orin 的离线迁移包，并完成移动硬盘复制、校验和安全卸载；Neo4j Docker 卷历史数据未随主迁移包迁移。
- 曾排查电源模式切换导致服务退出，结论更接近系统重启/停机流程导致 Docker 和服务被停止，而不是 RabbitBot 业务进程自身崩溃。
- QA workflow 早期测试发现 AGX 上 VLM token 流式对多句问题不稳定，因此改为默认 `RABBITBOT_QA_VLM_STREAM=0`，仍保留按句 TTS 分段播报。

## 已验证的事实

- 当前分支为 `June6_workflow`。
- 最近提交包括：`266e521 记录 QA 触发导览 workflow 启动测试`、`9bded4f 修复控制台重启端口清理与 TTS 默认后端`、`66a525f 修正控制台导览 ready 状态口径`。
- 最近测试确认 `rabbitbot-loop.service`、`rabbitbot-control-console.service`、`docker.service` 为 active，关键端口 `8000/7687/28180/28182/28184/28185` 均监听。
- STT `/exec` 的 `inject_text_async` 可用于命令形式注入文本，普通问题和“开始导览”均返回 HTTP 200。
- `guide_state` 是当前 QA/导览业务状态的关键诊断文件，默认路径为 `runtime/nav_workflow_control/guide_state`。
- 本轮压缩报告前 Git 工作区干净；压缩报告本身是本轮唯一修改。

## 阻塞问题

无报告压缩层面的阻塞。运行层面剩余风险主要是完整导览验证：机器人行走模式、导航实际移动、TTS 本地 REDMI 音响播放线程是否卡住，以及是否需要手动恢复到待命状态。

## 建议的下一步

- 如果只需要验证“QA 触发导览启动”，最近测试已经满足要求。
- 如果要验证完整导览闭环，先确认机器人行走模式和现场安全，再处理或观察 `点咖啡` 后 TTS 队列是否继续播放。
- 如需回到待命状态，现场确认机器人位置和安全后，再决定发送 `back`、重启 `rabbitbot-loop.service`，或关闭导航主程序。
- 后续修改台词、点位、启动脚本、控制台或 QA 逻辑后，继续更新本报告，但保持旧内容摘要化，避免重新膨胀。

## 注意事项

- `conf/dialogue_<序号>.json` 多数台词文件被 Git 忽略，现场修改台词后不会自动出现在 `git status`。
- 修改台词 JSON、点位或 `back_points` 后需要重启 workflow/loop 才会重新读取。
- 直接调用 28180 `/go_to_async` 使用六元组 `(x, y, ox, oy, oz, ow)`，workflow 内部点位仍可能包含 `z/mode` 等字段。
- 当前控制台端口清理会调用 `fuser -k 28180/tcp`，只应在关闭或重启导航主程序流程中使用。
- AGX-orin 日志时间曾出现与当前会话日期不一致的情况，排查时请同时看系统时间和日志 run_id。

## 近期完整记录

## 本轮补充：QA 模式触发导览 workflow 整合

### 背景和目标

Aaron 要求将 QA workflow 与导览 workflow 整合：系统默认处于 QA 语音问答模式；当 QA 识别到“开始导览”口令后，启动原有导览流程；导览过程中不允许语音打断；导览结束后恢复 QA 模式。要求导览流程本身继续沿用现有严格 DOCX workflow、导航闸门、点位和返航编排，不改导览台词和动作执行逻辑。

### 当前状态

已完成：

- `rabbitbot/agno_agents/vlm_qa_workflow.py` 已新增导览触发逻辑：默认口令为 `开始导览`，可通过 `RABBITBOT_QA_GUIDE_TRIGGER_PHRASES` 配置多个逗号分隔口令。
- QA workflow 收到导览口令后，会向共享命令文件写入 `go`，并进入导览等待状态；等待期间不再调用 STT 监听，也不会进入 VLM 问答，因此导览过程中不会被 QA 打断。
- QA workflow 会读取导览状态文件，观察 `guide_running` 到 `guide_finished_waiting_back` 或 `qa_listening` 的状态变化；导览完成后恢复 QA 监听。
- `scripts_1/start_nav_bridge_workflow_loop.sh` 已默认启用 QA 模式：`RABBITBOT_NAV_WORKFLOW_ENABLE_QA=1` 时默认同时启用 VLM 与 STT 基础服务。
- 导航 loop 已新增共享状态文件：默认宿主路径为 `runtime/nav_workflow_control/guide_state`，容器路径为 `/workspace/projects/rabbitbot-dev-ros2-master/runtime/nav_workflow_control/guide_state`。
- 导航 loop 已将命令文件默认从 `/tmp/rabbitbot_nav_workflow_control/command` 调整到项目内 `runtime/nav_workflow_control/command`，确保容器内 QA 与宿主 loop 通过项目挂载访问同一个命令文件。
- `scripts_1/send_nav_workflow_command.sh` 已同步使用项目内控制目录，外部终端的 `go/back/quit` 仍可用。
- `scripts/start_vlm_qa_workflow.bash` 和 `scripts_1/start_unified_vlm_qa_workflow.sh` 已补充导览触发相关环境变量说明和透传。
- 导航 loop 已在关键阶段写入状态：`starting`、`guide_preparing`、`qa_listening`、`guide_running`、`guide_finished_waiting_back`、`returning`、`guide_prepare_failed`、`qa_disabled`。
- 导航 loop 的运行时健康检查已补充 VLM 8000 检查；默认 QA 模式下如果 VLM 掉线，会在 loop 日志中明确显示 `VLM(8000)`。

未完成：

- 本轮未重启 `rabbitbot-loop.service`，未启动新的导览流程，也未发送语音或文件 `go/back` 命令，避免现场真机误动作。
- 本轮未做完整实机验证：尚未确认默认 QA 模式启动后 VLM/STT 冷启动耗时、语音识别“开始导览”的现场准确率、导览结束恢复 QA 的实机节奏。

### 已验证的事实

- 已通过 `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile rabbitbot/agno_agents/vlm_qa_workflow.py scripts/run_vlm_qa_workflow.py rabbitbot/agno_agents/workflow.py`。
- 已通过 `bash -n` 检查：`scripts_1/start_nav_bridge_workflow_loop.sh`、`scripts_1/send_nav_workflow_command.sh`、`scripts/start_vlm_qa_workflow.bash`、`scripts_1/start_unified_vlm_qa_workflow.sh`、`scripts_1/start_unified_integration_workflow.sh`。
- 已通过轻量 Python helper 验证：`请开始导览` 和 `开始，导览！` 能命中导览触发，普通问题 `介绍一下你自己` 不会误触发；状态文件读取 `state=qa_listening` 正常。
- 已执行 `git diff --check`，未发现空白或补丁格式问题。
- 尝试运行 `python3 -m pytest tests/control_console -q` 失败，原因为系统 pytest 加载用户目录 anyio 插件时报 `ModuleNotFoundError: No module named '_pytest.scope'`；改用 `py310/bin/python -m pytest` 失败，原因为 `py310` 环境未安装 pytest。该问题属于测试环境依赖不一致，不是本轮代码路径的运行断言失败。

### 阻塞问题

- 实机验证仍需有人值守后重启 `rabbitbot-loop.service`；新 loop 默认会启动 VLM/STT，冷启动和资源占用明显高于原先只启动导览底座的模式。
- 当前运行中的 `rabbitbot-loop.service` 是本轮修改前启动的旧进程；不重启服务不会加载本轮 QA/导览整合逻辑。

### 建议的下一步

- 在确认现场安全后执行 `sudo systemctl restart rabbitbot-loop.service`，等待 VLM/STT/TTS/导航桥接全部就绪。
- 观察 `runtime/nav_workflow_control/guide_state`，确认状态最终进入 `qa_listening`。
- 用语音说“开始导览”，或用 `bash scripts_1/send_nav_workflow_command.sh go` 做非语音等价验证；确认状态切到 `guide_running`，导览期间 QA 日志不再出现新的 STT 监听轮次。
- 导览结束后确认状态切到 `guide_finished_waiting_back`，QA workflow 恢复监听并可回答普通问题。
- 如需下一轮导览，仍需先按原有流程发送 `back` 完成返航，待 loop 重新预启动下一轮导览并回到 `qa_listening` 后再说“开始导览”。

### 注意事项

- 新共享控制目录默认为 `runtime/nav_workflow_control`；如果现场仍用旧的 `/tmp/rabbitbot_nav_workflow_control/command` 手写命令，将不会被新 loop 默认读取，除非显式设置 `RABBITBOT_NAV_WORKFLOW_CONTROL_DIR`。
- QA 只在状态为空、`qa_listening` 或 `waiting_go` 时接受“开始导览”；如果状态为 `guide_running`、`guide_finished_waiting_back` 或 `returning`，会播报默认不可用提示，避免重复启动导览。
- 默认不在触发导览前额外播报“好的，开始导览”，避免改变原导览开场节奏；如需导览结束后播报恢复提示，可设置 `RABBITBOT_QA_GUIDE_RESUME_SPEECH`。
- 本轮新增日志点：QA 记录导览口令命中、命令文件写入、导览状态变化、等待超时和恢复 QA；导航 loop 记录 QA workflow 启停、状态文件写入、VLM/STT 默认启用、VLM 健康检查失败原因。

### 其它信息

- 生成时间：2026-06-17 00:00:00

## 本轮补充：控制台 ready 状态改用 QA/导览 guide_state

### 背景和目标

Aaron 要求修正网页控制台 ready 状态口径：QA/导览整合后，旧 `workflow.ready` 只表示导览 workflow 预启动闸门 ready，不能再单独代表“可执行导览”。本轮目标是让 `/api/status` 返回新的 `guide_state`，并让前端“所有服务已加载成功，可执行相关操作”和“导览”按钮以 `guide_state.state=qa_listening` 为准，避免 `guide_state=starting` 等阶段误判 ready。

### 当前状态

已完成：

- `ConsoleConfig` 新增 `guide_state_file`，默认路径与导航 loop 一致：`runtime/nav_workflow_control/guide_state`，也支持环境变量 `RABBITBOT_NAV_WORKFLOW_GUIDE_STATE_FILE` 覆盖。
- `rabbitbot/control_console/status.py` 新增 `GuideState` 和 `read_guide_state()`，解析并返回 `state`、`run_id`、`detail`、`time`；文件不存在或为空时返回 `state=unknown`。
- `/api/status` 已新增 `guide_state` 字段；即使主循环未运行，也会返回 `guide_state` 供前端诊断。
- 前端 `servicesReady(data)` 已改为要求 `main_loop=running`、导航桥接 ready、且 `guide_state.state === 'qa_listening'`。
- “导览”按钮已改为只在导航桥接 ready 且 `guide_state.state === 'qa_listening'` 时启用。
- Workflow 卡片和整体状态文案已改为显示新业务状态：`starting`、`guide_preparing`、`qa_listening`、`guide_running`、`guide_finished_waiting_back`、`returning`、`guide_prepare_failed`、`qa_disabled`、`unknown`。
- 旧 `workflow` 字段继续保留在 `/api/status` 中，作为诊断信息，不再覆盖新 `guide_state` 业务状态。

未完成：

- 本轮未在浏览器中人工点击验证页面；已通过后端接口和页面源码测试覆盖主要 ready 逻辑。

### 已验证的事实

- 已通过 `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile rabbitbot/control_console/app.py rabbitbot/control_console/config.py rabbitbot/control_console/status.py tests/control_console/test_app.py tests/control_console/test_status.py`。
- 已通过 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/control_console -q`，结果为 `62 passed`。
- 已通过 `git diff --check`。
- 新增测试覆盖：`guide_state` 文件缺失返回 unknown；`starting` 不应作为 ready；`qa_listening` 与主循环/导航 ready 组合为前端 ready 依据；`guide_running` 时前端导览按钮条件不满足；`read_guide_state()` 可解析四个字段。

### 阻塞问题

- 无代码层面阻塞。

### 建议的下一步

- 重启服务后打开控制台，观察 `guide_state=starting` 或 `guide_preparing` 阶段不再显示“所有服务已加载成功”。
- 等待状态进入 `qa_listening` 后，确认页面显示“QA 待命，可开始导览”，且“导览”按钮可用。
- 导览运行中确认页面显示“导览中”，且“导览”按钮禁用。

### 注意事项

- 前端 ready 已不再由旧 `workflow.ready` 决定；旧字段只用于排查预启动 workflow 闸门、pid、退出码等信息。
- 如果 `runtime/nav_workflow_control/guide_state` 不存在，控制台会显示状态未知，不会误判为 ready。
- 本轮新增日志点较少，主要复用导航 loop 已写入的 `guide_state` 状态文件；诊断重点从控制台 `/api/status.guide_state` 和导航 loop 日志中的“导览状态已更新”查看。

### 其它信息

- 生成时间：2026-06-17 00:00:00

## 本轮补充：提交控制台端口清理与 TTS 默认后端调整

### 背景和目标

Aaron 要求通过 SSH 接手 AGX-orin 上 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master` 项目，阅读交接报告和项目本身，确认当前工作区未提交内容，并整理为一次提交，确保工作区干净。

### 当前状态

已完成：

- 已阅读当前 `HANDOFF_REPORT.md`、项目 README、分支和最近提交，确认项目仍在 `June6_workflow` 分支。
- 已确认接手时未提交内容集中在 5 个文件：`rabbitbot/control_console/commands.py`、`scripts/start_tts_app.bash`、`scripts_1/unified_runtime/start_unified_container.sh`、`tests/control_console/test_app.py`、`tests/control_console/test_commands.py`。
- 已确认控制台重启/关闭导航主程序的逻辑从单次 `systemctl restart` 调整为 `stop -> 清理 28180 端口 -> start`，用于避免旧导航桥接进程残留占用端口。
- 已补充控制台端口清理日志和重启/关闭流程日志，记录端口、sudo/fuser 路径、返回码、输出摘要、耗时、降级原因和超时失败原因。
- 已修复端口清理降级判断：当 `sudo -n fuser` 输出需要密码或权限不足时，先识别为无权限并降级普通 `fuser`，避免把返回码 1 误判为 fuser 正常“无占用”。
- 已补充测试覆盖：重启顺序必须为 `stop -> cleanup -> start`；sudo 无权限时会降级执行普通 `fuser`；已有控制台 API 测试同步 mock 端口清理。
- 已确认 TTS 启动逻辑当前改为优先本地 `REDMI Speaker 2-6002`，未检测到首选本地音响时回退 Unitree G1 本体 TTS；统一容器默认 `RABBITBOT_TTS_BACKEND=local` 并显式透传首选本地设备。

未完成：

- 本轮未启动或停止 `rabbitbot-loop.service`、导航桥接、workflow 或统一容器，未触发机器人移动或播报。
- 本轮未做真实控制台点击、真实 systemd 重启或真实 TTS 出声验证。

### 已验证的事实

- `PYTHONPATH=/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/control_console/test_commands.py tests/control_console/test_app.py` 通过，结果为 `48 passed`。
- `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile` 已验证控制台命令、控制台 app 和对应测试文件语法通过。
- `bash -n scripts/start_tts_app.bash` 通过。
- `bash -n scripts_1/unified_runtime/start_unified_container.sh` 通过。
- `git diff --check` 通过。
- 接手时 `pytest` 裸命令不存在；使用 `python3 -m pytest` 并设置 `PYTHONPATH` 后测试可正常运行。

### 阻塞问题

无代码层面的阻塞。剩余风险是运行验证类风险：端口清理、systemd stop/start 顺序和 TTS 本地音响优先策略尚未在真实现场控制台操作中验证。

### 建议的下一步

- 现场安全窗口内，通过网页控制台执行一次“关闭程序”和“一键重启”，确认日志中出现导航主程序关闭/重启开始、端口清理开始、端口清理完成和导航主程序重启完成。
- 如果一键重启后仍提示 28180 占用，优先查看控制台服务日志中 `端口清理命令无权限`、`端口清理命令失败` 或 `端口清理超时` 记录。
- 下次启动统一容器后确认 TTS 日志中的后端和设备选择，重点检查是否选择到 `REDMI Speaker 2-6002` 或按预期回退 Unitree。

### 注意事项

- 控制台端口清理使用 `fuser -k 28180/tcp`，属于会终止占用该端口进程的操作；只应在关闭或重启导航主程序流程中触发。
- 日志只记录命令路径、端口、返回码和输出摘要，不记录敏感信息。
- 本轮没有改动导览台词、导航点位、QA workflow 逻辑或 systemd unit 文件。

### 其它信息

- 本轮新增/调整的日志点包括：导航主程序关闭开始/完成、重启开始/完成、端口清理开始、fuser 命令执行、无权限降级、命令失败、命令完成、端口释放完成和端口释放超时。
- 这些日志用于排查控制台停止/重启后 28180 端口仍被旧导航桥接占用、sudo 无权限、fuser 缺失、清理命令失败或端口迟迟未释放等问题。
- 生成时间：2026-06-17

## 本轮补充：QA 触发导览 workflow 启动测试

### 背景和目标

本轮按 Aaron 要求对当前 workflow 做一轮启动链路测试，重点确认三件事：全部基础服务能否正常启动；默认进入 QA 问答模式后大模型是否能正常回答问题；通过命令形式向 STT 注入“开始导览”后，是否能触发导览 workflow 启动。Aaron 已说明机器人可能没有开启行走模式，因此本轮不把导航是否实际移动或到点作为成败标准。

### 当前状态

已完成：

- 已确认测试开始前 Git 工作区干净，最新提交为 `9bded4f 修复控制台重启端口清理与 TTS 默认后端`。
- 已确认 `rabbitbot-loop.service`、`rabbitbot-control-console.service` 和 `docker.service` 均为 `active`。
- 已确认统一容器 `rabbitbot-unified-runtime` 正在运行。
- 已确认关键端口均在监听：VLM `8000`、Neo4j `7687`、导航桥接 `28180`、Memory `28182`、STT `28184`、TTS `28185`。
- 已确认 `runtime/nav_workflow_control/guide_state` 曾进入 `qa_listening`，表示导览 workflow 已预启动并停在 go 闸门，QA 模式处于待命。
- 已通过 STT 注入接口发送普通问题：`你好，请用一句话介绍你自己`；接口返回 HTTP 200，`utterance_id=1`。
- 已确认 QA/VLM/TTS 链路正常：TTS 日志显示回答被提交并播报，内容为“你好！”和“我是RabbitBot，一个能够回答各种问题的智能助手。”。
- 已通过 STT 注入接口发送导览口令：`开始导览`；接口返回 HTTP 200，`utterance_id=2`。
- 已确认导览被成功触发：`guide_state` 从 `qa_listening` 切换到 `guide_running`，导览 workflow 日志显示进入严格 DOCX 剧本并发送第一段导航目标。
- 已确认导览启动后继续推进：workflow 完成开场 TTS、动作调用、`1到2过渡` 和 `跟随步行到点位2` 两个导航步骤，随后进入 `点咖啡` 台词段。

未完成：

- 本轮没有验证机器人真实行走、导航到点精度或完整导览闭环；Aaron 已明确本轮不关注导航是否成功。
- 本轮没有执行 `back` 返航，也没有停止当前 `rabbitbot-loop.service`。
- 本轮没有修改业务代码。

### 已验证的事实

- `guide_state` 最终为 `state=guide_running`、`run_id=20260612_131441`，说明导览已经进入运行态。
- 服务最终仍保持可用：`rabbitbot-loop.service`、控制台和 Docker 为 active，28180/28182/28184/28185/8000/7687 仍在监听。
- STT 注入普通问题和导览口令均返回 HTTP 200。
- QA 问答路径使用当前配置 `vlm_stream=0`、`stream_tts=1`，普通问题已完成大模型回答和 TTS 分段播报。
- 导览 workflow 日志显示第一段目标为 test9 点位 `(0.1797, -0.1793, 0.0022, 0.1118, 0.0196, 0.9935)`，并成功进入后续剧本步骤；该事实只用于证明导览流程启动，不用于评价导航是否成功。
- 观察到一个非本轮判定项：进入 `点咖啡` 台词段后，TTS 已生成并入队 `tts_index=7..10`，但日志中只看到 `tts_index=7` 的 `tts_play_start`，未继续看到对应 `tts_play_done`；workflow 随后持续查询 `get_wav_count`。这不影响本轮“启动是否成功”的结论，但后续若要完整跑导览，需要单独排查 TTS 播放队列卡住风险。

### 阻塞问题

本轮目标无阻塞：服务启动、QA 问答、STT 口令触发导览启动三项均已验证通过。剩余风险是完整导览运行层面风险，主要是现场行走模式/导航状态和本轮观察到的 TTS 播放队列可能卡住。

### 建议的下一步

- 如果只验证“开始导览”触发链路，本轮已经满足要求。
- 如果要继续验证完整导览，需要先确认机器人行走模式已开启，再观察导航和 `点咖啡` 后续台词是否继续播报。
- 如后续发现卡在 `点咖啡`，优先检查 `logs/unified_runtime/rabbitbot_tts.log` 中 `tts_index=7` 是否缺少 `tts_play_done`，以及本地 REDMI 音响播放线程是否阻塞。
- 如需恢复待命状态，可在现场确认安全后按既有流程停止或重启 `rabbitbot-loop.service`，或根据当前位置决定是否发送 `back`。

### 注意事项

- 本轮测试通过 STT `/exec` 的 `inject_text_async` 注入文本，不依赖真实麦克风识别。
- 本轮没有因为导航状态做失败判定；机器人未开启行走模式时，导航是否移动不代表 workflow 启动失败。
- 远端日志时间显示为 2026-06-12，当前会话日期为 2026-06-17；后续排查时应注意 AGX-orin 系统时间可能与当前会话日期不一致。

### 其它信息

- 本轮没有新增或调整代码日志点。
- 本轮使用的关键日志包括：`logs/vlm_qa_workflow/vlm_qa_workflow_20260612_051412.log`、`logs/vlm_qa_workflow/vlm_qa_dialogue_20260612_051414.log`、`logs/nav_workflow_control/rabbitbot_workflow_20260612_131441.log`、`logs/unified_runtime/rabbitbot_tts.log`。
- 生成时间：2026-06-17

## 本轮补充：放宽 QA 问答提示词

### 背景和目标

Aaron 反馈当前提示词可能收得过紧，导致大模型经常回答“抱歉无法回答”。本轮目标是放宽 QA workflow 的系统提示词，让模型在信息不足或问题较宽泛时优先尝试给出有用回答，而不是直接拒答。

### 当前状态

已完成：

- 已检查 `rabbitbot/agno_agents/vlm_qa_workflow.py` 的 `QA_SYSTEM_PROMPT`，确认当前 QA 提示词虽然已经解除导览范围限制，但仍缺少“信息不足时先合理回答或追问”的明确要求。
- 已在历史 QA 日志中确认出现过“很抱歉，您没有提供足够的信息让我能够回答您的问题。”这类保守拒答。
- 已将 QA 系统提示词放宽为 `qa_broad`：明确 RabbitBot 是开放式中文语音问答助手，可回答日常聊天、通用知识、轻量技术解释、机器人能力说明、园区导览和当前画面相关问题。
- 已新增提示词约束：用户问题不完整或上下文不足时，不要直接说无法回答；先按最可能含义给出简短有用回答，并在结尾补一句澄清问题。
- 已调整实时信息、专业诊断、法律医疗金融等高风险问题策略：不编造事实，但应给通用背景、判断思路和安全建议，而不是直接拒答。
- 已保留必要边界：不泄露隐私、不执行危险或违法请求，不模拟导航命令，不输出动作标签或工具调用标记。
- 已将启动日志中的 `prompt_profile` 从 `qa_independent` 改为 `qa_broad`，便于现场确认新提示词是否生效。

未完成：

- 本轮未重启当前正在运行的 QA/导览服务；已运行进程不会热加载本次代码改动。需要重启 `rabbitbot-loop.service` 或重新启动 QA workflow 后，新提示词才会生效。
- 本轮未做在线 VLM 问答实测，避免干扰当前现场运行状态。

### 已验证的事实

- `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile rabbitbot/agno_agents/vlm_qa_workflow.py` 通过。
- `bash -n scripts/start_vlm_qa_workflow.bash` 通过。
- `git diff --check` 通过。
- 轻量检查确认提示词包含“开放式中文语音问答助手”“不要直接说无法回答”“只有在问题明显不可理解”等关键放宽规则。

### 阻塞问题

无代码层面阻塞。运行层面唯一注意点是：必须重启 QA/导览相关进程后，`qa_broad` 提示词才会实际参与问答。

### 建议的下一步

- 现场安全窗口内重启 `rabbitbot-loop.service` 或 QA workflow，让新提示词生效。
- 用之前容易触发“无法回答”的问题做对比测试，重点观察问答日志是否从拒答变为“给出合理回答 + 必要澄清”。
- 如果仍然过于保守，可继续降低系统提示中的风险措辞，或针对常见现场问题加 few-shot 示例。

### 注意事项

- 本轮只放宽 QA workflow，不改严格 DOCX 导览台词和导览 workflow 的导航/动作逻辑。
- 导览触发口令“开始导览”仍由外部流程处理，QA 回答中不会模拟导航命令。

### 其它信息

- 本轮调整的日志点：启动日志和 VLM 推理日志中的 `prompt_profile` 改为 `qa_broad`，用于确认运行进程是否加载新提示词。
- 生成时间：2026-06-17
