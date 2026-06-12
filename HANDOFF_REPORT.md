# 交接报告

## 背景和目标

本轮目标是在六月六日 DOCX/PDF 剧本已对齐、过渡点和新地图坐标已更新的基础上，将导览台词从 `workflow.py` 抽离到独立 JSON 文件，便于现场直接修改文案；同时将默认称呼配置为台词文件中的 `variables.leader_calling` 键。项目主机 `AGX-orin-FX`，路径 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，分支 `June6_workflow`。

## 当前状态

已完成：

- 已保持严格 DOCX 剧本开场逻辑：不在开场台词前额外导航点位1，直接从点位1开始台词。
- 已保持当前 DOCX 剧本步骤顺序：`1到2过渡`、`跟随步行到点位2`、`点咖啡`、`初步介绍`、`拿取咖啡`、`前往3到5过渡点`、`前往点位5`、`告别并指引小巴方向`。
- 已保持 `1->2过渡点位` 和 `3->5过渡点位` 为独立只导航、无台词步骤，避免在过渡点提前播报。
- 已按现场新采地图更新 DOCX 点位坐标：`点位1`、`1->2过渡点位`、`点位2`、`点位3`、`3->5过渡点位`、`点位5` 已写入 `DOCX_SCRIPT_POINTS`；其中本轮按最新反馈将点位1改为 `(1.9105, -1.6180, 0.0117, -0.0029, 0.0265, -0.2046, 0.9785)`。
- 已将导览台词文件命名格式改为 `conf/dialogue_<序号>.json`，当前默认文件为 `conf/dialogue_0.json`；不显式指定时默认加载 0 号台词；启动 workflow 时可通过 `RABBITBOT_DIALOGUE_INDEX=<序号>` 选择对应台词文件。
- 本轮核实并修复：`workflow.py` 已支持 `RABBITBOT_DIALOGUE_INDEX`，但 `start_nav_bridge_workflow_loop.sh` 原先没有向容器内 workflow 透传该变量，因此 loop 场景下不能可靠切换台词序号；现已补齐透传和启动日志。
- 本轮已将 `conf/dialogue*` 前缀台词文件加入 `.gitignore`，并从 Git 索引移除 `conf/dialogue_0.json`；Orin 本地文件仍保留，`conf` 目录本身和其它非 dialogue 配置文件不被整体忽略。
- 本轮已补齐 `workflow.py` 顶部运行环境变量速查注释，覆盖严格剧本、台词序号/文件覆盖、咖啡车后台命令、导航、动作、profile 和 mock 视觉相关变量。
- 本轮已将 `send_delivery_task.py` 纳入版本管理，并为脚本补充中文命令说明和 AIR 咖啡车接口调用日志。
- 本轮已按现场要求先停止当前 workflow 进程组，保留 unified 容器和 TTS/STT/Memory 后台服务继续运行。
- 本轮提交后发现现场仍有一次旧式外部 `docker exec ... bash scripts/start_kuavo_agno_workflow.bash | tee` 命令重新拉起 workflow；已再次只停止该旧 workflow 进程组，容器和后台服务仍保留。
- 本轮已改造 unified `start_workflow()`：workflow 现在以独立进程组启动，`^C`/TERM/EXIT 会触发清理逻辑，先 TERM 后按需 KILL 整个 workflow 进程组。
- 本轮已将 `0203788` 中 `workflow.py` 的 workflow 运行环境变量速查注释同步补充到联调和非联调两个 unified workflow 启动脚本，便于现场启动前直接查看台词、咖啡车、导航、动作和日志相关变量。
- 本轮新增 `scripts_1/start_nav_bridge_workflow_loop.sh`，用于合并启动导航桥接和 unified 基础服务，并通过外部 `go/back` 命令循环启动 workflow、剧本结束后返航到点位1、再等待下一次 `go`。
- 本轮已补齐 `scripts_1/start_nav_bridge_workflow_loop.sh` 的台词切换支持：启动 loop 时可通过 `RABBITBOT_DIALOGUE_INDEX=<序号>` 选择 `conf/dialogue_<序号>.json`，也可继续使用旧变量 `RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX` 或文件覆盖变量 `RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE`；脚本会在预启动 workflow 时打印本轮台词来源。
- 本轮修正 `start_nav_bridge_workflow_loop.sh` 的运行环境：导航控制日志默认改到普通用户可写的 `logs/nav_workflow_control`，并在启动导航桥接前显式 source Humble 和 `custom_action_ws`，避免普通用户写日志失败后改用 sudo 导致 ROS 动态库和 uvicorn 环境丢失。
- 本轮已将 `start_nav_bridge_workflow_loop.sh` 默认导航地图从 `/home/unitree/test.pcd` 改为 `/home/unitree/test1.pcd`；仍可通过 `NAV_PCD_PATH` 环境变量临时覆盖。
- 本轮修复 `start_nav_bridge_workflow_loop.sh` 的 `go/back` 控制体验：命令轮询默认从 1 秒降到 0.2 秒；workflow 运行期间提前收到 `back` 时会立即记录并排队，待 workflow 结束后自动返航。
- 本轮已移除 DOCX 剧本结束后的普通问答模式：严格 DOCX 剧本完成后 workflow 会结束，不再进入“你好，请问你需要我做什么吗”的 STT/TTS 循环；现场本地忽略文件 `examples/run_kuavo_agno.py` 的“流程测试完成”播报也已改为默认关闭。
- 本轮已修复 `back` 返航路径：`start_nav_bridge_workflow_loop.sh` 不再从点位5直接发送点位1单一目标，而是按 `3->5过渡点位 -> 点位3 -> 点位2 -> 1->2过渡点位 -> 点位1` 分段返航；每段都会重置导航状态、发送目标、轮询状态并打印分段耗时。
- 本轮已优化 `go` 后 workflow 启动延迟：`start_nav_bridge_workflow_loop.sh` 现在会先预启动 workflow，并让新 runner 在 AppContext 初始化完成后停在启动闸门；收到 `go` 时只写入闸门文件释放开场，避免现场再等待 Python/import/AppContext 初始化。
- 本轮新增可提交入口 `scripts/run_kuavo_agno_workflow.py`，`scripts/start_kuavo_agno_workflow.bash` 已从 ignored 的 `examples/run_kuavo_agno.py` 切到该入口；`scripts/start_all_services.sh` 和编排脚本的运行检测也已补充新 runner 匹配。
- 本轮修复启动脚本直接退出问题：根因是预启动 workflow 时宿主侧日志被写到 `logs/unified_runtime/rabbitbot_workflow_*.log`，该目录当前为 `root:root 755`，普通用户 `pc` 无法创建文件，`set -e` 触发脚本退出并清理导航桥接。现在宿主日志、ready/go 闸门和状态文件均改到普通用户可写的 `logs/nav_workflow_control`，容器内对应路径为 `/workspace/projects/rabbitbot-dev-ros2-master/logs/nav_workflow_control`。
- 本轮增强 `scripts/run_kuavo_agno_workflow.py`：启动时主动将项目根目录加入 `sys.path`，避免直接运行或容器内验证时因未设置 `PYTHONPATH` 找不到 `rabbitbot`。
- 本轮定位 `back` 无法返航的原因：当前脚本处于预启动 workflow 后等待 `go` 的阶段，旧逻辑只接受 `go`，收到 `back` 会被 `wait_command go` 读走并作为非当前阶段命令忽略，因此不会进入返航。
- 本轮同时发现预启动状态目录不一致：ready/go 闸门已在 `logs/nav_workflow_control`，但 runner 的 `status/pid/exit_code` 仍受 `RABBITBOT_LOG_DIR` 影响写入旧目录，主脚本可能看不到 workflow 完成状态。已将 docker exec 传入的 `RABBITBOT_LOG_DIR` 改为容器内 `logs/nav_workflow_control`，使 ready、go、status、pid、exit_code 统一。
- 本轮修复等待 `go` 阶段的 `back` 行为：新增 `wait_go_or_back`，等待 go 时收到 back 会停止当前预启动 workflow 和日志 tail，然后直接执行分段返航；同时检测 ready 文件存在但预启动进程已退出的 stale 状态，自动重新预启动。
- 本轮新增 `scripts_1/send_nav_workflow_command.sh`，供其它终端发送 `go`、`back` 或 `quit` 控制命令；命令通过 `/tmp/rabbitbot_nav_workflow_control/command` 文件传递，不依赖主终端 stdin。
- 已将默认称呼抽为 `variables.leader_calling`，台词中的 `{leader_calling}` 会在运行时替换；缺少该键时 workflow 会报出明确配置错误，不再静默使用代码内固定称呼。
- 本轮已按现场要求调整 `conf/dialogue_0.json`：开场问候句改为“{leader_calling}您好，我叫小智。”；点位5小巴引导合并为一个播报段，减少句间 TTS 停顿，最后“各位再会！”仍单独配合挥手动作。
- 本轮复查所有运行态称呼：严格 DOCX 台词中的个性化称呼均来自 `conf/dialogue_0.json` 的 `variables.leader_calling`；当前配置为 `姚区长`，格式化后会播报“姚区长您好，我叫小智。”、“对了，姚区长、各位...”、“姚区长，咖啡和饮料来了...”和“姚区长、各位领导...”。
- 本轮同步修正非严格剧本导览兜底称呼：普通 scripted tour 的转场介绍和结束语现在也优先使用 `ctx.leader_info.leader_calling` 或 `variables.leader_calling`，不再硬编码“各位领导”。
- 当前开场不再包含“第一次来园区”问答；第三段欢迎各位朋友的台词仍使用 `face_wave` 动作。
- 已调整 dialogue01/dialogue02 的握手动作时序：
  - `shake_hand` 现在从开场问候“{leader_calling}您好，我叫小智。”开始时启动。
  - dialogue02 “欢迎您来到滨湖复星人形机器人产业园。”仍在同一个握手动作窗口内播报。
  - `release` 收手仍复用 `_do_arm_during_speech` 的原有流程，在 dialogue02 播报结束后执行。
- 已将 TTS 默认启动路径切到 Unitree G1 本体音响：未显式设置 `RABBITBOT_TTS_BACKEND` 时默认使用 `unitree`，未显式设置 `RABBITBOT_UNITREE_TTS_VOLUME` 时默认音量为 `100`。
- 已新增 Unitree G1 本体 TTS 后端：
  - 新增 `scripts/unitree_g1_tts_bridge.cpp`，通过宇树 SDK2 `AudioClient.TtsMaker` 向 G1 发送播报文本。
  - 新增 `scripts/build_unitree_g1_tts_bridge.sh`，自动使用 `/mnt/ssd/navgation/projects/unitree_sdk2` 或 `/workspace/projects/unitree_sdk2` 构建桥接程序。
  - 新增 `rabbitbot/audio/unitree_g1_tts.py`，封装桥接程序调用、音量设置、网卡配置、等待估算和日志。
  - `tts_app.py` 新增 `RABBITBOT_TTS_BACKEND=unitree` 后端；默认仍为本地 TTS，不影响原外接音箱方案。
  - `scripts/start_tts_app.bash` 在 Unitree 模式下跳过 Orin 本地输出声卡扫描，避免因没有外接音箱导致 TTS 服务启动失败。
  - 统一容器脚本新增 Unitree TTS 相关环境变量，并在 TTS 后端或网卡配置变化时重建旧容器。

未完成：

- 尚未在完整 unified workflow 中验证 Unitree 本体 TTS 与 STT 打断、`tts_wait`、开场动作并发的整体节奏。
- 尚未在真机/完整 workflow 中验证提前伸手后的握手距离、收手时机、TTS 节奏和现场观感。

## 已验证的事实

