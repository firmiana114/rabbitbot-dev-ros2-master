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

## 本轮补充：排查控制台服务未就绪提示

### 背景和目标

Aaron 反馈前端显示“服务仍未全部就绪，请查看状态或打开日志排查”。本轮目标是通过 SSH 查看当前服务、端口、控制台 `/api/status`、`guide_state` 和相关日志，确认未就绪原因。本轮只做排查和记录，不改业务代码，不启动导览、不发送 `go/back`，不触发机器人移动。

### 当前状态

已完成：

- 已确认 `rabbitbot-loop.service`、`rabbitbot-control-console.service`、`docker.service` 均为 active。
- 已确认控制台 8080、导航桥接 28180、VLM 8000、Neo4j 7687 已监听。
- 已确认控制台 `/api/status` 返回 `main_loop=running`、`nav_bridge.ready=true`、定位成功，地图为 `/home/unitree/test7.pcd`。
- 已确认前端未就绪的直接原因是 `guide_state.state=starting`，未进入 `qa_listening`。
- 已确认启动链路先等待 VLM，VLM 在 09:59:06 就绪；随后卡在 TTS `/exec` 服务 28185 就绪等待。
- 已确认 TTS 日志显示：未找到稳定可用的外接输出音频设备，拒绝启动 TTS；容器内没有检测到 `REDMI Speaker 2-6002`，`aplay -l` 和 `pactl list short sinks` 也未列出可用输出设备。
- 已确认当前容器环境为 `RABBITBOT_TTS_BACKEND=local`、`RABBITBOT_TTS_ALLOW_BUILTIN=0`，因此没有外接本地音响时 TTS 会按设计拒绝启动。

未完成：

- 本轮未修复 TTS 未就绪问题，未修改配置为 Unitree 后端或内置声卡回退。
- 本轮未重启服务，未验证现场音响重新连接后的恢复情况。

### 已验证的事实

- `runtime/nav_workflow_control/guide_state` 当前为 `state=starting`、`detail=导航 loop 初始化`。
- `logs/unified_runtime/qwen2.5-vl-7b-gptq.log` 显示 VLM 已启动并开放 `/v1/models`。
- `logs/unified_runtime/rabbitbot_tts.log` 显示 TTS 因未找到稳定可用外接输出音频设备退出。
- `/tmp/rabbitbot_tts_sounddevice.err` 在容器内记录多次“未检测到指定 TTS 输出设备: redmi speaker 2-6002”，最后一次扫描没有发现可用输出设备。
- `/etc/systemd/system/rabbitbot-loop.service` 模板中的默认地图仍显示 test9，但 `runtime/rabbitbot-loop.env` 已覆盖为 `NAV_PCD_PATH="/home/unitree/test7.pcd"`；这不是本次未就绪原因。

### 阻塞问题

当前阻塞是 TTS 输出设备不可用：本地 TTS 后端要求检测到稳定外接音频输出，当前容器内看不到 REDMI 音响或任何可用输出设备，因此 28185 不会启动，后续 STT/Memory/QA 也无法完成，控制台无法进入 ready。

### 建议的下一步

- 优先现场确认 `REDMI Speaker 2-6002` 是否已连接、供电、配对，并能被 AGX/容器看到。
- 如果现场允许临时用内置声卡或其它输出，需要设置 `RABBITBOT_TTS_ALLOW_BUILTIN=1` 并确认启动脚本会把该变量传给 TTS 子进程后再重启服务。
- 如果希望不依赖本地 REDMI 音响，可改用 `RABBITBOT_TTS_BACKEND=unitree` 或恢复 `auto` 回退策略，并重启 `rabbitbot-loop.service` 验证。
- TTS 修复后，等待 28185 启动，再观察后续 28184、28182 和 `guide_state=qa_listening`。

### 注意事项

- 当前不要直接点击“导览”作为排查动作，因为业务状态还没进入 `qa_listening`。
- 仅 VLM 冷启动慢不是最终故障；VLM 已就绪，当前卡点是 TTS 设备不可见。
- 如果修改 systemd 仓库模板，需要同步到 `/etc/systemd/system/rabbitbot-loop.service` 后执行 daemon-reload，否则系统实际 unit 仍保留旧模板内容。

