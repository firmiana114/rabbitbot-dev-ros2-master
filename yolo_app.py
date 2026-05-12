#!/usr/bin/env python3
# yolo_app.py
import os
import cv2
import torch
from ultralytics import YOLO
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ------------------ 初始化 ------------------
print("PyTorch CUDA 可用:", torch.cuda.is_available())
print("PyTorch 版本:", torch.__version__)
print("CUDA 版本:", torch.version.cuda)
print("cuDNN 版本:", torch.backends.cudnn.version())

YOLO_DIR = os.environ.get(
    "RABBITBOT_YOLO_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "yolo-detect")),
)
model = YOLO(os.path.join(YOLO_DIR, "yolov8n.pt"))
model.to('cuda')
print("YOLO 模型当前设备:", next(model.model.parameters()).device)

# ------------------ FastAPI ------------------
app = FastAPI(title="YOLOv8 本地图片全身检测",
              description="输入本地图片路径，返回全身人形框坐标字符串")

class DetectRequest(BaseModel):
    img_path: str

class DetectResponse(BaseModel):
    boxes: str   # "[[x0,y0,x1,y1],...]"

# 宽松档（默认推荐先试试）
MAX_ASPECT = 2.0      # 原 1.2 → 2.0
MIN_AREA_RATIO = 0.01  # 原 0.04 → 1%

# ========== 新增阈值 ==========
MIN_PIXEL_AREA = 6000   # 像素面积，可调
# ==============================

@app.post("/detect", response_model=DetectResponse)
def detect(req: DetectRequest):
    img = cv2.imread(req.img_path)
    if img is None:
        raise HTTPException(status_code=400,
                            detail="图片读取出错，请检查 img_path 是否正确")

    results = model(img, classes=0, conf=0.30, verbose=False)[0]

    # 1. 全部框 → [x1,y1,x2,y2,area]
    boxes = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        area = (x2 - x1) * (y2 - y1)
        boxes.append([int(x1), int(y1), int(x2), int(y2), area])

    # 2. 按面积升序
    boxes.sort(key=lambda b: b[4])

    # 3. IoU 过滤参数
    iou_thresh = 0.3   # 可调
    keep = []

    def iou(a, b):
        # a,b : [x1,y1,x2,y2]
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = a[4] + b[4] - inter
        return inter / union if union > 0 else 0

    for i, small in enumerate(boxes):
        is_part = False
        # 只与比它大的框比较
        for j in range(i + 1, len(boxes)):
            if iou(small, boxes[j]) > iou_thresh:
                is_part = True
                break
        if not is_part:
            keep.append(small[:4])  # 不要 area 字段

    # 4. ******* 新增：过小框直接扔掉 *******
    keep = [box for box in keep if (box[2] - box[0]) * (box[3] - box[1]) >= MIN_PIXEL_AREA]

    return DetectResponse(boxes=str(keep).replace(" ", ""))

# ------------------ 启动命令 ------------------
# uvicorn yolo_app:app --host 0.0.0.0 --port 8000
