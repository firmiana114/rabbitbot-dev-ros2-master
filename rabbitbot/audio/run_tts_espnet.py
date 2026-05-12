
import io
import os
import time
import json
import argparse
import requests
import soundfile as sf
import sounddevice as sd
import librosa
import threading
import queue
import torch
from kokoro import KPipeline, KModel
from enum import Enum
#from espnet2.bin.tts_inference import Text2Speech
from rabbitbot.audio.tts_utils import process_text_en_for_stt, process_text_zh_for_stt
from rabbitbot.tools.logging import logger as file_logger
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Language selection")
    parser.add_argument("--lang", type=str, default="zh")
    parser.add_argument("--output-device-index", type=int)
    args = parser.parse_args()
    return args


class TTSStatus(Enum):
    RUNNING = 0
    STOPPED = 1


class SDOutputStream(object):

    def __init__(self, device_id, target_sr):
        self.device_id = device_id
        self.target_sr = target_sr
        self.play_finish_event = threading.Event()
        self.stream = None
        self.stream_lock = threading.Lock()
        self.restart()

    def play_finish_cb(self):
        self.play_finish = True

    def play_and_wait(self, audio):
        with self.stream_lock:
            self.play_finish = False
            self.play_finish_event.clear()
            if self.stream is not None:
                self.stream.write(audio)
        #while not self.play_finish:
        #    time.sleep(0.1)
        #print("SDOutputStream: Wait ...")
        #self.play_finish_event.wait()
        #print("SDOutputStream: Play and wait finish!")

    def stop(self):
        with self.stream_lock:
            self.play_finish = True
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None

    def restart(self):
        with self.stream_lock:
            if self.stream is not None:
                return
            self.stream = sd.OutputStream(device=self.device_id,
                                          samplerate=self.target_sr,
                                          channels=1,
                                          finished_callback=self.play_finish_event.set)
            self.stream.start()


class CloudTTS(object):

    def __init__(self, host_url):
        print(f"CloudTTS: host_url {host_url}")
        self.host_url = host_url

    def tts(self, text, language, speed):
        payload = {
            "text": text,
            "language": language,
            "speed": speed
        }
        resp = requests.post(self.host_url + "/tts", json=payload, timeout=10)
        #audio = resp.json()["audio"]

        resp.raise_for_status()
        wav_bytes = resp.content          # 这就是 r.content
        audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")

        wav_data = np.array(audio, dtype=np.float32)
        #print(text)
        return wav_data


