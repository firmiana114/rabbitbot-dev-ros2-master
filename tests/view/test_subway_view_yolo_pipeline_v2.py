
import os
import cv2
import time
import json
import asyncio
import argparse
import requests
from typing import Optional
from textwrap import dedent
from agno.agent import Agent
from agno.exceptions import ModelProviderError
from rabbitbot.context import AppContext
from rabbitbot.tools.vision_agno import VisionToolkit
from rabbitbot.tools.sound_agno import tts_sound, tts_wait
from rabbitbot.robots.constants import MoveType
import numpy as np
from yolo_agent import YoloAgent
from utils import read_frame, get_fps, load_h265, get_frame_count_h265, concat_images_horizontal
from image_enhance import enhance_bag_separation, advanced_edge_sharpen, texture_based_separation, simple_adjust
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import torch
import torchreid
from torchvision import transforms
import traceback


REPO_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = REPO_DIR.parent
TEST_DATA_ROOT = Path(os.environ.get("RABBITBOT_TEST_DATA_ROOT", PROJECTS_DIR / "downloads"))
DATA_DIR = str(Path(os.environ.get("RABBITBOT_SUBWAY_DATA_DIR", TEST_DATA_ROOT / "agi-robot-subway-v2" / "agi_data_small")))
REID_MODEL_PATH = Path(os.environ.get(
    "RABBITBOT_REID_MODEL_PATH",
    PROJECTS_DIR / "models" / "deep-person-reid" / "osnet_x1_0_market_256x128_amsgrad_ep150_stp60_lr0.0015_b64_fb10_softmax_labelsmooth_flip.pth"
))
VISION_WORKSPACE_DIR = Path(os.environ.get(
    "RABBITBOT_VISION_WORKSPACE_DIR",
    REPO_DIR / "workspace" / "tools" / "vision_tools"
))
PIXEL_POINTS_PATH = Path(os.environ.get(
    "RABBITBOT_PIXEL_POINTS_PATH",
    REPO_DIR / "tests" / "view" / "pixel_points.json"
))
# 这里加载torchreid的模型
model = torchreid.models.build_model(name='osnet_x1_0', num_classes=751, pretrained=False)
torchreid.utils.load_pretrained_weights(model, str(REID_MODEL_PATH))
model = model.to("cuda")
model.eval()
json_path = str(PIXEL_POINTS_PATH)

def create_view_agent(ctx, instructions):
    model = ctx.agno_model
    view_agent = Agent(
        name='View Agent',
        role='Viewer',
        instructions=instructions,
        model=model,
        debug_mode=False,
        add_history_to_messages=False,
        num_history_runs=1,
    )
    return view_agent

def read_points_list():

    # 检查文件是否存在
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON文件不存在: {json_path}")

    # 2. 读取JSON文件，提取多边形顶点坐标
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 提取points中的x、y坐标，并转换为OpenCV要求的格式
    points_list = []
    for point in data["points"]:
        x = int(point["x"])
        y = int(point["y"])
        points_list.append([x, y])
    return points_list
points_list=read_points_list()

def point_in_bbox(point: tuple, bbox: tuple) -> bool:
    """判断单个点是否在框内"""
    x, y = point
    xmin, ymin, xmax, ymax = bbox
    return (xmin <= x <= xmax) and (ymin <= y <= ymax)

def line_segment_intersect(a1, a2, b1, b2) -> bool:
    """判断两条线段是否相交（跨立实验）"""
    def ccw(A, B, C):
        return (B[0]-A[0])*(C[1]-A[1]) - (B[1]-A[1])*(C[0]-A[0])

    return (ccw(a1,a2,b1)*ccw(a1,a2,b2) <= 0) and (ccw(b1,b2,a1)*ccw(b1,b2,a2) <= 0)

def is_polygon_and_bbox_overlap_opencv(polygon_points: list, bbox: tuple) -> bool:
    """纯OpenCV实现：判断多边形与框是否重合"""
    xmin, ymin, xmax, ymax = bbox
    # 1. 快速边界框筛选
    poly_np = np.array(polygon_points, dtype=np.int32)
    poly_xmin, poly_xmax = poly_np[:,0].min(), poly_np[:,0].max()
    poly_ymin, poly_ymax = poly_np[:,1].min(), poly_np[:,1].max()
    if (poly_xmax < xmin) or (poly_xmin > xmax) or (poly_ymax < ymin) or (poly_ymin > ymax):
        return False

    # 2. 检查多边形顶点是否在框内
    for (x, y) in polygon_points:
        if point_in_bbox((x, y), bbox):
            return True

    # 3. 检查框的顶点是否在多边形内
    bbox_points = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    poly_np = np.array(polygon_points, dtype=np.int32).reshape((-1,1,2))
    for (x, y) in bbox_points:
        # cv2.pointPolygonTest：点在多边形内返回正数，在边上返回0，在外返回负数
        if cv2.pointPolygonTest(poly_np, (x, y), measureDist=False) >= 0:
            return True

    # 4. 检查多边形边与框的边是否相交
    bbox_edges = [
        (bbox_points[0], bbox_points[1]),  # 上边框
        (bbox_points[1], bbox_points[2]),  # 右边框
        (bbox_points[2], bbox_points[3]),  # 下边框
        (bbox_points[3], bbox_points[0])   # 左边框
    ]
    # 遍历多边形的边
    poly_edges = []
    n = len(polygon_points)
    for i in range(n):
        p1 = polygon_points[i]
        p2 = polygon_points[(i+1)%n]  # 闭合多边形：最后一个点连回第一个点
        poly_edges.append((p1, p2))
    # 检查所有边的相交情况
    for pe in poly_edges:
        for be in bbox_edges:
            if line_segment_intersect(pe[0], pe[1], be[0], be[1]):
                return True

    # 所有情况都不满足
    return False

