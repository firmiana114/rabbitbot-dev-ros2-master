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

## 本轮补充：阅读项目与交接报告并确认当前状态

### 背景和目标

Aaron 要求通过 SSH 登录 AGX-orin-FX，阅读 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master` 项目和交接报告，确认当前项目背景、近期工作、运行状态和工作区情况。本轮以读取、梳理和非侵入式检查为主，不启动或停止机器人相关服务，不触发导览、返航、TTS 播报或机器人移动。

### 当前状态

已完成：

- 已通过 SSH 阅读项目根目录、README、控制台 README、Git 分支、最近提交、受版本管理文件清单和完整交接报告。
- 已确认当前分支为 `June6_workflow`，最近提交包含 `eacade8 进一步放宽qa提示词`、`f8d2404 放宽 QA 问答提示词减少拒答`、`33c1500 压缩交接报告保留近期重点`。
- 已确认当前业务入口主要包括：`rabbitbot/agno_agents/vlm_qa_workflow.py`、`rabbitbot/agno_agents/workflow.py`、`rabbitbot/control_console/`、`scripts_1/start_nav_bridge_workflow_loop.sh`、`scripts_1/unified_runtime/start_unified_container.sh`。
- 已确认接手时存在 6 个未提交业务改动：`conf/dialogue_0.json`、`scripts/start_tts_app.bash`、`scripts_1/start_nav_bridge_workflow_loop.sh`、`scripts_1/start_unified_integration_workflow.sh`、`scripts_1/systemd/rabbitbot-loop.service`、`scripts_1/unified_runtime/start_unified_container.sh`。
- 已读取这些未提交差异：`dialogue_0.json` 从短 test9 剧本切到 test7 地图和 13 个点位长导览；TTS 默认后端从 `auto` 调整为 `local`；导航 loop 增加运行时健康检查连续失败阈值并将 TTS 健康检查改为端口检查；统一集成脚本会在 TTS 端口存在但 `/exec` 不响应时判定容器不兼容；systemd 默认地图改为 `/home/unitree/test7.pcd`；统一容器启动脚本会清理疑似卡死的旧 TTS 进程。
- 已确认当前运行状态文件为 `state=guide_finished_waiting_back`、`run_id=20260618_161702`、`exit_code=0`；`rabbitbot-loop.service` 当前为 inactive，`rabbitbot-control-console.service` 和 `docker.service` 为 active。

未完成：

- 本轮没有启动或停止任何服务，没有发送 `go/back`，没有验证真实机器人移动、真实语音识别或真实 TTS 出声。
- 本轮没有评审或接管 6 个既有未提交业务改动的正确性，仅记录其内容并做基础格式检查。

### 已验证的事实

- `python3 -m json.tool conf/dialogue_0.json` 通过，当前已修改台词文件是合法 JSON。
- `bash -n scripts/start_tts_app.bash` 通过。
- `bash -n scripts_1/start_nav_bridge_workflow_loop.sh` 通过。
- `bash -n scripts_1/start_unified_integration_workflow.sh` 和 `bash -n scripts_1/unified_runtime/start_unified_container.sh` 通过。
- AGX 环境未安装 `rg`，本轮使用 `find`、`grep`、`git ls-files` 和 `sed` 替代读取项目结构。

### 阻塞问题

无阅读层面的阻塞。后续如果要继续处理当前 6 个业务改动，需要先确认这些改动是否都是现场期望保留的 test7 长路线、TTS 本地后端和 TTS 卡死恢复策略。

### 建议的下一步

- 如需验收当前未提交业务改动，优先在现场安全窗口确认 test7 地图、13 个点位路线和返航点是否与现场一致。
- 如需恢复待命状态，先确认机器人现场位置和安全，再决定是否启动 `rabbitbot-loop.service` 或发送返航命令。
- 如需提交当前 6 个业务改动，应先完成至少一次脚本级验证和必要的服务启动验证，并在提交前更新本交接报告。

### 注意事项

- 本轮只提交交接报告更新，未提交既有 6 个业务改动，避免混入非本轮产生的现场改动。
- 当前 `rabbitbot-loop.service` 为 inactive，但 `guide_state` 保留在上次导览完成等待返航状态；后续判断 ready 时应同时看服务状态和 `guide_state`。
- `conf/dialogue_0.json` 当前已跟踪且有大幅差异；修改或提交前应重点检查 map_file、点位顺序、过渡点和 `back_points`。

### 其它信息

- 本轮没有新增或调整代码日志点；仅确认既有未提交脚本中包含运行时健康检查失败阈值、健康恢复、TTS 端口卡死识别、旧 TTS 进程清理等日志或诊断输出。
- 生成时间：2026-06-22

## 本轮补充：补充导览引导词、点位7等待和 TTS 读音调整

### 背景和目标

Aaron 要求基于当前 test7 长导览台词继续调整：每次前往地点前增加引导词，用于提示将前往的板块并引导客人跟随；点位7讲解完成后等待4分37秒，再前往下一个讲解点位；将分区讲解中的 ABCD 改成中文近似读音，避免 TTS 播报英文字母不稳定。同时要求把现有未提交改动一并提交。

### 当前状态

已完成：

- `conf/dialogue_0.json` 已为主要导航 step 增加 `guide` 字段，workflow 会在导航前先播报这些引导词。
- 已覆盖点位间过渡、点位2至点位13的主要前往提示，包括企业服务中心、科创带背景、创新资源、园区共建、复星创富、功能布局、规划配套、企业入驻、投融资、产学研、智慧园区和出口小巴方向。
- 已在点位7最后一段讲解后增加 `post_wait_seconds=277`，对应4分37秒等待，然后才进入下一步导航。
- 当前台词中 ABCD 分区实际位于功能布局讲解段，已替换为 `埃区域`、`毙区域`、`锡区域`、`第区域`。
- 本轮按要求一并纳入既有未提交改动：test7 长路线台词和点位、TTS 默认本地后端、导航 loop 健康检查失败阈值、TTS 端口卡死识别与旧 TTS 进程清理、systemd 默认地图切到 `/home/unitree/test7.pcd`。

未完成：

- 本轮没有启动或停止 `rabbitbot-loop.service`，没有触发真实导览、返航、机器人移动或 TTS 出声。
- 新增引导词和 277 秒等待尚未做现场完整导览验证。

### 已验证的事实

- `python3 -m json.tool conf/dialogue_0.json` 通过，台词 JSON 格式有效。
- `bash -n scripts/start_tts_app.bash` 通过。
- `bash -n scripts_1/start_nav_bridge_workflow_loop.sh` 通过。
- `bash -n scripts_1/start_unified_integration_workflow.sh` 通过。
- `bash -n scripts_1/unified_runtime/start_unified_container.sh` 通过。
- `git diff --check` 通过。
- 已确认 `conf/dialogue_0.json` 中不再包含 `A区域`、`B区域`、`C区域`、`D区域` 原始写法。

### 阻塞问题

无代码和配置层面的阻塞。运行层面仍需要现场安全窗口验证：test7 地图路线、13个点位、返航点、4分37秒等待节奏，以及本地 TTS 对新增引导词和中文近似读音的实际播报效果。

### 建议的下一步

- 现场安全确认后重启或启动 `rabbitbot-loop.service`，让新的台词 JSON、test7 地图和脚本配置生效。
- 完整跑一次导览，重点观察每次导航前是否先播报对应 `guide` 引导词。
- 到点位7后确认讲解播完会等待约277秒，再继续前往园区规划和硬件配套板块。
- 重点听功能布局段落中的 `埃区域`、`毙区域`、`锡区域`、`第区域` 是否比英文字母播报更稳定。

### 注意事项

- `post_wait_seconds` 是在对应台词段播报完成后生效；如果 TTS 队列自身卡住，等待计时会在该段完成后才开始。
- 新增 `guide` 字段依赖现有 workflow 逻辑，播报发生在该 step 导航前。
- 本轮提交包含此前未提交的脚本和 systemd 配置变更，部署时需确认实际 systemd unit 是否已从仓库模板同步到系统目录。

### 其它信息

- 本轮新增/调整的日志点：没有新增代码日志模块；但一并提交的导航 loop 和统一容器脚本包含运行时健康检查连续失败日志、健康恢复日志、TTS 端口卡死识别日志和旧 TTS 进程清理日志，可用于排查 TTS 卡死和服务恢复问题。
- 生成时间：2026-06-22

