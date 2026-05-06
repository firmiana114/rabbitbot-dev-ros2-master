import os
import sys
import time
import threading
import heapq
import queue
import numpy as np
import torch
import sounddevice as sd
from scipy.signal import resample_poly
import uvicorn
from fastapi import FastAPI, Request

# ===== 配置 =====
KOKORO_OFFICIAL_SR = 24000.0
VOICE_NAME = "/data/models/kokoro/Kokoro-82M/voices/zm_yunxi.pt"
os.environ["HF_HUB_OFFLINE"] = "1"
# ===== 扬声器查找 =====
def get_output_device_index(target_name='BT67'):
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if target_name in dev['name'] and dev['max_output_channels'] > 0:
            return idx
    return None

output_sound_index = get_output_device_index()
print('output_sound_index is:',output_sound_index)

# 检查设备是否直接支持 TARGET_SR，DEVICE_SR为麦克风原始采样率
try:
    sd.check_output_settings(device=output_sound_index, samplerate=KOKORO_OFFICIAL_SR)
    TARGET_SR = KOKORO_OFFICIAL_SR
    NEED_RESAMPLE = False
    print(f"✅ 设备直接支持 {KOKORO_OFFICIAL_SR} Hz，无需重采样")
except:
    # 如果不支持，则使用设备默认采样率，后续重采样
    TARGET_SR = int(sd.query_devices(output_sound_index, 'output')['default_samplerate'])
    NEED_RESAMPLE = True
    print(f"⚠️ 设备默认采样率为 {TARGET_SR} Hz，将实时从 {KOKORO_OFFICIAL_SR} Hz 重采样至 {TARGET_SR} Hz")

start_time = time.time()
# 模型加载部分 (保持原样)
original_cwd = os.getcwd()
sys.path.append(os.path.join(original_cwd, 'audio', 'kokoro'))
from kokoro import KPipeline, KModel
model = KModel(config= "/data/models/kokoro/Kokoro-82M/config.json",
              model="/data/models/kokoro/Kokoro-82M/kokoro-v1_0.pth")
model = model.to('cuda').eval()
pipeline = KPipeline(lang_code='z', device="cuda", model=model)

# ===== 全局状态管理 =====
# 音频堆：存放推理完成待播放的音频 (sid, seq_id, audio_data)
raw_audio_heap = []

current_session_id = 0
expected_seq_id = 0
recive_seq_id = 0

# 核心同步锁：保护所有全局变量和音频设备操作
GLOBAL_LOCK = threading.Lock()
# 打断信号
interrupt_event = threading.Event()

# ===== 1. 统一处理线程 (Producer & Consumer 协调) =====

def tts_manager_worker():
    global expected_seq_id, current_session_id, start_time

    # 创建一个持久的输出流
    # samplerate=TARGET_SR, channels=1 (单声道)
    stream = sd.OutputStream(samplerate=TARGET_SR, channels=1, dtype='float32',device=output_sound_index)
    stream.start()
    # 定义每块写入的大小 (比如 1024 帧，约 23ms)
    CHUNK_SIZE = 1024
    print("🚀 异步播放流已启动...")

    while True:
        audio_to_play = None
        this_sid = -1

        with GLOBAL_LOCK:
            if raw_audio_heap:
                top_sid, top_seq, audio_data = raw_audio_heap[0]

                # A: 丢弃过时数据
                if top_sid < current_session_id:
                    heapq.heappop(raw_audio_heap)
                    continue

                # B: 匹配当前序号
                if top_sid == current_session_id and top_seq == expected_seq_id:
                    _, _, audio_to_play = heapq.heappop(raw_audio_heap)
                    this_sid = top_sid

        if audio_to_play is not None:
            # --- 关键修改：切片式写入 ---
            # 将 numpy 数组按 CHUNK_SIZE 切分
            num_samples = len(audio_to_play)
            print(F'首句TTS时间为：{time.time() - start_time}s')
            for i in range(0, num_samples, CHUNK_SIZE):
                # 每一小块写入前，都检查一次打断信号
                if interrupt_event.is_set() or this_sid != current_session_id:
                    print(f"🛑 物理打断执行：丢弃 Session {this_sid} 剩余音频")
                    stream.stop()  # 立即清空声卡缓冲区
                    stream.start() # 重新启动流准备接收新声
                    break

                chunk = audio_to_play[i : i + CHUNK_SIZE]
                # 如果最后一块不够大，补齐它或者直接写
                stream.write(chunk)
            else:
                # 只有完整播完（没有被 break），才增加序号
                with GLOBAL_LOCK:
                    expected_seq_id += 1
        else:
            # 如果没有音频，且当前处于打断状态，再次确保流是空的
            if interrupt_event.is_set():
                stream.stop()
                stream.start()
            time.sleep(0.01)