def draw_transparent_polygon_on_pil(
    img: Image.Image,
    polygon_points: list,
    color: tuple = (0, 0, 255),  # 蓝色 (R, G, B)
    alpha: float = 0.3           # 透明度 0-1
) -> Image.Image:
    """
    在 PIL Image 上绘制带透明度的实心多边形（修复颜色+坐标双错误）

    Args:
        img: 原始 PIL Image 对象（RGB 格式）
        polygon_points: 多边形顶点列表，支持格式：
                        - [(x1,y1), (x2,y2), ...] （元组，推荐）
                        - [[x1,y1], [x2,y2], ...] （列表，自动转换）
        color: 多边形颜色，必须是 3元素元组 (R, G, B)
        alpha: 透明度 0-1 之间

    Returns:
        Image.Image: 绘制后的 PIL Image 对象
    """
    # 1. 基础校验
    if img.mode != "RGB":
        img = img.convert("RGB")
    if len(polygon_points) < 3:
        raise ValueError("多边形至少需要3个顶点")
    if not (0 <= alpha <= 1):
        raise ValueError("透明度 alpha 必须在 0-1 之间")

    # 2. 修复：强制颜色为合法的3元素整数元组
    if not isinstance(color, tuple) or len(color) != 3:
        raise ValueError(f"color必须是3元素元组 (R,G,B)，当前：{color}")
    color = tuple([max(0, min(255, int(c))) for c in color])  # 确保0-255整数

    # 3. 核心修复：强制坐标为「整数元组」格式（解决 incorrect coordinate type）
    valid_points = []
    img_width, img_height = img.size
    for idx, point in enumerate(polygon_points):
        # 处理点格式：支持列表/元组，统一转为元组
        if isinstance(point, (list, tuple)) and len(point) == 2:
            # 强制转为整数（PIL 不支持浮点数坐标）
            x = int(point[0])
            y = int(point[1])
            # 确保坐标在图片范围内（避免越界）
            x = max(0, min(img_width - 1, x))
            y = max(0, min(img_height - 1, y))
            valid_points.append((x, y))  # 必须是元组！
        else:
            raise ValueError(
                f"第{idx}个坐标格式错误，应为 [x,y] 或 (x,y)，当前：{point}"
            )
    if len(valid_points) < 3:
        raise ValueError("有效坐标点不足3个，无法绘制多边形")

    # 4. 创建透明图层
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 5. 绘制多边形（颜色+坐标均合法）
    polygon_color = color + (255,)  # RGBA 元组
    draw.polygon(valid_points, fill=polygon_color, outline=None)

    # 6. 融合图层实现透明度
    img_rgba = img.convert("RGBA")
    overlay_data = np.array(overlay, dtype=np.uint8)
    overlay_data[:, :, 3] = (overlay_data[:, :, 3] * alpha).astype(np.uint8)
    overlay_alpha = Image.fromarray(overlay_data, mode="RGBA")
    combined = Image.alpha_composite(img_rgba, overlay_alpha)

    # 7. 转回RGB并返回
    return combined.convert("RGB")

def crop_bbox_to_png(image_path: str,
                     x0: int, y0: int,
                     x1: int, y1: int,
                     save_path: str = None) -> str:
    """
    从 image_path 中抠出 bbox 区域，保存为 PNG。
    返回保存路径。
    """
    # 读图
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)  # 保留 alpha 通道
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    # 合法性检查
    h, w = img.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Invalid bbox: empty region.")

    # 切片裁剪
    crop = img[y0:y1, x0:x1]
    # 切片记录
    crop_h, crop_w = crop.shape[:2]    # 获取裁剪后的实际尺寸
    scale = min(256 / crop_h, 128 / crop_w)
    new_h, new_w = int(crop_h * scale), int(crop_w * scale)
    # 等比缩放
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    # 创建目标尺寸画布（用 0 填充，即黑色）
    assert len(crop.shape) == 3
    padded = np.zeros((256, 128, 3), dtype=np.uint8)
    # 居中放置
    dh, dw = (256 - new_h) // 2, (128 - new_w) // 2
    padded[dh:dh+new_h, dw:dw+new_w] = resized

    # 自动生成保存路径
    if save_path is None:
        base, _ = os.path.splitext(image_path)
        save_path = f"{base}_crop.png"
    else:
        img_filename = image_path.rsplit('/', 1)[1].rsplit('.', 1)[0]
        directory = Path(save_path)
        directory.mkdir(parents=True, exist_ok=True)
        crop_save_path = f"{save_path}/{img_filename}_crop_{x0}_{y0}_{x1}_{y1}.png"

        pad_save_path = f"{save_path}/{img_filename}_crop_pad_{x0}_{y0}_{x1}_{y1}.jpg"
        cv2.imwrite(pad_save_path, padded)
        print(f"已保存: {pad_save_path}")

    # 保存为 PNG（最高质量）
    cv2.imwrite(crop_save_path, crop, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    print(f"已保存: {crop_save_path}")
    return crop_save_path, padded, crop


def format_out_text(text):
    text_lst = text.split("\n")
    print(f"text_lst: {text_lst}")
    if "1" not in text_lst:
        return None
    tmp_lst = []
    if len(text_lst) >= 8:
        tmp_lst.append(text_lst[0])
        tmp_lst.append(text_lst[2])
        tmp_lst.append(text_lst[4])
        tmp_lst.append(text_lst[6])
        text_lst = tmp_lst
    print(f"text_lst: {text_lst}")
    feat_lst = []
    if text_lst[3] == "1":
        feat_lst.append("带包")
    if text_lst[0] == "1":
        feat_lst.append("携带液体")
    if text_lst[1] == "1":
        feat_lst.append("简单交互")
    if text_lst[2] == "1":
        feat_lst.append("特殊人群")
    print(f"feat_lst: {feat_lst}")
    return "\n".join(feat_lst)


def format_out_text_v2(text):
    text_lst = text.split("\n")
    print(f"text_lst: {text_lst}")
    #if "1" not in text_lst:
    #    return ""
    print(f"text_lst: {text_lst}")
    feat_lst = []
    for i in range(0, 8, 2):
        if text_lst[i+1].startswith("【包】"):
            feat_lst.append("带包")
        elif text_lst[i+1].startswith("【饮料】"):
            feat_lst.append("携带液体")
        elif text_lst[i+1].startswith("【交互】"):
            feat_lst.append("简单交互")
        elif text_lst[i+1].startswith("【特殊人群】"):
            feat_lst.append("特殊人群")
    print(f"feat_lst: {feat_lst}")
    return "\n".join(feat_lst)


def draw_rectangle_and_text(img, box, text, box_idx):
    # 创建一个可绘制的对象
    draw = ImageDraw.Draw(img)

    # 解包边界框坐标
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    # 绘制矩形
    draw.rectangle([x0, y0, x1, y1], outline=(0, 255, 0), width=2)

    # 设置文本位置
    text_x = x0 + 5
    if box_idx % 2 == 0:
        text_y = y0 + 20
    else:
        text_y = y0 + h // 2 - 20

    font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 32)

    # 添加文本到图像
    draw.text((text_x, text_y), text, fill=(255, 0, 0), font=font)

    return img