class EspnetTTS(object):
    def __init__(self, lang, device_id, debug_mode=False):
        self.device = "cuda"
        print(f"EspnetTTS: device {self.device}")

        with open('kuavo_configs.json', 'r', encoding='utf-8') as file:
            config = json.load(file)
            self.tts_cloud_host_url = config["edge_tts_host_url"]

        self.lang = lang
        self.tts_engine_type = "kokoro"
        if self.tts_cloud_host_url is None or self.tts_cloud_host_url == "":
            if self.tts_engine_type == "espnet":
                if self.lang == "en":
                    model_tag = "kan-bayashi/ljspeech_tacotron2"
                elif self.lang == "zh":
                    model_tag = "kan-bayashi/csmsc_fastspeech2"
                else:
                    raise ValueError(f"Not supported TTS language: {self.lang}")
                self.text2speech = {"en": Text2Speech.from_pretrained(
                                            model_tag="kan-bayashi/ljspeech_tacotron2",
                                            device=self.device,
                                            speed_control_alpha=1.0
                                        ),
                                    "zh": Text2Speech.from_pretrained(
                                            model_tag="kan-bayashi/csmsc_fastspeech2",
                                            device=self.device,
                                            speed_control_alpha=1.0
                                        )
                                    }
                self.orig_sr = self.text2speech[self.lang].fs
            elif self.tts_engine_type == "kokoro":
                default_models_dir = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")
                )
                kokoro_model_dir = os.environ.get(
                    "KOKORO_MODEL_DIR",
                    os.path.join(default_models_dir, "kokoro", "Kokoro-82M"),
                )
                kokoro_config_path = os.path.join(kokoro_model_dir, "config.json")
                kokoro_model_path = os.path.join(kokoro_model_dir, "kokoro-v1_0.pth")
                kokoro_voice_path = os.path.join(kokoro_model_dir, "voices", "zm_yunxi.pt")
                if all(os.path.exists(p) for p in [kokoro_config_path, kokoro_model_path, kokoro_voice_path]):
                    kokoro_model = KModel(
                        repo_id="hexgrad/Kokoro-82M",
                        config=kokoro_config_path,
                        model=kokoro_model_path,
                    ).to("cuda").eval()
                    self.pipeline = KPipeline(lang_code='z', repo_id="hexgrad/Kokoro-82M", model=kokoro_model)
                    self.voice = kokoro_voice_path
                else:
                    self.pipeline = KPipeline(lang_code='z', device="cuda")
                    self.voice = "zm_yunxi"
                self.orig_sr = 24000
        else:
            self.text2speech = None
        self.device_id = device_id
        self.target_sr = self.orig_sr
        self.sd_stream = None
        if self.device_id is not None and self.device_id >= 0:
            info = sd.query_devices(self.device_id, 'output')
            self.target_sr = info["default_samplerate"]
            self.sd_stream = SDOutputStream(self.device_id, self.target_sr)
        else:
            print("EspnetTTS: 未配置输出音频设备，将跳过实际播放")
        self.debug_mode = debug_mode
        self.status = TTSStatus.RUNNING
        self.tts_index = 0
        self.interrupt_generation = 0
        queue_len = 4096
        self.tts_queue = np.zeros((queue_len))
        #self.tts_cloud_host_url = os.environ.get("TTS_CLOUD", None)
        if self.tts_cloud_host_url is not None and self.tts_cloud_host_url != "":
            self.tts_cloud = CloudTTS(self.tts_cloud_host_url)
            #self.orig_sr = 44100.0
            self.orig_sr = 16000.0
        else:
            self.tts_cloud = None

    def set_lang(self, lang):
        self.lang = lang
        if self.debug_mode:
            if lang == "zh":
                self.put_text("当前为中文语言模式")
            elif lang == "en":
                self.put_text("Now is English")

    def init_async_workers(self):
        self.text_q = queue.Queue(maxsize=8)
        self.wav_q = queue.Queue(maxsize=8)
        self.num_text = 0
        self.num_wav = 0

        self.text_thread = threading.Thread(target=self._text_worker)
        self.wav_thread = threading.Thread(target=self._wav_worker)
        self.text_thread.start()
        self.wav_thread.start()

    def _text_worker(self):
        if self.debug_mode:
            print("Text worker started")
        while True:
            item = self.text_q.get()
            if len(item) == 3:
                text, tts_index, generation = item
            else:
                text, tts_index = item
                generation = self.interrupt_generation
            if self.debug_mode:
                print(f"Get text: {text}, {self.status}")
            if text is None:
                self.num_text -= 1
                self.wav_q.put((None, None, generation))
                break
            if self.status != TTSStatus.RUNNING or generation != self.interrupt_generation:
                self.num_text -= 1
                continue
            start_time = time.time()
            if self.tts_cloud is None:
                if self.tts_engine_type == "espnet":
                    assert self.text2speech is not None
                    wav = self.text2speech[self.lang](text)["wav"]
                elif self.tts_engine_type == "kokoro":
                    assert self.pipeline is not None
                    generator = self.pipeline(
                        text, voice=self.voice,
                        speed=1.0, split_pattern=r'\n+'
                    )
                    for i, (gs, ps, audio) in enumerate(generator):
                        wav = audio.numpy()
            else:
                try:
                    wav = self.tts_cloud.tts(text, self.lang, 1.0)
                except Exception:
                    wav = None
            tts_time = time.time() - start_time
            if self.debug_mode:
                print(f"TTS time: {tts_time:.3f}")
            log_text = f"KokoroTTS: text {text}, time {tts_time:.3f}"
            print(log_text)
            file_logger.debug(log_text)
            if wav is not None and self.status == TTSStatus.RUNNING and generation == self.interrupt_generation:
                self.num_wav += 1
                self.wav_q.put((wav, tts_index, generation))
            #self.text_q.done()
            self.num_text -= 1
        if self.debug_mode:
            print("Text worker exit")

    def _wav_worker(self):
        if self.debug_mode:
            print("WAV worker started")
        while True:
            item = self.wav_q.get()
            if len(item) == 3:
                wav, tts_index, generation = item
            else:
                wav, tts_index = item
                generation = self.interrupt_generation
            if self.debug_mode:
                print(f"Get WAV: {self.status}, {self.num_wav}")
            if wav is None:
                #continue
                break
            if self.status != TTSStatus.RUNNING or generation != self.interrupt_generation:
                self.num_wav -= 1
                continue
            if isinstance(wav, torch.Tensor):
                wav_data = wav.view(-1).cpu().numpy()
            else:
                wav_data = wav
            if self.sd_stream is not None:
                data_resampled = librosa.resample(wav_data, orig_sr=self.orig_sr, target_sr=self.target_sr)
                #sd.play(data_resampled, self.target_sr, device=self.device_id)
                #sd.wait()
                try:
                    self.tts_queue[tts_index] = 1
                    self.sd_stream.play_and_wait(data_resampled)
                except Exception:
                    pass
            else:
                self.tts_queue[tts_index] = 1
            self.num_wav -= 1
            #self.wav_q.done()
        if self.debug_mode:
            print("WAV worker exit")

    def put_text(self, text):
        if self.debug_mode:
            print(f"Put text: {text}")
        self.text_q.put((text, self.tts_index, self.interrupt_generation))
        self.num_text += 1
        tts_index = self.tts_index
        self.tts_index += 1
        return tts_index

    def put_wav(self, wav):
        self.num_wav += 1
        self.wav_q.put((wav, self.tts_index, self.interrupt_generation))
        self.tts_index += 1

    def _drain_queue(self, q):
        count = 0
        while True:
            try:
                q.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count

    def get_wav_count(self):
        return max(0, self.num_text) + max(0, self.num_wav)

    def get_play(self, tts_index):
        return self.tts_queue[tts_index]

    def wait_wav_queue(self):
        while self.get_wav_count() > 0:
            time.sleep(0.5)

    def set_status(self, status):
        self.status = status

    def stop(self):
        self.status = TTSStatus.STOPPED
        #sd.stop()

    def stop_wait_restart(self, soft_stop):
        self.status = TTSStatus.STOPPED
        self.interrupt_generation += 1
        try:
            drained_text = self._drain_queue(self.text_q)
            drained_wav = self._drain_queue(self.wav_q)
            self.num_text = max(0, self.num_text - drained_text)
            self.num_wav = max(0, self.num_wav - drained_wav)
            # 不在 stop 请求里关闭并重建 sounddevice 流。
            # 现场发现 stop 与播放线程的 stream.write 并发时，ALSA/PortAudio
            # 可能触发底层内存损坏并导致 TTS 服务进程退出。
        except Exception as e:
            print(f"TTS stop_wait_restart error: {e}")
        self.status = TTSStatus.RUNNING

    def text_to_wav(self, text, speed=1.0):
        start_time = time.time()
        if self.tts_cloud is None:
            if self.tts_engine_type == "espnet":
                wav = self.text2speech[self.lang](text)["wav"]
            elif self.tts_engine_type == "kokoro":
                generator = self.pipeline(
                    text, voice=self.voice,
                    speed=1.0, split_pattern=r'\n+'
                )
                for i, (gs, ps, audio) in enumerate(generator):
                    wav = audio.numpy()
        else:
            speed = 1.2
            wav = self.tts_cloud.tts(text, self.lang, speed)
        duration = time.time() - start_time
        print(f"EspnetTTS: text_to_wav {text}, duration {duration:.3f}")
        return wav

    def sound(self, text, speed=1.0):
        wav = self.text_to_wav(text, speed)
        if self.sd_stream is None:
            return
        wav_data = wav.view(-1).cpu().numpy()
        data_resampled = librosa.resample(wav_data, orig_sr=self.orig_sr, target_sr=self.target_sr)
        sd.play(data_resampled, self.target_sr, device=self.device_id)
        sd.wait()

    def sound_wav(self, wav_data, orig_sr):
        if self.sd_stream is None:
            return
        data_resampled = librosa.resample(wav_data, orig_sr=orig_sr, target_sr=self.target_sr)
        self.sd_stream.play_and_wait(data_resampled)

    def save_wav(self, text, file_path):
        if self.lang == "en":
            text = process_text_en_for_stt(text)
        elif self.lang == "zh":
            text = process_text_zh_for_stt(text)
        if text is not None:
            wav = self.text2speech[self.lang](text)["wav"]
            sf.write(file_path, wav.view(-1).cpu().numpy(), self.text2speech[self.lang].fs, "PCM_16")

    def close(self):
        self.put_text(None)


