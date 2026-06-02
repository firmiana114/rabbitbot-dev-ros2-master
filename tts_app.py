
import os
from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse

import ast
import json
import random
import numpy as np
import soundfile as sf
from rabbitbot.audio.run_tts_espnet import EspnetTTS
from rabbitbot.audio.unitree_g1_tts import UnitreeG1TTS

from openai_chat_app import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessage,
    ChatUsage
)


app = FastAPI()


def env_enabled(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


tts_backend = os.environ.get("RABBITBOT_TTS_BACKEND", "unitree").strip().lower()
if tts_backend in {"g1", "robot"}:
    tts_backend = "unitree"
print(f"RABBITBOT_TTS_BACKEND: {tts_backend}")

lang = "zh"
print(f"language: {lang}")
if tts_backend == "unitree":
    out_device_id = None
    print("Initilize UnitreeG1TTS ...")
    tts_engine = UnitreeG1TTS(lang=lang)
else:
    out_device_id = os.environ.get("OUTPUT_DEVICE_INDEX")
    out_device_id = int(out_device_id) if out_device_id and out_device_id.strip() else None
    print(f"out_device_id: {out_device_id}")
    print("Initilize EspnetTTS ...")
    tts_engine = EspnetTTS(lang=lang, device_id=out_device_id, debug_mode=False)
tts_engine.init_async_workers()
preload_fast_sound = env_enabled("RABBITBOT_TTS_FAST_SOUND_PRELOAD", True)
startup_speech = env_enabled("RABBITBOT_TTS_STARTUP_SPEECH", True)
print(f"RABBITBOT_TTS_FAST_SOUND_PRELOAD: {preload_fast_sound}")
print(f"RABBITBOT_TTS_STARTUP_SPEECH: {startup_speech}")

warmup_enabled = env_enabled("RABBITBOT_TTS_WARMUP", True)
print(f"RABBITBOT_TTS_WARMUP: {warmup_enabled}")
if warmup_enabled:
    # 启动阶段静默预热：即使关闭了启动播报(STARTUP_SPEECH)与快捷音预生成(FAST_SOUND_PRELOAD)，
    # 也在此吸收 jieba/kokoro/librosa 三处首次冷启动，避免首句真实播报延迟约 6~7 秒。无声音输出。
    # 此处异步 worker 仍空闲，warmup 同步执行不会与合成线程并发使用 kokoro pipeline。
    tts_engine.warmup()

before_text = ""

if startup_speech:
    if lang == "zh":
        tts_engine.put_text(f"{before_text}你好，我是智元机二机器人")
        tts_engine.put_text(f"{before_text}正在进行声音测试")
        tts_engine.put_text(f"{before_text}我们可以带您参观智元公司的数据采集厂")
        #tts_engine.close()
        #exit(1)


def rms(y):
    return np.sqrt(np.mean(y**2))

def normalize_rms(y, target_rms=0.2):   # 0.1 ≈ −20 dBFS
    gain = target_rms / (rms(y) + 1e-8)
    return y * gain

class FastSound(object):

    def __init__(self, tts_engine, preload=True):
        self.tts_engine = tts_engine
        self.preload = preload and getattr(tts_engine, "supports_wav_output", True)
        if preload and not self.preload:
            print("FastSound: 当前 TTS 后端不支持本地 wav 预生成，已切换为文本直发模式")
        self.wav_list = {
            "welcome": [],
            "ready": [],
            "think": [],
            "thinkwhy": [],
            "thinkstatement": [],
            "thinkother": [],
            "sorry": [],
            "cancel": [],
            "navichat": [],
            "naviguide": [],
            "introguide": [],
            "unknown": [],
        }
        self.text_list = {stype: [] for stype in self.wav_list}

    def add_text(self, text, stype, speed):
        self.text_list[stype].append((text, speed))
        if self.preload:
            wav_data = self.tts_engine.text_to_wav(text, speed)
            self.wav_list[stype].append((text, wav_data))
        else:
            print(f"FastSound: 跳过启动预生成 stype={stype}, text={text}")

    def add_wav_file(self, filepath, text, stype):
        data, samplerate = sf.read(filepath, dtype='float32')
        data = normalize_rms(data)
        print(f"add_wav_file: {samplerate}")
        #data = data.astype(np.float32)
        self.wav_list[stype].append((text, data))
        self.tts_engine.sound_wav(data, 16000)

    def random_tts(self, stype):
        wav_lst = self.wav_list.get(stype, [])
        text_lst = self.text_list.get(stype, [])
        if wav_lst:
            rand_num = random.randint(0, len(wav_lst)-1)
            print(f"FastSound: rand_num {rand_num}")
            text, wav_data =  wav_lst[rand_num]
            if text !=  "，，":
                self.tts_engine.put_wav(wav_data)
        elif text_lst:
            rand_num = random.randint(0, len(text_lst)-1)
            print(f"FastSound: lazy rand_num {rand_num}")
            text, speed = text_lst[rand_num]
            if text !=  "，，":
                if getattr(self.tts_engine, "supports_wav_output", True):
                    wav_data = self.tts_engine.text_to_wav(text, speed)
                    self.wav_list[stype].append((text, wav_data))
                    self.tts_engine.put_wav(wav_data)
                else:
                    print(f"FastSound: 当前 TTS 后端直接播报文本 stype={stype}, text={text}")
                    self.tts_engine.put_text(text)
        else:
            print(f"FastSound: 未配置音频类型 {stype}")


fast_sound = FastSound(tts_engine, preload=preload_fast_sound)
NORMAL_SOUND_SPEED = 1.0
SLOW_SOUND_SPEED = 0.9
fast_sound.add_text(f"{before_text}欢迎来到智元公司，下面我来带你参观展厅，当然我也可以和你聊聊天。你有什么需要吗？", "welcome", NORMAL_SOUND_SPEED)

#fast_sound.add_text(f"{before_text}我准备好了，可以和我说话", "ready")
#fast_sound.add_text(f"{before_text}我已经就位，来和我讲一句话吧", "ready")
#fast_sound.add_text(f"{before_text}我很厉害哟，快来和我聊天吧", "ready")
#fast_sound.add_text(f"{before_text}要不要我带你六一六，给你介绍一下智元公司", "ready")
fast_sound.add_text(f"{before_text}要不要我带你走一走，给你介绍一下智元公司", "ready", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}要不要和我聊聊天", "ready", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}你还有什么想知道的吗？", "ready", NORMAL_SOUND_SPEED)
#fast_sound.add_text(f"{before_text}欢迎来到智元机器人，你需要什么帮助吗？", "ready")