def extract_reid_feature_from_bbox(padded, transform):
    """
    返回 L2 归一化的特征向量 (1, 512)
    """
    reid_input = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)  # (256, 128, 3) RGB
    pil_img = Image.fromarray(reid_input)
    tensor = transform(pil_img).unsqueeze(0).to("cuda")  # (1, 3, 256, 128)

    with torch.no_grad():
        feat = model(tensor)
        feat = feat / feat.norm(dim=1, keepdim=True)  # L2 normalize
    return feat  # 在 GPU 上


def find_similar_crop_path(query_feat, feat_list, threshold=0.6):
    max_sim = -1
    best_path = None
    best_detect_text = None

    for feat_item in feat_list:
        old_feat = feat_item['feature']
        old_path = feat_item['save_path']
        old_detect_text = feat_item['detect_text']
        # 余弦相似度（假设都已L2归一化）
        sim = torch.mm(query_feat, old_feat.t()).item()  # 或 numpy.dot

        print(f"检查旧框：old_path {old_path}, sim {sim}")

        if sim > max_sim:
            max_sim = sim
            best_path = old_path
            best_detect_text = old_detect_text

    if max_sim > threshold:
        print(f"找到旧框：path {best_path}，max_sim {max_sim}")

    return (best_path, best_detect_text) if max_sim > threshold else (None, None)


