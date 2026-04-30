#!/usr/bin/env python3
"""简单的麦克风录制和回放测试"""

import pyaudio
import wave
import sys

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
RECORD_SECONDS = 5
OUTPUT_FILE = "test_recording.wav"


def find_default_input_device():
    """自动查找可用的输入设备（优先 PulseAudio 和 default）"""
    p = pyaudio.PyAudio()
    # 优先查找支持输入的设备
    candidates = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            candidates.append((i, info))
    p.terminate()

    if not candidates:
        return None, None

    # 优先选择 PulseAudio 或 default 设备（兼容性最好）
    for idx, info in candidates:
        name = info["name"].lower()
        if "pulse" in name or "default" in name:
            return idx, info

    # 其次选择名称包含 mic、input、usb 等关键词的设备
    for idx, info in candidates:
        name = info["name"].lower()
        if any(k in name for k in ["mic", "input", "usb", "bt67", "wireless"]):
            return idx, info

    return candidates[0]


def list_devices():
    """列出所有音频设备"""
    p = pyaudio.PyAudio()
    print("可用音频设备:")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        has_input = info["maxInputChannels"] > 0
        has_output = info["maxOutputChannels"] > 0
        if has_input or has_output:
            channels = []
            if has_input:
                channels.append(f"输入({info['maxInputChannels']}ch)")
            if has_output:
                channels.append(f"输出({info['maxOutputChannels']}ch)")
            print(f"  [{i}] {info['name']}")
            print(f"      采样率: {info['defaultSampleRate']}, {' '.join(channels)}, hw:{info.get('hostApi', 0)}")
    p.terminate()


def record_audio(device_index=None):
    """录制音频"""
    p = pyaudio.PyAudio()

    # 自动查找设备
    if device_index is None:
        device_index, info = find_default_input_device()
        if device_index is None:
            print("错误：未找到可用的输入设备！")
            p.terminate()
            return None
        print(f"自动选择设备: {info['name']} [index={device_index}]")

    # 获取设备信息
    info = p.get_device_info_by_index(device_index)
    channels = max(1, int(info["maxInputChannels"]))
    rate = int(info["defaultSampleRate"])

    print(f"设备: {info['name']}")
    print(f"  输入通道: {info['maxInputChannels']} -> 使用 {channels}")
    print(f"  采样率: {rate}")

    print(f"\n正在录制 {RECORD_SECONDS} 秒...")
    print("请对着麦克风说话...\n")

    stream = p.open(
        format=FORMAT,
        channels=channels,
        rate=rate,
        input=True,
        input_device_index=device_index
    )
    
    frames = []
    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
    
    print("录制完成！")

    stream.stop_stream()
    stream.close()

    # 保存为 WAV 文件
    with wave.open(OUTPUT_FILE, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    print(f"已保存到: {OUTPUT_FILE} (通道数: {channels}, 采样率: {rate})")
    p.terminate()
    return OUTPUT_FILE


def play_audio(filename, device_index=None):
    """播放音频文件"""
    p = pyaudio.PyAudio()

    print(f"\n正在播放 {filename}...")

    wf = wave.open(filename, 'rb')
    channels = wf.getnchannels()
    rate = wf.getframerate()

    # 自动查找输出设备
    if device_index is None:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxOutputChannels"] > 0:
                name = info["name"].lower()
                if "pulse" in name or "default" in name:
                    device_index = i
                    break
        if device_index is None:
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["maxOutputChannels"] > 0:
                    device_index = i
                    break

    if device_index is not None:
        info = p.get_device_info_by_index(device_index)
        print(f"输出设备: {info['name']} [index={device_index}]")

    stream = p.open(
        format=p.get_format_from_width(wf.getsampwidth()),
        channels=channels,
        rate=rate,
        output=True,
        output_device_index=device_index
    )

    data = wf.readframes(CHUNK)
    while data:
        stream.write(data)
        data = wf.readframes(CHUNK)

    print("播放完成！")

    stream.stop_stream()
    stream.close()
    wf.close()
    p.terminate()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_devices()
    else:
        # 先列出设备
        list_devices()
        
        # 录制 (使用 Wireless Mic Rx: USB Audio (hw:0,0))
        filename = record_audio(device_index=0)
        
        # 播放
        play_audio(filename)
