# 交接报告

## 背景和目标

本轮目标是在六月六日 DOCX/PDF 剧本已对齐、过渡点和新地图坐标已更新的基础上，将导览台词从 `workflow.py` 抽离到独立 JSON 文件，便于现场直接修改文案；同时将默认称呼配置为台词文件中的 `variables.leader_calling` 键。项目主机 `AGX-orin-FX`，路径 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，分支 `June6_workflow`。

## 当前状态

已完成：

- 已保持严格 DOCX 剧本开场逻辑：不在开场台词前额外导航点位1，直接从点位1开始台词。
- 已保持当前 DOCX 剧本步骤顺序：`1到2过渡`、`跟随步行到点位2`、`点咖啡`、`初步介绍`、`拿取咖啡`、`前往3到5过渡点`、`前往点位5`、`告别并指引小巴方向`。
- 已保持 `1->2过渡点位` 和 `3->5过渡点位` 为独立只导航、无台词步骤，避免在过渡点提前播报。
- 已按 2026-06-02 现场新采地图更新 DOCX 点位坐标：`1->2过渡点位`、`点位2`、`点位3`、`3->5过渡点位`、`点位5` 已写入 `DOCX_SCRIPT_POINTS`；点位1未重新提供，保持当前 workflow 中原坐标。
- 已新增 `docs/june6_guide_dialogue.json` 作为六月六日导览台词文件，开场台词、DOCX 严格剧本步骤台词、动作绑定、咖啡车后台命令配置均从该文件读取。
- 已将默认称呼抽为 `variables.leader_calling`，台词中的 `{leader_calling}` 会在运行时替换；缺少该键时 workflow 会报出明确配置错误，不再静默使用代码内固定称呼。
- 当前开场不再包含“第一次来园区”问答；第三段欢迎各位朋友的台词仍使用 `face_wave` 动作。
- 已调整 dialogue01/dialogue02 的握手动作时序：
  - `shake_hand` 现在从 dialogue01 “亚勤院士您好。”开始时启动。
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
- 本轮按最新剧本删除两处问答交互：开场不再询问“是否第一次来园区”，改为直接播报“亚勤院士，各位，请随我来，我简单的介绍一下园区。”；点咖啡不再等待领导回答，改为直接播报准备咖啡饮料并在“我来给各位安排。”开播时呼叫 AIR 咖啡车。
- 本轮已从 `拿取咖啡` 场景移除“我再给各位介绍一下产业园和清华创新中心的合作成果。”这句独立播报；该场景现在只保留咖啡和饮料自取提示，随后直接进入 `前往3到5过渡点`。
- 上一轮现场释放了导航桥接常用端口 `28180`：当时确认占用方为 `python3` 进程 PID `7283`，执行结束后复查 `ss -ltnp "sport = :28180"` 已无监听进程。
- 本轮处理旧导航桥接进程：先结束 `start_nav_arm_bridge.sh eno1 /home/unitree/test1.pcd` 的 PID `41946` 进程组；随后复查发现同命令又拉起 PID `42936` 进程组并占用 28180，已继续结束其 `goGoalNavigation66`、`humble_robot_agent_bridge`、`tail`、`tee` 子进程。最终复查 `ss -ltnp "sport = :28180"` 已无监听进程。
- 本轮同步更新了 `docs/DOCX严格剧本workflow逻辑.md` 和 `docs/直接导航命令.txt` 中的点位坐标说明，直接导航命令中的点位5路径已改为包含 `3->5过渡`。
- 本轮已验证 `docs/june6_guide_dialogue.json` 可通过 `python3 -m json.tool` 解析，`rabbitbot/agno_agents/workflow.py` 可通过 `python3 -m py_compile` 语法检查。

## 阻塞问题

无代码层面的阻塞。运行层面有两个待恢复/验证事项：一是上一轮 BT67 外接音响已从 Orin 声卡列表消失且 TTS 当前未运行，需要现场恢复声卡后再启动；二是本轮 AIR 咖啡车呼叫逻辑未实际运行，避免误触发现场配送任务，需在真机 workflow 点咖啡环节验证。Unitree `TtsMaker` 只返回机器人接收状态，当前没有官方播放完成回调；`wait_speech` 使用文本长度估算等待时间，后续如发现台词衔接过快或过慢，需要调节 `UnitreeG1TTS._estimate_duration` 或新增更可靠的播放状态查询。

## 建议的下一步

