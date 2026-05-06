import os
import sys
import time
import re
import threading
import requests
import numpy as np
import sounddevice as sd
import soundfile as sf
import queue
from scipy.signal import resample_poly
from funasr import AutoModel
import torch

import psutil
# ===== Jetson 专属优化：系统调度 =====
def optimize_jetson_process():
    """针对 Orin AGX 的调度优化，确保不被其他进程挤占"""
    p = psutil.Process(os.getpid())
    # 1. 提升 CPU 优先级 (Linux 最高为 -20)
    try:
        p.nice(-20)
    except: pass
    # 2. 核心绑定 (Affinity)
    # Orin AGX 有 12 核，0-3 通常处理系统中断，我们将 STT 绑定到 4-11 核
    try:
        p.cpu_affinity(list(range(4, 12)))
    except: pass
    # 3. 设置实时调度策略 (需要 sudo 权限)
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(99))
        print("🚀 已开启 SCHED_FIFO 实时调度优先级")
    except:
        print("⚠️ 提示: 请使用 'sudo' 运行以获得最高调度权限")

# ===== 麦克风设备查找 =====
def get_input_device_index(target_name='DJI MIC MINI'):
    devices = sd.query_devices()
    print(devices)
    for idx, dev in enumerate(devices):
        if target_name in dev['name'] and dev['max_input_channels'] > 0:
            print(f"🎤 Using mic: {dev['name']} (index={idx})")
            return idx
    return None
input_sound_index = get_input_device_index()

# ===== 文本预处理 =====
def preprocess_voice_text(text: str):
    if not text or not text.strip():
        return "", "NEUTRAL"
    text = text.strip()
    text = re.sub(r"^(嗯|啊|哦|呃|哎|哈|嘿|喂)\s*", "", text)
    # 提取所有情感标签
    emotion_tags = re.findall(r'<\|([^|]+)\|>', text)
    print(emotion_tags)
    text = re.sub(r'<\|.*?\|>', '', text).strip()
    # 处理情感标签
    emotion = emotion_tags[1] if len(emotion_tags) >= 2 else "NEUTRAL"
    return (text[:2000] if text else ""), emotion

# ===== 发送到本地 /v1 =====
def send_to_local_api(text: str, emotion: str):
    try:
        requests.post("http://0.0.0.0:28184/v1", json={"text": text,"emotion": emotion}, timeout=1)
    except Exception as e:
        print(f"❌ 发送到主进程失败: {e}")
        pass

# ======================
# 配置你的设备
# ======================
INPUT_CHANNELS = 1                                   # 单声道
SAMPLE_RATE_MODEL = 16000                            # SenseVoice 要求

# 检查设备是否直接支持 TARGET_SR，DEVICE_SR为麦克风原始采样率
try:
    sd.check_input_settings(device=input_sound_index, samplerate=SAMPLE_RATE_MODEL)
    DEVICE_SR = SAMPLE_RATE_MODEL
    NEED_RESAMPLE = False
    print(f"✅ 设备直接支持 {SAMPLE_RATE_MODEL} Hz，无需重采样")
except:
    # 如果不支持，则使用设备默认采样率，后续重采样
    DEVICE_SR = int(sd.query_devices(input_sound_index, 'input')['default_samplerate'])
    NEED_RESAMPLE = True
    print(f"⚠️ 设备默认采样率为 {DEVICE_SR} Hz，将实时重采样至 {SAMPLE_RATE_MODEL} Hz")

# VAD/ASR 参数
SILENCE_SEC = 0.3      # 语音结束后等待 0.3 秒再识别
BUFFER_MAX_SEC = 15   # 最多缓存 1.5 秒音频

# 限制缓冲区大小
max_samples = int(BUFFER_MAX_SEC * SAMPLE_RATE_MODEL)

# 加载模型（GPU + INT8）
print("Loading models...")
# 加载模型类型，Fun-ASR-Nano-2512和 "SenseVoiceSmall" 有很大不同
# 中文、英文SenseVoiceSmall，体积较小而且快
# 中文、英文、日文 for Fun-ASR-Nano-2512
# 中文、英文、粤语、日文、韩文、越南语、印尼语、泰语、马来语、菲律宾语、阿拉伯语、
# 印地语、保加利亚语、克罗地亚语、捷克语、丹麦语、荷兰语、爱沙尼亚语、芬兰语、希腊语、
# 匈牙利语、爱尔兰语、拉脱维亚语、立陶宛语、马耳他语、波兰语、葡萄牙语、罗马尼亚语、
# 斯洛伐克语、斯洛文尼亚语、瑞典语 for Fun-ASR-MLT-Nano-2512
MODEL_TYPE = "SenseVoiceSmall"  
if MODEL_TYPE == "Fun-ASR-Nano-2512":
    asr_model = AutoModel(
                model="Fun-ASR-Nano-2512",
                trust_remote_code=True,          # ⚠️ 必须添加，允许加载远程代码
                remote_code="audio/Fun-ASR/model.py",         # ⚠️ 必须指定，模型定义文件（请确认路径）
                device="cuda",
                disable_log=True,)
else:
    asr_model = AutoModel(
                model="/data/models/SenseVoiceSmall",
                # model_revision="v2.0.4",
                device="cuda",
                disable_log=True,
                # 关键：打开过滤
                use_itn=True,      # 可选：同步打开文本正则化（数字、符号规整）
                ban_emo_emo=False,  # 可选：去掉情感标签 <|NEUTRAL|> 等
                ban_emo_lang=True,  # 关键：去掉语种标签 <|zh|> <|en|> …
                disable_update=True
            )