# 启动管理线程
threading.Thread(target=tts_manager_worker, daemon=True).start()

# ===== 2. 接口层 =====

app = FastAPI()

@app.post("/v1")
async def receive_tts_text(request: Request):
    global current_session_id, expected_seq_id, recive_seq_id, start_time

    body = await request.json()
    text = body.get("text", "").strip()
    is_new_talk = bool(body.get("interrupt", False))

    print(f"收到请求：text='{text}', interrupt={is_new_talk}")
    if not text: return {"status": "empty"}

    # 1. 处理打断逻辑 (这部分必须加锁)
    with GLOBAL_LOCK:
        if is_new_talk:
            start_time = time.time()
            interrupt_event.set()
            # 这里不需要专门调用 sd.stop() 了，
            # worker 线程检测到信号后会操作 stream.stop()

            current_session_id += 1
            expected_seq_id = 0
            recive_seq_id = 0
            raw_audio_heap.clear()

            interrupt_event.clear()

        # 锁定当前请求的 Session ID
        this_sid = current_session_id
        # 注意：这里我们给这一整段文本分配一个起始序号
        # 如果一段话会产生多个音频块，我们需要让它们连续
        start_seq = recive_seq_id

    # 2. 推理过程 (直接写在接口函数里，不加锁，否则播放线程会卡死)
    try:
        # 记录内部产生的小块序号
        internal_seq = start_seq
        generator = pipeline(text, voice=VOICE_NAME, speed=1.0)
        duration = 0.0

        for _, _, audio in generator:
            # 【关键】检查在这个循环过程中，是否有新请求进来把 session 刷掉了
            if interrupt_event.is_set() or this_sid != current_session_id:
                print(f"🚫 正在推理时被中止: sid={this_sid}")
                return {"status": "interrupted"}

            # 处理音频
            wav_data = audio.numpy() if hasattr(audio, 'numpy') else audio
            resampled = resample_poly(wav_data, up=int(TARGET_SR), down=int(KOKORO_OFFICIAL_SR)).astype(np.float32)

            # 【关键】只在推入堆的一瞬间加锁
            with GLOBAL_LOCK:
                if this_sid == current_session_id:
                    heapq.heappush(raw_audio_heap, (this_sid, internal_seq, resampled))
                    duration += len(resampled) / TARGET_SR
                    print(f"📦 已入堆: sid={this_sid}, seq={internal_seq}")
                    internal_seq += 1

        # 推理完后更新全局接收序号，供下一个文本片段使用
        with GLOBAL_LOCK:
            if this_sid == current_session_id:
                recive_seq_id = internal_seq

    except Exception as e:
        print(f"推理错误: {e}")
        return {"status": "error", "msg": str(e)}

    return {"status": "ok", "last_seq": internal_seq - 1, "audio_time": duration}

if __name__ == "__main__":
    generator = pipeline("发音服务已启动", voice=VOICE_NAME, speed=1.0)
    for _, _, audio in generator:
        wav = audio.numpy()
        if isinstance(wav, torch.Tensor):
            wav_data = wav.view(-1).cpu().numpy()
        else:
            wav_data =wav
        data_resampled = resample_poly(wav_data, up=TARGET_SR, down=KOKORO_OFFICIAL_SR)
        # print("▶️ 播放音频...")
        # sd.play(data_resampled, samplerate=TARGET_SR,device=output_sound_index)
    uvicorn.run(app, host="127.0.0.1", port=28185, log_level="warning")