# fast_sound.add_text(f"{before_text}我听到了，让我想一想", "think")
# fast_sound.add_text(f"{before_text}好的，我可能要思考一会儿", "think")
# fast_sound.add_text(f"{before_text}收到，麻烦您稍等我一会", "think")
# fast_sound.add_text(f"{before_text}我听到您的声音太好听了，夸一下", "think")
# fast_sound.add_text(f"{before_text}我有点笨，要花点时间想一下", "think")

fast_sound.add_text(f"{before_text}好的，好的", "think", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}没问，题的", "think", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}可以的，没问题", "think", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}好呀，好呀", "think", SLOW_SOUND_SPEED)
fast_sound.add_text("，，", "think", SLOW_SOUND_SPEED)

fast_sound.add_text(f"{before_text}我想一下", "thinkwhy", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}怎么说呢", "thinkwhy", SLOW_SOUND_SPEED)
#fast_sound.add_wav_file("data/tts/how_to_say_16k.wav", f"{before_text}怎么说呢", "thinkwhy")
fast_sound.add_text(f"{before_text}我先试试理解", "thinkwhy", SLOW_SOUND_SPEED)
fast_sound.add_text("，，", "thinkwhy", SLOW_SOUND_SPEED)

fast_sound.add_text(f"{before_text}你说的对", "thinkstatement", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}这是一个好观点", "thinkstatement", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}给你点个赞", "thinkstatement", SLOW_SOUND_SPEED)
fast_sound.add_text("，，", "thinkstatement", SLOW_SOUND_SPEED)

