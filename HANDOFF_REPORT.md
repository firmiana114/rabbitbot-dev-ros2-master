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
- 本轮已将 `conf/dialogue*` 前缀台词文件加入 `.gitignore`，并从 Git 索引移除 `conf/dialogue_0.json`；Orin 本地文件仍保留，`conf` 目录本身和其它非 dialogue 配置文件不被整体忽略。
- 本轮已补齐 `workflow.py` 顶部运行环境变量速查注释，覆盖严格剧本、台词序号/文件覆盖、咖啡车后台命令、导航、动作、profile 和 mock 视觉相关变量。
- 本轮已将 `send_delivery_task.py` 纳入版本管理，并为脚本补充中文命令说明和 AIR 咖啡车接口调用日志。
- 本轮已按现场要求先停止当前 workflow 进程组，保留 unified 容器和 TTS/STT/Memory 后台服务继续运行。
- 本轮提交后发现现场仍有一次旧式外部 `docker exec ... bash scripts/start_kuavo_agno_workflow.bash | tee` 命令重新拉起 workflow；已再次只停止该旧 workflow 进程组，容器和后台服务仍保留。
- 本轮已改造 unified `start_workflow()`：workflow 现在以独立进程组启动，`^C`/TERM/EXIT 会触发清理逻辑，先 TERM 后按需 KILL 整个 workflow 进程组。
- 本轮已将 `0203788` 中 `workflow.py` 的 workflow 运行环境变量速查注释同步补充到联调和非联调两个 unified workflow 启动脚本，便于现场启动前直接查看台词、咖啡车、导航、动作和日志相关变量。
- 本轮新增 `scripts_1/start_nav_bridge_workflow_loop.sh`，用于合并启动导航桥接和 unified 基础服务，并通过外部 `go/back` 命令循环启动 workflow、剧本结束后返航到点位1、再等待下一次 `go`。
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
- 本轮按现场要求调整 back 返航路径：不再判断机器人是否在点位5附近，而是收到 back 后先导航到 `点位5`，然后再执行 `3->5过渡点位 -> 点位3 -> 点位2 -> 1->2过渡点位 -> 点位1` 的逆序返航。
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
- back 返航路径现在有 6 段，第一段为 `点位5`。如果机器人实际不在点位5或定位漂移，脚本会先尝试回到点位5，再继续返航。
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
