
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
from rabbitbot.context import AppContext
from rabbitbot.tools.vision_agno import VisionToolkit
from rabbitbot.tools.sound_agno import tts_sound, tts_wait
from rabbitbot.robots.constants import MoveType

from yolo_agent import YoloAgent
from utils import read_frame, get_fps


REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROJECTS_DIR = os.path.abspath(os.path.join(REPO_DIR, ".."))
TEST_DATA_ROOT = os.environ.get("RABBITBOT_TEST_DATA_ROOT", os.path.join(PROJECTS_DIR, "downloads"))
DATA_DIR = os.environ.get("RABBITBOT_SUBWAY_DATA_DIR", os.path.join(TEST_DATA_ROOT, "agi-robot-subway"))
VISION_WORKSPACE_DIR = os.environ.get(
    "RABBITBOT_VISION_WORKSPACE_DIR",
    os.path.join(REPO_DIR, "workspace", "tools", "vision_tools")
)


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

    # 自动生成保存路径
    if save_path is None:
        base, _ = os.path.splitext(image_path)
        save_path = f"{base}_crop.png"
    else:
        img_filename = image_path.rsplit('/', 1)[1].rsplit('.', 1)[0]
        save_path = f"{save_path}/{img_filename}_crop_{x0}_{y0}_{x1}_{y1}.png"

    # 保存为 PNG（最高质量）
    cv2.imwrite(save_path, crop, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    return save_path


async def test_pipeline():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)

        yolo_agent = YoloAgent("127.0.0.1", 28190)
        inst = dedent("""
            你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请判断该人物是否具有以下四项属性：

            1. 携带包（例如背包、手提包、单肩包、托特包等）；
            2. 手持或携带饮料容器（例如水瓶、塑料杯、咖啡杯、保温杯、易拉罐等）；
            3. 正在进行交互手势（例如挥手、拍照、指物、将手机举到耳边等）；
            4. 属于特殊人群（例如使用轮椅、推行婴儿车、怀抱婴儿，或有婴幼儿随行等）。

            对每项属性，请按以下规则赋值：
            - 若属性明显存在，则标记为 1；
            - 若不存在或无法确定，则标记为 0。

            仅输出一个由 '0' 和 '1' 组成的 4 位字符串，顺序严格对应上述四项属性（包、饮料、交互、特殊人群）。
            不要包含任何其他文字、空格、标点、解释或格式。

            示例：
            - "1000" → 有包，无饮料，无交互，非特殊人群；
            - "0110" → 无包，有饮料，有交互，非特殊人群；
            - "0001" → 无包，无饮料，无交互，是特殊人群；
            - "0000" → 四项属性均不满足。
        """).strip()
        inst = dedent("""
            你是一个精准且可解释的视觉分析助手。给定一张包含单个人物的输入图像，请判断以下四项属性：

            1. 携带包（如背包、手提包等）；
            2. 手持或携带饮料容器（如水瓶、杯子、易拉罐等）；
            3. 正在进行交互手势（如挥手、拍照、指物等）；
            4. 属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿等）。

            判断原则：
            - 仅当属性在图像中清晰可见、无严重遮挡、无歧义时，才标记为 1；
            - 若模糊、被遮挡、视角受限或无法确认，则标记为 0。

            输出格式（必须严格遵守）：
            - 第一行：一个由 '0' 和 '1' 组成的 4 位字符串，**严格按照顺序：包、饮料、交互、特殊人群，不要改变这个顺序**；
            - 第二行：用一句简洁中文说明你的判断依据，聚焦于**图像中可见的具体视觉证据**（例如“肩背黑色双肩包，右手持透明水瓶，左手自然下垂，独立行走无辅助设备”）；
            - 不要包含任何其他文字、空行、标点冗余、JSON、引号或额外说明。

            示例输出：

            1000
            肩背灰色双肩包，双手空闲未持物品，身体静止无交互动作，无轮椅或婴儿随行。

            0110
            右手持咖啡杯，左手举手机至耳边似在通话，未见包具，独立站立。

            0000
            双手自然下垂，未见包、饮料、交互动作，身体健全无辅助设备。
        """).strip()
        inst = dedent("""
            你是一个精准且可解释的视觉分析助手。给定一张包含单个人物的输入图像，请**逐项**判断以下四个属性。对每一项，先输出判断结果（0 或 1），再在下一行给出**仅针对该项的简明解释**。

            判断顺序与内容：
            第1项：是否手持或携带饮料容器（如水瓶、杯子、易拉罐、保温杯等）；
            第2项：是否正在进行交互手势（如挥手、拍照、指物、打电话等）；
            第3项：是否属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿等）。
            第4项：是否携带包（如背包、手提包、单肩包等）；

            判断原则：
            - 仅当属性在图像中清晰可见、无严重遮挡、无歧义时，才标记为 1；
            - 若模糊、被遮挡、视角受限或无法确认，则标记为 0。

            输出格式（必须严格遵守）：
            - 共 8 行：每项占 2 行，先输出 "0" 或 "1"，再换行输出该项的解释；
            - 解释必须聚焦于**图像中可见的具体视觉证据**，简洁明确；
            - 不要包含属性编号、标题、标点冗余、JSON、空行或其他任何额外文本。

            示例输出：

            0
            双手空闲，未见任何饮料容器。
            0
            双臂自然下垂，无挥手、拍照或指物动作。
            0
            独立站立行走，无轮椅、婴儿车或怀抱婴儿。
            1
            肩背黑色双肩包，轮廓清晰可见。

            注意：输出必须正好 8 行，顺序不可更改。
        """).strip()
        inst = dedent("""
            你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请按以下顺序逐项判断，并为每项输出一行结果（0 或 1）：

            1. 是否手持或携带饮料容器（如水瓶、杯子、易拉罐、保温杯等）；
            2. 是否正在进行交互手势（如挥手、拍照、指物、打电话等）；
            3. 是否属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿等）；
            4. 是否携带包（如背包、手提包、单肩包等）。

            判断原则：
            - 仅当属性在图像中清晰可见、无严重遮挡、无歧义时，才标记为 1；
            - 若模糊、被遮挡、视角受限或无法确认，则标记为 0。

            输出要求：
            - 仅输出四行字符，每行字符限制为：'0' 或 '1'；
            - 顺序必须严格对应上述四项；
            - 不要包含任何解释、空行、标点、编号、JSON 或其他文本。

            示例输出：
            0
            0
            0
            1
        """).strip()
        # inst = dedent("""
        #     你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请判断该人物是否具有以下属性：

        #     手持或携带饮料容器（例如水瓶、塑料杯、咖啡杯、保温杯、易拉罐等）。

        #     对该属性，请按以下规则赋值：
        #     - 若属性明显存在，则标记为 1；
        #     - 若不存在或无法确定，则标记为 0。

        #     仅输出一个由 '0' 和 '1' 组成的 1 位字符串。
        #     不要包含任何其他文字、空格、标点、解释或格式。

        #     示例：
        #     - "1" → 有饮料；
        #     - "0" → 无饮料。
        # """).strip()
        # inst = dedent("""
        #     你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请判断该人物是否具有以下属性：

        #     正在进行交互手势（例如挥手、拍照、指物、将手机举到耳边等）。

        #     对该属性，请按以下规则赋值：
        #     - 若属性明显存在，则标记为 1；
        #     - 若不存在或无法确定，则标记为 0。

        #     仅输出一个由 '0' 和 '1' 组成的 1 位字符串。
        #     不要包含任何其他文字、空格、标点、解释或格式。

        #     示例：
        #     - "1" → 有交互；
        #     - "0" → 无交互。
        # """).strip()
        # inst = dedent("""
        #     你是一个精准的视觉分析助手。给定一张包含单个人物的输入图像，请判断该人物是否具有以下属性：

        #     属于特殊人群（例如使用轮椅、推行婴儿车、怀抱婴儿，或有婴幼儿随行等）。

        #     对该属性，请按以下规则赋值：
        #     - 若属性明显存在，则标记为 1；
        #     - 若不存在或无法确定，则标记为 0。

        #     仅输出一个由 '0' 和 '1' 组成的 1 位字符串。
        #     不要包含任何其他文字、空格、标点、解释或格式。

        #     示例：
        #     - "1" → 是特殊人群；
        #     - "0" → 非特殊人群。
        # """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))

        image_files = {
            "0": "带包识别1",
            "1": "带包识别2",
            "2": "带包不过安检",
            "3": "无包识别",
            "4": "携带液体1",
            "5": "携带液体2",
            "6": "弱交互1",
            "7": "弱交互2",
            "8": "弱交互3",
            "9": "特殊人群1",
            "10": "特殊人群2",
            "11": "入口处人流较大",
        }
        image_filename = image_files["0"]

        image_path = f"{DATA_DIR}/{image_filename}.png"
        save_dir = "workspace/tools/vision_tools"
        bbox_str = yolo_agent.detect(image_path)
        bboxes = json.loads(bbox_str)
        bboxes = sorted(bboxes, key=lambda bbox: bbox[0])
        num_bboxes = len(bboxes)
        print(f"num_bboxes: {num_bboxes}")
        print(f"bboxes: {bboxes}")
        for bbox in bboxes:
            x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
            img_size = (x1 - x0, y1 - y0)
            print(f"img_size: {img_size}")
            save_path = crop_bbox_to_png(image_path, x0, y0, x1, y1, save_dir)
            print(f"save_path: {save_path}")
            try:
                out_text = view_tool.detect(view_agent, save_path)
                #out_text = view_tool.detect(view_agent, save_path)
                print(f"out_text: {out_text}")
            except:
                pass


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
        save_dir = VISION_WORKSPACE_DIR
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


async def main(args):
    await test_pipeline()
    #await test_retrograde()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run RabbitBot workflow example.')
    parser.add_argument('--patch', action='store_true', help='Enable patching for bot and VLN agent.')
    args = parser.parse_args()
    asyncio.run(main(args))
