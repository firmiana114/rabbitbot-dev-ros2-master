# 交接报告

## 背景和目标

本轮目标是修复 TTS 首句播报延迟问题：启动 workflow 后，终端已打印开场第一句「亚勤院士您好，请把话筒给亚勤院士。」，但要等约 6~7 秒音响才出声。项目运行主机为 `AGX-orin-FX`，项目路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`，分支 `June6_workflow`。

经定位，延迟由三处**一次性冷启动**叠加在首句真实合成上造成（详见“已验证的事实”）。由于统一容器为保持“启动安静”默认关闭了启动播报与快捷音预生成（`RABBITBOT_TTS_STARTUP_SPEECH=0`、`RABBITBOT_TTS_FAST_SOUND_PRELOAD=0`），这些冷启动没有被预热吸收，全部压到了第一句真实播报。

修复思路：在 TTS 服务端启动末尾增加一次**静默预热**，只做“合成 + 重采样”，不向音频设备输出，把冷启动在启动阶段吃掉，且不破坏“启动安静”。

## 当前状态

已完成：

- `rabbitbot/audio/run_tts_espnet.py`：`EspnetTTS` 新增 `warmup(self, text="你好，欢迎参观。")` 方法。
  - 复用现有 `text_to_wav()` 合成一段短文本，触发 jieba 分词与 kokoro 首次推理冷启动。
  - 对合成结果调用一次 `librosa.resample(...)`，触发 numba/soxr 首次 JIT 编译；结果丢弃。
  - 全程**不调用** `sd_stream.play_and_wait` / `sd.play`，无任何声音输出。
  - 异常被捕获并记录，预热失败不阻断服务启动。
- `tts_app.py`：在读取启动开关后、`before_text` 之前调用 `tts_engine.warmup()`。
  - 新增开关 `RABBITBOT_TTS_WARMUP`（默认开），**独立于** `STARTUP_SPEECH` / `FAST_SOUND_PRELOAD`，因此即使保持“启动安静”也会预热。
  - 调用点位于任何 `put_text` / 快捷音预生成之前，此时异步合成线程空闲，`warmup` 同步执行不会与合成线程并发使用 kokoro pipeline。
- 已在统一容器内单独重启 TTS 服务并完成端到端验证，确认修复生效（见“已验证的事实”）。

未完成：

- 尚未在完整 workflow 真机运行中观察开场第一句「亚勤院士…」的现场体感（已通过单句实测确认时延消除，建议下次跑 workflow 时再做一次现场确认）。

## 已验证的事实

- 延迟根因时间线（修复前，同一句 `tts_index=0`，来自 `logs/unified_runtime/rabbitbot_tts.log`）：
  - 合成阶段约 3.5s：含 jieba 首次加载 `Loading model cost 1.300 seconds` + kokoro 首次推理。
  - wav 就绪到真正播放又隔约 3.33s：`librosa.resample` 首次调用。
  - 文本入队到出声合计约 6.8s。
- 容器内实测 `librosa.resample`：首次 **2.491s**，第二次 **0.002s**，确认是首次 JIT 冷启动。
- `SDOutputStream` 在服务启动时一次性开好持久输出流，`play_and_wait` 只是 `write`，**不是每句重开**，故延迟与音频/蓝牙设备无关。
- 改动后 `rabbitbot/audio/run_tts_espnet.py` 与 `tts_app.py` 均通过 `ast.parse` 语法校验。
- 重启 TTS 后启动日志确认预热生效：`RABBITBOT_TTS_WARMUP: True`、`TTS预热完成: 合成耗时=2.204s, 重采样耗时=1.902s, 总耗时=4.106s`，且 `out_device_id: 24`（BT67）选择正常。
- 重启后首句真实播报「延迟测试一二三四五」实测：合成 **0.538s**、wav 就绪→播放 **0.003s**，文本入队到出声约 **0.54s**——较修复前约 6.8s 降低约 12 倍，冷启动已被启动期预热吸收。

## 阻塞问题

当前无阻塞，修复已端到端验证通过。

## 建议的下一步

1. 下次重跑统一容器 / workflow 时，确认启动日志出现 `RABBITBOT_TTS_WARMUP: True` 与 `TTS预热完成: ...`，并在现场确认开场第一句「亚勤院士…」基本无延迟。
2. 若现场有特殊需要可设 `RABBITBOT_TTS_WARMUP=0` 关闭预热（会退回首句慢）。
3. 重启 TTS 的标准做法（与编排一致）：在容器内 `cd $PROJECT_DIR && export RABBITBOT_TTS_DEVICE=cuda RABBITBOT_TTS_FAST_SOUND_PRELOAD=0 RABBITBOT_TTS_STARTUP_SPEECH=0 && bash scripts/start_tts_app.bash`，日志写 `logs/unified_runtime/rabbitbot_tts.log`。

## 注意事项

- 预热只合成+重采样、**不出声**，不影响“启动安静”的现场预期。
- 预热与 `STARTUP_SPEECH` / `FAST_SOUND_PRELOAD` 解耦：即便后两者为 0，预热仍会执行。
- 当 `STARTUP_SPEECH=1` 时预热仍会先于启动播报同步完成，二者无并发冲突；此时启动播报相当于已被预热加速。
- 本轮新增日志点（中文）：`TTS预热开始` / `TTS预热完成（含合成、重采样、总耗时）` / `TTS预热失败（不影响服务启动）`，用于诊断冷启动是否被成功吸收及定位预热异常。
- 本轮未改动 workflow 剧本文案与动作字段。
- 验证时单独重启了 TTS 服务，旧日志已备份为 `logs/unified_runtime/rabbitbot_tts.log.before_warmup`。

## 其它信息

本轮修改集中在 `rabbitbot/audio/run_tts_espnet.py` 与 `tts_app.py`。如需同步到 `feature/unified-runtime-image` 等其它分支，可 cherry-pick 本轮提交。