### 其它信息

- 本轮没有新增或调整代码日志点；使用的关键日志为 `journalctl -u rabbitbot-loop.service`、`logs/unified_runtime/qwen2.5-vl-7b-gptq.log`、`logs/unified_runtime/rabbitbot_tts.log` 和 `/tmp/rabbitbot_tts_sounddevice.err`。
- 生成时间：2026-06-22

## 本轮补充：手动重启 TTS 并恢复导览链路

### 背景和目标

Aaron 要求在前端未就绪排查后“重启TTS试试”。本轮目标是在不改业务代码、不切换 TTS 后端的前提下，按当前 `local` 后端配置手动拉起 TTS，观察 28185 是否恢复，并确认控制台 ready 链路是否继续推进。

### 当前状态

已完成：

- 已确认重启前容器内无 TTS 进程，28185 未监听，`guide_state` 仍为 `starting`。
- 已在 `rabbitbot-unified-runtime` 容器内按现有配置手动启动 `scripts/start_tts_app.bash`，保留 `RABBITBOT_TTS_BACKEND=local`、`RABBITBOT_TTS_ALLOW_BUILTIN=0` 和首选设备 `REDMI Speaker 2-6002`。
- TTS 本次启动成功，28185 已监听，`/exec wait_speech` 返回 `{"out_text":"TTS finished"}`。
- loop 随后识别到 `TTS /exec 服务 (28185) 已就绪`，继续启动 STT 和 Memory Agent。
- 28184、28182、28185、8000、28180、8080 均已监听。
- `guide_state` 曾进入 `qa_listening`，随后 STT 真实识别到“开始导览”，workflow 释放 go 闸门并进入 `guide_running`。
- 当前 workflow run_id 为 `20260622_100400`，已进入严格 DOCX 剧本和 test7 导览流程。

未完成：

- 本轮没有停止当前导览，没有发送 `back`，也没有人工干预机器人运动。
- 未确认 TTS 本次为什么能成功检测到输出设备；可能是音响在排查过程中恢复可见，也可能是设备枚举延迟恢复。

### 已验证的事实

- `logs/unified_runtime/rabbitbot_tts.log` 显示 TTS 预热完成、Uvicorn 在 28185 启动，并处理 `/exec` 请求。
- `journalctl -u rabbitbot-loop.service` 显示 `TTS /exec 服务 (28185) 已就绪`。
- `runtime/nav_workflow_control/guide_state` 当前为 `state=guide_running`、`run_id=20260622_100400`。
- STT 日志显示识别文本为“开始导览”，这解释了为什么系统从 `qa_listening` 继续切到 `guide_running`；本轮没有通过命令文件手动发送 `go`。
- 最新 workflow 日志显示已加载 `conf/dialogue_0.json`，`map_file=test7.pcd`，并开始执行新增引导词，例如“一站式企业服务和交流路演中心板块”。

### 阻塞问题

当前未见服务级阻塞。剩余风险是导览正在运行中，需要现场确认机器人移动、TTS 播报、点位导航和后续点位7等待是否符合预期。

### 建议的下一步

- 现场观察当前导览是否按 test7 路线继续运行，重点听 TTS 是否稳定出声。
- 如果需要中止或返航，应先确认现场安全，再用控制台返航或既有 `back` 流程处理。
- 若下次重启仍出现 28185 不启动，优先查看 REDMI 音响连接和 `/tmp/rabbitbot_tts_sounddevice.err`。

### 注意事项

- 当前已进入 `guide_running`，控制台不会再显示“可开始导览”的待命状态；这是导览已开始，不是服务未就绪。
- TTS 是手动在现有容器中拉起的；如后续重启整个容器或服务，仍需确认音频设备可见。
- 本轮没有修改业务代码或配置。

### 其它信息

- 本轮没有新增或调整代码日志点；关键日志为 `logs/unified_runtime/rabbitbot_tts.log`、`logs/unified_runtime/rabbitbot_stt.log`、`logs/nav_workflow_control/rabbitbot_workflow_20260622_100400.log` 和 `journalctl -u rabbitbot-loop.service`。
- 生成时间：2026-06-22