- Orin 和 G1 通过有线网卡 `eno1` 通信，Orin 上 `eno1` 地址为 `192.168.123.222/24`。
- Orin 当前没有安装 Python 版 `unitree_sdk2py` 和 `cyclonedds`，因此本轮使用已有 C++ `unitree_sdk2` 实现桥接。
- `/mnt/ssd/navgation/projects/unitree_sdk2` 中存在 G1 `AudioClient`、`TtsMaker`、`SetVolume` 和 aarch64 SDK 库。
- `scripts/build_unitree_g1_tts_bridge.sh` 已成功构建 `build/unitree_g1_tts_bridge`。
- 直接运行桥接程序已成功返回：`SetVolume ret=0`，`TtsMaker ret=0`。
- 通过 `UnitreeG1TTS` Python 后端发送“后端测试”已成功返回 `ret=0`，并完成本地估算等待。
- 已通过检查：`bash -n`、`python3 -m py_compile`、桥接程序构建和帮助输出。
- 现有本体 TTS 日志会记录初始化、桥接程序构建、请求开始、返回码、耗时、音量、网卡、speaker id 和估算播放时长。
- 本轮只读调用 Unitree G1 `AudioClient.GetVolume` 查询当前机器人本体音量，返回 `ret=0`、`volume=85`，查询未触发播报，也未调用 `SetVolume`。
- 本轮已验证默认配置干运行初始化：默认后端为 `unitree`，默认网卡为 `eno1`，默认音量为 `100`；`bash -n` 和 `python3 -m py_compile` 均通过。
- 本轮核实机器人本体 TTS 变成女声的原因：当前 unified 容器环境为 `RABBITBOT_TTS_BACKEND=unitree`、`RABBITBOT_UNITREE_TTS_SPEAKER_ID=0`；宇树 G1 `TtsMaker(text, speaker_id)` 的 `speaker_id=0` 对应中文/自动 TTS，不是原 Orin 本地 TTS 音色选择，因此音色由 G1 内置语音服务决定。
- 本轮现场将 TTS 运行时切回 Orin 本地外接音响：宿主机识别到 USB 音响 `BT67`，`aplay -l` 为 `card 2, device 0`；使用 `RABBITBOT_TTS_BACKEND=local RECREATE_CONTAINER=1 RUN_WORKFLOW_AFTER_START=0` 重建统一容器基础服务，TTS 日志确认选中 `BT67: USB Audio (hw:2,0)`，`OUTPUT_DEVICE_INDEX=24`，HTTP `/docs` 返回 200。
- 本轮已通过当前 TTS 服务向 BT67 外接音响发送试播文本“测试测试”，`text_to_speech` 返回 `out_text=0`，随后 `wait_speech` 返回 `TTS finished`。
- 本轮已将 DOCX 剧本点咖啡环节的“我来给各位安排。”配置为播报开始时同步后台呼叫 AIR 咖啡车；后台命令默认解析为 `python3 /mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/send_delivery_task.py run`，在 unified 容器内会自动改用 `/workspace/projects/rabbitbot-dev-ros2-master/send_delivery_task.py`。
- 本轮新增 DOCX 剧本总耗时终端打印：严格 DOCX 模式下从开场第一句实际 TTS 前开始计时；若开场被跳过，则从 DOCX 第一段台词前兜底开始；剧本完成时打印 `DOCX 剧本总耗时`，包含开始时间、结束时间和秒级耗时。
- 本轮按最新剧本删除两处问答交互：开场不再询问“是否第一次来园区”，改为直接播报“{leader_calling}，各位，请随我来，我简单的介绍一下园区。”；点咖啡不再等待领导回答，改为直接播报准备咖啡饮料并在“我来给各位安排。”开播时呼叫 AIR 咖啡车。
- 本轮已从 `拿取咖啡` 场景移除“我再给各位介绍一下产业园和清华创新中心的合作成果。”这句独立播报；该场景现在只保留咖啡和饮料自取提示，随后直接进入 `前往3到5过渡点`。
- 上一轮现场释放了导航桥接常用端口 `28180`：当时确认占用方为 `python3` 进程 PID `7283`，执行结束后复查 `ss -ltnp "sport = :28180"` 已无监听进程。
- 本轮处理旧导航桥接进程：先结束 `start_nav_arm_bridge.sh eno1 /home/unitree/test1.pcd` 的 PID `41946` 进程组；随后复查发现同命令又拉起 PID `42936` 进程组并占用 28180，已继续结束其 `goGoalNavigation66`、`humble_robot_agent_bridge`、`tail`、`tee` 子进程。最终复查 `ss -ltnp "sport = :28180"` 已无监听进程。
- 本轮同步更新了 `docs/DOCX严格剧本workflow逻辑.md` 和 `docs/直接导航命令.txt` 中的点位坐标说明，直接导航命令中的点位5路径已改为包含 `3->5过渡`。
- 本轮同步更新了 `docs/DOCX严格剧本workflow逻辑.md` 和 `docs/直接导航命令.txt` 中的点位1坐标，已与 workflow 和返航脚本默认点位1保持一致。
- 本轮已验证 `conf/dialogue_0.json` 可通过 `python3 -m json.tool` 解析，`rabbitbot/agno_agents/workflow.py` 可通过 `python3 -m py_compile` 语法检查；同时验证未设置环境变量时默认解析到 0 号台词，且 `RABBITBOT_DIALOGUE_INDEX=0` 路径可解析。
- 本轮已验证 `send_delivery_task.py --help` 可正常输出命令说明，`python3 -m py_compile rabbitbot/agno_agents/workflow.py send_delivery_task.py` 语法检查通过；未在本轮实际触发 `run`，避免误呼叫咖啡车。
- 本轮停止当前 workflow 后已复查：容器内不再存在 `run_kuavo_agno.py`、`start_kuavo_agno_workflow.bash` 或 workflow 日志 `tee` 进程；unified 容器仍运行，TTS/STT/Memory 服务进程仍在。
- 本轮对旧式外部 `docker exec` 重新拉起的 workflow 再次执行停止后复查：容器内已无 workflow 相关进程，TTS/STT/Memory 服务仍在，`rabbitbot-unified-runtime` 容器仍运行。
- 本轮已验证 `scripts_1/unified_runtime/start_unified_container.sh` 通过 `bash -n` 语法检查；未重新拉起完整 workflow，避免现场流程被误触发。
- 本轮已验证 `scripts_1/start_unified_integration_workflow.sh` 和 `scripts_1/start_unified_non_integration_workflow.sh` 通过 `bash -n` 语法检查；本轮未停止、重启或重新拉起 workflow。
- 本轮已验证 `scripts_1/start_nav_bridge_workflow_loop.sh` 和 `scripts_1/send_nav_workflow_command.sh` 通过 `bash -n` 语法检查；未实际启动导航桥接、未启动 workflow、未发送返航命令，避免影响现场运行。
- 本轮已验证普通用户 `pc` 对 `logs` 目录有写权限，但 `logs/unified_runtime` 当前为 `root:root 755`，这是直接运行编排脚本时创建导航控制日志失败的原因；同时验证 ROS 动态库缺失可通过 source Humble 和 `custom_action_ws` 修复。
- 本轮已验证 `scripts_1/start_nav_bridge_workflow_loop.sh` 通过 `bash -n` 语法检查；未实际启动导航桥接或 workflow。
- 本轮已验证本次返航修改后的 `scripts_1/start_nav_bridge_workflow_loop.sh` 通过 `bash -n`，`rabbitbot/agno_agents/workflow.py` 通过 `python3 -m py_compile`；未实际发送 `back` 或启动导航，避免影响现场运行。
- 本轮已验证预启动闸门相关静态检查：`scripts_1/start_nav_bridge_workflow_loop.sh`、`scripts/start_kuavo_agno_workflow.bash`、`scripts/start_all_services.sh` 均通过 `bash -n`，`scripts/run_kuavo_agno_workflow.py` 通过 `python3 -m py_compile`，`git diff --check` 通过。
- 本轮已验证当前权限事实：宿主 `logs/nav_workflow_control` 为 `pc:pc` 且可写，宿主 `logs/unified_runtime` 为 `root:root 755` 且 `pc` 不可写；这解释了启动脚本在创建 `rabbitbot_workflow_*.log` 时直接退出。
- 本轮已在当前运行的 `rabbitbot-unified-runtime` 容器内验证 `py310/bin/python scripts/run_kuavo_agno_workflow.py --help` 可正常导入并输出帮助，且容器内 `/workspace/projects/rabbitbot-dev-ros2-master/logs/nav_workflow_control` 可写；未实际启动 workflow。
- 本轮已验证当前现场状态：`start_nav_bridge_workflow_loop.sh` 仍在运行，28180 正常监听，最新 control 目录只有 `20260603_144523.ready`，无当前 `status/pid` 文件，容器内也无 `run_kuavo_agno_workflow.py` 进程；这说明当前实例已经处于等待 `go` 的旧逻辑阶段，发送 `back` 不会返航。
- 本轮已验证修复后的 `scripts_1/start_nav_bridge_workflow_loop.sh` 通过 `bash -n`，`git diff --check` 通过；未停止当前脚本实例，未实际触发返航。
- 本轮已验证 6 元组修复后的 `scripts_1/start_nav_bridge_workflow_loop.sh` 通过 `bash -n`，`git diff --check` 通过；未停止当前旧脚本实例，未重新触发返航。
- 本轮进一步按现场描述复查 `20260603_144523`：机器人已在点位5且 workflow 已结束，`status/finished_at/exit_code` 实际写在旧的 `logs/unified_runtime/workflow_control`，而当时主脚本预期从 `logs/nav_workflow_control/workflow_control` 读取状态；因此主脚本没有识别 workflow 完成，也不会进入 `wait_command back` 或返航流程，`back` 表现为无响应。
- 本轮复查前台未打印 workflow 日志问题：同一 run `20260603_144523` 中，主脚本前台 tail 的 `logs/nav_workflow_control/rabbitbot_workflow_20260603_144523.log` 为 0 字节，而实际 workflow 输出写入 `logs/unified_runtime/rabbitbot_workflow_20260603_144523.log`，大小约 81KB；因此前台只看到导航桥接日志。该问题与状态文件落点不一致同源，重启新版本脚本后 `RABBITBOT_LOG_DIR` 已改为容器内 `logs/nav_workflow_control`，前台 tail 应恢复 workflow 日志。
- 本轮只读复查现场状态：`back` 命令文件已写入但当前旧脚本实例仍在等待 workflow 结束，因此不会立即消费；本轮修复对已运行的旧脚本实例不热更新，需下次重启编排脚本生效。

## 阻塞问题

无代码层面的阻塞。本轮返航分段路径、go 预启动闸门和等待 go 阶段 back 返航尚未真机完整验证，且已运行的旧 `start_nav_bridge_workflow_loop.sh` 实例不会热更新，需要重启该编排脚本后新返航逻辑、低延迟 go 和等待 go 阶段 back 才生效。运行层面另有两个待恢复/验证事项：一是上一轮 BT67 外接音响已从 Orin 声卡列表消失且 TTS 当前未运行，需要现场恢复声卡后再启动；二是本轮 AIR 咖啡车呼叫逻辑未实际运行，避免误触发现场配送任务，需在真机 workflow 点咖啡环节验证。Unitree `TtsMaker` 只返回机器人接收状态，当前没有官方播放完成回调；`wait_speech` 使用文本长度估算等待时间，后续如发现台词衔接过快或过慢，需要调节 `UnitreeG1TTS._estimate_duration` 或新增更可靠的播放状态查询。

## 建议的下一步

- 用如下方式启动 unified 模式验证本体播报：`RECREATE_CONTAINER=1 bash scripts_1/start_unified_integration_workflow.sh`；默认会使用 Unitree G1 本体音响、`eno1` 网卡和音量 `100`。
- 真机跑一次完整开场，重点观察 `shake_hand` 是否从“{leader_calling}您好”开始伸手，并确认收手仍发生在“欢迎您来到滨湖复星人形机器人产业园”之后。
- 当前默认音量已改为 100；如现场觉得过响或破音，可通过 `RABBITBOT_UNITREE_TTS_VOLUME=85` 或更低值临时覆盖后重启 TTS/unified 流程。
- 若必须恢复原来的男声/本地音色，需要评估两条路线：一是回退 `RABBITBOT_TTS_BACKEND=local` 使用 Orin 外接音箱；二是改用 G1 `PlayStream` 播放 Orin 本地合成的 PCM 音频。仅调整 `RABBITBOT_UNITREE_TTS_SPEAKER_ID` 预计不能切换到中文男声。
- 如要继续使用 Orin 外接音响，需先让 Orin 重新识别 BT67，再用 `RABBITBOT_TTS_BACKEND=local RECREATE_CONTAINER=1` 重建/启动 unified；如不带 `RABBITBOT_TTS_BACKEND=local`，会按代码默认值回到机器人本体音响。
- 真机跑点咖啡环节时，重点观察“我来给各位安排。”开播时是否同时出现 `DOCX 后台命令已启动` 和 `DOCX 后台命令结束` 日志，并确认 stdout 中咖啡车接口返回 `success=true` 和运行时 `task_id`。
- 重新拉起导航桥接后，先用 `docs/直接导航命令.txt` 中的新坐标逐点验证 `1->2过渡`、`点位2`、`点位3`、`3->5过渡` 和 `点位5` 到点精度。
- 若使用新的导航 + workflow 编排脚本，主终端执行 `bash scripts_1/start_nav_bridge_workflow_loop.sh`，其它终端用 `bash scripts_1/send_nav_workflow_command.sh go` 启动 workflow，剧本完成后用 `bash scripts_1/send_nav_workflow_command.sh back` 返回点位1。
- 重启 `start_nav_bridge_workflow_loop.sh` 后，真机重点验证 `back` 是否按点位5、`3->5过渡点位`、点位3、点位2、`1->2过渡点位`、点位1的逆序路径行走，并观察每段日志中的 `返航分段 x/5` 状态和耗时。
- 重启 `start_nav_bridge_workflow_loop.sh` 后，先观察主终端是否出现 `workflow 已完成预启动并停在 go 闸门`，再发送 `go`，重点确认第一句台词是否在闸门释放后快速开始，并查看 `workflow启动闸门: stage=released` 与 TTS 请求日志的时间差。
- 如果再次出现启动后直接退出，优先看终端是否有 `Permission denied`，并确认脚本打印的 workflow 日志路径应位于 `logs/nav_workflow_control/rabbitbot_workflow_*.log`，不应再位于 `logs/unified_runtime`。
- 如果机器人已在点位5但主脚本显示正在等待 `go`，新版本允许直接发送 `back` 进入返航；旧运行实例不会具备该能力，需要重启 `start_nav_bridge_workflow_loop.sh` 后再试。
- 本轮确认最新 `start_nav_bridge_workflow_loop.sh` 已包含 `wait_go_or_back`：等待 `go` 阶段收到 `back` 会停止预启动 workflow 并直接执行 `return_to_start`，因此无需再增加“接近点位5才接收 back”的额外判断；当前未发现该编排脚本仍在运行。
- 本轮复查 2026-06-03 15:02 左右 back 不返航的新日志：脚本已经收到 `back` 并进入分段返航，但第一段目标发给 28180 时使用了 7 元组 `(x,y,z,ox,oy,oz,ow)`；28180 直接接口按 6 元组 `(x,y,ox,oy,oz,ow)` 解析，导致 `z=-0.1921` 被当成 `q_x`，姿态参数整体错位，底层导航返回 `Failed to obtain the current pose information`，机器人停在点位5不动。
- 本轮已将 `start_nav_bridge_workflow_loop.sh` 中直接发给 28180 的返航点位改为 6 元组，并新增 `normalize_go_to_task` 兼容转换：如外部环境变量仍传入 7 元组，会自动去掉 z 并打印 `任务格式已兼容转换` warning。
- 本轮按现场最新要求调整 back 返航路径：收到 back 后按 `原点位5 -> 返回点1 -> 返回点2 -> 点位1` 导航；返回点1 为 `(6.4327, 8.2585, 0.0505, 0.0827, 0.5996, -0.7944)`，返回点2 为 `(9.8023, -3.1366, -0.0442, 0.0674, 0.9944, 0.0684)`，均为 28180 直接接口使用的六元组格式。
- 本轮同步更新 `docs/直接导航命令.txt`，明确直接调用 28180 `/go_to_async` 使用 `(x, y, ox, oy, oz, ow)`，不包含 z。
- 如需现场修改称呼，直接改当前选中台词文件的 `variables.leader_calling`；如需修改台词，改对应 `opening` 键或 `steps[].segments[].text`。修改后重启 workflow 让进程重新读取台词文件。
- `conf/dialogue_<序号>.json` 文件已被 Git 忽略；新增或修改现场台词后不会出现在 `git status` 中。如需提交其它配置文件，请避免使用 `dialogue` 前缀。
- 完整跑完 DOCX 剧本后，确认终端出现 `DOCX 剧本总耗时`，并检查耗时是否覆盖开场第一句到最后一句“各位再会！”结束后的剧本完成时刻。
- 真机复测点位5时，重点听“移步门外，乘坐无人驾驶小巴车深入了解我们园区”是否已经作为同一段连续播报，确认没有明显句间停顿。
- 修改 `variables.leader_calling` 后需要重启 workflow；台词文件会在 workflow 进程内缓存，同一个进程运行期间不会自动热更新。
- 如需新增其它台词，复制 `conf/dialogue_0.json` 为 `conf/dialogue_1.json`、`conf/dialogue_2.json` 等并修改内容，再用 `RABBITBOT_DIALOGUE_INDEX=1` 或 `RABBITBOT_DIALOGUE_INDEX=2` 启动 workflow。
- 继续确认 dialogue01 中“上前靠近领导A一步”是否已有机器人动作或底盘接口；当前本轮未实现该靠近动作。
- 继续按上一轮建议清理重复 `entity` 字段。
- 明确是否有 OK 手势动作字段；如果有，再把点咖啡后的 `right_hand_up` 改为 OK 动作。

## 注意事项

