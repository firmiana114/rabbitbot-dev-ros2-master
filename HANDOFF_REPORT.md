# 交接报告

## 背景和目标

本轮目标是将当前 `June6_workflow` 分支的 STT 灵敏度调整为与 `tianjin` 分支一致，同时由本轮选择更适合导览现场的静音结束时间。当前项目运行在 Orin 主机 `AGX-orin-FX`，项目路径为 `/mnt/ssd/navgation/projects/rabbitbot-dev-ros2-master`。

## 当前状态

已完成：

- 已确认当前实际存在的对照分支为 `tianjin`，未发现本地 `tianjinworkflow` 分支。
- 已将 `tianjin` 分支中的 STT 参数化配置、VAD 判定、最小 RMS 过滤、最短语音时长、输入增益、音频队列处理和麦克风音量设置同步到 `June6_workflow`。
- 已将默认静音结束时间设置为 `0.50` 秒。该值比旧的 `0.30` 秒更不容易截断现场讲话中的短停顿，同时仍保持较快响应。
- Workflow 打断阈值 `RABBITBOT_INTERRUPT_RMS_THRESHOLD=0.02` 未调整，因为当前分支与 `tianjin` 分支已经一致。

未完成：

- 尚未启动统一容器进行真实麦克风输入验证。
- 尚未在展览现场环境下确认 `0.50` 秒静音结束时间是否需要继续微调。

## 已验证的事实

- `scripts/start_stt_funasr_app.bash` 现在默认导出以下 STT 参数：
  - `STT_SILENCE_SEC=0.50`
  - `STT_VAD_WINDOW_SEC=0.45`
  - `STT_VAD_KEEP_SEC=0.12`
  - `STT_VAD_SPEECH_THRES=0.12`
  - `STT_VAD_START_HITS=1`
  - `STT_MIN_RMS=0.022`
  - `STT_MIN_UTTERANCE_SEC=0.35`
  - `STT_INPUT_BLOCK_SEC=0.1`
  - `STT_INPUT_LATENCY=high`
  - `STT_AUDIO_QUEUE_MAX_CHUNKS=160`
  - `STT_INPUT_GAIN=1.0`
  - `STT_INPUT_VOLUME_PERCENT=80`
- `stt_app_funasr.py` 会打印 STT 过滤参数，便于从服务日志确认实际生效值。
- `stt_app_funasr.py` 会在检测到语音、跳过过短音频、跳过过低音量音频、音频队列满、音频流状态异常等关键路径输出诊断信息。

## 阻塞问题

当前没有代码层面的阻塞。运行层面仍依赖统一容器、麦克风设备和现场音量环境。

## 建议的下一步

- 启动统一非联调或联调 workflow，观察 STT 启动日志中的过滤参数是否为预期值。
- 使用现场麦克风做一次近距离、正常距离和背景噪声下的识别测试。
- 如果仍然误触发，优先提高 `STT_MIN_RMS` 或 `STT_VAD_SPEECH_THRES`；如果漏听，优先降低 `STT_MIN_RMS` 或提高麦克风输入音量。
- 如果响应偏慢，可将 `STT_SILENCE_SEC` 从 `0.50` 下调到 `0.45`；如果仍截断短停顿，可上调到 `0.55`。

## 注意事项

- `RABBITBOT_INTERRUPT_RMS_THRESHOLD` 属于 workflow 打断检测阈值，不等同于 STT 服务内部的 VAD 和 RMS 阈值。
- 本轮只调整 STT 灵敏度相关逻辑，没有修改六月六日导览剧本内容。
- STT 参数均可通过环境变量覆盖，脚本默认值只是统一启动时的基线。

## 其它信息

本轮修改集中在 `stt_app_funasr.py` 和 `scripts/start_stt_funasr_app.bash`。如果后续需要完全复现 `tianjin` 的行为，需要特别注意本轮刻意将静音结束时间从 `tianjin` 启动脚本默认的 `0.45` 秒调整为了 `0.50` 秒。