fast_sound.add_text(f"{before_text}好的，好的", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}我听到了", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}收到，收到", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}好耶，好耶", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}了解，了解", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}没问题，没问题", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text(f"{before_text}在的，在的", "thinkother", SLOW_SOUND_SPEED)
fast_sound.add_text("，，", "thinkother", SLOW_SOUND_SPEED)

fast_sound.add_text(f"{before_text}对不起，我听不太清楚，可以再说一次吗", "sorry", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}抱歉，我可能听不太清，请重复一遍", "sorry", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}不好意思，我没听清楚你的话，可以再说一次吗", "sorry", NORMAL_SOUND_SPEED)

fast_sound.add_text(f"{before_text}我无法回答这个问题。我只是个导览机器人。请问你对展厅哪个板块感兴趣呢？我可以带你去看看", "unknown", NORMAL_SOUND_SPEED)

fast_sound.add_text(f"{before_text}好的，这个命令已经取消了", "cancel", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}已经成功取消命令", "cancel", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}好的，我收到了你的取消指令", "cancel", NORMAL_SOUND_SPEED)

fast_sound.add_text(f"{before_text}我们边走边聊，好吗？", "navichat", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}现在可以和我聊天哟", "navichat", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}我走路可能要一点时间，可以和我闲聊吗？", "navichat", NORMAL_SOUND_SPEED)

fast_sound.add_text(f"{before_text}好的，请跟我来", "naviguide", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}好的，下面我带你去", "naviguide", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}好的，我们出发吧", "naviguide", NORMAL_SOUND_SPEED)

fast_sound.add_text(f"{before_text}这一块你有什么想了解的吗？", "introguide", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}你还想了解什么吗？", "introguide", NORMAL_SOUND_SPEED)
fast_sound.add_text(f"{before_text}你还想让我介绍什么吗？", "introguide", NORMAL_SOUND_SPEED)

if startup_speech and lang == "zh":
    #tts_engine.put_text(f"{before_text}机器人语音输出模块加载完毕")
    tts_engine.put_text(f"{before_text}机器人语音输出模块加载完毕")
elif startup_speech and lang == "en":
    import nltk
    nltk.download('averaged_perceptron_tagger_eng')
    tts_engine.put_text("P4-28: Sound module setup completed")

print("Initilization completed!")

async def _exec(task, lang, text, timeout) -> str:
    if task == "set_language":
        tts_engine.set_lang(lang)
        out_text = "Set language success"
    elif task == "text_to_speech":
        tts_engine.set_lang(lang)
        #tts_engine.sound(text)
        tts_index = tts_engine.put_text(text)
        out_text = str(tts_index)
    elif task == "stop":
        soft_stop = False
        if text == "soft":
            soft_stop = True
        tts_engine.stop_wait_restart(soft_stop)
        out_text = "TTS finished"
    elif task == "wait_speech":
        tts_engine.wait_wav_queue()
        out_text = "TTS finished"
    elif task == "get_wav_count":
        wav_count = tts_engine.get_wav_count()
        out_text = str(wav_count)
    elif task == "get_play":
        tts_index = int(text)
        play = tts_engine.get_play(tts_index)
        out_text = str(play)
    elif task.startswith("fast_sound"):
        stype = task.split("_")[-1]
        fast_sound.random_tts(stype)
        out_text = "Fast sound"
    else:
        out_text = f"Unsupported task: {task}"
    return out_text

@app.post("/exec")
async def exec_api(task: str = Form(...)):
    try:
        print(f"Get data: {task}")
        input_dict = ast.literal_eval(task)
        task = input_dict["task"]
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