- 默认 TTS 后端现在是 `unitree`，默认音量是 `100`；如需回退 Orin 本地外接音箱，需要显式设置 `RABBITBOT_TTS_BACKEND=local`。
- 当前 TTS 运行状态需现场恢复：上一轮重启 TTS 时 BT67 从 Orin 声卡列表消失，当前 `http://127.0.0.1:28185/docs` 返回 `000`，`/proc/asound/cards` 仅剩 HDA/APE；需重新插拔或恢复 BT67 后再启动 TTS。
- `send_delivery_task.py` 已纳入版本管理；默认模板 ID 保持现场已验证可用的 `delivery_1780402103401`，如 AIR 咖啡车任务模板变更，应优先通过脚本 `--template-id` 或 workflow 的 `RABBITBOT_COFFEE_DELIVERY_COMMAND` 覆盖后再固化。
- 上一轮观察到的旧容器 `RABBITBOT_UNITREE_TTS_VOLUME=85` 已不再是当前运行状态；当前默认 Unitree 音量仍为 `100`，但使用 `RABBITBOT_TTS_BACKEND=local` 时 Unitree 音量配置不参与本地外接音响播放。
- Unitree 本体 TTS 当前通过 C++ 桥接程序发命令，不依赖 Python 版宇树 SDK。
- unified 创建容器和容器内启动 TTS 时会打印后端、Unitree 网卡和音量，方便排查是否仍沿用旧容器或旧音量。
- unified 入口现在会在 workflow 启动时打印 workflow 进程组 PGID；按 `^C` 时应看到“收到 INT 信号，正在停止 workflow 进程组”和最终停止完成日志。如仍有残留，应优先按日志中的 PGID 排查。
- 新的 `^C` 清理逻辑只覆盖 `scripts_1/unified_runtime/start_unified_container.sh` 的 `start_workflow()` 路径；如果现场直接执行旧式 `docker exec ... bash scripts/start_kuavo_agno_workflow.bash | tee`，仍会绕过该 trap，需要改用 unified 入口或同步改造外部启动命令。
- 联调脚本和非联调脚本顶部的 workflow 环境变量速查注释需与 `workflow.py` 中对应注释保持同步；后续新增运行变量时应同步更新三处说明。
- `start_nav_bridge_workflow_loop.sh` 会独占启动 28180 导航桥接；如果 28180 已被旧桥接或其它服务占用，脚本会退出，不会自动 kill 旧进程。
- `start_nav_bridge_workflow_loop.sh` 默认使用 `/home/unitree/test1.pcd`；如果现场切回其它地图，可用 `NAV_PCD_PATH=/path/to/map.pcd bash scripts_1/start_nav_bridge_workflow_loop.sh` 覆盖。
- `start_nav_bridge_workflow_loop.sh` 运行期间如果提前发送 `back`，新版本会排队到 workflow 完成后返航；旧版本实例不会热更新，需重启脚本后才具备该能力。
- 严格 DOCX 剧本完成后现在默认不进入剧本后问答；现场本地忽略文件 `examples/run_kuavo_agno.py` 也默认不播报“流程测试完成”，如确需恢复结束播报，可临时设置 `RABBITBOT_WORKFLOW_FINISH_SPEECH=1`。
- 不建议用 `sudo` 启动 `start_nav_bridge_workflow_loop.sh`；sudo 会切换 Python 用户包和部分 ROS 环境，容易出现 `uvicorn` 或 ROS 动态库找不到的问题。
- `start_nav_bridge_workflow_loop.sh` 的返航现在是分段路径，默认顺序为 `3->5过渡点位 -> 点位3 -> 点位2 -> 1->2过渡点位 -> 点位1`；点位可分别通过 `RABBITBOT_NAV_WORKFLOW_POINT_3_TO_5_TRANSITION`、`RABBITBOT_NAV_WORKFLOW_POINT_3`、`RABBITBOT_NAV_WORKFLOW_POINT_2`、`RABBITBOT_NAV_WORKFLOW_POINT_1_TO_2_TRANSITION`、`RABBITBOT_NAV_WORKFLOW_POINT_1` 覆盖，最终点位1仍可用 `RABBITBOT_NAV_WORKFLOW_START_POINT` 兼容覆盖。返航状态通过 28180 `/go_to_status` 轮询，`status=3` 视为当前分段成功。
- `start_nav_bridge_workflow_loop.sh` 的 `go` 现在使用预启动闸门：可用 `RABBITBOT_NAV_WORKFLOW_GATE_READY_TIMEOUT_SECONDS` 调整等待预启动就绪超时，用 `RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS` 调整 workflow 内部闸门轮询间隔，用 `RABBITBOT_NAV_WORKFLOW_STATUS_POLL_SECONDS` 调整 workflow 运行期间状态和 back 预接收轮询间隔。
- `logs/unified_runtime` 当前由 root 拥有，普通用户不要在宿主侧直接写该目录；新的导航 workflow 编排运行日志和闸门控制文件默认放在 `logs/nav_workflow_control`，避免再次触发权限退出。
- 新版本中 workflow 预启动的 `ready/go/status/pid/exit_code` 都应位于 `logs/nav_workflow_control/workflow_control`；如果只看到 ready 而没有 status/pid，应优先检查是否仍在运行旧脚本实例或旧环境变量。
- 直接调用 28180 `/go_to_async` 与 workflow 内部点位格式不同：workflow `DOCX_SCRIPT_POINTS` 仍保留 `z`，但 curl 直接接口和 `start_nav_bridge_workflow_loop.sh` 返航目标应使用六元组；如果导航日志里出现 `q_x` 等于原 z 值，说明又发生了 7 元组误传。
- back 返航路径现在有 4 段：`原点位5 -> 返回点1 -> 返回点2 -> 点位1`；如需现场微调返回点，可覆盖 `RABBITBOT_NAV_WORKFLOW_BACK_POINT_1` 和 `RABBITBOT_NAV_WORKFLOW_BACK_POINT_2`。
- DOCX 后台命令日志会记录命令解析来源、启动 PID、超时时间、退出码、耗时、stdout/stderr 摘要，可用于排查 AIR 咖啡车接口是否被调用以及返回结果。
- `send_delivery_task.py` 现在会向 stderr 记录 AIR 咖啡车接口请求开始、HTTP 状态、耗时、返回字节数、运行任务 ID 以及失败原因；workflow 捕获后台命令 stderr 后可直接辅助定位网络、接口或模板问题。
- DOCX 剧本计时日志会在终端打印 `DOCX 剧本总计时开始` 和 `DOCX 剧本总耗时`，用于现场快速确认整段流程耗时。
- 当前 DOCX 剧本不再包含“第一次来园区”和“是否送咖啡饮料”的 STT 问答等待；如后续再恢复问答，需要重新配置 `listen_key`/`early_listen` 并验证监听超时。
- 当前 `拿取咖啡` 场景不再包含合作成果介绍台词；如后续要恢复相关内容，需要先确认正式文案，再重新加入独立播报 segment。
- `workflow.py` 现在只保留流程结构和台词文件加载/校验逻辑；六月六日 DOCX 导览具体台词应优先维护 `conf/dialogue_<序号>.json`，不要再直接写回 `DOCX_SCRIPT_STEPS`。
- 如果再次启动 `start_nav_arm_bridge.sh` 仍提示 28180 被占用，应优先现场复查当时的 `ss -ltnp "sport = :28180"` 输出；本轮结束旧桥接进程后该端口已经为空。
- 如果在容器内使用宿主机构建的桥接程序，`UnitreeG1TTS` 会自动设置 `LD_LIBRARY_PATH` 到 `/workspace/projects/unitree_sdk2/thirdparty/lib/aarch64` 或宿主机对应路径。
- 如果现场觉得伸手过早或动作时长影响话筒交接，可优先检查动作日志中的 `action=shake_hand` 耗时和随后的 `release` 耗时。

## 其它信息

如需同步到 `feature/unified-runtime-image`，可 cherry-pick 本轮提交。

## 本轮补充：旧日志归档

- 本轮已归档旧日志：将早于 2026-06-04 且未被进程打开、非 `latest` 链接、非 `latest` 目标的历史日志移动到 `logs/archive_20260604_083348_old_logs`。
- 当前正在写入的 `logs/nav_workflow_control/nav_bridge_20260604_083009.log` 保持原位；今天日志和无日期服务日志保持原位。
- 本轮归档前通过 `/proc/*/fd` 核实当前打开的项目日志；归档后复查当前打开日志仍在原路径。
- 旧日期日志剩余项仅为 `logs/unified_runtime/rabbitbot_workflow_20260603_144523.log`，该文件是 `rabbitbot_workflow_latest.log` 的目标文件，故保留以避免破坏 latest 链接。
- 归档目录内包含 `ARCHIVE_MANIFEST.txt` 和 `ARCHIVE_MANIFEST_ROOT.txt`，分别记录普通用户权限和容器 root 权限归档的文件清单。

## 本轮补充：workflow 开场后提前退出原因

- 本轮定位 2026-06-04 08:46 左右 workflow 提前退出：run_id 为 `20260604_084641`，退出码为 `1`，不是剧本正常结束。
- 直接原因是第三句开场欢迎语“各位朋友，也欢迎你们！”调用 TTS 时失败；workflow 日志中 `tts_index` 为空，旧逻辑随后执行 `int('')` 抛出 `ValueError`，loop 看到 workflow finished 后进入等待 `back` 阶段。
- TTS 服务端根因日志显示 Unitree G1 本体 TTS 桥接在该句执行 `SetVolume(100)` 时返回 `ret=3104`，随后 HTTP 返回 500；前两句 TTS 均正常返回。
- 本轮已修复 `rabbitbot/audio/unitree_g1_tts.py`：默认只在首次 Unitree TTS 请求时设置音量；如果设置音量失败或机器人音频服务忙，会记录 `tts_request_retry_without_volume` 并保留当前音量重试播报。
- 本轮已修复 `rabbitbot/tools/sound_agno.py`：当 TTS 返回空值或非法索引时记录 `workflow_tts_request_invalid_response`，并抛出带上下文的 `RuntimeError`，避免后续只看到难以定位的 `ValueError`。
- 已验证：Python 源码编译检查通过；模拟桥接返回验证第一句带 `--volume`、第二句不带；模拟 `SetVolume` 失败验证会不带音量重试并返回成功索引。
- 额外状态：复查时 `rabbitbot-unified-runtime` 容器已退出，Docker 状态为 `ExitCode=137`、`OOMKilled=false`，28185 TTS 端口不再监听；本轮未重新拉起容器或 workflow。

## 本轮补充：TTS 失败不再终止 workflow

- 本轮确认：上一版修复后，如果 Unitree TTS 重试后仍失败，`tts_sound` 仍可能抛出异常并导致 workflow 退出，这不满足现场导览“不能因单句 TTS 失败中断”的要求。
- 本轮已将 `rabbitbot/tools/sound_agno.py` 的 TTS 工具层改为默认可恢复：`text_to_speech` 异常、空 `tts_index`、非法 `tts_index`、`wait_speech` 异常、`get_wav_count/get_play` 异常都会记录 `TTS请求链路` 日志并返回可继续的默认值。
- 默认策略：单句 TTS 失败返回 `tts_index=-1`，后续台词和导航继续执行；与失败 TTS 绑定的动作会跳过，避免等待不存在的播放索引。
- 新增 `RABBITBOT_TTS_STRICT_FAILURE` 开关：默认 `0`，表示 TTS 失败只记录并继续；设为 `1/true/yes/on` 时恢复严格模式，把 TTS 失败视为致命错误。
- 已将 `RABBITBOT_TTS_STRICT_FAILURE` 写入 workflow、联调/非联调 unified 脚本和导航 loop 脚本注释；`start_nav_bridge_workflow_loop.sh` 和 `start_unified_integration_workflow.sh` 已透传该变量到容器内 workflow。
- 已验证：Python 源码编译检查通过，三个启动脚本 `bash -n` 通过；模拟 TTS 空返回、TTS 抛异常、等待失败、队列查询失败、非法 TTS 索引时均不会抛出到 workflow。

## 本轮补充：导航 workflow loop 系统服务

- 本轮新增 `scripts_1/systemd/rabbitbot-nav-workflow-loop.service`，用于将 `scripts_1/start_nav_bridge_workflow_loop.sh` 注册为 systemd 服务。
- 已将服务安装到 `/etc/systemd/system/rabbitbot-nav-workflow-loop.service`，并执行 `systemctl daemon-reload`。
- 已执行 `systemctl enable rabbitbot-nav-workflow-loop.service`，服务会在下次开机进入待命；本轮没有执行 `systemctl start`，因此没有启动第二个 loop 实例。
- 安装后验证：`systemctl status rabbitbot-nav-workflow-loop.service` 显示 `Loaded: enabled`、`Active: inactive (dead)`；当前手动运行的 `start_nav_bridge_workflow_loop.sh` 进程仍在，未被中断。
- 服务以 `pc` 用户运行，工作目录为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，异常退出时 `Restart=on-failure`，重启间隔 5 秒。
- 常用操作：启动 `sudo systemctl start rabbitbot-nav-workflow-loop.service`；停止 `sudo systemctl stop rabbitbot-nav-workflow-loop.service`；重启 `sudo systemctl restart rabbitbot-nav-workflow-loop.service`；查看日志 `journalctl -u rabbitbot-nav-workflow-loop.service -f`；取消开机自启 `sudo systemctl disable rabbitbot-nav-workflow-loop.service`。

## 本轮补充：系统服务重命名

- 本轮按现场要求将系统服务名从 `rabbitbot-nav-workflow-loop.service` 改为 `rabbitbot-loop.service`。
- 项目内服务模板同步重命名为 `scripts_1/systemd/rabbitbot-loop.service`，`SyslogIdentifier` 改为 `rabbitbot-loop`。
- 操作策略为先安装并启用新服务，再禁用并移除旧服务；全程没有执行 `systemctl start`，当前手动运行的 loop 进程未被中断。
- 新服务常用命令：`sudo systemctl start rabbitbot-loop.service`、`sudo systemctl stop rabbitbot-loop.service`、`sudo systemctl restart rabbitbot-loop.service`、`systemctl status rabbitbot-loop.service`、`journalctl -u rabbitbot-loop.service -f`。

## 本轮补充：systemd 下 go 不触发机器人移动原因

- 本轮定位 systemd 服务状态下发送 `send_nav_workflow_command.sh go` 后机器人不动：`rabbitbot-loop.service` 实际运行正常，导航桥接和统一容器基础服务均已启动，28180/28185/28184/28182 端口可用。
- 直接原因不是 go 命令未送达；日志显示 2026-06-04 15:35:52 已收到 `go` 并释放 workflow 闸门。
- workflow 随后立刻异常退出，run_id 为 `20260604_153323`，退出码为 `1`；根因是 systemd 默认环境没有设置台词序号，loop 脚本向容器透传了空字符串 `RABBITBOT_DIALOGUE_INDEX=''`，旧逻辑把空字符串视为非法序号而不是默认 0。
- workflow 异常退出后，loop 进入“等待 `back` 返回起点”阶段，因此后续再次发送 `go` 会被日志明确记录为 `当前阶段需要 back，忽略命令：go`。
- 本轮已修复 `rabbitbot/agno_agents/workflow.py`：`RABBITBOT_DIALOGUE_INDEX` 为空时视为未设置，继续读取旧变量 `RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX`；两个都为空时默认使用 `dialogue_0.json`。非法非数字序号仍会记录两个环境变量和最终生效值后报错。
- 已验证：Python 源码编译检查通过；空 `RABBITBOT_DIALOGUE_INDEX` 和空旧变量返回默认序号 `0`；显式 `RABBITBOT_DIALOGUE_INDEX=3` 返回 `3`；非法 `abc` 仍报 `DOCX 导览台词序号必须是数字`。
- 注意：当前正在运行的服务实例已经处于等待 `back` 阶段，本轮未自动发送 `back`、未重启服务、未中断现有 loop。要恢复现场可先发 `back` 完成本轮，或在确认安全后 `sudo systemctl restart rabbitbot-loop.service` 重新进入待命。

## 本轮补充：关闭 rabbitbot-loop 开机自启

- 本轮按现场要求将 `rabbitbot-loop.service` 设为不开机自启：已执行 `systemctl disable rabbitbot-loop.service`，并移除 `multi-user.target.wants` 下的启用链接。
- 已执行 `systemctl reset-failed rabbitbot-loop.service` 清理此前 TERM 退出留下的 failed 标记；最终状态验证为 `disabled / inactive (dead)`。
- 本轮没有执行 `systemctl start rabbitbot-loop.service`，系统服务不会在当前会话自动启动，也不会在下次开机自动启动。
- 复查发现 2026-06-04 15:39:22 有新的手动 `start_nav_bridge_workflow_loop.sh` 实例在运行，父进程不是 systemd；本轮未停止该手动实例。
- 如后续需要重新启用开机自启，可执行 `sudo systemctl enable rabbitbot-loop.service`；只临时启动则执行 `sudo systemctl start rabbitbot-loop.service`。

## 本轮补充：开场欢迎后长延迟定位