def test_nltk():
    import nltk
    nltk.download('averaged_perceptron_tagger_eng')


def test_wav_file_en(device_id):
    device = "cpu"
    text2speech = Text2Speech.from_pretrained(
        model_tag="kan-bayashi/ljspeech_tacotron2",
        device=device,
        speed_control_alpha=1.0,
    )

    text = "OK, I will take you to the most popular workshop"
    wav = text2speech(text)["wav"]
    file_path=f"data/espnet_tts/audio_output_en.wav"

    if device_id < 0:
        sf.write(file_path, wav.view(-1).cpu().numpy(), text2speech.fs, "PCM_16")
    else:
        print(sd.query_devices())
        info = sd.query_devices(device_id, 'output')
        print(info)
        target_sr = info["default_samplerate"]
        wav_data = wav.view(-1).cpu().numpy()
        data_resampled = librosa.resample(wav_data, orig_sr=text2speech.fs, target_sr=target_sr)
        sd.play(data_resampled, target_sr, device=device_id)
        sd.wait()


def test_wav_file_zh(device_id):
    device = "cpu"
    #model_tag = "kan-bayashi/csmsc_fastspeech2"
    model_tag = "kan-bayashi/csmsc_conformer_fastspeech2"
    text2speech = Text2Speech.from_pretrained(
        model_tag=model_tag,
        device=device,
        speed_control_alpha=1.0,
    )

    text = "你好，很高兴见到你"
    #text = "我马上带你去人最多的展台"
    #text = "你真好看，I like you"
    #text = "1加1等于2"
    wav = text2speech(text)["wav"]
    file_path=f"data/espnet_tts/audio_output_zh.wav"
    if device_id < 0:
        sf.write(file_path, wav.view(-1).cpu().numpy(), text2speech.fs, "PCM_16")
    else:
        info = sd.query_devices(device_id, 'output')
        target_sr = info["default_samplerate"]
        wav_data = wav.view(-1).cpu().numpy()
        data_resampled = librosa.resample(wav_data, orig_sr=text2speech.fs, target_sr=target_sr)
        sd.play(data_resampled, target_sr, device=device_id)
        sd.wait()


