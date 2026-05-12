
import os
from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse

import ast
import time
import json
import traceback
import logging
import threading
import wave
import pyaudio
from opencc import OpenCC
from RealtimeSTT import AudioToTextRecorder
import concurrent.futures

DEBUG_SAVE_AUDIO = True  # 保存录音调试文件
DEBUG_AUDIO_DIR = "/tmp/stt_debug"
import os
os.makedirs(DEBUG_AUDIO_DIR, exist_ok=True)

def debug_list_audio_devices():
    """列出所有 PyAudio 设备"""
    print("=" * 60)
    print("PyAudio 设备列表:")
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 or info["maxOutputChannels"] > 0:
            io_info = []
            if info["maxInputChannels"] > 0:
                io_info.append(f"输入({info['maxInputChannels']}ch)")
            if info["maxOutputChannels"] > 0:
                io_info.append(f"输出({info['maxOutputChannels']}ch)")
            print(f"  [{i}] {info['name']} - {', '.join(io_info)}")
    p.terminate()
    print("=" * 60)

from openai_chat_app import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessage,
    ChatUsage
)

from rabbitbot.provider import create_tts_agent
from rabbitbot.tools.sound_agno import tts_sound


app = FastAPI()

in_device_id = os.environ.get("INPUT_DEVICE_INDEX")
in_device_id = int(in_device_id) if in_device_id and in_device_id.strip() else None
print(f"in_device_id: {in_device_id}")

# 调试：列出设备
debug_list_audio_devices()

class NoInputRecorder:
    def __init__(self):
        self.language = "zh"
        self.global_prompt = None

    def set_language(self, language):
        self.language = language

    def set_global_prompt(self, prompt):
        self.global_prompt = prompt

    def set_enable_transcribe(self, enabled):
        pass

    def abort(self):
        pass

    def text(self):
        print("NoInputRecorder: 无输入设备，返回空识别结果")
        return ""


if in_device_id is None:
    print("未设置 INPUT_DEVICE_INDEX，STT 服务以无输入设备模式启动。")
    recorder = NoInputRecorder()
else:
    print("Initilize RealtimeSTT ...")
    default_models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
    local_model = os.environ.get(
        "STT_MODEL_PATH",
        os.path.join(default_models_dir, "faster-whisper", "Systran", "faster-whisper-base")
    )
    model = local_model if os.path.exists(local_model) else "base"
    print(f"stt_model: {model}")
    stt_device = os.environ.get("STT_DEVICE", "cpu")
    stt_compute_type = os.environ.get(
        "STT_COMPUTE_TYPE",
        "int8" if stt_device == "cpu" else "default"
    )
    print(f"stt_device: {stt_device}, stt_compute_type: {stt_compute_type}")
    recorder = AudioToTextRecorder(
        model=model,
        language="zh",
        compute_type=stt_compute_type,
        input_device_index=in_device_id,
        sample_rate=16000, buffer_size=512,
        webrtc_sensitivity=2, silero_sensitivity=0,
        faster_whisper_vad_filter=False,
        post_speech_silence_duration=0.2,
        silero_deactivity_detection=False,
        device=stt_device,
        spinner=False,
        level=logging.WARNING
    )

cc = OpenCC('t2s')

if False:
    while True:
        print("请对麦克风说话")
        text = recorder.text()
        text = cc.convert(text)
        print(f"识别文字：{text}")

class STTTimeoutWrapper(object):

    def __init__(self, recorder):
        self.recorder = recorder
        self.recoder_thread = None
        self.output_text = None
        self.recoder_status = "<REC_STOP>"

    def reset(self):
        self.output_text = None

    def stop_record(self):
        if self.recoder_status == "<REC_START>":
            print("STTTimeoutWrapper: Abort recoder")
            if hasattr(self.recorder, "set_enable_transcribe"):
                self.recorder.set_enable_transcribe(False)
            else:
                print("Recorder 不支持 set_enable_transcribe，跳过转写开关")
            if hasattr(self.recorder, "abort"):
                self.recorder.abort()
            else:
                print("Recorder 不支持 abort，跳过录音中止")
            if self.recoder_thread is not None:
                self.recoder_thread.join(timeout=2)
            if hasattr(self.recorder, "set_enable_transcribe"):
                self.recorder.set_enable_transcribe(True)
        self.recoder_status = "<REC_STOP>"

    def record(self):
        self.output_text = self.recorder.text()
        print(f"STTTimeoutWrapper: output_text {self.output_text}")
        self.recoder_status = "<REC_STOP>"

    def start(self, prompt=None):
        self.reset()

        if prompt and hasattr(self.recorder, "set_global_prompt"):
            self.recorder.set_global_prompt(prompt)
        elif prompt:
            print("Recorder 不支持 set_global_prompt，跳过全局提示词设置")

        self.recoder_status = "<REC_START>"
        self.recoder_thread = threading.Thread(target=self.record)
        self.recoder_thread.start()

    def text(self, timeout):
        self.start()

        time_sec = 0
        while self.output_text is None:
            time.sleep(1)
            time_sec += 1
            print(f"time_sec: {time_sec}")
            if time_sec > timeout:
                break
        print(f"output_text: {self.output_text}")

        if self.recoder_status != "<REC_STOP>":
            self.stop_record()

    def get_status(self):
        return self.recoder_status

    def get_output_text(self):
        return self.output_text


recorder_timeout = STTTimeoutWrapper(recorder)