- 本轮只读排查 2026-06-05 运行中“各位朋友，也欢迎你们！”之后长时间停顿的问题，未修改代码。
- 最近几轮对比显示异常集中在 `logs/nav_workflow_control/rabbitbot_workflow_20260605_115910.log`：该轮 `face_wave` 动作耗时 `24.048s`，到下一句“各位领导，各位，请随我来...”开始间隔 `24.249s`；其它相邻轮次同一动作约 `4.1s`、到下一句约 `4.3s`。
- workflow 日志显示 TTS 请求本身正常：该句 TTS `elapsed=0.346s`，随后 `wait_speech` 约 3 秒完成；长延迟发生在等待并发动作 `face_wave` 的 action 线程 join。
- 导航桥接日志 `logs/nav_workflow_control/nav_bridge_20260605_115805.log` 显示 `/do_arm_async task=face_wave` 的 `goal_response=22.02ms`，但 `wait_result=24012.32ms`，说明 HTTP 和 ROS goal 接收很快，卡在等待手臂 action 结果。
- 手臂 action server 日志 `/mnt/ssd/navgation/projects/unitree_slam_example_new/example/run_logs/nav_arm_bridge_20260605_115806/02_g1ArmOfficialActionServer.log` 显示 `face_wave` 接收后约 20 秒才打印 `Executing official action [face_wave] at fsm_id=-1 fsm_mode=-1`，最终 `receive_to_success=23997.30ms`。
- 结合 `g1_arm_official_action_server.cpp` 执行顺序，`Executing official action` 之前会调用 `GetFsmId` 和 `GetFsmMode`；本轮推断约 20 秒耗在这两个 Unitree 状态查询超时/失败上，之后 `face_wave` 本体动作约 4 秒完成。
- 结论：该次长延迟不是 TTS 合成或播放导致，也不是导航目标导致，而是手臂官方动作服务在执行 `face_wave` 前查询机器人 FSM 状态异常超时。后续若要修复，可考虑减少/跳过动作前 FSM 查询、给查询单独加短超时，或让 workflow 对开场并发动作设置最大等待时间。

## 本轮补充：stop 脚本增强宿主机清理

- 本轮增强 `scripts_1/stop_unified_workflow.sh`，使其除停止统一容器 workflow 和容器内后台服务外，还会清理宿主机导航、手臂动作服务和 `28180` bridge。
- 新增宿主机清理顺序：先停止 `start_nav_bridge_workflow_loop.sh` 进程组，让 loop 自身 trap 清理；再停止 `start_nav_arm_bridge.sh`；最后按明确进程名兜底清理 `goGoalNavigation66`、`g1ArmOfficialActionServer`、`humble_robot_agent_bridge:app` 和导航日志 tail。
- 新增 pid 文件兜底清理：扫描 `/mnt/ssd/navgation/projects/unitree_slam_example_new/example/run_logs` 下历史启动脚本记录的 `.pid` 文件，并在命令行匹配预期进程名时才停止，避免 PID 复用导致误杀。
- 新增清理日志：脚本会打印每类宿主机进程的发现/停止情况、PID、命令行、强制停止原因，以及最终 `28180` 端口是否释放，便于排查停止不彻底的问题。
- 已验证 `bash -n scripts_1/stop_unified_workflow.sh` 通过；本轮未实际执行 stop 脚本，避免中断现场可能存在的服务。
- 当前已知未跟踪文件仍为 `conf/dialogue_1500.json`、`conf/dialogue_1600.json`、`conf/dialogue_2000.json`，本轮未处理这些现场台词文件。

## 本轮补充：增强导航 workflow loop 健壮性

- 本轮增强 `scripts_1/start_nav_bridge_workflow_loop.sh`，目标是在后续做成 systemd 开机服务前，先提升长期待命和异常恢复能力。
- 新增运行时健康检查配置：
  - `RABBITBOT_NAV_WORKFLOW_HEALTH_CHECK_INTERVAL_SECONDS`：等待命令和 workflow 运行期间的健康检查间隔，默认 5 秒。
  - `RABBITBOT_NAV_WORKFLOW_LOST_PROCESS_GRACE_SECONDS`：workflow 进程丢失但状态文件未落盘时的宽限时间，默认 5 秒。
  - `RABBITBOT_NAV_WORKFLOW_NAV_RESTART_WAIT_SECONDS`：重启导航桥接前等待时间，默认 3 秒。
  - `RABBITBOT_NAV_WORKFLOW_BACK_RETRY_LIMIT`：返航失败后自动恢复导航桥接并重试的次数，默认 1。
  - `RABBITBOT_NAV_WORKFLOW_RETURN_FAILURE_WAIT_SECONDS`：返航失败恢复间隔，默认 2 秒。
- 新增基础服务健康检查：定期检查 unified 容器、Neo4j `7687`、TTS `28185`、STT `28184` 和 Memory `28182`；如果基础服务不健康，会记录失败项并尝试通过统一入口恢复，运行中容器不健康时会先重启容器。
- 新增导航桥接健康检查：检查本脚本启动的导航桥接进程组、`28180` 端口和 `/go_to_status` 状态接口；失败时会记录具体原因并可重启导航桥接。
- 等待 `go/back` 阶段如果健康检查失败，会停止当前预启动 workflow，恢复基础服务或导航桥接后重新预启动，避免旧 ready 状态卡住。
- 等待普通 `back` 命令阶段也会做周期性健康检查，避免 workflow 已结束但返航前服务已经下线。
- workflow 运行期间如果健康检查失败，只记录并等待 workflow 自身收敛，不在导览过程中主动重启服务，避免中途干扰导航或播报。
- workflow 运行期间如果状态文件仍为 `running`，但当前 run 的 workflow 进程已经丢失，超过宽限时间后会写入 `exit_code=127`、`finished_at` 和 `status=finished`，避免 loop 无限等待。
- 返航失败不再直接让脚本因 `set -e` 退出；脚本会按重试上限恢复导航桥接并重试，超过上限后保持返航阶段，等待现场确认后再次发送 `back` 重试。
- workflow 预启动命令发送失败现在会进入恢复分支，不再直接退出 loop。
- 新增和调整的日志点覆盖：健康检查失败项、运行阶段、服务恢复原因、导航桥接重启原因、workflow 进程丢失宽限时间、异常状态落盘、返航失败分段、自动重试次数和返航重试等待。
- 已验证：`bash -n scripts_1/start_nav_bridge_workflow_loop.sh` 通过，`git diff --check` 通过。
- 本轮未启动 `start_nav_bridge_workflow_loop.sh`，未启动 systemd 服务，未发送 `go/back` 命令，未触发机器人移动或播报。
- 当前仍未处理现场未跟踪台词文件：`conf/dialogue_1500.json`、`conf/dialogue_1600.json`、`conf/dialogue_2000.json`。
- 下一步建议：更新并启用 `rabbitbot-loop.service` 前，先用当前脚本做一次短时手动启动验证，确认只进入待命；再验证 `go`、workflow 完成、`back` 和异常恢复路径。

## 本轮补充：台词 JSON 增加地图和点位配置

### 背景和目标

本轮目标是按现场要求调整 `conf/dialogue_<序号>.json` 台词配置：在台词文件中记录当前使用的地图文件名，并把 DOCX 严格剧本点位列表从 workflow 代码侧抽到台词 JSON 中；workflow 需要优先使用台词文件中的点位，同时保留旧代码点位作为兜底。

### 当前状态

已完成：

- 已在 `conf/dialogue_0.json`、`conf/dialogue_1.json`、`conf/dialogue_2.json`、`conf/dialogue_3.json` 顶层新增 `map_file`，当前值为 `test1.pcd`。
- 已在上述 4 个台词 JSON 顶层新增 `points`，包含 `point_1`、`point_1_to_2_transition`、`point_2`、`point_3`、`point_4`、`point_3_to_5_transition`、`point_5` 共 7 个点位。
- 已将点位条目统一为 `name`、`summary`、`description`、`location` 结构；`location` 中包含 workflow 使用的 `x/y/z/ox/oy/oz/ow/mode` 字段。
- 已适配 `rabbitbot/agno_agents/workflow.py`：加载台词 JSON 时会读取并校验 `map_file` 和 `points`；DOCX 严格剧本步骤解析 `entity_key` 时优先使用台词文件点位。
- 已保留 `DOCX_SCRIPT_POINTS` 代码兜底：如果台词文件没有配置对应点位，workflow 仍会尝试使用旧的代码内点位。
- 已更新 `conf/README.md`，说明 `map_file`、`points`、点位字段和重启 workflow 后生效的要求。

未完成：

- 本轮未启动 systemd 服务、导航桥接或 workflow，未进行真机移动验证，避免影响现场运行。
- `map_file` 当前用于配置记录和日志排查；导航桥接实际加载的地图仍由 `NAV_PCD_PATH` 控制，现场需要确认两者一致。

### 已验证的事实

- `conf/dialogue_0.json` 到 `conf/dialogue_3.json` 均可通过 `python3 -m json.tool` 解析。
- 4 个台词 JSON 均已通过结构校验：`map_file=test1.pcd`，每个文件 `points=7`，所有点位均包含完整 `x/y/z/ox/oy/oz/ow/mode` 坐标字段。
- `rabbitbot/agno_agents/workflow.py` 已通过 `python3 -m py_compile` 语法检查。
- `git diff --check` 已通过。

### 阻塞问题

无代码层面的阻塞。剩余风险是运行层面尚未实测：需要在重启 workflow 后确认台词文件点位被正确加载，并确认 `NAV_PCD_PATH` 与台词文件 `map_file` 指向同一张地图。

### 建议的下一步

- 重启 workflow 或 `rabbitbot-loop.service` 后观察日志中 `DOCX 导览台词文件加载完成`，确认 `map_file=test1.pcd`、`points=7`。
- 发送 `go` 前确认导航桥接启动参数中的 `NAV_PCD_PATH` 仍为 `/home/unitree/test1.pcd` 或其它与台词 `map_file` 一致的路径。
- 真机完整跑一遍 DOCX 严格剧本，重点观察各 `entity_key` 对应的点位是否从台词 JSON 加载，并确认返航和过渡点行为没有回退到旧配置。

### 注意事项

- 台词 JSON 修改后需要重启 workflow；当前 workflow 会缓存台词配置，同一进程内不会自动热更新。
- 若现场新增台词文件，应复制现有 `dialogue_<序号>.json` 并保留 `map_file` 与完整 `points` 结构，否则 workflow 可能回退到代码内旧点位或在配置校验阶段报错。
- 坐标校验会在点位加载阶段报出文件路径、点位 key、location 序号和缺失/非法字段，便于快速定位台词文件配置错误。

### 其它信息

- 本轮新增/调整的日志点包括：台词文件加载完成时输出 `map_file` 和 `points` 数量；点位加载时输出使用台词文件配置或代码兜底配置、点位名、坐标数量和地图文件名。
- 这些日志用于区分导航失败时到底是台词文件点位未生效、回退到了代码兜底，还是地图文件与导航桥接实际加载地图不一致。

## 本轮补充：dialogue_1 切换 test9 点位

### 背景和目标

本轮目标是按现场提供的 test9 地图点位，更新 `conf/dialogue_1.json` 中 DOCX 严格剧本实际使用的导航点位。现场已先将该台词文件的地图字段改为 `test9.pcd`，本轮保留该配置并更新对应点位坐标。

### 当前状态

已完成：

- 已确认 `conf/dialogue_1.json` 当前 `map_file` 为 `test9.pcd`。
- 已更新 `point_1_to_2_transition`、`point_2`、`point_3`、`point_3_to_5_transition`、`point_5` 的 `location` 坐标为 test9 图提供值。
- 已确认 `dialogue_1.json` 当前 steps 实际引用上述 5 个点位；未提供新坐标且未被 steps 引用的 `point_1`、`point_4` 本轮未改动。
- 已保留 `dialogue_1.json` 当前已有称呼配置 `variables.leader_calling=各位领导`。

未完成：

- 本轮未启动 workflow、导航桥接或 systemd 服务。
- 本轮未进行真机导航验证。

### 已验证的事实

- `conf/dialogue_1.json` 已通过 `python3 -m json.tool` JSON 格式校验。
- test9 的 5 个点位均已通过字段完整性校验，包含 `x/y/z/ox/oy/oz/ow/mode`。
- `rabbitbot/agno_agents/workflow.py` 已通过 `python3 -m py_compile` 语法检查。

### 阻塞问题

无代码层面阻塞。剩余风险是运行层面尚未验证：需要启动 workflow 后确认日志加载 `dialogue_1.json`、`map_file=test9.pcd`，并确认导航桥接实际使用 test9 对应地图。

### 建议的下一步

- 使用 `RABBITBOT_DIALOGUE_INDEX=1` 或等效配置启动 workflow，确认实际选中 `dialogue_1.json`。
- 启动导航桥接前确认 `NAV_PCD_PATH` 指向 test9 对应地图文件。
- 真机按完整 DOCX 严格剧本跑一遍，重点验证 `1到2过渡`、点位2、点位3、`3到5过渡` 和点位5 的到点精度。

### 注意事项

- `dialogue_1.json` 的 `point_1` 和 `point_4` 坐标仍保留旧值；当前 steps 未引用它们。如后续剧本增加引用或现场需要完整 test9 点位表，应补充这两个点位的新坐标。
- 台词 JSON 修改后需要重启 workflow 才会重新加载。

## 本轮补充：排查 workflow 启动后机器人未移动

### 背景和目标

本轮目标是排查现场刚启动 workflow 后机器人未移动的原因。现场使用 `dialogue_1.json`，该台词文件已配置 `map_file=test9.pcd` 和 test9 点位。

### 当前状态

已完成：

- 已查看最新运行日志：run_id 为 `20260609_110301`，导航桥接日志为 `logs/nav_workflow_control/nav_bridge_20260609_110145.log`，workflow 日志为 `logs/nav_workflow_control/rabbitbot_workflow_20260609_110301.log`。
- 已确认 workflow 侧加载的是 `dialogue_1.json` 的 test9 配置，日志显示 `map_file=test9.pcd`，点位来自台词文件。
- 已确认导航桥接实际启动时仍使用 `/home/unitree/test1.pcd`，与 `dialogue_1.json` 的 `test9.pcd` 不一致。
- 已确认第一段导航请求已发出，目标为 test9 的 `1->2过渡点位`：`x=0.1797, y=-0.1793, ox=0.0022, oy=0.1118, oz=0.0196, ow=0.9935`。
- 已确认导航底层返回 `statusCode=4`、`errorCode=4`、`info=Failed to obtain the current pose information.`，机器人因此没有开始移动，workflow 随后一直轮询到 `status=1, sub=navigating`。
- 已修复 `scripts_1/start_nav_bridge_workflow_loop.sh`：如果未显式设置 `NAV_PCD_PATH`，脚本会从当前台词 JSON 的 `map_file` 自动推导导航地图路径；例如 `RABBITBOT_DIALOGUE_INDEX=1` 会使用 `/home/unitree/test9.pcd`。
- 已保留显式覆盖能力：如果启动时设置了 `NAV_PCD_PATH`，脚本仍优先使用该显式路径。

未完成：

- 本轮未重新启动导航桥接、workflow 或 systemd 服务。
- 本轮未验证 `/home/unitree/test9.pcd` 在导航底层是否可成功重定位。
- 本轮未做真机移动复测。

### 已验证的事实

- `rabbitbot-loop.service` 当前为 `disabled / inactive`，本次不是 systemd 服务启动。
- 当前无 `start_nav_bridge_workflow_loop.sh`、workflow runner、`goGoalNavigation66` 或 28180 监听进程；28182、28184、28185 和 7687 基础服务端口仍在监听。
- 最新导航桥接启动日志显示使用 `/home/unitree/test1.pcd`，并在 test1 上重定位成功，当前位姿约为 `x=0.8586, y=0.1355`。
- 最新 workflow 日志显示加载 `dialogue_1.json` 的 `map_file=test9.pcd` 和 test9 点位。
- `bash -n scripts_1/start_nav_bridge_workflow_loop.sh` 已通过。
- `dialogue_1.json` 的 `map_file` 可解析为 `/home/unitree/test9.pcd`。

### 阻塞问题

无代码层面阻塞。剩余运行风险是：如果导航底层无法读取或重定位 `/home/unitree/test9.pcd`，机器人仍不会移动；需要现场用新脚本重新启动后观察导航桥接启动日志。

### 建议的下一步

- 重新启动 loop 时使用 `RABBITBOT_DIALOGUE_INDEX=1 bash scripts_1/start_nav_bridge_workflow_loop.sh`，不要额外设置旧的 `NAV_PCD_PATH=/home/unitree/test1.pcd`。
- 启动后先确认终端出现 `根据台词文件设置导航地图`，并显示 `map_file=test9.pcd, NAV_PCD_PATH=/home/unitree/test9.pcd`。
- 再确认导航桥接日志中 `Loading map` 和 `start relocation with map` 均为 `/home/unitree/test9.pcd`。
- 如仍出现 `Failed to obtain the current pose information`，优先检查 test9 地图是否可被导航底层读取、当前位置是否能在 test9 地图中完成重定位。

