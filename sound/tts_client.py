import requests
import json

class TTSAgent:
    def __init__(self, host_url):
        print(f"TTSAgent: host_url {host_url}")
        self.host_url = host_url

    def run(self, input_dict: dict):
        try:
            resp = requests.post(self.host_url, json=input_dict, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("audio_time", 0.0)
        except Exception as e:
            print(f"TTSAgent Error: {e}")
        return 0

    def tts_sound(self,text, interrupt):
        input_dict = {"text": text, "interrupt": interrupt}
        print(f"📤 发送中: {text}")
        return self.run(input_dict)