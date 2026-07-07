# 交接报告

## 项目整体描述

- 项目路径：`/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，当前分支 `June6_workflow`。
- 项目用途：运行 AGX-orin 上 RabbitBot/Kuavo 机器人导览、问答、导航桥接、TTS/STT 和网页控制台。
- 核心功能：网页控制台查看服务/定位状态并发送导览、返航、启动/停止/重启；QA 语音模式识别“开始导览”；workflow 按 `conf/dialogue_*.json` 执行点位导航和讲解；TTS/STT/VLM/Memory 由统一容器提供。
- 主要模块：`rabbitbot/control_console` 是 FastAPI 控制台；`rabbitbot/agno_agents/workflow.py` 是导览 workflow；`scripts_1/start_nav_bridge_workflow_loop.sh` 负责导航桥接、QA 与 workflow 循环；`scripts/run_kuavo_agno_workflow.py` 是容器内 workflow 入口；`conf/dialogue_0.json` 是当前现场导览点位和台词配置。
- 关键目录：`conf/` 存放导览 JSON；`rabbitbot/` 存放 Python 业务逻辑；`scripts/` 和 `scripts_1/` 存放运行脚本和 systemd 配置；`tests/control_console/` 存放控制台单测；`logs/` 和 `runtime/` 是运行时日志/控制文件。
- 主要技术栈：Python 3.10、FastAPI、Uvicorn、pytest、ROS/导航桥接、Docker 统一运行时；前端是 `rabbitbot/control_console/app.py` 内嵌 HTML/CSS/原生 JavaScript。
- 运行入口：控制台通常通过 `python3 -m rabbitbot.control_console` 或 `scripts_1/start_control_console.sh`；导航导览主循环通过 `rabbitbot-loop.service` 调用 `scripts_1/start_nav_bridge_workflow_loop.sh`；workflow 由 `scripts/run_kuavo_agno_workflow.py` 启动。
- 核心数据流：网页控制台保存/读取 `conf/dialogue_0.json`；主循环预启动 workflow 并停在 go 闸门；收到 go 后 workflow 读取导览 JSON、导航到 `points` 中的坐标并播报 `steps[].segments[].text`；导览结束后等待 back 返航。
- 重要配置：`RABBITBOT_DIALOGUE_INDEX`/`RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE` 选择台词文件；`NAV_PCD_PATH`/`map_file` 控制地图；`RABBITBOT_NAV_WORKFLOW_*` 控制主循环、状态和命令文件；`RABBITBOT_TTS_*`、`RABBITBOT_QA_*` 控制语音链路。
- 外部依赖：Unitree/Kuavo 导航桥接、ROS 工作空间、Docker 容器 `rabbitbot-unified-runtime`、本地或本体 TTS、STT/VLM/Memory 服务；具体部署版本未确认。
- 常用命令：`python3 -m pytest tests/control_console/test_app.py tests/control_console/test_commands.py`；`python3 -m json.tool conf/dialogue_0.json`；`python3 -m py_compile rabbitbot/control_console/app.py rabbitbot/control_console/dialogue.py`；`systemctl status rabbitbot-loop.service`。

## 当前状态

- 本轮实现了“点位坐标/讲解台词”热更新表格：控制台新增两列表格、`+` 新增行、保存点位台词。
- 新增接口：`GET /api/dialogue/hot-rows` 读取表格管理的点位台词；`POST /api/dialogue/hot-rows` 校验并写回 `conf/dialogue_0.json`。
- 表格保存会生成 `console_point_<id>` 点位和对应 step，并带 `source="control_console_table"` 标记；再次保存只替换这些标记项，不改原有导览、返航点和其它配置。
- 坐标输入采用 JSON 对象，必填 `x/y/z/ox/oy/oz/ow`，`mode` 缺省为 `1`；台词不能为空。
- workflow 新增 `reload_docx_guide_dialogue()`，并在 go 闸门释放后清空台词缓存，确保等待开始导览期间保存的配置能在本次导览启动时重新读取。
- 控制台保存/读取/校验失败/备份/写入路径增加了 INFO/ERROR 日志，日志记录行数、路径、点位 key、错误类型，不记录完整台词或大段 JSON。
- 顺手修正 `loop_service_autostart_enabled()`：只有 `systemctl is-enabled` 明确输出 `enabled` 才显示已启用，空输出不再误判。
- 2026-07-07 补充：热更新表格首次没有新增点位时，前端会自动显示一行空白输入；接口提示改为“当前暂无表格新增点位，请点击 + 添加”，避免误以为已有 18 个导览点应该出现在该表格中。
- 2026-07-07 再次补充：热更新表格升级为完整台词表，新增“点位名字”列；加载 `dialogue_0.json` 时会显示 `opening` 和全部 `steps` 对应的点位坐标/讲解台词；`opening` 行不需要点位坐标，讲解台词栏显示并保存 opening JSON 对象。
- 2026-07-07 领导称呼补充：控制台新增独立“领导称呼”输入框和加载/保存按钮，读写 `variables.leader_calling`；保存时会校验非空、非法字符和长度，下一次导览生效，无需重启导航主程序。
- 2026-07-07 前端按钮精简：控制台页面移除“对话”“视觉导航”“开始程序”“刷新状态”四个按钮；后端接口和自动刷新未删除，避免影响已有调用和状态更新。
- 2026-07-07 按钮布局补充：控制台将“导览”和“返航”放在同一行，“一键重启”“关闭程序”“开机自启动”保留在下一行。
- 2026-07-07 界面重排补充：控制台页面按参考图调整为左侧导航、顶部状态条和卡片式仪表盘布局；可见区域保留任务控制、机器人状态、领导称呼、点位台词热更新和模型服务，移除“导览讲解词”和“最近日志”两个可见面板。
- 2026-07-07 子页面补充：控制台左侧导航支持切换“总览、任务控制、机器人状态、领导称呼、点位台词、模型服务”子页面；页面样式改为自适应浏览器窗口，窄屏时导航、状态条、按钮组和表格区域自动换行或滚动。
- 2026-07-07 任务控制视觉补充：移除左侧“收起”入口；“任务控制”子页面改为深色科技风导览控制台，包含机器人状态、运动状态、中心机器人视觉区、任务信息、导航地图、语音交互和底部运动控制区，保留原导览/返航/重启/关闭/自启动接口。
- 2026-07-07 任务控制真实状态标注补充：任务控制页除底部控制按钮外的展示型模块均标注“开发中”；使用 imagegen 生成机器人图片并保存为 `rabbitbot/control_console/static/unitree-g1-dashboard.png`，FastAPI 挂载 `/static/control_console` 提供页面静态资源。
- 2026-07-07 总览入口补充：移除左侧“总览”选项卡和总览页，控制台默认进入“任务控制”子页面。

## 已验证事实

- `python3 -m py_compile rabbitbot/control_console/app.py rabbitbot/control_console/dialogue.py rabbitbot/control_console/commands.py scripts/run_kuavo_agno_workflow.py rabbitbot/agno_agents/workflow.py tests/control_console/test_app.py` 已通过。
- `python3 -m json.tool conf/dialogue_0.json` 已通过，当前现场台词 JSON 格式有效。
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/control_console/test_app.py tests/control_console/test_commands.py` 已通过，结果为 61 passed。
- 2026-07-07 小修后再次运行同一组控制台测试，结果仍为 61 passed。
- 2026-07-07 完整台词表修改后运行 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/control_console/test_app.py tests/control_console/test_commands.py`，结果为 62 passed；`python3 -m py_compile rabbitbot/control_console/app.py rabbitbot/control_console/dialogue.py tests/control_console/test_app.py` 通过；`python3 -m json.tool conf/dialogue_0.json` 通过。
- 2026-07-07 领导称呼修改后运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 按钮精简后再次运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 按钮布局调整后再次运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 界面重排后运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 子页面与自适应布局修改后运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 任务控制视觉修改后运行同一组控制台测试，结果为 65 passed；相关 py_compile 和 JSON 校验通过。
- 2026-07-07 任务控制开发中标注和机器人图片替换后运行同一组控制台测试，结果为 66 passed；相关 py_compile、JSON 校验和静态图片访问通过。
- 2026-07-07 总览入口删除后运行同一组控制台测试，结果为 66 passed；相关 py_compile 和 JSON 校验通过。
- 直接运行系统 `python3 -m pytest ...` 会因远端全局 pytest/anyio 插件版本不匹配失败，失败发生在 pytest 启动阶段；关闭插件自动加载可正常测试。

## 阻塞问题

- 无代码层阻塞。
- 本轮未重启控制台、未重启导航主程序、未发送 go/back、未移动机器人。
- 热更新真实现场生效还需在网页控制台保存一行后启动下一次导览验证；当前仅完成单测和静态校验。

## 下一步

- 若要现场验证：刷新控制台页面，填写坐标 JSON 和讲解台词，保存后在下一次导览中确认新增点位按末尾顺序执行。
- 若页面当前由旧进程服务，需重启控制台进程后才能看到新增表格；不需要为了台词数据保存而重启导航主程序。
- 若新增点位需要插入到中间路线，而不是追加末尾，需要扩展表格为可排序/指定插入位置。

## 注意事项

- 仓库在本轮开始前已有未提交改动：`conf/dialogue_0.json`、`rabbitbot/control_console/app.py`、`commands.py`、`tests/control_console/*`、sudoers 文件和一个备份 JSON；提交时需要只纳入本轮相关变更，避免覆盖或误提交无关现场调整。
- `conf/dialogue_0.json` 当前已有现场台词/点位调整，本轮没有通过热更新接口写入现场新行。
- 表格管理的点位以 `source="control_console_table"` 为边界；不要手工给普通点位加这个 source，避免下次保存被替换。
- 历史近期工作一行摘要：此前主要围绕导览台词、TTS/REDMI 外放恢复、QA 触发、定位/导航异常排查、控制台状态和自启动控制做过多轮现场修复与只读分析。