### 注意事项

- 台词文件 `map_file` 与导航桥接实际 `NAV_PCD_PATH` 必须一致；只修改台词 JSON 不会让旧版本脚本自动换地图。
- 新版本脚本只在 `NAV_PCD_PATH` 未显式设置时自动读取台词地图；显式设置仍会覆盖台词地图。
- 当前 workflow 状态文件仍显示 `20260609_110301.status=running`，但对应进程和 28180 已不存在，这是本次中途退出后的陈旧状态；重新启动新 run 时会生成新的 run_id。

### 其它信息

- 本轮新增日志点：loop 启动准备阶段会打印使用显式导航地图，或打印根据台词文件推导出的 `dialogue`、`map_file` 和最终 `NAV_PCD_PATH`。
- 该日志用于快速诊断台词点位与导航桥接地图是否一致。

## 本轮补充：禁用 STT 服务自动启动

### 背景和目标

当前 workflow 已不再需要 STT 语音识别服务（严格 DOCX 剧本已移除全部 STT 问答监听），现场要求 workflow 启动时不再自动拉起 STT 服务（28184），以减少资源占用和无关启动失败风险。

### 当前状态

已完成：

- 新增统一开关 `RABBITBOT_UNIFIED_START_STT`，默认 `0`（不启动 STT）；如确需启动，可显式设置 `RABBITBOT_UNIFIED_START_STT=1`。开关命名和接线方式与已有的 `RABBITBOT_UNIFIED_START_EMBEDDING` 保持一致。
- `scripts_1/unified_runtime/start_unified_container.sh`：新增开关默认值；`start_stt()` 顶部增加跳过守卫，开关非 `1` 时打印跳过日志并直接返回，不再启动 STT、不再等待 28184；同步更新文件头注释。
- `scripts_1/start_unified_integration_workflow.sh`：新增开关默认值与头部注释；基础服务等待阶段对 STT(28184) 改为条件等待，开关非 `1` 时打印跳过日志；`ensure_compatible_container` 新增 STT 开关比较项，开关变化时触发容器重建；docker run 时通过 `-e RABBITBOT_UNIFIED_START_STT` 透传到容器内。
- `scripts_1/start_nav_bridge_workflow_loop.sh`：新增开关默认值；基础服务健康检查 `base_services_health_ok` 中 STT(28184) 改为仅在开关为 `1` 时才检查，避免关闭 STT 后健康检查误判为不健康并触发误重启；调用集成脚本时透传 `RABBITBOT_UNIFIED_START_STT`。
- `scripts/start_all_services.sh`（旧版全量启动入口）：新增开关默认值；主流程 `start_stt` 调用改为条件执行，开关非 `1` 时打印跳过日志，避免 STT 从该旧入口回流。

未完成：

- 本轮只做脚本改造和静态检查，未在真机/容器中实际重启 workflow 验证（避免中断现场可能正在运行的服务）。

### 已验证的事实

- 已确认 workflow 不会因关闭 STT 服务而在初始化阶段失败：`rabbitbot/context.py` 中 `self.stt_agent = create_stt_agent()`，而 `rabbitbot/provider.py` 的 `create_stt_agent()` 仅构造 `STTAgent(host_url)` 对象、保存 URL，不在构造时连接 28184；STT 客户端为懒连接，只有真正触发监听时才请求服务，而严格 DOCX 剧本已不再触发监听。
- 4 个脚本均通过 `bash -n` 语法检查。
- 本轮补丁脚本对每处替换做命中次数断言（期望命中 1 次），全部精确命中：container 3 处、integration 7 处、navloop 3 处、all_services 2 处。

### 阻塞问题

无代码层面阻塞。当前运行中的容器若是在本次改动前创建并已启动 STT，本次脚本改动不会主动停止已在运行的 STT 进程；如需让已运行实例也不再有 STT，可用 `RECREATE_CONTAINER=1`（开关比较会因 STT 配置变化自动触发重建）重建容器，或手动停止 STT 进程。

### 建议的下一步

- 下次重启统一服务时无需额外设置即默认不启动 STT；如临时需要 STT，整链路设置 `RABBITBOT_UNIFIED_START_STT=1` 后再启动。
- 启动后确认终端出现 `RABBITBOT_UNIFIED_START_STT=0，跳过 STT` 日志，并确认 28184 未被监听、workflow 仍正常进入开场。

### 注意事项

- `RABBITBOT_UNIFIED_START_STT` 默认 `0`；该开关同时影响统一容器入口、联调编排脚本、导航 loop 健康检查和旧版全量启动脚本，四处行为一致。
- 关闭 STT 后，导航 loop 的基础服务健康检查不再包含 STT(28184)，因此 STT 缺失不会再触发健康检查失败或服务自动恢复。
- 本轮新增/调整日志点：四处启动路径在跳过 STT 时均打印 `RABBITBOT_UNIFIED_START_STT=0，跳过 STT ...` 或 `跳过等待 STT 服务 (28184)`，用于现场快速确认 STT 确实未启动且为预期行为。

## 本轮补充：back 返航点位支持台词文件配置

### 背景和目标

本轮目标是按现场要求让 `back` 返航点位也支持写入 `conf/dialogue_<序号>.json` 台词文件；如果台词文件没有显式配置返航点位，则导航 loop 按当前台词 `steps[].entity_key` 对应的 go 点位序列反向生成返航路线。

### 当前状态

已完成：

- 已在 `scripts_1/start_nav_bridge_workflow_loop.sh` 中新增 `read_dialogue_back_route()`，用于读取当前台词 JSON 的顶层 `back_points`。
- `back_points` 支持字符串数组引用 `points` 键，也支持对象数组直接写 `name` 和 `location`，或通过 `point_key` / `entity_key` 引用 `points`。
- 未配置或配置为空数组时，脚本会从 `steps[].entity_key` 提取 go 点位，去掉连续重复点位，再反向生成返航序列；如果 `points` 中存在 `point_1`，会补为最终起点。
- 返航发送给 28180 的坐标统一使用六元组 `(x, y, ox, oy, oz, ow)`，从台词 `location` 中自动忽略 `z` 和 `mode`。
- 如果读取台词返航配置失败，脚本会记录失败原因，并回退到原有环境变量返航点位 `POINT_5_TASK -> BACK_POINT_1_TASK -> BACK_POINT_2_TASK -> START_POINT_TASK`。
- 已更新 `conf/README.md`，说明 `back_points` 字段、两种配置写法、默认反序策略和 28180 六元组格式。

未完成：

- 本轮未启动导航桥接、workflow、systemd 服务或容器，未触发机器人移动。
- 本轮未在真机上验证实际 `back` 返航路径。

### 已验证的事实

- `bash -n scripts_1/start_nav_bridge_workflow_loop.sh` 通过。
- 使用当前 `conf/dialogue_1.json` 做只读解析验证时，未配置 `back_points` 会输出 `reverse_go_points`，路线为：点位5 -> 3->5过渡点位 -> 点位3 -> 点位2 -> 1->2过渡点位 -> 点位1。
- 使用临时台词 JSON 显式设置 `back_points=["point_5", "point_3", "point_1"]` 时，只读解析验证输出 `dialogue_back_points`，并按显式配置生成三段返航路线。

### 阻塞问题

无代码层面阻塞。剩余风险是运行层面尚未验证：需要现场重启新版本 loop 后发送 `back`，确认 28180 接收的目标点位、地图和机器人实际移动路线一致。

### 建议的下一步

- 如需自定义返航路线，可在当前台词 JSON 顶层增加 `back_points`，优先使用字符串数组引用 `points` 键，避免复制坐标造成 go/back 不一致。
- 现场重启 `scripts_1/start_nav_bridge_workflow_loop.sh` 后，观察返航开始日志中的 `source`、`dialogue`、`segments` 和 `route`，确认是 `dialogue_back_points` 还是 `reverse_go_points`。
- 真机验证时重点确认 `dialogue_1.json` / `test9.pcd` 下默认反序路线是否符合现场回程动线；如果默认反序不适合现场，可在 `dialogue_1.json` 中显式写 `back_points`。

### 注意事项

- `back_points` 修改后需要重启导航 loop 才会重新读取台词文件；已运行的旧 loop 实例不会热更新。
- 返航点位读取依赖台词文件 `points`，因此 `points` 中引用的 `location` 至少要有一组完整坐标。
- `back_points` 写错类型、引用不存在的 point key、坐标字段缺失或字段非数字时，脚本会记录错误并回退到原有环境变量兜底返航点。

### 其它信息

- 本轮新增/调整的日志点包括：返航开始时打印返航来源、台词文件路径、分段数和完整路线；读取台词返航配置失败时打印失败原因和兜底来源；最终目标日志打印最后一段返航目标。
- 这些日志用于排查现场到底使用了台词显式返航点、go 点位反序，还是因配置错误回退到了旧环境变量点位。

## 本轮补充：dialogue_fuxing 增加显式返航点位

### 背景和目标

本轮目标是按现场要求更新备份台词文件 `conf/dialogue_fuxing.json`：该文件由原始 0 号台词复制而来，用于复星原始路线备份；历史返航点位曾写在脚本环境变量中，但没有进入台词文件，本轮需要补入台词 JSON。

### 当前状态

已完成：

- 已在 `conf/dialogue_fuxing.json` 顶层新增 `back_points`。
- 返航路线配置为 `点位5 -> 返回点1 -> 返回点2 -> 点位1`。
- `返回点1` 坐标为 `(6.4327, 8.2585, 0.0505, 0.0827, 0.5996, -0.7944)`。
- `返回点2` 坐标为 `(9.8023, -3.1366, -0.0442, 0.0674, 0.9944, 0.0684)`。
- `点位5` 和 `点位1` 通过 `point_key` 引用台词文件已有 `points`，避免复制已有 go 点位坐标。

未完成：

- 本轮未启动 workflow、导航桥接、systemd 服务或容器。
- 本轮未发送 `go/back`，未触发机器人移动。

### 已验证的事实

- `python3 -m json.tool conf/dialogue_fuxing.json` 通过。
- 使用 `start_nav_bridge_workflow_loop.sh` 的 `read_dialogue_back_route` 只读解析 `conf/dialogue_fuxing.json`，输出来源为 `dialogue_back_points`，路线为点位5、返回点1、返回点2、点位1。
- `conf/dialogue_fuxing.json` 当前不被 Git 忽略，可纳入提交。

### 阻塞问题

无代码层面阻塞。剩余风险是运行层面尚未真机验证返航路线。

### 建议的下一步

- 如需使用该备份台词启动 workflow，设置 `RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE=/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/conf/dialogue_fuxing.json` 或容器内对应路径。
- 真机验证时观察返航开始日志，确认 `source=dialogue_back_points` 且路线为 `点位5 -> 返回点1 -> 返回点2 -> 点位1`。

### 注意事项

- `back_points` 修改后需要重启导航 loop 才会被新预启动 workflow/返航逻辑读取。
- 返回点1、返回点2是 28180 直接接口六元组格式，不包含 workflow go 点位中的 `z` 和 `mode`。

## 本轮补充：接手阅读与状态确认

### 背景和目标