vad_model = AutoModel(model="/data/models/fsmn_vad", 
                      device="cuda",
                      disable_log=True,
                      disable_pbar=True,
                      disable_update=True)

# 预热模型
dummy_audio = np.random.randn(16000).astype(np.float32)
if MODEL_TYPE == "Fun-ASR-Nano-2512":
    dummy_tensor = torch.from_numpy(dummy_audio).float()
    _ = asr_model.generate(
            input=[dummy_tensor],
            cache={},
            batch_size=1,
            hotwords=["开放时间"],
            language="中文",
            itn=True, # or False
        )
else:
    _ = asr_model.generate(input=dummy_audio, batch_size_s=0)
_ = vad_model.generate(input=dummy_audio, chunk_size=320)
print("模型加载完毕!")

# 全局变量
audio_queue = queue.Queue(maxsize=10)
# 存储重采样后的 16kHz 音频
audio_buffer_ = []  
# 存储存放当前语音段的完整 16k 音频（用于最终 ASR）
recording_buffer = []
last_voice_time = time.time()
input_speech = False

def resample_audio(audio_48k):
    # 使用 scipy.signal.resample（基于 FFT，速度更快）
     # 确保是 float32
    audio_48k = np.asarray(audio_48k, dtype=np.float32)
    
    # 如果原始是 int16（范围 [-32768, 32767]），需要归一化
    if np.abs(audio_48k).max() > 1.0:
        print("enter???????")
        audio_48k = audio_48k / 32768.0  # 转到 [-1, 1]
    
    # 重采样
    audio_16k = resample_poly(audio_48k, SAMPLE_RATE_MODEL, DEVICE_SR).astype(np.float32)
    return audio_16k

def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"采集状态异常: {status}")
    # 取单声道
    audio_48k = indata[:, 0].flatten()
    try:
        # 队列满时丢弃旧数据，避免阻塞采集
        audio_queue.put_nowait(audio_48k)
    except queue.Full:
        pass  # 静默丢弃，优先保证实时性

def vad_asr_thread():
    global audio_buffer_, last_voice_time, recording_buffer, input_speech
    
    while True:
        try:
            frame_ = audio_queue.get_nowait()
        except queue.Empty:
            continue
        # 重采样到 16kHz
        audio_16k = resample_audio(frame_)
        audio_buffer_.extend(audio_16k)
        if input_speech :
            recording_buffer.extend(audio_16k)
        
        # 每积累 0.4 秒音频做一次 VAD，经过测试必须要0.4秒，否则无法识别到人声
        if len(audio_buffer_) >= int(0.35 * SAMPLE_RATE_MODEL):
            vad_input  = np.array(audio_buffer_, dtype=np.float32)
            # sf.write("debug_vad_input.wav", vad_input, SAMPLE_RATE_MODEL)
            segments = vad_model.generate(
                input=vad_input,
                chunk_size=160,  # 10ms @ 16kHz
                speech_thres=0.1
            )
            has_speech = len(segments) > 0 and len(segments[0]["value"]) > 0
            # 未检测到人声音时进行的打印调试
            # print(segments)
            current_time = time.time()
            if has_speech:
                if not input_speech:
                    input_speech = True
                    print("🎤 检测到语音，正在录制...")
                    recording_buffer = audio_buffer_.copy()
                last_voice_time = current_time
            else:
                 # 无语音
                if input_speech:
                # 无语音，检查是否超时
                    if current_time - last_voice_time > SILENCE_SEC :
                        input_speech = False
                        if len(recording_buffer) > int(0.3 * SAMPLE_RATE_MODEL):
                            # sf.write("debug_stt.wav", np.array(recording_buffer), SAMPLE_RATE_MODEL)
                            # 触发 ASR
                            start_time = time.time()
                            if MODEL_TYPE == "Fun-ASR-Nano-2512":
                                result = asr_model.generate(
                                    input=[torch.from_numpy(np.array(recording_buffer, dtype=np.float32)).float()],
                                    cache={},
                                    batch_size=1,
                                    hotwords=["Chatgpt","Gemini"],
                                    language="中文",
                                    itn=True, # or False
                                )
                            else:
                                audio = np.array(recording_buffer, dtype=np.float32)
                                rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
                                print('rms is:',rms)
                                if rms<0.04:
                                    result = [{"text": ""}]
                                else:
                                    result = asr_model.generate(
                                        input=audio,
                                        language="zh",
                                        hotword=["ChatGPT","Gemini"]
                                    )
                            text, emotion = preprocess_voice_text(result[0]["text"])
                            if text:
                                print(f"\n🎙️ 识别结果: {text}")
                                print(f"⏱️ 识别耗时: {time.time() - start_time:.2f} 秒")
                                send_to_local_api(text,emotion)
                        # 清空记录人声的库
                        recording_buffer = []
            # 清理 VAD 缓冲区，保留最近 0.1 秒的数据以实现滑动
            audio_buffer_ = audio_buffer_[-int(0.1 * SAMPLE_RATE_MODEL):]

# ======================
# 启动录音（使用你的设备）
# ======================
if __name__ == "__main__":
    optimize_jetson_process()
    # 启动处理线程
    threading.Thread(target=vad_asr_thread, daemon=True).start()
    print("输入设备序列号为：",input_sound_index)
    
    # 启动录音流（48kHz → 实时重采样）
    with sd.InputStream(
        device=input_sound_index,
        channels=INPUT_CHANNELS,
        samplerate=DEVICE_SR,
        callback=audio_callback,
        blocksize=int(DEVICE_SR * 0.05),  # ← 50ms
        dtype='float32',
        latency='low'
    ):
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 退出程序")