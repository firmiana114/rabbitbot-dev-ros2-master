
import re
import time
import json
import os
import random
import threading
from datetime import datetime

from rabbitbot.tools.navi_agno import is_navigating


_recent_tts_texts = []
_recent_tts_lock = threading.Lock()


def _sound_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _format_trace_fields(fields):
    return ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)


def _normalize_echo_text(text):
    text = re.sub(r"\[A:[^\]]+\]", "", text or "")
    return re.sub(r"[\s，。！？?、,.!；;：:\"'“”‘’（）()\[\]【】]+", "", text)


def _remember_tts_text(text):
    normalized_text = _normalize_echo_text(text)
    if len(normalized_text) < 4:
        return

    now = time.time()
    max_age = float(os.getenv("RABBITBOT_TTS_ECHO_WINDOW_SECONDS", "45"))
    with _recent_tts_lock:
        _recent_tts_texts.append((now, normalized_text))
        _recent_tts_texts[:] = [
            item for item in _recent_tts_texts[-20:]
            if now - item[0] <= max_age
        ]


def _tts_strict_failure_enabled():
    return os.getenv("RABBITBOT_TTS_STRICT_FAILURE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _handle_tts_failure(stage, text=None, error=None, fallback=None, **fields):
    field_text = _format_trace_fields({**fields, "error": error})
    suffix = f", {field_text}" if field_text else ""
    print(f"[{_sound_timestamp()}] TTS请求链路: stage={stage}, text={text}{suffix}")
    if _tts_strict_failure_enabled():
        if isinstance(error, BaseException):
            raise RuntimeError(f"TTS失败且启用严格模式: stage={stage}, text={text}") from error
        raise RuntimeError(f"TTS失败且启用严格模式: stage={stage}, text={text}, error={error}")
    return fallback


def _longest_common_substring(a, b):
    if not a or not b:
        return 0, 0, 0

    previous = [0] * (len(b) + 1)
    best_len = 0
    best_a_end = 0
    best_b_end = 0
    for i, a_char in enumerate(a, 1):
        current = [0] * (len(b) + 1)
        for j, b_char in enumerate(b, 1):
            if a_char == b_char:
                current[j] = previous[j - 1] + 1
                if current[j] > best_len:
                    best_len = current[j]
                    best_a_end = i
                    best_b_end = j
        previous = current
    return best_len, best_a_end - best_len, best_b_end - best_len


def clean_stt_echo_text(text):
    if not _is_valid_interrupt_text(text):
        return text

    cleaned_text = _normalize_echo_text(text)
    if not cleaned_text:
        return ""

    min_match_chars = int(os.getenv("RABBITBOT_TTS_ECHO_MIN_CHARS", "8"))
    max_age = float(os.getenv("RABBITBOT_TTS_ECHO_WINDOW_SECONDS", "45"))
    now = time.time()
    with _recent_tts_lock:
        recent_tts_texts = [
            tts_text for timestamp, tts_text in _recent_tts_texts
            if now - timestamp <= max_age
        ]

    changed = False
    # Remove at most a few contaminated chunks; most inputs contain one echo tail.
    for _ in range(3):
        best = (0, 0, 0)
        for tts_text in recent_tts_texts:
            match_len, stt_start, _ = _longest_common_substring(cleaned_text, tts_text)
            if match_len > best[0]:
                best = (match_len, stt_start, stt_start + match_len)

        match_len, remove_start, remove_end = best
        if match_len < min_match_chars:
            break

        # ASR often inserts a short connector before copied robot speech, e.g.
        # "一加一等于几这滨湖区..." where the echo starts at "滨湖区".
        if remove_start > 0 and cleaned_text[remove_start - 1] in {"这", "那", "是", "的", "了"}:
            remove_start -= 1

        before = cleaned_text
        cleaned_text = (cleaned_text[:remove_start] + cleaned_text[remove_end:]).strip()
        changed = True
        print(f"清理TTS回声污染: match_len={match_len}, before={before}, after={cleaned_text}")

        if not cleaned_text:
            break

    if changed:
        return cleaned_text
    return text


def tts_sound(tts_agent, text, lang):
    input_dict = {"task": "text_to_speech", "lang": lang, "text": text, "timeout": 30}
    print(input_dict)
    _remember_tts_text(text)
    #def sound_agent_run():
    #    tts_agent.run(json.dumps(input_dict))
    #threading.Thread(target=sound_agent_run).start()
    request_start = time.perf_counter()
    print(
        f"[{_sound_timestamp()}] TTS请求链路: "
        f"stage=workflow_tts_request_start, text={text}"
    )
    try:
        tts_index = tts_agent.run(json.dumps(input_dict))
    except Exception as exc:
        elapsed = time.perf_counter() - request_start
        return _handle_tts_failure(
            "workflow_tts_request_exception",
            text=text,
            error=f"{type(exc).__name__}: {exc}",
            fallback=-1,
            elapsed=f"{elapsed:.3f}s",
        )
    elapsed = time.perf_counter() - request_start
    print(
        f"[{_sound_timestamp()}] TTS请求链路: "
        f"stage=workflow_tts_request_done, tts_index={tts_index}, "
        f"elapsed={elapsed:.3f}s, text={text}"
    )
    try:
        return int(tts_index)
    except (TypeError, ValueError) as exc:
        return _handle_tts_failure(
            "workflow_tts_request_invalid_response",
            text=text,
            error=f"{type(exc).__name__}: {exc}",
            fallback=-1,
            tts_index=tts_index,
            elapsed=f"{elapsed:.3f}s",
        )


def tts_wait(tts_agent):
    input_dict = {"task": "wait_speech", "lang": "", "text": "", "timeout": 30}
    print(input_dict)
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    try:
        out_text = tts_agent.run(json.dumps(input_dict))
    except Exception as exc:
        return _handle_tts_failure(
            "workflow_tts_wait_exception",
            error=f"{type(exc).__name__}: {exc}",
            fallback="TTS wait skipped",
        )
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
    try:
        out_text = tts_agent.run(json.dumps(input_dict))
        wav_count = int(out_text)
    except Exception as exc:
        return _handle_tts_failure(
            "workflow_tts_wav_count_exception",
            error=f"{type(exc).__name__}: {exc}",
            fallback=0,
        )
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
    ignored_texts = {"<REC_TIMEOUT>", "<REC_STOP>", "<REC_DUPLICATE>", "Timeout", "Started", "Stopped"}
    return text not in ignored_texts


def _normalize_interrupt_control_text(text):
    return re.sub(r"[\s，。！？?、,.!；;：:\"'“”‘’（）()\[\]【】]+", "", text or "").lower()


def _is_ignored_interrupt_text(text, ignored_interrupt_texts=None):
    if not ignored_interrupt_texts:
        return False
    normalized_text = _normalize_interrupt_control_text(text)
    if normalized_text == "":
        return False
    normalized_ignored_texts = {
        _normalize_interrupt_control_text(item)
        for item in ignored_interrupt_texts
    }
    return normalized_text in normalized_ignored_texts


def tts_long_text_with_stt_stop(
    tts_agent,
    text,
    stt_agent,
    robot,
    before_text=None,
    ignored_interrupt_texts=None,
    ignore_unlisted_interrupts=False,
):
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
                if _is_ignored_interrupt_text(out_text, ignored_interrupt_texts):
                    print("忽略剧本继续确认词：", out_text)
                    stt_start_async(stt_agent)
                    continue
                if ignore_unlisted_interrupts and not (out_text.startswith("停止") or "停" in out_text):
                    print("严格演出模式忽略剧本讲解输入：", out_text)
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


def tts_ask_with_early_stt(
    tts_agent,
    text,
    stt_agent,
    timeout=8,
    lang="zh",
    stop_tts_on_answer=False,
    trace_event=None,
    trace_id=None,
):
    """在播报问题前启动 STT，避免用户需要等待监听启动后才能回答。"""
    trace_start = time.perf_counter()

    def emit_trace(phase, **fields):
        elapsed = time.perf_counter() - trace_start
        payload = {
            "phase": phase,
            "trace_id": trace_id,
            "elapsed_from_listen_start": round(elapsed, 6),
            **fields,
        }
        print(
            f"[{_sound_timestamp()}] 早听应答链路: "
            f"{_format_trace_fields(payload)}"
        )
        if trace_event:
            trace_event(**payload)

    print(f"audio_input early ask: timeout {timeout}")
    emit_trace("listen_start_request", timeout=timeout, question_text=text)
    listen_start_perf = time.perf_counter()
    start_result = audio_input_execute(stt_agent, "start_async", "")
    emit_trace(
        "listen_start_done",
        result=start_result,
        elapsed=round(time.perf_counter() - listen_start_perf, 6),
    )
    emit_trace("question_tts_request_start", text=text)
    question_tts_perf = time.perf_counter()
    question_tts_index = tts_sound(tts_agent, text, lang)
    emit_trace(
        "question_tts_request_done",
        tts_index=question_tts_index,
        elapsed=round(time.perf_counter() - question_tts_perf, 6),
        text=text,
    )

    time_sec = 0
    poll_index = 0
    audio_input_text = audio_input_execute(stt_agent, "get_text_async")
    audio_input_status = audio_input_execute(stt_agent, "get_status_async")
    emit_trace("stt_poll", poll_index=poll_index, status=audio_input_status, text=audio_input_text)
    while audio_input_text == "" and audio_input_status == "<REC_START>":
        time.sleep(0.2)
        time_sec += 0.2
        if time_sec > timeout:
            audio_input_text = "<REC_TIMEOUT>"
            emit_trace("stt_timeout", poll_index=poll_index, waited=round(time_sec, 3))
            break
        poll_index += 1
        audio_input_text = audio_input_execute(stt_agent, "get_text_async")
        audio_input_status = audio_input_execute(stt_agent, "get_status_async")
        emit_trace("stt_poll", poll_index=poll_index, status=audio_input_status, text=audio_input_text)

    emit_trace("stt_raw_text_received", status=audio_input_status, text=audio_input_text, poll_count=poll_index + 1)
    emit_trace("stt_dedupe_start", text=audio_input_text)
    audio_input_text = _dedupe_stt_utterance(stt_agent, audio_input_text)
    emit_trace("stt_dedupe_done", text=audio_input_text)
    if stop_tts_on_answer and _is_valid_interrupt_text(audio_input_text):
        emit_trace("question_tts_stop_start", text=text)
        stop_perf = time.perf_counter()
        tts_stop(tts_agent)
        emit_trace(
            "question_tts_stop_done",
            elapsed=round(time.perf_counter() - stop_perf, 6),
            text=text,
        )
        time.sleep(0.1)
    if audio_input_status == "<REC_STOP>" and audio_input_text == "":
        audio_input_text = "<REC_STOP>"
    emit_trace("stt_stop_request_start", final_text=audio_input_text)
    stop_listen_perf = time.perf_counter()
    stop_result = audio_input_execute(stt_agent, "stop_async")
    emit_trace(
        "stt_stop_request_done",
        result=stop_result,
        elapsed=round(time.perf_counter() - stop_listen_perf, 6),
        final_text=audio_input_text,
    )
    emit_trace("listen_return", final_text=audio_input_text)
    return audio_input_text


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
        #tts_wait(tts_agent)


def _is_invalid_tts_index(tts_index):
    try:
        return tts_index is None or int(tts_index) < 0
    except (TypeError, ValueError):
        return True


def tts_get_play(tts_agent, tts_index):
    if _is_invalid_tts_index(tts_index):
        return 1
    input_dict = {"task": "get_play", "lang": "", "text": f"{tts_index}", "timeout": 30}
    #run_response = tts_agent.run(json.dumps(input_dict))
    #out_text = run_response.content
    try:
        out_text = tts_agent.run(json.dumps(input_dict))
        return int(float(out_text))
    except Exception as exc:
        return _handle_tts_failure(
            "workflow_tts_get_play_exception",
            error=f"{type(exc).__name__}: {exc}",
            fallback=1,
            tts_index=tts_index,
        )


def action_with_tts(robot, action_name, tts_agent, tts_index, timeout=30):
    if _is_invalid_tts_index(tts_index):
        print(f"action_with_tts: tts_index={tts_index} invalid, skip action {action_name}")
        return

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


def _dedupe_stt_utterance(stt_agent, text):
    text = clean_stt_echo_text(text)
    if not _is_valid_interrupt_text(text):
        return text

    utterance_id = getattr(stt_agent, "last_utterance_id", 0)
    if not utterance_id:
        return text

    consumed_ids = getattr(stt_agent, "_consumed_utterance_ids", set())
    if utterance_id in consumed_ids:
        print(f"忽略重复语音识别结果: utterance_id={utterance_id}, text={text}")
        return "<REC_DUPLICATE>"

    consumed_ids.add(utterance_id)
    setattr(stt_agent, "_consumed_utterance_ids", consumed_ids)
    return text


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
    audio_input_text = _dedupe_stt_utterance(stt_agent, audio_input_text)
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
    audio_input_text = _dedupe_stt_utterance(stt_agent, audio_input_text)
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