tts_agent = create_tts_agent()
tts_sound(tts_agent, "，，机器人语音输入模块加载完毕", "zh")
#tts_sound(tts_agent, "，，夸父机器人P4-28语音输入模块加载完毕", "zh")
#tts_sound(tts_agent, "，，已经启动高性能计算加速", "zh")
#tts_sound(tts_agent, "，，已经启动 G P U 计算加速", "zh")

print("Initilization completed!")


async def _exec(task, lang, text, timeout) -> str:
    def set_recorder_language(language):
        if hasattr(recorder, "set_language"):
            recorder.set_language(language)
        else:
            print(f"Recorder 不支持 set_language，继续使用初始化语言: {language}")

    def run_get_text_with_timeout(func, text, timeout=10):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func, text)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return "Timeout"

    def run_stt_with_timeout(func, timeout=10):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return "Timeout"

    out_text = None
    if task == "set_language":
        set_recorder_language(lang)
        out_text = "Set language success"
    elif task == "speech_to_text":
        set_recorder_language(lang)
        if text != "":
            def get_text(text):
                return text
            out_text = run_get_text_with_timeout(get_text, text, timeout=timeout)
        else:
            print(f"[STT] >>> 开始录音，等待语音输入（超时: {timeout}秒）...")
            
            # 使用线程超时保护录音
            result_holder = [None]
            def record_with_timeout():
                try:
                    result_holder[0] = recorder.text()
                    print(f"[STT] >>> record_with_timeout 完成，结果: '{result_holder[0]}'")
                except Exception as e:
                    print(f"[STT] >>> record_with_timeout 异常: {e}")
                    traceback.print_exc()
                    result_holder[0] = ""
            
            record_thread = threading.Thread(target=record_with_timeout)
            record_thread.start()
            record_thread.join(timeout=timeout)
            
            if record_thread.is_alive():
                print("[STT] >>> 录音超时，强制停止")
                if hasattr(recorder, 'abort'):
                    recorder.abort()
                out_text = result_holder[0] if result_holder[0] else ""
            else:
                out_text = result_holder[0] if result_holder[0] else ""
            
            print(f"[STT] >>> 录音转换完成，原始结果: '{out_text}'")
            if out_text and out_text.strip():
                print(f"[STT] >>> 识别到有效文字，准备转换...")
            else:
                print(f"[STT] >>> 未识别到语音或返回为空")
            if lang == "zh":
                out_text = cc.convert(out_text)
                print(f"[STT] >>> 繁简转换完成: '{out_text}'")
    elif task == "speech_to_text_async":
        set_recorder_language(lang)
        try:
            print(f"[STT] >>> speech_to_text_async 开始录音，超时设置: {timeout}秒")
            recorder_timeout.text(timeout)
            out_text = recorder_timeout.get_output_text()
            print(f"[STT] >>> speech_to_text_async 录音完成，原始结果: '{out_text}'")
        except Exception as e:
            traceback.print_exc()
            raise e

        if out_text is not None:
            if out_text.strip():
                print(f"[STT] >>> speech_to_text_async 识别到有效文字")
            else:
                print(f"[STT] >>> speech_to_text_async 未识别到语音或返回为空")
            if lang == "zh":
                out_text = cc.convert(out_text)
                print(f"[STT] >>> speech_to_text_async 繁简转换完成: '{out_text}'")
        else:
            out_text = ""
    elif task == "start_async":
        set_recorder_language(lang)
        try:
            recorder_timeout.start(text)
        except Exception as e:
            traceback.print_exc()
            raise e
        out_text = "Started"
    elif task == "stop_async":
        #recorder.stop()
        try:
            recorder_timeout.stop_record()
        except Exception as e:
            traceback.print_exc()
            raise e
        out_text = "Stopped"
    elif task == "get_status_async":
        try:
            out_text = recorder_timeout.get_status()
        except Exception as e:
            traceback.print_exc()
            raise e
    elif task == "get_text_async":
        try:
            out_text = recorder_timeout.get_output_text()
        except Exception as e:
            traceback.print_exc()
            raise e
        if out_text is None:
            out_text = ""
        else:
            recorder_timeout.reset()
        if lang == "zh":
            out_text = cc.convert(out_text)
    else:
        out_text = f"Unsupported task: {task}"

    print("out_text:", out_text)
    return out_text


@app.post("/exec")
async def exec_api(task: str = Form(...)):
    try:
        input_dict = ast.literal_eval(task)
        task = input_dict["task"]
        if not task.startswith("get_"):
            print(f"Get data")
            print(task)
        lang = input_dict["lang"]
        text = input_dict["text"]
        timeout = input_dict["timeout"]

        out_text = await _exec(task, lang, text, timeout)

        return JSONResponse(content={"out_text": str(out_text)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    try:
        last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "Hello!")
        print(f"Received request: last_user_msg")
        print(last_user_msg)
        input_dict = json.loads(last_user_msg)
        task = input_dict["task"]
        lang = input_dict["lang"]
        text = input_dict["text"]
        timeout = input_dict["timeout"]
        print(f"Received request: task={task}, lang={lang}, text={text}")

        out_text = await _exec(task, lang, text, timeout)

        response_content = out_text
        print(f"Response content: {out_text}")

        response = ChatCompletionResponse(
            id="chatcmpl-12345",
            object="chat.completion",
            created=1677858242, # 模拟时间戳
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=response_content),
                    finish_reason="stop"
                )
            ],
            usage=ChatUsage(
                prompt_tokens=sum(len(m.content.split()) for m in request.messages),
                completion_tokens=len(response_content.split()),
                total_tokens=sum(len(m.content.split()) for m in request.messages) + len(response_content.split())
            )
        )

        return response

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
