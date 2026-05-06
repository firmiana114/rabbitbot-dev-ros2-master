
import re
import time
import json
import os
import random
import threading

from rabbitbot.tools.navi_agno import is_navigating


def tts_sound(tts_agent, text, lang):
    input_dict = {"task": "text_to_speech", "lang": lang, "text": text, "timeout": 30}
    print(input_dict)
    #def sound_agent_run():
    #    tts_agent.run(json.dumps(input_dict))
    #threading.Thread(target=sound_agent_run).start()
    tts_index = tts_agent.run(json.dumps(input_dict))
    return int(tts_index)


def tts_wait(tts_agent):
    input_dict = {"task": "wait_speech", "lang": "", "text": "", "timeout": 30}
    print(input_dict)
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    out_text = tts_agent.run(json.dumps(input_dict))
    return out_text


def tts_stop(tts_agent, soft_stop=False):
    text = ""
    if soft_stop:
        text = "soft"
    input_dict = {"task": "stop", "lang": "", "text": text, "timeout": 30}
    print(input_dict)
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    out_text = tts_agent.run(json.dumps(input_dict))
    return out_text


def tts_fast(tts_agent, type):
    return
    input_dict = {"task": f"fast_sound_{type}", "lang": "", "text": "", "timeout": 30}
    print(input_dict)
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    out_text = tts_agent.run(json.dumps(input_dict))
    return out_text


def tts_get_wav_count(tts_agent):
    input_dict = {"task": "get_wav_count", "lang": "", "text": "", "timeout": 30}
    #print(input_dict)
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    out_text = tts_agent.run(json.dumps(input_dict))
    wav_count = int(out_text)
    return wav_count


def get_interrupt_rms_threshold():
    raw_value = os.getenv("RABBITBOT_INTERRUPT_RMS_THRESHOLD", "0")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        print(f"Invalid RABBITBOT_INTERRUPT_RMS_THRESHOLD={raw_value}, use 0")
        return 0.0


def stt_get_last_rms(stt_agent):
    input_dict = {"task": "get_last_rms", "lang": "zh", "text": "", "timeout": 30}
    try:
        out_text = stt_agent.run(json.dumps(input_dict))
        return float(out_text)
    except Exception as exc:
        print(f"stt_get_last_rms failed: {exc}")
        return None


def is_interrupt_loud_enough(stt_agent):
    threshold = get_interrupt_rms_threshold()
    if threshold <= 0:
        return True
    rms = stt_get_last_rms(stt_agent)
    if rms is None:
        return True
    if rms < threshold:
        print(f"忽略低音量打断: rms={rms:.6f}, threshold={threshold:.6f}")
        return False
    return True


def _is_valid_interrupt_text(text):
    if text is None:
        return False
    text = text.strip()
    if text == "":
        return False
    ignored_texts = {"<REC_TIMEOUT>", "<REC_STOP>", "Timeout", "Started", "Stopped"}
    return text not in ignored_texts


def tts_long_text_with_stt_stop(tts_agent, text, stt_agent, robot, before_text=None):
    sentences = re.split(r'[，；。]', text)

    tts_stop_event = threading.Event()
    tts_stop_stop_event = threading.Event()
    interrupt_text_holder = {"text": ""}

    def tts_stop_task():
        print("监听线程开始")
        stt_start_async(stt_agent)
        while True:
            time.sleep(0.1)  # 缩短检测间隔，提高响应速度
            out_text = stt_get_text_async(stt_agent)
            if _is_valid_interrupt_text(out_text):
                out_text = out_text.strip()
                if not is_interrupt_loud_enough(stt_agent):
                    stt_start_async(stt_agent)
                    continue
                print("收到打断输入：", out_text)
                if not (out_text.startswith("停止") or "停" in out_text):
                    interrupt_text_holder["text"] = out_text
                tts_stop_event.set()
                break
            if tts_stop_stop_event.is_set():
                print("监听线程被停止")
                break
        print("监听线程退出")
        stt_stop_async(stt_agent)

    tts_stop_thread = threading.Thread(target=tts_stop_task)
    tts_stop_thread.start()

    for sentence in sentences:
        if sentence == "":
            continue
        # 每次发送前检查是否收到停止命令
        if tts_stop_event.is_set():
            break
        action_name = None
        if sentence.startswith("[A:"):
            ei = sentence.index("]")
            action_name = sentence[3:ei]
            sentence = sentence[ei+1:]
        sentence = sentence.strip()
        if before_text is not None:
            sentence = before_text + sentence
        tts_index = tts_sound(tts_agent, sentence, "zh")
        if action_name is not None:
            action_with_tts(robot, action_name, tts_agent, tts_index)
        time.sleep(1)
        #tts_wait(tts_agent)
    # 如果循环被 break 退出，说明已收到停止命令，直接停止并清空队列
    if tts_stop_event.is_set():
        tts_stop(tts_agent)
        time.sleep(0.2)
    else:
        # 正常播放完毕
        while True:
            time.sleep(0.05)
            if tts_stop_event.is_set():
                tts_stop(tts_agent)
                time.sleep(0.2)
                break
            if tts_get_wav_count(tts_agent) == 0:
                break

    tts_stop_stop_event.set()
    tts_stop_thread.join()
    return interrupt_text_holder["text"]