async def test_pipeline():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)

        yolo_agent = YoloAgent("127.0.0.1", 28190)
        inst_v1_0 = dedent("""
            你是一个精准的视觉分析助手。输入图像由**三帧同一个人的连续画面横向拼接而成**（从左到右：帧1 → 帧2 → 帧3），请**仅基于最后一帧**（最右侧）进行分析。

            判断以下四项属性。对每一项，先输出 "0" 或 "1"，再在下一行给出**仅针对该项的简明解释**。

            判断顺序：
            第1项：是否手持或携带饮料容器（如水瓶、杯子、易拉罐、保温杯等）；
            第2项：是否正在进行交互手势（如挥手、拍照、指物、打电话等）——**仅当最后一帧中人物面部和身体正面可见时才可判为1**；
            第3项：是否属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿等）；
            第4项：是否携带包（如背包、手提包、单肩包等）。

            判断原则：
            - 所有属性必须在**最后一帧中清晰可见、无严重遮挡、无歧义**才标记为 1；
            - “正面可见”指能清楚看到双眼、鼻子、嘴巴及身体朝向镜头；
            - “特殊人群”不包括能正常行走的老年人；
            - 若图像模糊、遮挡、角度偏转（如侧脸、背影）或无法确认，则一律标记为 0。

            输出格式（必须严格遵守）：
            - 共 8 行：每项占 2 行，先输出 "0" 或 "1"，再换行输出解释；
            - 解释需基于**最后一帧中的具体视觉证据**，简洁明确；
            - 禁止包含编号、标题、标点、JSON、空行或任何额外文本。

            示例输出：
            0
            最后一帧双手自然下垂，未见饮料容器。
            0
            人物背对镜头，无法确认交互动作。
            0
            无轮椅、婴儿车或怀抱婴儿。
            1
            背部可见黑色双肩包，轮廓清晰。
        """).strip()
        inst_v1_1 = dedent("""
            你是一个严谨的视觉分析助手。输入图像由三帧同一个人的连续画面横向拼接而成（从左到右：帧1 → 帧2 → 帧3），请**仅基于最后一帧**（最右侧）进行分析。

            请严格按以下顺序逐项判断。对每一项：
            - 首先根据图像证据决定输出 "0" 或 "1"；
            - 然后在下一行，**仅当输出为 "1" 时，描述支持该判断的具体视觉证据**；
            - **若输出为 "0"，则必须写“无”**，不得描述“未见...”或“没有...”。

            判断顺序与定义：
            第1项（饮料）：是否手持或携带饮料容器（如水瓶、杯子、易拉罐、保温杯等）；
            第2项（交互）：是否正在进行交互手势（如挥手、拍照、指物、打电话等）——仅当人物面部和身体正面可见时才可判为1；
            第3项（特殊人群）：是否使用轮椅、推行婴儿车、怀抱婴儿等；正常行走的老年人不属于此类；
            第4项（包）：是否携带包（如背包、手提包、单肩包、购物袋等）。

            判断原则：
            - 仅当属性在最后一帧中**清晰可见、无遮挡、无歧义**时，才输出 "1"；
            - 若模糊、遮挡、角度偏转或无法确认，输出 "0"，解释写“无”。

            输出格式（必须严格遵守）：
            - 共 8 行：每项占 2 行；
            - 第1行：仅 "0" 或 "1"；
            - 第2行：若为 "1"，写具体证据（以【属性名】开头）；若为 "0"，**仅写“无”**；
            - 禁止使用“未见”、“没有”、“无法确认”等否定描述；
            - 禁止包含编号、标点冗余、JSON、空行或其他文本。

            示例输出：

            0
            无
            0
            无
            1
            【特殊人群】怀抱婴儿，婴儿头部清晰可见。
            1
            【包】右肩斜挎黑色格纹布袋。

            另一个示例：
            1
            【饮料】右手持透明塑料水瓶，瓶身反光可见。
            0
            无
            0
            无
            0
            无
        """).strip()
        inst_v1_2 = dedent("""
            你是一个高度严谨的视觉分析助手。输入图像由多帧同一个人的连续画面横向构成，请**基于多帧**进行分析，不要忽略每一帧的细节。

            请严格按以下顺序逐项判断。对每一项：
            - 首先根据图像证据决定输出 "0" 或 "1"；
            - 然后在下一行，**仅当输出为 "1" 时，描述支持该判断的具体视觉证据**；
            - **若输出为 "0"，则必须写“无”**，不得使用“未见”“没有”等否定描述。

            判断顺序与定义：
            第1项（饮料）：是否手持或携带**典型且可确认的饮料容器**，必须同时满足：
                - 容器形态典型（如圆柱水瓶、带盖咖啡杯、易拉罐、运动水壶、透明塑料瓶）；
                - **可见关键特征**：如透明瓶身见液体、杯盖、吸管、品牌 logo（如农夫山泉、星巴克）、易拉罐拉环；
                - 手持位置合理（手握瓶身/杯身，非仅提袋或夹持）；
                - **明确排除**：手机、雨伞、文件、药瓶、不透明无特征圆柱体、手部反光、模糊物体；
                - 若容器被遮挡、不透明且无特征、或仅为手部姿势推测，则视为不存在。
            第2项（包）：是否携带**明显可辨的包具**，必须同时满足：
                - 具有典型包的形态（如封闭袋体、提手、肩带、拉链等）；
                - 位于典型携带位置（肩部、背部、手提、斜跨、腰间等）；
                - 常见类型包括：背包、手提包、单肩包、托特包、斜挎包、塑料袋；
                - 若包被遮挡、则视为不存在。
            第3项（特殊人群）：是否为**行动不便的人士**，必须同时满足：
                - 常见类型包括：婴儿、儿童、残疾人；
                - **明确排除**：正常行走或步行的老年人。
            第4项（交互）：是否**正在进行交互手势**，必须同时满足：
                - 常见类型包括：如挥手、拍照；
                - **明确排除**：打电话；
                - 仅当人物面部和身体正面可见时才可判为1。

            判断原则：
            - 所有四项属性均要求**清晰可见、结构明确、无歧义**才可标 1；

            输出格式（必须严格遵守）：
            - 共 8 行：每项占 2 行；
            - 第1行：仅 "0" 或 "1"；
            - 第2行：若为 "1"，以【属性名】开头写具体证据；若为 "0"，**仅写“无”**；
            - 禁止包含编号、标点冗余、JSON、空行或其他文本。

            示例输出：

            0
            无
            1
            【包】背部清晰可见黑色双肩包，两侧肩带及包体轮廓完整。
            0
            无
            0
            无

            另一个示例（严格拒绝模糊情况）：
            0
            无
            0
            无
            0
            无
            0
            无
        """).strip()
        inst_v1_3 = dedent("""
            你是一个高度严谨的视觉分析助手。输入图像由多帧同一个人的连续画面横向构成，请**基于多帧**进行分析，并且以**最后一帧的内容**为主，其他帧是辅助判断。

            请严格按以下顺序逐项判断。对每一项：
            - 首先根据图像证据决定输出置信度（0.0到1.0）；
            - 然后在下一行，**仅当输出为大于0.6时，描述支持该判断的具体视觉证据**；
            - **若输出为小于0.6，则必须写“无”**，不得使用“未见”“没有”等否定描述。

            判断顺序与定义：
            第1项（饮料）：是否手持或携带**典型且可确认的饮料容器**，必须同时满足：
                - 容器形态典型（如圆柱水瓶、带盖咖啡杯、易拉罐、运动水壶、透明塑料瓶）；
                - **可见关键特征**：如透明瓶身见液体、杯盖、吸管、品牌 logo（如农夫山泉、星巴克）、易拉罐拉环；
                - 手持位置合理（手握瓶身/杯身，非仅提袋或夹持）；
                - **明确排除**：手机、雨伞、文件、药瓶、不透明无特征圆柱体、手部反光、模糊物体；
                - 若容器被遮挡、不透明且无特征、或仅为手部姿势推测，则视为不存在。
            第2项（包）：是否携带**明显可辨的包具**，必须同时满足：
                - 具有典型包的形态（如封闭袋体、提手、肩带、拉链等）；
                - 位于典型携带位置（肩部、背部、手提、斜跨、腰间等）；
                - 常见类型包括：背包、手提包、单肩包、托特包、斜挎包、塑料袋。
            第3项（特殊人群）：是否为**行动不便的人士**，必须同时满足：
                - 常见类型包括：婴儿、儿童、残疾人；
                - **明确排除**：正常行走或步行的老年人。
            第4项（交互）：是否**正在进行交互手势**，必须同时满足：
                - 常见类型包括：如挥手、拍照；
                - **明确排除**：打电话；
                - 仅当人物面部和身体正面可见时才可判为1。

            判断原则：
            - 所有四项属性均要求**清晰可见、结构明确、无歧义**；

            输出格式（必须严格遵守）：
            - 共 8 行：每项占 2 行；
            - 第1行：置信度（0.0到1.0）；
            - 第2行：若置信度大于0.6，以【属性名】开头写具体证据；若为置信度小于0.6，**仅写“无”**；
            - 禁止包含编号、标点冗余、JSON、空行或其他文本。

            示例输出：

            0.1
            无
            0.9
            【包】背部清晰可见黑色双肩包，两侧肩带及包体轮廓完整。
            0.2
            无
            0.3
            无

            另一个示例（严格拒绝模糊情况）：
            0.2
            无
            0.1
            无
            0.4
            无
            0.5
            无
        """).strip()
        # inst_v1_0 = dedent("""
        #     你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请按以下顺序逐项判断，并为每项输出一行结果（0 或 1）：

        #     1. 是否手持或携带饮料容器（如水瓶、杯子、易拉罐、保温杯等）；
        #     2. 是否正在进行交互手势（如挥手、拍照、指物、打电话等）；
        #     3. 是否属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿等）；
        #     4. 是否携带包（如背包、手提包、单肩包等）。

        #     判断原则：
        #     - 仅当属性在图像中清晰可见、无严重遮挡、无歧义时，才标记为 1；
        #     - 若模糊、被遮挡、视角受限或无法确认，则标记为 0。

        #     输出要求：
        #     - 仅输出四行字符，每行字符限制为：'0' 或 '1'；
        #     - 顺序必须严格对应上述四项；
        #     - 不要包含任何解释、空行、标点、编号、JSON 或其他文本。

        #     示例输出：
        #     0
        #     0
        #     0
        #     1
        # """).strip()

        # 预处理变换（注意：归一化参数必须与训练一致）
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        view_agent = create_view_agent(ctx, inst_v1_2)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        root_dir = Path(DATA_DIR)
        # 搜索head_stereo_right.h265
        h265_files = list(root_dir.rglob("head_stereo_right.h265"))
        video_files = {
            ### "1": DATA_DIR+"/94149/87bf4e4c-c6f7-4226-b5a9-96b287fb2d04/camera/head_stereo_right/head_stereo_right.h265",
            # "0": DATA_DIR+"/94149/9bf125ab-e3ff-43ac-aa11-ba4e4eca3831/camera/head_stereo_right/head_stereo_right.h265",
            # "2": DATA_DIR+"/94149/c7199446-c79e-45a1-a019-c4da82a68628/camera/head_stereo_right/head_stereo_right.h265",
            # "3": DATA_DIR+"/94150/6fbbbb88-392f-42b2-a68d-f3f5caddcd77/camera/head_stereo_right/head_stereo_right.h265",
            # "4": DATA_DIR+"/94151/9abdac3f-f199-40ee-902f-284ce2cd9896/camera/head_stereo_right/head_stereo_right.h265",
            # "5": DATA_DIR+"/94151/9e02be8b-7a06-45b4-aca2-d8c1c3ccd2db/camera/head_stereo_right/head_stereo_right.h265",
            # "6": DATA_DIR+"/94151/17b28c1e-4166-4cbc-94a3-d66758b0caaa/camera/head_stereo_right/head_stereo_right.h265",
            # "7": DATA_DIR+"/94151/53deb98e-366b-452b-8d3c-8ad652e40959/camera/head_stereo_right/head_stereo_right.h265",
            # "8": DATA_DIR+"/94151/23747bf2-b856-4278-bfea-aa806ee4e500/camera/head_stereo_right/head_stereo_right.h265",
            # "9": DATA_DIR+"/94151/81605ec2-0a2d-4092-b83f-e355fca49b11/camera/head_stereo_right/head_stereo_right.h265",
            # "10": DATA_DIR+"/94151/a8ed05e9-ee7a-4cb0-b186-a81df904d15d/camera/head_stereo_right/head_stereo_right.h265",
            # "11": DATA_DIR+"/94151/a2317682-cd1e-4ef7-b79b-eb3bacee59c7/camera/head_stereo_right/head_stereo_right.h265",
            # "12": DATA_DIR+"/94151/b80f11f7-96cd-4dd6-a698-6a2997287866/camera/head_stereo_right/head_stereo_right.h265",
            # "13": DATA_DIR+"/94152/b4753439-f8f0-4cd0-8c8e-bdca91e63a20/camera/head_stereo_right/head_stereo_right.h265",
            # "14": DATA_DIR+"/94154/9b369dae-da70-4bc1-ae87-3bfe99a34c52/camera/head_stereo_right/head_stereo_right.h265",
            # "15": DATA_DIR+"/94154/adac841e-fdc8-4943-a339-fa9fa2b182e4/camera/head_stereo_right/head_stereo_right.h265",
            # "16": DATA_DIR+"/94154/e80d6c50-703a-408b-8e3d-548779defec1/camera/head_stereo_right/head_stereo_right.h265",
            # "17": DATA_DIR+"/94155/7670b7e3-c951-4f9d-b5a8-f00c3602b4d0_婴儿车/camera/head_stereo_right/head_stereo_right.h265",
            # "18": DATA_DIR+"/94155/abd0374f-ba0f-4692-9ec8-4067667beb4c/camera/head_stereo_right/head_stereo_right.h265",
            # "19": DATA_DIR+"/94156/b98c2491-64ca-4c31-bf39-dcc95ac06010/camera/head_stereo_right/head_stereo_right.h265",
            "21": DATA_DIR+"/94157/dfedbda4-0f69-45bb-8cb7-83d147c74fe8/camera/head_stereo_right/head_stereo_right.h265",
            ### "20": DATA_DIR+"/94157/adac841e-fdc8-4943-a339-fa9fa2b182e4/camera/head_stereo_right/head_stereo_right.h265",
        }
        #video_filepath = video_files["3"]
        num_pre_frames = 2
        frame_step = 60

        # history_features记录之前两帧和现在这一帧，三帧的人物特征
        history_features = {}
        # for video_filepath in h265_files:
        for vi in video_files.keys():
            #if vi != "17":
            #   continue
            video_filepath = video_files[vi]
            try:
                # 先获取全部帧信息
                total = get_frame_count_h265(video_filepath)
                print(f"✓ 找到文件，总帧数: {total}")

                # 读取第一帧
                H265_OUTPUT_DIR = f"workspace/tools/vision_tools/video_{vi}"
                for i in range(0, total, frame_step):
                    #if i > 240:
                    #    continue
                    success, frame = load_h265(video_filepath, i)
                    draw_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    width, height = draw_img.size
                    print(f"✓ 成功读取第{i}帧，形状: {frame.shape}")
                    if success:
                        #H265_OUTPUT_DIR = Path(video_filepath).parent
                        directory = Path(H265_OUTPUT_DIR)
                        directory.mkdir(parents=True, exist_ok=True)
                        image_path = f"{H265_OUTPUT_DIR}/h265_{i}.png"
                        out_image_path = f"{H265_OUTPUT_DIR}/h265_output_{i}.jpg"
                        cv2.imwrite(image_path, frame)
                        enhance_image_path = f"{H265_OUTPUT_DIR}/h265_enhance_{i}.png"
                        #enhance_bag_separation(image_path, enhance_image_path)
                        #simple_adjust(image_path=image_path, brightness=20, saturation=1.0, output_path=enhance_image_path)
                    bbox_save_dir = f"workspace/tools/vision_tools/video_{vi}/bbox"
                    bbox_str = yolo_agent.detect(image_path)
                    bboxes = json.loads(bbox_str)
                    bboxes = sorted(bboxes, key=lambda bbox: bbox[0])
                    num_bboxes = len(bboxes)
                    print(f"num_bboxes: {num_bboxes}")
                    print(f"bboxes: {bboxes}")
                    this_frame_ft = []
                    bbox_idx = 0
                    debug_ouput_text = ""
                    for bbox in bboxes:
                        if not is_polygon_and_bbox_overlap_opencv(points_list, bbox):
                            print("不相关")
                            continue
                        x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
                        #x1 = x1 + 100 if x1 + 100 <= width else width
                        debug_ouput_text += f"bbox: ({x0}, {y0}, {x1}, {y1})\n"
                        img_size = [x1 - x0, y1 - y0]
                        print(f"img_size: {img_size}")
                        save_path, padded, crop = crop_bbox_to_png(image_path, x0, y0, x1, y1, bbox_save_dir)
                        print(f"save_path: {save_path}")

                        # 添加了将切分图像生成为特征
                        feat = extract_reid_feature_from_bbox(padded, transform)
                        # 记录特征
                        this_frame_ft.append({'feature': feat, 'save_path': save_path, 'detect_text': ""})

                        # Detect
                        def detect_with_retry(view_agent, save_path_lst, last_detect_text=None, max_retries=3, delay=2):
                            for attempt in range(max_retries):
                                try:
                                    return view_tool.detect(view_agent, save_path_lst, last_detect_text)
                                except ModelProviderError as e:
                                    if "timed out" in str(e).lower() and attempt < max_retries - 1:
                                        print(f"第 {attempt + 1} 次超时，{delay}秒后重试...")
                                        time.sleep(delay)
                                        delay *= 2  # 指数退避
                                    else:
                                        raise
                            return None

                        last_detect_text = None
                        if num_pre_frames > 0:
                            save_path_lst = []
                            for j in range(-num_pre_frames, 0, 1):
                                old_frame_idx = i + j * frame_step
                                if old_frame_idx >= 0:
                                    old_feat_list = history_features[str(old_frame_idx)]
                                    old_crop_path, old_detect_text = find_similar_crop_path(feat, old_feat_list, 0.85)
                                    if old_frame_idx == (i - frame_step):
                                        last_detect_text = old_detect_text
                                    if old_crop_path is not None:
                                        save_path_lst.append(old_crop_path)
                            save_path_lst.append(save_path)

                            # save_path_lst.append(save_path)
                            # j = -1
                            # old_frame_idx = i + j * frame_step
                            # while len(save_path_lst) < (num_pre_frames+1) and old_frame_idx >= 0:
                            #     old_feat_list = history_features[str(old_frame_idx)]
                            #     old_crop_path = find_similar_crop_path(feat, old_feat_list, 0.85)
                            #     if old_crop_path is not None:
                            #         save_path_lst.append(old_crop_path)
                            #     j = j - 1
                            #     old_frame_idx = i + j * frame_step
                            # save_path_lst.reverse()

                            concat_save_path = concat_images_horizontal(save_path_lst, bbox_save_dir)

                            #out_text = view_tool.detect(view_agent, save_path_lst)
                            out_text = detect_with_retry(view_agent, save_path_lst, last_detect_text)
                            #out_text = detect_with_retry(view_agent, [concat_save_path])
                        else:
                            out_text = view_tool.detect(view_agent, save_path)
                        this_frame_ft[-1]["detect_text"] = out_text
                        debug_ouput_text += f"detect:\n{out_text}\n"
                        print(f"out_text: {out_text}")
                        draw_text = format_out_text_v2(out_text)
                        print(f"draw_text: {draw_text}")
                        if draw_text is not None:
                            draw_rectangle_and_text(draw_img, bbox, draw_text, bbox_idx)
                            bbox_idx += 1
                        #input("Press to ENTER to process next bbox")
                    # 更新history_features
                    history_features[str(i)] = this_frame_ft
                    # 保存带框图片
                    time.sleep(1.0)
                    with_poloy=draw_transparent_polygon_on_pil(draw_img, points_list)
                    with_poloy.save(out_image_path, format="JPEG")
                    # exit()
                    # 保存debug文本
                    with open(f'{H265_OUTPUT_DIR}/h265_output_{i}.txt', 'w', encoding='utf-8') as f:
                        f.write(debug_ouput_text)

                #exit()
                #break

            except Exception as e:
                print(f"✗ 读取H265文件失败: {e}")
                traceback.print_exc()


