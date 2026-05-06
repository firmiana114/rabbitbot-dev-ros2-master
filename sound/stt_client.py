
import queue
import threading
from fastapi import FastAPI, Request
import uvicorn

class STTReceiver:
    """封装 STT 接收服务，对外提供队列"""
    def __init__(self, maxsize=5, host="127.0.0.1", port=28184):
        self.queue = queue.Queue(maxsize=maxsize)
        self.emotion_queue = queue.Queue(maxsize=maxsize)
        self.host = host
        self.port = port
        self.app = FastAPI(title="Main STT Receiver")
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/v1")
        async def receive_stt_text(request: Request):
            try:
                body = await request.json()
                text = body.get("text", "")
                emotion = body.get("emotion", "")
                if text and text.strip():
                    self.queue.put(text.strip())
                    print(f"📨 收到STT: {text}")
                self.emotion_queue.put(emotion)
                return {"status": "ok"}
            except Exception as e:
                print(f"❌ 解析JSON失败: {e}")
                return {"status": "error", "message": str(e)}

    def start(self):
        """在后台线程中启动 HTTP 服务"""
        def _run():
            uvicorn.run(self.app, host=self.host, port=self.port, log_level="warning")
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        print(f"STT receiver started at {self.host}:{self.port}")

    def get_queue(self):
        """返回队列引用，供主程序消费数据"""
        return self.queue

    def get_emotion_queue(self):
        """返回识别情感，供主程序消费数据"""
        return self.emotion_queue