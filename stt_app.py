
import os
from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse

import ast
import time
import json
import traceback
import logging
import threading
from datetime import datetime
from opencc import OpenCC
from RealtimeSTT import AudioToTextRecorder
import concurrent.futures
import numpy as np

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

last_recorded_rms = 0.0
last_recorded_rms_lock = threading.Lock()


def _stt_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _stt_trace(stage, **fields):
    field_text = ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    suffix = f", {field_text}" if field_text else ""
    print(f"[{_stt_timestamp()}] STT服务链路: stage={stage}{suffix}")


def update_last_recorded_rms(chunk):
    global last_recorded_rms
    try:
        audio = np.frombuffer(chunk, dtype=np.int16)
        if audio.size == 0:
            rms = 0.0
        else:
            audio_float = audio.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(audio_float * audio_float)))
        with last_recorded_rms_lock:
            last_recorded_rms = rms
    except Exception as exc:
        print(f"update_last_recorded_rms error: {exc}")


def get_last_recorded_rms():
    with last_recorded_rms_lock:
        return last_recorded_rms


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
        webrtc_sensitivity=1, silero_sensitivity=0.2,
        faster_whisper_vad_filter=False,
        post_speech_silence_duration=0.2,
        silero_deactivity_detection=False,
        device=stt_device,
        spinner=False,
        level=logging.WARNING,
        on_recorded_chunk=update_last_recorded_rms,
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
        self.output_utterance_id = 0
        self.utterance_id = 0
        self.recoder_status = "<REC_STOP>"

    def reset(self):
        self.output_text = None
        self.output_utterance_id = 0

    def stop_record(self):
        if self.recoder_status == "<REC_START>":
            stop_start = time.perf_counter()
            _stt_trace("stop_record_start", status=self.recoder_status)
            print("STTTimeoutWrapper: Abort recoder")
            if hasattr(self.recorder, "set_enable_transcribe"):
                self.recorder.set_enable_transcribe(False)
            self.recorder.abort()
            if self.recoder_thread is not None:
                self.recoder_thread.join()
            if hasattr(self.recorder, "set_enable_transcribe"):
                self.recorder.set_enable_transcribe(True)
            _stt_trace(
                "stop_record_done",
                elapsed=round(time.perf_counter() - stop_start, 6),
                output_text=self.output_text,
                utterance_id=self.output_utterance_id,
            )
        self.recoder_status = "<REC_STOP>"

    def record(self):
        record_start = time.perf_counter()
        _stt_trace("record_thread_start")
        self.output_text = self.recorder.text()
        _stt_trace(
            "record_text_returned",
            elapsed=round(time.perf_counter() - record_start, 6),
            output_text=self.output_text,
        )
        if self.output_text:
            self.utterance_id += 1
            self.output_utterance_id = self.utterance_id
        print(f"STTTimeoutWrapper: output_text {self.output_text}")
        self.recoder_status = "<REC_STOP>"

    def start(self, prompt=None):
        self.reset()

        if prompt and hasattr(self.recorder, "set_global_prompt"):
            self.recorder.set_global_prompt(prompt)
        elif prompt:
            print("Recorder 不支持 set_global_prompt，跳过全局提示词设置")

        self.recoder_status = "<REC_START>"
        _stt_trace("start_record", prompt=prompt)
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

    def get_output_utterance_id(self):
        return self.output_utterance_id


recorder_timeout = STTTimeoutWrapper(recorder)

tts_agent = create_tts_agent()
tts_sound(tts_agent, "，，机器人语音输入模块加载完毕", "zh")
#tts_sound(tts_agent, "，，夸父机器人P4-28语音输入模块加载完毕", "zh")
#tts_sound(tts_agent, "，，已经启动高性能计算加速", "zh")
#tts_sound(tts_agent, "，，已经启动 G P U 计算加速", "zh")

print("Initilization completed!")


async def _exec(task, lang, text, timeout):
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
    utterance_id = 0
    if task == "set_language":
        set_recorder_language(lang)
        out_text = "Set language success"
    elif task == "speech_to_text":
        set_recorder_language(lang)
        if text != "":
            def get_text(text):
                #time.sleep(15)
                return text
            out_text = run_get_text_with_timeout(get_text, text, timeout=timeout)
        else:
            out_text = recorder.text()
            #out_text = run_stt_with_timeout(recorder.text, timeout=timeout)
            if lang == "zh":
                out_text = cc.convert(out_text)
    elif task == "speech_to_text_async":
        set_recorder_language(lang)
        try:
            recorder_timeout.text(timeout)
            out_text = recorder_timeout.get_output_text()
            utterance_id = recorder_timeout.get_output_utterance_id()
        except Exception as e:
            traceback.print_exc()
            raise e

        if out_text is not None:
            if lang == "zh":
                out_text = cc.convert(out_text)
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
            utterance_id = recorder_timeout.get_output_utterance_id()
        except Exception as e:
            traceback.print_exc()
            raise e
        if out_text is None:
            out_text = ""
        else:
            recorder_timeout.reset()
        if lang == "zh":
            out_text = cc.convert(out_text)
    elif task == "get_last_rms":
        out_text = f"{get_last_recorded_rms():.6f}"
    else:
        out_text = f"Unsupported task: {task}"

    print("out_text:", out_text)
    return out_text, utterance_id


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

        out_text, utterance_id = await _exec(task, lang, text, timeout)

        return JSONResponse(content={"out_text": str(out_text), "utterance_id": utterance_id})

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

        out_text, _ = await _exec(task, lang, text, timeout)

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