本轮目标是按 Aaron 要求读取 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master/HANDOFF_REPORT.md`，接手当前 `rabbitbot-dev-ros2-master` 项目状态，并确认后续应优先关注的运行风险。

### 当前状态

已完成：

- 已完整读取当前交接报告，确认最近工作集中在导航 workflow loop、台词 JSON 点位配置、test9 地图切换、默认关闭 STT、返航路线支持台词配置，以及 `dialogue_fuxing.json` 显式返航点位。
- 已确认远端 Git 分支为 `June6_workflow`，读取前工作区干净。
- 已确认最新提交为 `dc398ae fix: ignore future log files in console status`。

未完成：

- 本轮未启动 workflow、导航桥接、systemd 服务或容器。
- 本轮未发送 `go/back`，未触发机器人移动或语音播报。
- 本轮未修改业务代码或运行脚本。

### 已验证的事实

- 交接报告中最新风险点仍是运行验证类风险：`dialogue_1.json` 的 `map_file=test9.pcd` 需要与导航桥接实际 `NAV_PCD_PATH=/home/unitree/test9.pcd` 保持一致。
- `RABBITBOT_UNIFIED_START_STT` 当前默认应为 `0`，严格 DOCX 剧本不依赖 STT 服务启动。
- `back_points` 已支持从台词 JSON 读取；未配置时会按 go 点位反序生成返航路线。
- `conf/dialogue_fuxing.json` 已配置显式返航路线：点位5、返回点1、返回点2、点位1。

### 阻塞问题

无接手层面的阻塞。本轮未进行真机或服务重启验证，因此运行层面的剩余风险仍以原交接报告记录为准。

### 建议的下一步

- 如需继续验证 test9 路线，优先使用 `RABBITBOT_DIALOGUE_INDEX=1 bash scripts_1/start_nav_bridge_workflow_loop.sh`，并确认日志打印 `map_file=test9.pcd` 和 `NAV_PCD_PATH=/home/unitree/test9.pcd`。
- 如需验证返航，重启新版本 loop 后观察返航开始日志中的 `source`、`dialogue`、`segments` 和 `route`，确认实际使用台词显式返航点或 go 点位反序路线。
- 如需让当前运行实例关闭 STT，需要重建容器或手动停止旧 STT 进程；脚本改动不会热更新已运行容器。

### 注意事项

- 本轮只进行了只读接手和交接报告更新；没有更改日志逻辑、服务配置或台词内容。
- 后续任何台词 JSON、地图、导航脚本或服务启动逻辑变更后，仍需同步更新本交接报告并提交。

### 其它信息

- 本轮没有新增或调整代码日志点；仅确认已有交接报告中记录的关键日志点，包括台词文件地图/点位加载日志、导航 loop 地图推导日志、返航来源与路线日志、STT 跳过日志。

## 本轮补充：移动硬盘迁移包准备

### 背景和目标

本轮目标是按 Aaron 要求，为将当前 AGX-orin 上的 RabbitBot 项目迁移到另一台 `HaiSong-orin` 做离线迁移准备。由于网络传输慢，迁移策略改为先在 AGX-orin 本机生成可搬运的 tar 迁移包，再通过移动硬盘带到目标机恢复。

### 当前状态

已完成：

- 已确认 `rabbitbot-unified-runtime:20260518` 镜像在 `HaiSong-orin` 上已存在。
- 已确认 AGX-orin 上 `/mnt/ssd/navgation/projects` 总体约 12G，包含 `rabbitbot-dev-ros2-master` 本体、模型目录、`unitree_sdk2`、`unitree_slam_example_new`、`custom_action_ws`、`pyorbbecsdk-v2-py310` 等项目内依赖。
- 已确认 AGX-orin 上项目外但运行需要的宿主依赖包括 `/opt/ros/humble`、`/home/pc/.local`、`/usr/local/lib/libddsc*`、`/usr/local/lib/libddscxx*`、`/etc/systemd/system/rabbitbot-loop.service` 和 `/etc/systemd/system/rabbitbot-control-console.service`。
- 已确认 `HaiSong-orin` 当前没有 `/mnt/ssd/navgation/projects`，没有 `/opt/ros`，没有 `uvicorn/fastapi/rclpy/custom_action_interfaces` 等宿主 Python/ROS 导入环境，也没有 rabbitbot systemd 服务文件。
- 已生成迁移包目录：`/mnt/ssd/navgation/migration_bundles/rabbitbot_orin_migration_20260609_125551`。
- 迁移包包含：`rabbitbot-projects.tar`、`rabbitbot-host-runtime.tar`、`restore_on_target.sh`、`README_迁移说明.md` 和 `SHA256SUMS`。
- 已完成 SHA256 实读校验，所有文件均为 `OK`。
- 已确认移动硬盘在 AGX-orin 上识别为 `/dev/sda1`，文件系统为 exFAT，标签为 `PortableSSD`。

未完成：

- 移动硬盘当前尚未挂载；SSH 下执行 `udisksctl mount -b /dev/sda1` 被 polkit 拒绝，原因是远程会话没有本机交互授权终端。
- 尚未把迁移包复制到移动硬盘。
- 尚未在 `HaiSong-orin` 上恢复迁移包或启动服务验证。
- 本轮未打包 Neo4j Docker 卷。当前只读检查显示 `rabbitbot_unified_neo4j_data` 约 19G、`rabbitbot_unified_neo4j_logs` 约 14M；该卷属于运行数据，不是启动依赖。如需迁移历史记忆数据，建议停止 `rabbitbot-unified-runtime` 容器后另行打包。

### 已验证的事实

- AGX-orin 当前移动硬盘识别信息：`sda1 exfat PortableSSD`，但无挂载点。
- AGX-orin 当前 `/mnt/ssd` 剩余空间在生成迁移包后约 44G。
- `rabbitbot-projects.tar` 大小约 12G，内容根路径为 `projects/`。
- `rabbitbot-host-runtime.tar` 大小约 1.2G，内容包含 `opt/ros/humble/`、`home/pc/.local/`、DDS 动态库和两个 systemd 服务文件。
- `HaiSong-orin` `/mnt/ssd` 可用空间约 700G，足够恢复迁移包。
- `HaiSong-orin` 当前没有 rabbitbot systemd 服务，恢复脚本默认只执行 `systemctl daemon-reload`，不会自动 enable/start 服务。
- `/home/unitree` 是机器人本体侧路径，不是 Orin 主机侧需要拷贝的目录；服务配置里的 `/home/unitree/test9.pcd` 会在运行时传给导航底层。

### 阻塞问题

当前唯一阻塞是移动硬盘未挂载。需要在 AGX-orin 本机图形界面挂载 `PortableSSD`，或在 AGX-orin 本机终端执行 sudo mount 后，再复制迁移包目录。

### 建议的下一步

- 在 AGX-orin 本机挂载移动硬盘，确认出现挂载点，例如 `/media/pc/PortableSSD`。
- 挂载后复制整个目录 `/mnt/ssd/navgation/migration_bundles/rabbitbot_orin_migration_20260609_125551` 到移动硬盘。必须复制 tar 文件，不要把 tar 解开后再复制，因为 exFAT 不能保留 Linux 权限和软链接。
- 将移动硬盘接到 `HaiSong-orin` 并挂载后，在迁移包目录内执行 `bash restore_on_target.sh`。
- 恢复后先确认 `sha256sum -c SHA256SUMS`、`/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master` 存在、`source /opt/ros/humble/setup.bash` 可用，再决定是否启用或启动 `rabbitbot-loop.service` 和 `rabbitbot-control-console.service`。
- 如果需要迁移 Neo4j 历史数据，先停止 AGX-orin 上 `rabbitbot-unified-runtime` 容器，再单独打包 `rabbitbot_unified_neo4j_data` 和 `rabbitbot_unified_neo4j_logs` 卷。

### 注意事项

- 迁移包是 tar 归档，适合放在 exFAT 移动硬盘上；不要直接裸拷贝 `/mnt/ssd/navgation/projects` 到 exFAT。
- `restore_on_target.sh` 需要 sudo 权限来写入 `/opt/ros/humble`、`/usr/local/lib` 和 `/etc/systemd/system`。
- 恢复脚本会执行 `sudo chown -R pc:pc /home/pc/.local /mnt/ssd/navgation/projects`，目标机应存在 `pc` 用户。
- 目标机恢复后仍需按现场实际网络和机器人连接检查 `NAV_PCD_PATH`、网卡名和音频设备。

### 其它信息

- 本轮没有修改业务代码或运行脚本，因此没有新增代码日志点。
- 本轮新增的迁移包 README 和恢复脚本包含中文说明和恢复阶段日志输出，便于目标机恢复时定位校验、解包、宿主运行时恢复、`ldconfig` 和 systemd reload 等步骤。

## 本轮补充：迁移包已复制到移动硬盘

### 背景和目标

本轮目标是在 Aaron 提供 AGX-orin sudo 授权后，将已生成并校验的 RabbitBot 离线迁移包复制到移动硬盘，供后续带到 `HaiSong-orin` 恢复。

### 当前状态

已完成：

- 已确认 AGX-orin 上移动硬盘为 `/dev/sda1`，文件系统为 exFAT，标签为 `PortableSSD`。
- 已确认 AGX-orin 当前没有内核 exFAT 模块，`mount -t exfat` 会报 `unknown filesystem type 'exfat'`。
- 已使用系统已有 `exfat-fuse` 将移动硬盘挂载到 `/media/pc/PortableSSD`。
- 已将迁移包目录复制到移动硬盘：`/media/pc/PortableSSD/rabbitbot_orin_migration_20260609_125551`。
- 已执行 `sync`，确保写入落盘。
- 已在移动硬盘挂载点内执行 `sha256sum -c SHA256SUMS`，所有文件校验均为 `OK`。

未完成：

- 本轮尚未在 `HaiSong-orin` 上恢复迁移包。
- 本轮尚未弹出移动硬盘；如需拔盘，应先执行安全卸载。
- 本轮仍未迁移 Neo4j Docker 卷运行数据；该卷不是启动依赖，如需历史记忆数据需另行停容器后打包。

### 已验证的事实

- 移动硬盘挂载点：`/media/pc/PortableSSD`。
- 移动硬盘上迁移包目录大小约 13G。
- 移动硬盘校验结果：`rabbitbot-projects.tar: OK`、`rabbitbot-host-runtime.tar: OK`、`restore_on_target.sh: OK`、`README_迁移说明.md: OK`。
- 移动硬盘剩余空间约 1.4T。
- exFAT 挂载后文件权限显示为统一可执行，这是 exFAT/FUSE 表现；tar 包内部权限仍由归档保存。

### 阻塞问题

无当前拷贝层面的阻塞。后续阻塞只可能来自目标机恢复时的 sudo 权限、目标机系统库兼容性、现场网卡/机器人连接和是否需要 Neo4j 历史数据。

### 建议的下一步

- 拔出移动硬盘前先执行安全卸载，例如在 AGX-orin 上执行 `sync` 后 `sudo umount /media/pc/PortableSSD`。
- 将移动硬盘接入 `HaiSong-orin` 并挂载后，进入 `rabbitbot_orin_migration_20260609_125551` 目录执行 `bash restore_on_target.sh`。
- 目标机恢复后先做只读验证，再决定是否启用 systemd 服务：检查 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`、`/opt/ros/humble`、`/home/pc/.local`、`/usr/local/lib/libddsc.so` 是否存在，并执行 `source /opt/ros/humble/setup.bash`。

### 注意事项

- 移动硬盘为 exFAT，只适合存放 tar 文件；不要在移动硬盘上解包后再搬迁项目目录。
- 如需迁移 Neo4j 历史数据，应先停止 AGX-orin 上 `rabbitbot-unified-runtime` 容器，再单独打包 Docker 卷，避免复制运行中的数据库文件。
- 目标机恢复脚本默认不会自动启动服务，避免在未确认现场网络、地图和机器人连接前触发移动或播报。

### 其它信息

- 本轮没有修改业务代码或运行脚本，因此没有新增代码日志点。
- 本轮新增的交接信息记录了 exFAT-FUSE 挂载方式、迁移包复制位置和移动硬盘端 SHA256 校验结果，便于后续确认离线介质是否可直接用于恢复。

## 本轮补充：移动硬盘已安全卸载

### 背景和目标

本轮目标是在迁移包复制并完成移动硬盘端 SHA256 校验后，安全卸载 AGX-orin 上的 `PortableSSD`，确保可以物理拔盘并转移到 `HaiSong-orin`。

### 当前状态

已完成：

- 已执行 `sync` 等待移动硬盘写入落盘。
- 已卸载 `/media/pc/PortableSSD`。
- 已复查 `lsblk`，`/dev/sda1` 仍识别为 `exfat PortableSSD`，但已无挂载点。

未完成：

- 尚未在 `HaiSong-orin` 上挂载移动硬盘和执行恢复脚本。

### 已验证的事实

- 移动硬盘卸载后不再出现在 `findmnt` 输出中。
- 当前可以物理拔出移动硬盘并接入 `HaiSong-orin`。

### 阻塞问题

无 AGX-orin 侧迁移介质准备阻塞。

### 建议的下一步

- 将移动硬盘接入 `HaiSong-orin`。
- 挂载后进入 `rabbitbot_orin_migration_20260609_125551` 目录，执行 `bash restore_on_target.sh`。
- 恢复完成后先做只读验证，再决定是否启动 rabbitbot 服务。

### 注意事项

- 如果在目标机看到 exFAT 文件权限统一显示为可执行，属于 exFAT/FUSE 正常表现；实际 Linux 权限保存在 tar 包内部。

### 其它信息

- 本轮没有修改业务代码或运行脚本，因此没有新增代码日志点。

## 本轮补充：排查切换电源模式后服务退出

### 背景和目标

本轮目标是按 Aaron 要求排查“以前切换电源模式后有些服务会崩”的现场现象，确认当前 AGX-orin 上是否存在同类情况，并定位原因。

### 当前状态

已完成：

- 已只读排查 `systemctl`、Docker 状态、`/var/log/auth.log`、`/var/log/syslog`、`/var/log/kern.log`、Docker inspect/logs 和项目日志。
- 已确认 2026-06-12 12:13:19 在项目目录执行过 `sudo /usr/sbin/nvpmodel -m 0`，即从原先 `MODE_30W` 切到 `MAXN`。
- 已确认切换前 `jtop` 记录为 `nvpmodel running in [2]MODE_30W - Default: 2`，当前启动后 `nvpmodel -q` 和 `jtop` 均显示 `MAXN`。
- 已确认 2026-06-12 12:13:26 开始系统级停机流程，随后停止图形会话、用户会话、jtop、Docker、nvfancontrol 等系统服务。
- 已确认 `rabbitbot-unified-runtime` 当前为 `Exited (137)`，Docker inspect 显示 `OOMKilled=false`；该退出码符合系统停机时 Docker/容器收到终止后被强制结束的表现，不是容器内 Python 业务异常或 OOM。
- 已确认当前 `rabbitbot-control-console.service` 和 `docker.service` 正常运行，`rabbitbot-loop.service` 为 disabled/inactive，`rabbitbot-unified-runtime` 容器未自动恢复。

未完成：

- 本轮未重启 `rabbitbot-unified-runtime`、`rabbitbot-loop.service`、导航桥接或 workflow。
- 本轮未再次执行 `nvpmodel -m` 做破坏性复现，避免再次触发系统重启或中断现场。

### 已验证的事实

- `/var/log/auth.log` 明确记录：`Jun 12 12:13:19 ... COMMAND=/usr/sbin/nvpmodel -m 0`。
- `/var/log/syslog` 显示：12:13:26 开始停止用户会话和图形界面，12:13:56 systemd 停止 Multi-User、Docker、nvfancontrol 等服务，并且 dockerd 收到 `Processing signal 'terminated'`。
- Docker inspect 显示 `rabbitbot-unified-runtime` 的 `ExitCode=137`、`OOMKilled=false`、`Finished=2026-06-12T04:14:09Z`。
- 当前系统时间存在回拨现象：`last -x` 中上一轮结束时间约为 12:14，当前启动时间约为 11:11；因此 Docker 中的 12:14 退出记录属于上一轮启动周期，不应误判为当前 11:xx 会话内刚发生。
- 项目日志中 2026-06-12 11:16 的 loop 启动曾使用 `/home/unitree/test9.pcd`，导航底层返回 `Load pcd failed`；该问题与电源模式切换导致服务退出是两个独立问题。

### 阻塞问题

无代码层面阻塞。当前运行层面风险是：切换电源模式后如果整机重启，非自启动的 `rabbitbot-unified-runtime` 容器和 `rabbitbot-loop.service` 不会自动恢复，需要人工或控制台重新启动。

### 建议的下一步

- 后续切换电源模式前，先停止 RabbitBot 导航 loop、workflow、导航桥接和统一容器，避免被系统停机流程强制杀掉后留下 `Exited (137)` 状态。
- 切换电源模式后先确认 `nvpmodel -q`、Docker、`rabbitbot-control-console.service`、`rabbitbot-unified-runtime`、28180/28182/28185 等服务状态，再启动 workflow。
- 如果需要切换到 `MAXN` 并立即继续演示，应把“切换电源模式 -> 等待重启完成 -> 重新启动统一容器基础服务 -> 再启动 loop/workflow”作为固定操作流程。
- 如需自动恢复，可考虑为统一容器基础服务增加明确的 systemd 管理方式，或让控制台在检测到容器 `Exited (137)` 且 `OOMKilled=false` 时提示“上次可能因系统重启/停机退出，需要重新启动基础服务”。

### 注意事项

- 本次证据不支持“RabbitBot 某个服务因电源模式参数变化自行崩溃”的判断；更准确的说法是：执行 `nvpmodel -m 0` 后系统进入重启/停机流程，Docker 和 RabbitBot 服务被系统正常停止，部分进程如 jtop 未及时退出后被 SIGKILL。
- `ExitCode=137` 不等于一定是内存不足；本次 Docker 明确给出 `OOMKilled=false`，应优先按系统停机/强制终止分析。
- 当前 `nvpmodel` 已是 `MAXN`，再次执行切换命令前应确认现场是否允许重启。

### 其它信息

- 本轮没有修改业务代码或运行脚本，因此没有新增代码日志点。
- 本轮新增的交接信息记录了电源模式切换命令、系统停机时间线、Docker 退出码解释和后续恢复建议，便于后续避免把系统级重启误判为业务服务崩溃。

## 本轮补充：启动 workflow 并观察服务稳定性

### 背景和目标

本轮按 Aaron 要求，在 AGX-orin 上启动一次 workflow，观察启动、预启动、实际 `go` 运行、导航过程中的服务状态，重点确认此前切换电源模式后相关服务退出的问题是否仍会表现为服务崩溃。

### 当前状态

- 已执行 `sudo systemctl start rabbitbot-loop.service` 启动导航桥接、统一容器基础服务和 workflow 预启动逻辑。
- 已发送 `bash scripts_1/send_nav_workflow_command.sh go`，workflow 已实际进入导览流程。
- 本轮为避免机器人在持续障碍物状态下继续尝试导航，已执行 `sudo systemctl stop rabbitbot-loop.service` 停止本次 loop/workflow。
- 停止后 `rabbitbot-loop.service` 被 systemd 标记为 `failed (status=143)`，这是 stop 触发 SIGTERM 后脚本退出码导致；尝试 `systemctl reset-failed rabbitbot-loop.service` 时当前 sudo 规则要求密码，未清理该 failed 标记。
- 停止后导航桥接 28180 已关闭，workflow 进程已停止；Docker、`rabbitbot-control-console.service` 和统一容器基础服务仍在运行。

### 已验证的事实

- 启动前基线：`rabbitbot-control-console.service` 与 Docker 为 running，`rabbitbot-loop.service` inactive/dead，`rabbitbot-unified-runtime` 为 `Exited (137)`。
- `rabbitbot-loop.service` 启动后成功拉起导航桥接，28180 端口打开；日志显示使用显式地图 `NAV_PCD_PATH=/home/unitree/test9.pcd`。
- 导航启动阶段提示 `Warning: PCD path is not visible from this shell: /home/unitree/test9.pcd`，但随后底层重定位成功，日志出现 `[Ready] Navigation system ready for commands!`。
- 统一容器 `rabbitbot-unified-runtime` 从退出态恢复为 running，Neo4j 7687、TTS 28185、Memory 28182 均就绪；STT 28184 按当前配置跳过，保持 closed，符合预期。
- workflow 预启动成功，生成 run_id `20260612_112819`，ready 文件落盘；发送 `go` 后闸门释放，日志显示 `workflow启动闸门: stage=released`。
- workflow 加载默认台词 `conf/dialogue_0.json`，日志显示 `map_file=test9.pcd, points=7, steps=8, segments=6`。
- 开场 TTS 请求成功，握手动作 `shake_hand` 经 28180 返回成功；后续 `face_wave` 动作也成功。
- 出现一次非致命收手动作超时：`release` async 请求 3 秒 read timeout，workflow 记录失败但继续执行，后续 release 再次成功。
- workflow 发出实际导航目标：
  - `1->2过渡点位`：`(0.1797, -0.1793, 0.0022, 0.1118, 0.0196, 0.9935)`
  - `点位2`：`(1.3443, 0.2059, 0.0137, 0.1131, 0.1278, 0.9852)`