def tts_long_text(tts_agent, text, stt_agent, robot, before_text=None):
    sentences = re.split(r'[，；。]', text)

    for sentence in sentences:
        if sentence == "":
            continue
        action_name = None
        if sentence.startswith("[A:"):
            ei = sentence.index("]")
            action_name = sentence[3:ei]
            sentence = sentence[ei+1:]
        sentence = sentence.strip()
        if before_text is not None:
            sentence = before_text + sentence
        tts_index = tts_sound(tts_agent, sentence, "zh")
        if action_name is not None:
            action_with_tts(robot, action_name, tts_agent, tts_index)
        time.sleep(1)
        #tts_wait(tts_agent)


def tts_get_play(tts_agent, tts_index):
    input_dict = {"task": "get_play", "lang": "", "text": f"{tts_index}", "timeout": 30}
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    out_text = tts_agent.run(json.dumps(input_dict))
    return int(float(out_text))


def action_with_tts(robot, action_name, tts_agent, tts_index, timeout=30):
    def _run():
        start_time = time.time()
        while True:
            time.sleep(0.5)
            if tts_get_play(tts_agent, tts_index):
                robot.do_arm(action_name)
                break
            if time.time() - start_time > timeout:
                print(f"action_with_tts: wait tts_index={tts_index} timeout, skip action {action_name}")
                break
    threading.Thread(target=_run, daemon=True).start()


def wait_with_tts(tts_agent, tts_index, timeout=30):
    start_time = time.time()
    while True:
        time.sleep(0.5)
        if tts_get_play(tts_agent, tts_index):
            break
        if time.time() - start_time > timeout:
            print(f"wait_with_tts: wait tts_index={tts_index} timeout")
            break


def audio_input_execute(stt_agent, task, text="", timeout=30):
    input_dict = {"task": task, "lang": "zh", "text": text, "timeout": timeout}
    if not task.startswith("get_"):
        print(input_dict)
    sound_input = json.dumps(input_dict)
    #sound_input = original_task
    if task == "stop":
        def audio_input_stop():
            stt_agent.run(sound_input)
        threading.Thread(target=audio_input_stop).start()
        out_text = "Stop"
    else:
        #run_response = stt_agno_agent.run(sound_input)
        #out_text = run_response.content
        out_text = stt_agent.run(sound_input)
    return out_text


def audio_input_execute_timeout(stt_agent, timeout=30, text=""):
    #out_text = input("请输入语音文字：")
    #return out_text
    print(f"audio_input: timeout {timeout}")
    audio_input_execute(stt_agent, "start_async", text)
    time_sec = 0
    audio_input_status = audio_input_execute(stt_agent, "get_status_async")
    audio_input_text = audio_input_execute(stt_agent, "get_text_async")
    while audio_input_text == "" and audio_input_status == "<REC_START>":
        time.sleep(0.5)
        time_sec += 0.5
        #print(f"audio_input: time_sec {time_sec}, timeout {timeout}")
        if time_sec > timeout:
            audio_input_text = "<REC_TIMEOUT>"
            break
        audio_input_status = audio_input_execute(stt_agent, "get_status_async")
        audio_input_text = audio_input_execute(stt_agent, "get_text_async")
    if audio_input_status == "<REC_STOP>" and audio_input_text == "":
        audio_input_text = "<REC_STOP>"
    if audio_input_text == "<REC_TIMEOUT>":
        audio_input_execute(stt_agent, "stop_async")
    return audio_input_text


async def audio_input_execute_timeout_navi(stt_agent, timeout, navi_tools):
    audio_input_execute(stt_agent, "start_async")
    time_sec = 0
    audio_input_status = audio_input_execute(stt_agent, "get_status_async")
    audio_input_text = audio_input_execute(stt_agent, "get_text_async")
    while audio_input_text == "" and audio_input_status == "<REC_START>":
        time.sleep(0.5)
        time_sec += 1
        if time_sec > timeout:
            audio_input_text = "<REC_TIMEOUT>"
            break
        if not await is_navigating(navi_tools):
            audio_input_text = "<NAVI_REACH>"
            break
        audio_input_status = audio_input_execute(stt_agent, "get_status_async")
        audio_input_text = audio_input_execute(stt_agent, "get_text_async")
    if audio_input_status == "<REC_STOP>" and audio_input_text == "":
        audio_input_text = "<REC_STOP>"
    if audio_input_text == "<REC_TIMEOUT>" or audio_input_text == "<NAVI_REACH>":
        audio_input_execute(stt_agent, "stop_async")
    return audio_input_text


