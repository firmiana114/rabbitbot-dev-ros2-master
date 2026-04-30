
import time
import requests
from typing import Optional


class YoloAgent:
    """
    调用本地 FastAPI-YOLO 服务的轻量级客户端
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.base_url = f"http://{host}:{port}"
        self.detect_endpoint = f"{self.base_url}/detect"

    def detect(self, img_path: str) -> Optional[str]:
        """
        输入：本地图片绝对/相对路径
        返回：BBOX 坐标字符串 "[[x0,y0,x1,y1],...]"，无目标返回 "[]"
        失败返回 None
        """
        try:
            start_time = time.time()
            resp = requests.post(
                self.detect_endpoint,
                json={"img_path": img_path},
                timeout=30
            )
            resp.raise_for_status()
            boxes_str = resp.json()["boxes"]
            detect_time = time.time() - start_time
            print(f"yolo_time: {detect_time:.3f}")
            return boxes_str
        except Exception as e:
            print(f"[YoloAgent] detect error: {e}")
            return None
