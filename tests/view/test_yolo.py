
import os
import json

from utils import draw_bboxes
from yolo_agent import YoloAgent


def main():
    DATA_DIR = "/datanvme/fuchengjia/downloads/agi-robot-subway"
    image_path = os.path.join(DATA_DIR, "无包识别.png")
    yolo_agent = YoloAgent("127.0.0.1", 28190)
    bbox_str = yolo_agent.detect(image_path)
    bboxes = json.loads(bbox_str)
    for bbox in bboxes:
        print(f"bbox: {bbox}")
        x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    save_path = draw_bboxes(bboxes, image_path, "workspace/yolo")
    print("BBOX 图片已保存到：", save_path)


if __name__ == "__main__":
    main()