async def test_retrograde():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        yolo_agent = YoloAgent("127.0.0.1", 28190)
        # inst = dedent("""
        #     你是一个精准的视觉分析助手。请分析输入的单人图像，并判断以下两个条件是否**同时成立**：

        #     1. 该人处于**严格正面姿态**：面部（包括双眼、鼻子、嘴巴）和身体躯干基本正对镜头，**不允许侧脸、半侧身、背影或明显偏转角度（如向左或向右）**；
        #     2. 该人**正在行走**：呈现自然行走的姿态，例如一只脚离地、双臂摆动、重心前移等，**排除站立、奔跑、骑车、坐姿或静止不动等情况**。

        #     仅当上述两个条件都明确满足时，输出：
        #     1

        #     其他所有情况（包括姿态非正面、未行走、图像模糊、遮挡严重、无法确定等），均输出：
        #     0

        #     **输出要求：**
        #     - 仅输出一个字符：`1` 或 `0`。
        #     - 不要包含任何其他文字、空格、标点、解释或格式。
        # """).strip()
        inst = dedent("""
            你是一个专业的视觉时序分析助手。用户将提供同一个人的连续三帧图像（按时间顺序排列），你需要综合这三帧的信息，判断该人在**当前时刻**（尤其是最后一帧）的**身体朝向**。

            朝向定义如下：
            - “正”：人物正面朝向摄像头，清晰可见面部（双眼、鼻子、嘴巴）和身体正面；
            - “背”：人物背对摄像头，只能看到后脑勺、背部或后背衣物；
            - “左”：人物面向画面左侧（即其身体朝左，右脸或右侧身体更明显）；
            - “右”：人物面向画面右侧（即其身体朝右，左脸或左侧身体更明显）。

            请基于三帧的动态和姿态信息，做出最准确的判断。

            **输出要求：**
            - 仅输出一个中文字符：`正`、`背`、`左` 或 `右`。
            - 不要输出任何其他文字、标点、空格、解释或格式。
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        video_path = f"{DATA_DIR}/逆行.mp4"
        save_dir = str(VISION_WORKSPACE_DIR)
        video_fps = get_fps(video_path)
        print(f"视频帧数：{video_fps}")
        frame_idx_list = [90, 120, 150]
        frames = []
        for frame_idx in frame_idx_list:
            frame = read_frame(video_path, frame_idx)
            frames.append(frame)
        if len(frames) > 0:
            save_path_lst = []
            for i in range(len(frames)):
                frame = frames[i]
                frame_idx = frame_idx_list[i]
                image_path = f"{save_dir}/逆行_{frame_idx}.png"
                cv2.imwrite(image_path, frame)
                print(f"已保存视频帧：{image_path}")

                bbox_str = yolo_agent.detect(image_path)
                print(f"bbox_str: {bbox_str}")
                bboxes = json.loads(bbox_str)
                num_bboxes = len(bboxes)
                print(f"num_bboxes: {num_bboxes}")
                print(f"bboxes: {bboxes}")
                for bbox in bboxes:
                    x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
                    save_path = crop_bbox_to_png(image_path, x0, y0, x1, y1, save_dir)
                    print(f"save_path: {save_path}")
                    save_path_lst.append(save_path)
            try:
                out_text = view_tool.detect(view_agent, save_path_lst)
                print(f"out_text: {out_text}")
            except Exception as e:
                print(e)
                pass


async def test_retrograde_h265():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        yolo_agent = YoloAgent("127.0.0.1", 28190)
        # inst = dedent("""
        #     你是一个精准的视觉分析助手。请分析输入的单人图像，并判断以下两个条件是否**同时成立**：

        #     1. 该人处于**严格正面姿态**：面部（包括双眼、鼻子、嘴巴）和身体躯干基本正对镜头，**不允许侧脸、半侧身、背影或明显偏转角度（如向左或向右）**；
        #     2. 该人**正在行走**：呈现自然行走的姿态，例如一只脚离地、双臂摆动、重心前移等，**排除站立、奔跑、骑车、坐姿或静止不动等情况**。

        #     仅当上述两个条件都明确满足时，输出：
        #     1

        #     其他所有情况（包括姿态非正面、未行走、图像模糊、遮挡严重、无法确定等），均输出：
        #     0

        #     **输出要求：**
        #     - 仅输出一个字符：`1` 或 `0`。
        #     - 不要包含任何其他文字、空格、标点、解释或格式。
        # """).strip()
        inst = dedent("""
            你是一个专业的视觉时序分析助手。用户将提供同一个人的连续三帧图像（按时间顺序排列），你需要综合这三帧的信息，判断该人在**当前时刻**（尤其是最后一帧）的**身体朝向**。

            朝向定义如下：
            - “正”：人物正面朝向摄像头，清晰可见面部（双眼、鼻子、嘴巴）和身体正面；
            - “背”：人物背对摄像头，只能看到后脑勺、背部或后背衣物；
            - “左”：人物面向画面左侧（即其身体朝左，右脸或右侧身体更明显）；
            - “右”：人物面向画面右侧（即其身体朝右，左脸或左侧身体更明显）。

            请基于三帧的动态和姿态信息，做出最准确的判断。

            **输出要求：**
            - 仅输出一个中文字符：`正`、`背`、`左` 或 `右`。
            - 不要输出任何其他文字、标点、空格、解释或格式。
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        video_files = {
            "0": DATA_DIR+"/94149/9bf125ab-e3ff-43ac-aa11-ba4e4eca3831/camera/head_stereo_right/head_stereo_right.h265",
            "1": DATA_DIR+"/94149/87bf4e4c-c6f7-4226-b5a9-96b287fb2d04/camera/head_stereo_right/head_stereo_right.h265",
            "2": DATA_DIR+"/94149/c7199446-c79e-45a1-a019-c4da82a68628/camera/head_stereo_right/head_stereo_right.h265",
        }
        num_pre_frames = 2
        frame_step = 60

        history_features = {}
        # for video_filepath in h265_files:
        for vi in video_files.keys():
            video_filepath = video_files[vi]
            try:
                # 先获取全部帧信息
                total = get_frame_count_h265(video_filepath)
                print(f"✓ 找到文件，总帧数: {total}")

                # 读取第一帧
                for i in range(0, total, frame_step):
                    success, frame = load_h265(video_filepath, i)
                    draw_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    print(f"✓ 成功读取第{i}帧，形状: {frame.shape}")
                    if success:
                        #H265_OUTPUT_DIR = Path(video_filepath).parent
                        H265_OUTPUT_DIR = f"workspace/tools/vision_tools/video_{vi}"
                        directory = Path(H265_OUTPUT_DIR)
                        directory.mkdir(parents=True, exist_ok=True)
                        image_path = f"{H265_OUTPUT_DIR}/h265_{i}.png"
                        out_image_path = f"{H265_OUTPUT_DIR}/h265_output_{i}.jpg"
                        cv2.imwrite(image_path, frame)
                    bbox_save_dir = f"workspace/tools/vision_tools/video_{vi}/bbox"
                    bbox_str = yolo_agent.detect(image_path)
                    bboxes = json.loads(bbox_str)
                    bboxes = sorted(bboxes, key=lambda bbox: bbox[0])
                    num_bboxes = len(bboxes)
                    print(f"num_bboxes: {num_bboxes}")
                    print(f"bboxes: {bboxes}")
                    this_frame_ft = []
                    bbox_idx = 0
                    for bbox in bboxes:
                        x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
                        img_size = [x1 - x0, y1 - y0]
                        print(f"img_size: {img_size}")
                        save_path, padded, crop = crop_bbox_to_png(image_path, x0, y0, x1, y1, bbox_save_dir)
                        print(f"save_path: {save_path}")

                        # 添加了将切分图像生成为特征
                        feat = extract_reid_feature_from_bbox(padded, transform)
                        # 记录特征
                        this_frame_ft.append({'feature': feat, 'save_path': save_path})

                        # Detect
                        if num_pre_frames > 0:
                            save_path_lst = []
                            for j in range(-num_pre_frames, 0, 1):
                                old_frame_idx = i + j * frame_step
                                if old_frame_idx >= 0:
                                    old_feat_list = history_features[str(old_frame_idx)]
                                    old_crop_path = find_similar_crop_path(feat, old_feat_list, 0.92)
                                    if old_crop_path is not None:
                                        save_path_lst.append(old_crop_path)
                            save_path_lst.append(save_path)
                            concat_images_horizontal(save_path_lst, bbox_save_dir)
                            out_text = view_tool.detect(view_agent, save_path_lst)
                        else:
                            out_text = view_tool.detect(view_agent, save_path)
                        print(f"out_text: {out_text}")
                        draw_text = out_text
                        print(f"draw_text: {draw_text}")
                        if draw_text is not None:
                            draw_rectangle_and_text(draw_img, bbox, draw_text, bbox_idx)
                            time.sleep(1.0)
                            bbox_idx += 1
                        #input("Press to ENTER to process next bbox")
                    # 更新history_features
                    history_features[str(i)] = this_frame_ft
                    # 保存带框图片
                    time.sleep(1.0)
                    draw_img.save(out_image_path, format="JPEG")

                #exit()
                #break

            except Exception as e:
                print(f"✗ 读取H265文件失败: {e}")
                traceback.print_exc()


async def main(args):
    await test_pipeline()
    #await test_retrograde()
    #await test_retrograde_h265()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run RabbitBot workflow example.')
    parser.add_argument('--patch', action='store_true', help='Enable patching for bot and VLN agent.')
    args = parser.parse_args()
    asyncio.run(main(args))