- 用如下方式启动 unified 模式验证本体播报：`RECREATE_CONTAINER=1 bash scripts_1/start_unified_integration_workflow.sh`；默认会使用 Unitree G1 本体音响、`eno1` 网卡和音量 `100`。
- 真机跑一次完整开场，重点观察 `shake_hand` 是否从“{leader_calling}您好”开始伸手，并确认收手仍发生在“欢迎您来到滨湖复星人形机器人产业园”之后。
- 当前默认音量已改为 100；如现场觉得过响或破音，可通过 `RABBITBOT_UNITREE_TTS_VOLUME=85` 或更低值临时覆盖后重启 TTS/unified 流程。
- 若必须恢复原来的男声/本地音色，需要评估两条路线：一是回退 `RABBITBOT_TTS_BACKEND=local` 使用 Orin 外接音箱；二是改用 G1 `PlayStream` 播放 Orin 本地合成的 PCM 音频。仅调整 `RABBITBOT_UNITREE_TTS_SPEAKER_ID` 预计不能切换到中文男声。
- 如要继续使用 Orin 外接音响，需先让 Orin 重新识别 BT67，再用 `RABBITBOT_TTS_BACKEND=local RECREATE_CONTAINER=1` 重建/启动 unified；如不带 `RABBITBOT_TTS_BACKEND=local`，会按代码默认值回到机器人本体音响。
- 真机跑点咖啡环节时，重点观察“我来给各位安排。”开播时是否同时出现 `DOCX 后台命令已启动` 和 `DOCX 后台命令结束` 日志，并确认 stdout 中咖啡车接口返回 `success=true` 和运行时 `task_id`。
- 重新拉起导航桥接后，先用 `docs/直接导航命令.txt` 中的新坐标逐点验证 `1->2过渡`、`点位2`、`点位3`、`3->5过渡` 和 `点位5` 到点精度。
- 如需现场修改称呼，直接改 `docs/june6_guide_dialogue.json` 的 `variables.leader_calling`；如需修改台词，改对应 `opening` 键或 `steps[].segments[].text`。修改后重启 workflow 让进程重新读取台词文件。
- 完整跑完 DOCX 剧本后，确认终端出现 `DOCX 剧本总耗时`，并检查耗时是否覆盖开场第一句到最后一句“各位再会！”结束后的剧本完成时刻。
- 继续确认 dialogue01 中“上前靠近领导A一步”是否已有机器人动作或底盘接口；当前本轮未实现该靠近动作。
- 继续按上一轮建议清理重复 `entity` 字段。
- 明确是否有 OK 手势动作字段；如果有，再把点咖啡后的 `right_hand_up` 改为 OK 动作。

## 注意事项

- 默认 TTS 后端现在是 `unitree`，默认音量是 `100`；如需回退 Orin 本地外接音箱，需要显式设置 `RABBITBOT_TTS_BACKEND=local`。
- 当前 TTS 运行状态需现场恢复：上一轮重启 TTS 时 BT67 从 Orin 声卡列表消失，当前 `http://127.0.0.1:28185/docs` 返回 `000`，`/proc/asound/cards` 仅剩 HDA/APE；需重新插拔或恢复 BT67 后再启动 TTS。
- `send_delivery_task.py` 当前仍是未跟踪文件，但 workflow 已依赖它作为 AIR 咖啡车呼叫脚本；如后续整理仓库，应决定是否将该脚本纳入版本管理。
- 上一轮观察到的旧容器 `RABBITBOT_UNITREE_TTS_VOLUME=85` 已不再是当前运行状态；当前默认 Unitree 音量仍为 `100`，但使用 `RABBITBOT_TTS_BACKEND=local` 时 Unitree 音量配置不参与本地外接音响播放。
- Unitree 本体 TTS 当前通过 C++ 桥接程序发命令，不依赖 Python 版宇树 SDK。
- unified 创建容器和容器内启动 TTS 时会打印后端、Unitree 网卡和音量，方便排查是否仍沿用旧容器或旧音量。
- DOCX 后台命令日志会记录命令解析来源、启动 PID、超时时间、退出码、耗时、stdout/stderr 摘要，可用于排查 AIR 咖啡车接口是否被调用以及返回结果。
- DOCX 剧本计时日志会在终端打印 `DOCX 剧本总计时开始` 和 `DOCX 剧本总耗时`，用于现场快速确认整段流程耗时。
- 当前 DOCX 剧本不再包含“第一次来园区”和“是否送咖啡饮料”的 STT 问答等待；如后续再恢复问答，需要重新配置 `listen_key`/`early_listen` 并验证监听超时。
- 当前 `拿取咖啡` 场景不再包含合作成果介绍台词；如后续要恢复相关内容，需要先确认正式文案，再重新加入独立播报 segment。
- `workflow.py` 现在只保留流程结构和台词文件加载/校验逻辑；六月六日 DOCX 导览具体台词应优先维护 `docs/june6_guide_dialogue.json`，不要再直接写回 `DOCX_SCRIPT_STEPS`。
- 如果再次启动 `start_nav_arm_bridge.sh` 仍提示 28180 被占用，应优先现场复查当时的 `ss -ltnp "sport = :28180"` 输出；本轮结束旧桥接进程后该端口已经为空。
- 如果在容器内使用宿主机构建的桥接程序，`UnitreeG1TTS` 会自动设置 `LD_LIBRARY_PATH` 到 `/workspace/projects/unitree_sdk2/thirdparty/lib/aarch64` 或宿主机对应路径。
- 如果现场觉得伸手过早或动作时长影响话筒交接，可优先检查动作日志中的 `action=shake_hand` 耗时和随后的 `release` 耗时。

## 其它信息

如需同步到 `feature/unified-runtime-image`，可 cherry-pick 本轮提交。