def yes_or_no_quick_match(text):
    text = text.strip().lower()

    neg_words = {"不是", "不对", "错的", "不正确", "不需要", "不用", "不想"}
    for w in neg_words:
        if w in text:
            return "n"

    pos_words = {"是", "对的", "正确", "是的", "对", "需要", "可以", "好的", "好呀", "好","没错", "没问题"}
    for w in pos_words:
        if w in text:
            return "y"

    return "?"

def yes_or_no_quick_match_grab(text):
    text = text.strip().lower()

    neg_words = {"不是", "不对", "错的", "不正确", "不需要", "不用", "不想"}
    for w in neg_words:
        if w in text:
            return "n"

    pos_words = {"是", "对的", "正确", "是的", "对", "需要", "可以", "礼品", "分发", "好的", "好呀", "好"}
    for w in pos_words:
        if w in text:
            return "y"

    return "y"

def audio_input_yes_or_no(stt_agent):
    print("请说肯定或否定词")
    #out_text = audio_input_execute(stt_agent, "speech_to_text", timeout=300)
    out_text = audio_input_execute_timeout(stt_agent, timeout=300)
    val = yes_or_no_quick_match(out_text)
    return val


def _normalize_confirm_text(text):
    return re.sub(r"[\s，。！？?、,.!]+", "", text or "")


def is_self_confirm_echo(text, prompt_text, entity_name=None):
    normalized_text = _normalize_confirm_text(text)
    normalized_prompt = _normalize_confirm_text(prompt_text)
    if normalized_text == "" or normalized_prompt == "":
        return False
    if normalized_text in normalized_prompt or normalized_prompt in normalized_text:
        return True
    if entity_name:
        normalized_entity = _normalize_confirm_text(entity_name)
        if normalized_entity and normalized_entity in normalized_text:
            confirm_words = ["带你去", "是否想去", "一起去", "看看", "看一看", "好吗"]
            if any(word in normalized_text for word in confirm_words):
                return True
    return False


def audio_input_yes_or_no_ignore_echo(stt_agent, prompt_text, entity_name=None, timeout=300, max_retry=2):
    print("请说肯定或否定词")
    for _ in range(max_retry + 1):
        out_text = audio_input_execute_timeout(stt_agent, timeout=timeout)
        if is_self_confirm_echo(out_text, prompt_text, entity_name):
            print(f"忽略机器人确认语回声: {out_text}")
            continue
        return yes_or_no_quick_match(out_text)
    return "?"


def audio_input_stop_chat(stt_agent):
    def quick_match(text: str) -> int:
        text = text.strip().lower()

        stop_words = {"停止说话", "停止聊天", "停止", "停"}
        for w in stop_words:
            if w in text:
                return 1

        return 0

    out_text = audio_input_execute_timeout(stt_agent, timeout=30)
    print(f"audio_input_stop_chat: out_text {out_text}")
    if not _is_valid_interrupt_text(out_text):
        return "<UNKNOWN_MSG>"
    if not is_interrupt_loud_enough(stt_agent):
        return "<UNKNOWN_MSG>"
    out_text = out_text.strip()
    val = quick_match(out_text)
    if val == 1:
        return "<STOP_CHAT>"
    return out_text


def stt_start_async(stt_agent):
    return audio_input_execute(stt_agent, "start_async")


def stt_get_text_async(stt_agent):
    return audio_input_execute(stt_agent, "get_text_async")


def stt_stop_async(stt_agent):
    return audio_input_execute(stt_agent, "stop_async")


def identify_think_type(text):
    text = text.strip()
    why_keywords = ['为什么', '什么', '为何', '怎么会', '怎么回事', '咋回事', '怎么这样']
    opinion_keywords = ['我觉得', '我认为', '你说得对', '你说得没错', '我同意', '没错', '对']

    if any(re.search(kw, text) for kw in why_keywords):
        return "thinkwhy"

    if any(re.search(kw, text) for kw in opinion_keywords):
        return "thinkstatement"

    return "thinkother"


def build_guide_go_to_text(entity_name):
    candidates = [
        f"那我带你去{entity_name}看看吧，好吗？",
        f"你是否想去往{entity_name}？",
        f"要不我们一起去{entity_name}看一看？",
    ]

    n = len(candidates)
    rand_n = random.randint(0, n-1)
    return candidates[rand_n]


def build_stt_prompt_by_list(lst):
    return "、".join(lst) if len(lst) > 0 else ""
