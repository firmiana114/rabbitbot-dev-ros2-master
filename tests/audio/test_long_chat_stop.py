
import re
import time
import threading
from agno.agent import Agent
from rabbitbot.agno_agents.sound import RealtimeSTT, RealtimeTTS
from rabbitbot.tools.sound_agno import (
    tts_sound, tts_wait, tts_stop, tts_fast, tts_get_wav_count,
    stt_start_async,
    stt_get_text_async,
    stt_stop_async,
)
from rabbitbot.provider import (
    create_stt_agent,
    create_tts_agent,
)

def tts_long_text_with_stt_stop(tts_agent, text, stt_agent):
    #sentences = text.split("。").split("，")
    sentences = re.split(r'[，。]', text)
    sentences = [sentence for sentence in sentences if sentence.strip()]

    tts_stop_event = threading.Event()
    tts_stop_stop_event = threading.Event()

    def tts_stop_task():
        print("监听线程开始")
        stt_start_async(stt_agent)
        while True:
            time.sleep(0.2)
            out_text = stt_get_text_async(stt_agent)
            if out_text != "":
                print("收到命令：", out_text)
                if out_text.startswith("停止") or "停" in out_text:
                    tts_stop_event.set()
                    break
                else:
                    stt_start_async(stt_agent)
            if tts_stop_stop_event.is_set():
                print("监听线程被停止")
                break
        print("监听线程退出")
        stt_stop_async(stt_agent)

    tts_stop_thread = threading.Thread(target=tts_stop_task)
    tts_stop_thread.start()

    for sentence in sentences:
        if sentence != "":
            tts_sound(tts_agent, sentence, "zh")
            time.sleep(1)
        #tts_wait(tts_agent)
    while True:
        time.sleep(0.2)
        if tts_stop_event.is_set():
            tts_stop(tts_agent)
            break
        if tts_get_wav_count(tts_agent) == 0:
            break

    tts_stop_stop_event.set()
    tts_stop_thread.join()

if __name__ == "__main__":
    stt_agent = create_stt_agent()
    tts_agent = create_tts_agent()

    text = "深圳是中国广东省的一个经济特区，也是中国的四大一线城市之一。这座城市以高科技产业闻名，被誉为“中国硅谷”。" \
        "在深圳，你可以看到许多高新技术企业如华为、腾讯等。除了科技产业之外，深圳还拥有丰富的历史文化遗产。" \
        "例如，在深圳市中心的罗湖口岸附近有著名的关帝庙，它建于明朝时期，已有几百年的历史了。" \
        "还有大芬油画村，这里有许多画廊和艺术工作室，展示了各种风格的艺术作品。" \
        "欢迎您来深圳旅游，体验新时代的高新城市。"
    
    #text = "深圳是中国广东省的一个经济特区，也是中国的四大一线城市之一。" \
    #    "在深圳，你可以看到许多高新技术企业如华为、腾讯等。除了科技产业之外，深圳还拥有丰富的历史文化遗产。"
    text = "IROS的会议时间是"

    tts_long_text_with_stt_stop(tts_agent, text, stt_agent)