- 进入第二段导航后，28180 `/go_to_status` 长时间保持 `{"status":"1","last_status":-1,"next_status":1,"sub":"navigating"}`，workflow 日志持续显示 `NavigationStatus.ACTIVE`。
- 导航底层持续输出 `[SLAM Info] "There are obstacles nearby, please be careful"`，这是本轮 workflow 未完成的直接运行原因；观察期间不是 Docker、control-console、统一容器、TTS、Memory 或 workflow 自身崩溃。
- 观察期间 `rabbitbot-loop.service`、Docker、`rabbitbot-control-console.service` 均保持 active；`rabbitbot-unified-runtime` 保持 Up；8080、28180、28182、28185、7687 均按阶段可用。
- 本轮未复现“切换电源模式后服务崩”的系统级退出；实际运行瓶颈是物理导航路径持续检测到障碍物。

### 阻塞问题

- workflow 未自然跑完整程，因为第二段导航持续处于 `ACTIVE/navigating`，底层持续报告附近有障碍物。
- `rabbitbot-loop.service` 停止后留下 failed 标记；清理该标记需要具备 `systemctl reset-failed rabbitbot-loop.service` 的 sudo 权限或现场输入密码。
- AGX shell 侧仍看不到 `/home/unitree/test9.pcd`，虽然本轮底层重定位成功，但该提示仍会影响后续排查判断。

### 建议的下一步

- 现场确认机器人周边和到点位2路径是否确有障碍物；清障后再启动 workflow 复测导航完成情况。
- 如需清理服务状态，可由具备 sudo 密码或免密权限的现场人员执行 `sudo systemctl reset-failed rabbitbot-loop.service`。
- 下次复测前先确认 28180 关闭、`rabbitbot-loop.service` inactive，再启动服务，避免旧导航桥接占用端口。
- 如希望停服务不留下 failed 标记，建议后续调整脚本或 systemd unit，让 SIGTERM 停止时返回 0，或设置合适的 `SuccessExitStatus=143`。
- 针对 `release` 3 秒超时，可考虑调高 async release 的短超时时间，或在日志中区分“命令已发出但等待回执超时”和“动作执行失败”。

### 注意事项

- 本轮为安全起见，在持续障碍物状态下主动停止了 `rabbitbot-loop.service`；停止后 28180 已关闭，但统一容器基础服务仍运行，28182、28185、7687 仍开放。
- 持续出现的 DDS `ddsi_udp_conn_write to udp/172.18.0.1:7410 failed` 日志没有导致服务退出，但噪声较大，后续如需降低日志干扰，应检查 DDS 网络接口/容器网络配置。
- 不要把本轮未跑完整误判为服务崩溃；关键服务在观察窗口内保持正常。

### 其它信息

- 本轮未修改业务代码或脚本，因此没有新增代码日志点。
- 本轮使用已有日志完成排查，关键日志点包括：导航地图加载和重定位、统一基础服务就绪、workflow 闸门释放、TTS 请求开始/完成、动作 HTTP 请求/回执、导航目标发送、导航状态轮询和底层障碍物提示。

## 本轮补充：修复 TTS 请求成功但现场无声问题

### 背景和目标

本轮目标是按 Aaron 要求排查并修复“机器人 TTS 不能说话”的现场问题。重点区分 28185 TTS 服务不可用、音频后端配置错误、外接音响缺失和 Unitree G1 本体 TTS 请求返回成功但现场无声等情况。

### 当前状态

已完成：

- 已确认 `rabbitbot-unified-runtime` 容器正在运行，28185 TTS 服务端口开放，`/docs` 可访问。
- 已确认当前 TTS 服务运行后端为 `RABBITBOT_TTS_BACKEND=unitree`，不是之前验证过的 Orin 本地外接 USB 音响后端。
- 已确认宿主机当前 `aplay -l` 和 `lsusb` 均未识别到之前交接报告中成功出声的 USB 音响 `BT67`。
- 已确认 Orin 到 G1 的 `eno1` 网卡在线，`192.168.123.222/24` 正常，且可 ping 通 G1 侧 `192.168.123.161`。
- 已用正确表单格式向 28185 `/exec` 发送短句“TTS诊断测试。”，接口返回 `{"out_text":"3"}`，随后 `wait_speech` 返回 `TTS finished`。
- 已修改 `scripts_1/unified_runtime/start_unified_container.sh` 和 `scripts_1/start_unified_integration_workflow.sh`，将 `RABBITBOT_UNITREE_TTS_SET_VOLUME_EACH_REQUEST` 默认值设为 `1`，并在启动 TTS 时显式透传该变量。
- 已增强统一容器和联调启动日志，启动时会打印 Unitree TTS 是否“每次请求设置音量”，便于后续判断配置是否生效。
- 已重启当前容器内 TTS 服务，28185 `/docs` 恢复可访问。
- 已发送短句“TTS修复验证。”，接口返回 `{"out_text":"0"}`，随后 `wait_speech` 返回 `TTS finished`。
- 已验证新日志生效：初始化日志显示 `set_volume_each_request=True`，本轮短句桥接日志显示 `volume=100`、`SetVolume ret=0`、`TtsMaker ret=0`。

未完成：

- 本轮无法通过 SSH 直接确认现场是否实际听到声音，需要现场人工听感确认。
- 外接 USB 音响 `BT67` 当前未被系统识别；如现场希望继续使用外接音响，需要重新插拔、换线或恢复 USB 音响后，再切回 `RABBITBOT_TTS_BACKEND=local` 并重建/重启容器。

### 已验证的事实

- 当前 TTS 日志显示 Unitree 本体 TTS 初始化成功：网卡 `eno1`，speaker `0`，音量 `100`。
- 当前 TTS 日志显示多次 `TtsMaker` 请求返回 `ret=0`，包括 workflow 开场台词和本轮诊断短句。
- 旧逻辑只在首次请求设置音量，后续请求桥接程序日志中 `volume=-1`，如果 G1 音频服务在运行中重置音量，可能出现请求成功但实际静音。
- 新逻辑会让 TTS 启动脚本默认每次请求都携带音量设置，降低机器人端音量状态漂移导致静音的风险。
- 当前运行中的 TTS 已按新逻辑启动，不需要等待下一次容器重建才生效。

### 阻塞问题

- 当前没有代码层面的阻塞。
- 现场层面仍需人工确认本体扬声器是否实际出声。
- 如果现场必须使用 `BT67` 外接音响，当前阻塞是 AGX-orin 没有识别到该 USB 音响硬件。

### 建议的下一步

- 现场听感确认本体 TTS 是否已经恢复。
- 如果仍无声，优先检查 G1 本体音频服务或扬声器状态；软件侧 28185、DDS 网络和 `TtsMaker ret=0` 均已确认正常。
- 如果要切回外接音响，先确认 `aplay -l` 或 `lsusb` 能看到 `BT67`，再用 `RABBITBOT_TTS_BACKEND=local RECREATE_CONTAINER=1 RUN_WORKFLOW_AFTER_START=0` 重建统一容器基础服务。

### 注意事项

- 当前 `BT67` 缺失时不要强行切到 local 后端，否则 `scripts/start_tts_app.bash` 会因为找不到稳定外接输出设备而拒绝启动 TTS。
- Unitree 本体 TTS 的 `TtsMaker` 只能确认机器人音频服务接受请求，不能通过 SSH 证明扬声器实际发声。

### 其它信息

- 本轮新增/调整的日志点：统一容器和联调启动时打印 TTS 后端、Unitree 网卡、音量以及“每次请求设置音量”配置；Unitree TTS 原有日志继续记录请求开始、返回码、耗时、音量、网卡、speaker id 和估算播放时长。
- 这些日志用于诊断 TTS 后端是否选错、Unitree 音量配置是否生效、请求是否成功到达 G1 音频服务，以及后续是否仍存在“接口成功但现场无声”的硬件侧问题。

## 本轮补充：修复 Unitree TTS 桥接进程过早退出

### 背景和目标

本轮继续处理 Aaron 现场反馈：workflow 正常执行，机器人手臂动作正常，但机器人没有播报语音。上一轮已确认 28185、TtsMaker 返回码和音量设置均正常，但现场仍无声，因此本轮进一步对比宇树官方 SDK 示例。

### 当前状态

已完成：

- 已运行宇树官方 `g1_audio_client_example eno1` 示例；Aaron 现场确认确实听到了声音，而且包含中文和英文播报。
- 已确认 G1 本体扬声器和宇树 SDK 音频服务可用，问题不在机器人硬件、网卡或 SDK 基础通信。
- 已定位关键差异：官方示例在 `TtsMaker` 后会继续 `Sleep(5)` 或 `Sleep(8)`，保持 DDS 客户端进程存活；项目自定义 `unitree_g1_tts_bridge` 原先在 `TtsMaker ret=0` 后立即退出，可能导致请求被接收但 DDS 客户端过早销毁，现场听不到完整播报。
- 已修改 `scripts/unitree_g1_tts_bridge.cpp`，新增 `--hold-seconds` 参数；`TtsMaker ret=0` 后会按指定秒数保持客户端存活，并记录保持开始和结束日志。
- 已修改 `rabbitbot/audio/unitree_g1_tts.py`，按台词估算时长向桥接程序传入 `--hold-seconds`，默认启用 `RABBITBOT_UNITREE_TTS_BRIDGE_HOLD=1`。
- 已调整 Python 后端的命令超时时间，避免长句因为桥接进程保持存活而被本地超时杀掉。
- 已调整 Python 后端的 `wait_speech` 逻辑：桥接程序内部已等待主要播报时长后，`wait_speech` 只保留短尾部缓冲，避免台词间隔翻倍。
- 已增强桥接二进制自动重建逻辑：当 C++ 源码或构建脚本比现有二进制更新时，启动 TTS 会自动重建桥接程序，避免继续使用旧二进制。
- 已完成 C++ 桥接程序重建，`--help` 输出已包含 `--hold-seconds`。
- 已直接运行新桥接程序发送“桥接保持修复测试。”并保持 4 秒，Aaron 现场确认已经听到该句。
- 已重启当前容器内 28185 TTS 服务，并发送“HTTP路径修复测试。”；接口返回 `{"out_text":"0"}`，`wait_speech` 返回 `TTS finished`。
- 已验证 TTS 日志显示 `bridge_hold_enabled=True`、`bridge_hold_seconds=3.500s`，桥接 stdout 包含“保持客户端存活”和“保持完成”。

未完成：

- 仍需在下一次完整 workflow 中确认所有台词与动作并发节奏是否合适。

### 已验证的事实

- 官方 SDK 示例可让现场听到声音，证明 G1 本体音频链路可用。
- 官方 SDK 示例在 TTS 后保持进程存活，这是项目桥接程序此前缺少的行为。
- 项目自定义桥接程序增加保持后，现场已确认直接桥接测试句可听到。
- 28185 HTTP 路径已经使用新桥接保持逻辑，日志显示 HTTP 请求耗时约等于保持时长，而不是立即返回。

### 阻塞问题

- 当前无代码层面阻塞。

### 建议的下一步

- 下一步可运行 workflow 开场验证台词和动作并发节奏。
- 如果台词间隔偏慢，优先微调 `RABBITBOT_UNITREE_TTS_BRIDGE_HOLD_EXTRA_SECONDS` 或 `_estimate_duration`，不要移除 `--hold-seconds`。

### 注意事项

- 后续如果调短 `RABBITBOT_UNITREE_TTS_BRIDGE_HOLD_EXTRA_SECONDS` 或关闭 `RABBITBOT_UNITREE_TTS_BRIDGE_HOLD`，可能再次出现 `TtsMaker ret=0` 但现场无声的问题。
- Unitree TTS 没有可靠播放完成回调时，桥接保持时长仍基于文本长度估算；如台词衔接过慢或过快，应调整估算公式或相关环境变量，而不是移除桥接保持逻辑。

### 其它信息

- 本轮新增日志点：桥接程序打印 `hold_seconds`、保持客户端存活开始和结束；Python 后端打印 `bridge_hold_seconds`、`post_bridge_wait_seconds`、命令超时和自动重建原因。
- 这些日志用于诊断 DDS 客户端生命周期是否覆盖真实播报窗口，以及二进制是否已经包含最新桥接逻辑。

## 本轮补充：同步 ShuHao TTS/STT 逻辑与 VLM 问答 workflow

### 背景和目标

Aaron 要求将 `ShuHao-orin` 上已经完成的 TTS/STT 逻辑和 `qa_workflow` 同步到当前 `AGX-orin` 项目。由于 AGX 项目分支 `June6_workflow` 落后 ShuHao 的 `feature/qa-vlm-workflow` 多个版本，本轮目标不是整仓覆盖，而是选择性合并相关能力，并保留 AGX 已经验证过的 Unitree TTS `--hold-seconds` 桥接保持修复。

### 当前状态

已完成：

- 新增 `rabbitbot/agno_agents/vlm_qa_workflow.py`，用于持续监听 STT、调用 VLM 生成回答，并通过 TTS 播报。
- 新增 `scripts/run_vlm_qa_workflow.py` 和 `scripts/start_vlm_qa_workflow.bash`，作为容器内 VLM 问答 workflow 入口。
- 新增 `scripts_1/start_unified_vlm_qa_workflow.sh`，作为宿主侧启动入口；会显式启用 VLM 与 STT，先启动统一容器基础服务，再前台运行问答 workflow。
- 同步 ShuHao 的 `scripts/start_tts_app.bash` TTS auto 后端健康检查逻辑：检查 Unitree 网卡、链路载波、IPv4、桥接程序和只读 `GetVolume` 探测，失败时回退 local 后端并输出分阶段日志。
- 同步 `scripts/start_stt_app.bash` 的 STT 输入设备自动选择策略日志，便于现场判断麦克风选择顺序。
- 合并 `scripts/unitree_g1_tts_bridge.cpp`：保留 AGX 已验证的 `--hold-seconds` 播报保持逻辑，同时加入 ShuHao 的 `--probe get_volume` 只读探测能力。
- 更新 `scripts/build_unitree_g1_tts_bridge.sh`，优先从当前项目父目录推导 `unitree_sdk2`，兼容 AGX 的 `/mnt/ssd/navgation/projects/unitree_sdk2` 布局。
- 更新 `scripts_1/start_unified_integration_workflow.sh` 和 `scripts_1/unified_runtime/start_unified_container.sh`：默认 TTS 后端改为 `auto`，透传 Unitree TTS 健康检查参数，TTS 就绪检查改为 `/exec` 表单接口探活，避免仅 `/docs` 可访问但协议不兼容的假就绪。

未完成：

- 本轮未启动 VLM 问答 workflow，避免加载模型、重建容器或占用现场音频设备。
- 本轮未启动导航 workflow、导航桥接、systemd 服务，也未发送 `go/back`。
- 本轮未做现场语音问答实测；后续仍需在有人值守时确认 STT 麦克风、VLM 加载耗时和 TTS 实际出声节奏。

### 已验证的事实