def test_wav_files_en():
    device = "cpu"
    text2speech = Text2Speech.from_pretrained(
        model_tag="kan-bayashi/ljspeech_tacotron2",
        device=device,
        speed_control_alpha=1.0,
    )

    num_files = 20
    for i in range(num_files):
        filepath = f"data/text_en/audio_output_{i:03d}.txt"
        if os.path.exists(filepath):
            print(f"filepath: {filepath}")
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.readline()
                print(f"text: {text}")
                wav = text2speech(text)["wav"]
                file_path=f"data/espnet_tts/audio_output_{i:03d}.wav"
                sf.write(file_path, wav.view(-1).cpu().numpy(), 22050)


def test_wav_files_zh():
    device = "cpu"
    text2speech = Text2Speech.from_pretrained(
        model_tag="kan-bayashi/csmsc_fastspeech2",
        device=device,
        speed_control_alpha=1.0,
    )

    num_files = 20
    for i in range(num_files):
        filepath = f"data/text_zh/audio_zh_output_{i:03d}.txt"
        if os.path.exists(filepath):
            print(f"filepath: {filepath}")
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.readline()
                print(f"text: {text}")
                wav = text2speech(text)["wav"]
                file_path=f"data/espnet_tts_zh/audio_output_{i:03d}.wav"
                sf.write(file_path, wav.view(-1).cpu().numpy(), 22050)


async def test_epsnet_tts(lang, out_device_id):
    tts_engine = EspnetTTS(lang=lang, device_id=out_device_id)
    await tts_engine.init_async_workers()

    text = "OK, I will take you to the most popular workshop"
    await tts_engine.put_text(text)
    text = "OK, I will take you to the most popular workshop"
    await tts_engine.put_text(text)
    text = "OK, I will take you to the most popular workshop"
    await tts_engine.put_text(text)

    await tts_engine.put_text(None)

    await tts_engine.wait_workers()


if __name__ == "__main__":
    #test_nltk()

    args = parse_args()
    device_id = args.output_device_index

    if args.lang == "en":
        test_wav_file_en(device_id)
    elif args.lang == "zh":
        test_wav_file_zh(device_id)

    #test_wav_files_en()
    #test_wav_files_zh()

    #test_epsnet_tts(args.lang, device_id)
