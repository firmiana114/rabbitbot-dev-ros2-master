# 交接报告

## 背景和目标

本轮目标：修复 DOCX 剧本"送咖啡"段的可用性问题——询问句「对了，{leader_calling}、各位…我让我的小伙伴给送过来？」之后，机器人几乎立刻就说「好的，我来给各位安排。」，用户在听完问句后没有作答时间。项目主机 `AGX-orin-FX`，路径 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，分支 `June6_workflow`。

## 当前状态

已完成：

- 将 `rabbitbot/agno_agents/workflow.py` 中 `DOCX_SCRIPT_STEPS` 的"点咖啡"段 `coffee_order` 监听超时 `listen_timeout` 由 `8` 提高到 `16`，并加中文注释说明原因。
- 改动后通过 `ast.parse` 语法校验。

未完成：

- 尚未在真机/完整 workflow 中实测"用户在问句后作答能被正确捕获"。建议下次跑非联调或联调时验证。

## 已验证的事实（根因）

- 该段 `early_listen=True`，是"边播问句边监听"，且监听超时从**问句开播那一刻**起算。
- 询问句约 35 字，合成约 9~10 秒音频（参照"亚勤院士您好，请把话筒给亚勤院士。"16 字 = 4.35s 推算）。
- 旧超时仅 8 秒 < 问句时长，导致问句播完时监听已超时（多次运行日志均为 `poll_count=40`、`<REC_TIMEOUT>`、`elapsed≈8.55s`），留给"听完问句后作答"的有效时间 ≈ 0，故现象上"问完立刻说好的"。
- 对比：开场短问句「您是第一次来我们园区吗？」在 8 秒窗口下问句播完后仍有余量，实测 6.3s 听到用户"是的"，机制本身正常。
- `tts_sound` 为非阻塞入队，问句与"好的"经 TTS 队列先后无缝播出；改大超时不影响该衔接。
- 全文件仅"点咖啡"段有一处 `listen_timeout`（`dog_show_confirmation` 判定函数尚在，但 June6 重写后剧本已无狗表演/沙盘监听段），故只改这一处即可。

## 阻塞问题

无。

## 建议的下一步

- 跑 workflow 验证：到"送咖啡"段时，机器人问完后应保留约 6~7 秒作答窗口；用户回答能被识别并存入 `ctx.docx_script_answers["coffee_order"]`。
- 若现场觉得无人作答时的等待偏长，可下调该值（如 14）；若问句被改长，需同步上调。注意该超时是"问句时长 + 作答窗口"的总和，不是纯作答时间。
- 备选优化（本轮未做，Aaron 因其会引入小延迟而否决）：改成"先播完问句再单独开窗监听"。

## 注意事项

- 本轮仅改一个配置数值 + 注释，未改执行逻辑、未新增/调整日志点（现有"早听应答链路/用户到TTS链路"trace 已记录 timeout 与轮询过程，足够诊断）。
- 未改任何话术文案与动作字段。

## 其它信息

本轮修改集中在 `rabbitbot/agno_agents/workflow.py`（`DOCX_SCRIPT_STEPS` 点咖啡段）。如需同步到 `feature/unified-runtime-image`，可 cherry-pick 本轮提交。