- 同步前 AGX 工作区干净，分支为 `June6_workflow`。
- 已执行 `bash -n` 检查以下脚本并通过：`scripts/start_tts_app.bash`、`scripts/start_stt_app.bash`、`scripts/build_unitree_g1_tts_bridge.sh`、`scripts/start_vlm_qa_workflow.bash`、`scripts_1/start_unified_vlm_qa_workflow.sh`、`scripts_1/start_unified_integration_workflow.sh`、`scripts_1/unified_runtime/start_unified_container.sh`。
- 已使用 `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile` 编译 `rabbitbot/agno_agents/vlm_qa_workflow.py`、`scripts/run_vlm_qa_workflow.py` 和 `rabbitbot/audio/unitree_g1_tts.py` 通过；直接写项目 `__pycache__` 会遇到已有 root 权限缓存文件，因此使用临时 pycache 目录规避。
- 已执行 `git diff --check` 通过。
- 已重新构建 `build/unitree_g1_tts_bridge`，`--help` 输出同时包含 `--hold-seconds` 与 `--probe get_volume`。
- 已用 `py310/bin/python scripts/run_vlm_qa_workflow.py --help` 验证 QA 入口可导入并输出帮助。

### 阻塞问题

无代码层面阻塞。运行层面仍需现场确认：启动 QA workflow 会启用 VLM 与 STT，可能占用 GPU、麦克风和 TTS 服务；应在非导览时段验证。

### 建议的下一步

- 先在确认现场安全且不影响导览的窗口运行：`bash scripts_1/start_unified_vlm_qa_workflow.sh`。
- 如需只测纯语音问答，保持默认 `RABBITBOT_QA_INCLUDE_IMAGE=0`。
- 如需测试视觉问答，可先使用 `RABBITBOT_QA_INCLUDE_IMAGE=1 RABBITBOT_QA_IMAGE_SOURCE=mock`，再切换到机器人实时图像。
- 如果 TTS auto 回退 local 后端失败，优先查看 `logs/unified_runtime/rabbitbot_tts.log` 中 `TTS启动检查` 分阶段日志，确认是网卡、carrier、IPv4、桥接构建还是 `GetVolume` 探测失败。
- 如果 QA workflow 启动时容器因 `RABBITBOT_UNIFIED_START_STT=1` 或 `RABBITBOT_UNIFIED_START_VLM=1` 与旧容器配置不一致而重建，这是预期行为。

### 注意事项

- 本轮没有从 ShuHao 整文件覆盖 AGX 的 TTS 后端，避免丢失 AGX 最新的 `--hold-seconds` 修复；当前桥接程序同时具备保持客户端存活和只读探测能力。
- 默认 TTS 后端现在是 `auto`；链路健康时应选择 Unitree，本体链路不可用时会尝试回退 local，并在日志中给出原因。
- QA workflow 不执行导航，不发送 `go/back`，也不启动导览剧本；它只负责语音监听、VLM 推理和 TTS 播报。

### 其它信息

- 本轮新增/调整日志点：TTS 启动检查会记录 auto 判定开始、接口状态、carrier/IP 检查结果、桥接构建状态、Unitree 音频服务探测开始/成功/失败和最终后端；QA workflow 会记录启动配置、每轮监听、STT 输入摘要、VLM 推理耗时、流式 TTS 分段、问答日志写入和异常失败路径。
- 生成时间：2026-06-16 18:10:00

## 本轮补充：AGX QA workflow 运行测试与 VLM 流式阻塞

### 背景和目标

Aaron 要求在 AGX 上实际测试 QA workflow，重点确认 STT/TTS 设备选择、通过 28184 `/exec inject_text_async` 纯命令行注入问题，以及多句回答场景下的流式 TTS 行为。

### 当前状态

已完成：

- 启动 `scripts_1/start_unified_vlm_qa_workflow.sh`，验证统一容器能拉起 Neo4j、VLM、TTS、STT、Memory 和 Robot Agent。
- 验证 VLM 冷启动约 4 分钟量级，启动日志显示模型加载、torch compile、graph capture 和 8000 API server 就绪。
- 验证 TTS auto 设备选择逻辑，发现首次 `GetVolume` 探测缺少 `LD_LIBRARY_PATH`，导致 `libddsc.so.0` 找不到并错误回退 local；已修复 `scripts/start_tts_app.bash`，探测前自动加入 Unitree SDK2 thirdparty 动态库路径。
- 修复后 TTS auto 成功选择 Unitree：`GetVolume ret=0, volume=100`，28185 `/exec` 就绪。
- 验证 STT 设备选择：STT 选择 `NVIDIA Jetson AGX Orin APE: - (hw:1,0)`，index=4，并成功监听 28184。
- 使用 Aaron 指定的 curl 方式向 28184 注入文本，接口返回 HTTP 200 和 `utterance_id`。
- 第一轮短问题“你好，请用一句话介绍你自己”成功完成：QA workflow 收到文本、调用 VLM、流式输出首 token，并拆成 2 个 TTS 分段播报。
- 多句问题测试暴露 prompt 质量问题：原 prompt 会让模型复述“用户问题/回答要求”；已调整 QA prompt，最终文本模式改为直接传用户原文，并增加 `RABBITBOT_QA_VLM_MAX_TOKENS` 上限。
- 已停止本轮测试启动的 `rabbitbot-unified-runtime` 容器，释放 28180、28182、28184、28185、8000、7687 等端口，避免留下高资源占用服务。

未完成：

- 多句流式问答没有达到可交付效果。测试中 vLLM 流式接口在多次异常/中断后进入无响应状态，后续 `stream=true` curl 和 `stream=false` curl 均在 20 秒内无有效返回。
- 本轮未继续重启 VLM 做第四轮完整复测，避免反复加载模型和长时间占用现场资源。

### 已验证的事实

- TTS auto 选择和 Unitree 探测修复有效：日志包含 `Unitree桥接动态库路径已设置`、`Unitree音频服务探测通过`、`effective=unitree`。
- STT 注入命令有效，例如注入多句问题时返回 `HTTP=200` 和对应 `utterance_id`。
- QA workflow 的流式 TTS 机制本身可工作：日志中出现多个 `流式 TTS 分段已提交`，并调用 28185 `/exec` 播报。
- 当前最大问题不是 STT 注入或 TTS 分段，而是 VLM 输出质量与流式接口稳定性：多句问题出现重复复述，之后 VLM 8000 进入请求无有效返回状态。
- 直接非流式 vLLM 原始问题曾返回内容，说明模型服务在干净状态下可推理；但异常流式请求/中断后服务可能变为不健康。

### 阻塞问题

- QA workflow 的多句流式问答仍有阻塞：当前 vLLM 流式接口不稳定，且 prompt 稳定性不足。需要进一步隔离 vLLM 流式接口、Python SDK 客户端和 prompt 采样参数。

### 建议的下一步

- 下轮先不启动完整 QA workflow，直接用 8000 做最小化 curl 矩阵测试：`stream=false/true`、原始用户问题、短 prompt、不同 `max_tokens`，确认哪个组合稳定。
- 如果 `stream=true` 持续不稳定，可先为 QA workflow 增加非流式 VLM fallback，然后再做 TTS 分段播放。
- 若继续使用流式 VLM，应给 `_create_vlm_stream()` 增加首 token 超时和异常恢复日志，避免 workflow 卡死。
- 继续保留本轮 TTS `LD_LIBRARY_PATH` 修复；该修复是明确有效的兼容性修复。

### 注意事项

- 本轮停止了测试容器，AGX 结束时没有保持 RabbitBot 基础服务运行。
- 本轮修改后仍需提交：`rabbitbot/agno_agents/vlm_qa_workflow.py` 和 `scripts/start_tts_app.bash`。

### 其它信息

- 本轮新增/调整日志点：TTS auto 探测新增 Unitree 桥接动态库路径日志；QA workflow 的 VLM token 上限可通过 `RABBITBOT_QA_VLM_MAX_TOKENS` 调整，后续排查可结合 `VLM 首 token 到达`、`VLM 流式问答完成` 和 `流式 TTS 分段已提交` 判断卡点。
- 生成时间：2026-06-16 18:55:00

## 本轮补充：强制重建容器后复测 QA workflow

### 背景和目标

Aaron 要求重启全部服务和容器后重新测试 AGX 的 QA workflow，确认上一轮 VLM 不稳定是否由服务状态残留导致。

### 当前状态

已完成：

- 已使用 `RECREATE_CONTAINER=1` 强制删除并重建 `rabbitbot-unified-runtime` 容器。
- 已重新拉起 Neo4j、VLM、TTS、STT、Memory Agent 和 Robot Agent。
- 已确认 VLM 冷启动流程正常，8000 `/v1/models` 就绪。
- 已确认 TTS `/exec`、STT 28184、Memory 28182、Robot Agent 28180 均就绪。
- 已直接测试 8000：
  - 非流式短问题 `stream=false` 正常返回，HTTP 200，耗时约 4.5 秒。
  - 流式短问题 `stream=true` 能输出 token；测试命令用 `head` 截断输出导致 curl 写管道失败，但 token 已实际返回。
- 已通过 28184 注入短问题“你好，请用一句话介绍你自己”，QA workflow 收到文本，VLM 首 token 约 0.327 秒，TTS 成功播报 1 个分段。
- 已通过 28184 注入多句问题“请用三句话介绍语音问答系统的工作流程，每句话都要简短”，复现 VLM 多句请求无首 token 的问题。
- 在 QA 多句请求挂起后，直接测试 8000 同一多句问题的 `stream=true` 和 `stream=false`，均在超时时间内无有效输出。
- 已停止本轮测试容器，释放 28180、28182、28184、28185、8000、7687，避免留下不健康 VLM 进程占用资源。

未完成：

- 多句 QA 流式问答仍未跑通。
- 本轮未修改代码，仅完成重建容器后的复测与报告记录。

### 已验证的事实

- 重建容器能消除上一轮残留状态，短问题链路稳定可用。
- 当前问题具有输入形态相关性：短问题 `stream=false` / `stream=true` 和完整 QA 都能工作；多句问题会导致 QA 和直接 8000 请求无有效返回。
- 这次复测进一步说明问题不是单纯由旧容器残留导致，也不是 STT 注入或 TTS 设备选择导致，而是 VLM 对该类多句请求的生成/流式处理稳定性问题。

### 阻塞问题

- AGX 上多句 VLM 请求仍会触发 8000 无有效返回，阻塞 QA 多句流式问答验收。

### 建议的下一步

- 先绕开完整 QA workflow，直接对 8000 做更细粒度矩阵测试：
  - 短问题、多句问题、改写后的多句问题。
  - `stream=false` / `stream=true`。
  - `max_tokens=32/64/96`。
  - `temperature=0`、`top_p`、`top_k` 等采样参数。
- 如果确认只有特定中文请求触发卡住，可在 QA workflow 中加入问题改写或安全 prompt 模板。
- 如果确认 `stream=true` 对稍长请求不稳定，应为 QA workflow 增加非流式 fallback、首 token 超时和请求取消/重启提示。

### 注意事项

- 本轮结束时 AGX 没有保留测试容器运行，相关端口均已释放。
- 当前 Git 工作区在报告更新前是干净状态。

### 其它信息

- 本轮未新增业务代码日志点；复测主要使用现有日志：服务就绪日志、VLM 首 token 日志、TTS 分段日志、STT 注入返回和 8000 curl 响应。
- 生成时间：2026-06-16 19:20:00

## 本轮补充：隔离 QA workflow 与导览提示词

### 背景和目标

Aaron 指出导览 workflow 的提示词会强调机器人只是导览机器人、只能回答小范围问题，可能影响 QA workflow 的回答行为。本轮目标是让 `vlm_qa_workflow.py` 的问答身份、回答范围和输出规则与导览 workflow 明确无关，同时兼顾 AGX 上多句 VLM 流式请求不稳定的问题。

### 当前状态

已完成：

- 已在 `rabbitbot/agno_agents/vlm_qa_workflow.py` 新增独立 `QA_SYSTEM_PROMPT`，明确 QA workflow 是独立语音问答助手，不承担展厅路线引导、展品讲解流程推进或机器人动作控制。
- 已明确禁止 QA workflow 将自己描述为“只能回答导览相关问题”的机器人，也不再把回答范围限制在展厅、展品或参观路线内。
- 已将纯文本 QA 调用改为 `system + user` 消息结构；视觉 QA 的 prompt 也内嵌同一套 QA 独立提示词。
- 已新增 `RABBITBOT_QA_VLM_STREAM`，默认 `0`，避免 AGX 上多句问题触发 vLLM token 流式请求卡住；如需重新验证 token 流式，可显式设置为 `1`。
- 已新增 `RABBITBOT_QA_VLM_MAX_TOKENS` 配置并在启动脚本中透传；为空时使用根据 `RABBITBOT_QA_MAX_ANSWER_CHARS` 推导的默认值。
- 已保留 `RABBITBOT_QA_STREAM_TTS=1` 的按句 TTS 路径：默认关闭 VLM token 流式时，先完整生成回答，再按句拆分提交 TTS，仍可测试多句播报链路。
- 已更新 `scripts/start_vlm_qa_workflow.bash` 和 `scripts_1/start_unified_vlm_qa_workflow.sh` 的环境变量说明、透传和启动日志，启动时会打印 `prompt_profile=qa_independent`。

未完成：

- 本轮没有重新启动全部容器或 QA workflow 实测，因为上一轮已按 Aaron 要求停止所有容器和服务；本轮只做静态验证和代码提交。
- 新的非流式 VLM + 分句 TTS 路径仍需在 AGX 服务重新启动后，用 28184 注入短问题和多句问题做完整链路复测。

### 已验证的事实

- 已在 AGX 仓库内通过 `PYTHONPYCACHEPREFIX=/tmp/rabbitbot_pycache_check python3 -m py_compile rabbitbot/agno_agents/vlm_qa_workflow.py`。
- 已在 AGX 仓库内通过 `bash -n scripts/start_vlm_qa_workflow.bash`。
- 已在 AGX 仓库内通过 `bash -n scripts_1/start_unified_vlm_qa_workflow.sh`。
- 已在 AGX 仓库内通过 `git diff --check`。
- 当前改动没有引用导览 workflow 的 `prompts.py` 导览身份提示词；QA profile 通过日志标记为 `qa_independent`。

### 阻塞问题

- 无代码层面的阻塞。
- 运行层面仍需重启服务后验证 AGX VLM 对多句中文问题的非流式稳定性；如果非流式仍卡住，需要继续做 8000 端口最小化矩阵测试。

### 建议的下一步

- 重启统一容器和基础服务后，优先用 28184 注入以下两类文本验证：
  - 短问题：“你好，请用一句话介绍你自己”。
  - 多句问题：“请用三句话介绍语音问答系统的工作流程，每句话都要简短”。
- 测试时重点观察 workflow 日志中的 `prompt_profile=qa_independent`、`VLM 推理开始/完成`、`VLM 输出流式已关闭`、`流式 TTS 分段已提交` 和 `完整回答分段 TTS 等待完成`。
- 如必须恢复 token 级流式输出，可临时设置 `RABBITBOT_QA_VLM_STREAM=1`，但要准备好 vLLM 长回答卡住的复现和服务重启。

### 注意事项

- `RABBITBOT_QA_STREAM_TTS=1` 现在不等同于 VLM token 流式；默认含义是回答生成完成后按句提交 TTS。
- `RABBITBOT_QA_VLM_STREAM=1` 才会恢复原来的 VLM token 流式并边生成边提交 TTS。
- QA 独立提示词只约束 `vlm_qa_workflow.py`，不会改变导览 workflow 的正式导览台词、动作、导航或导览提示词。

### 其它信息

- 本轮新增/调整日志点：workflow 启动日志新增 `stream_tts`、`vlm_stream`、`vlm_max_tokens`、`prompt_profile`；VLM 推理开始日志新增 `stream`、`max_tokens`、`prompt_profile`；关闭 VLM token 流式时新增回退路径日志；完整回答分句播报结束后新增分段数量、已播报字符数和等待耗时日志。
- 生成时间：2026-06-16 19:30:00

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
