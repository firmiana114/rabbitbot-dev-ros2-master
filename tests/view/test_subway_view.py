
import os
import cv2
import time
import asyncio
import argparse
from pathlib import Path
from textwrap import dedent
from agno.agent import Agent
from rabbitbot.context import AppContext
from rabbitbot.tools.vision_agno import VisionToolkit
from rabbitbot.tools.sound_agno import tts_sound, tts_wait
from rabbitbot.robots.constants import MoveType

from utils import read_frame, get_fps


REPO_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = REPO_DIR.parent
TEST_DATA_ROOT = Path(os.environ.get("RABBITBOT_TEST_DATA_ROOT", PROJECTS_DIR / "downloads"))
DATA_DIR = str(Path(os.environ.get("RABBITBOT_SUBWAY_DATA_DIR", TEST_DATA_ROOT / "agi-robot-subway")))


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


async def test_bag():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个视觉理解助手。请分析输入图像，完成以下任务：

            - 检测图像中所有行人。
            - 判断每个行人是否携带包（包括背包、手提包、斜挎包等任何形式的包）。
            - 仅对携带包的行人，输出其边界框（BBOX），格式为 [x_min, y_min, x_max, y_max]，坐标采用绝对坐标。
            - 如果没有行人带包，则输出空列表。

            输出要求：
            - 仅输出一个 List 格式的对象，包含键 "bboxes"，其值为边界框列表。
            - 不要 JSON 格式的对象。
            - 不要包含任何解释、注释或其他文本。

            示例输出（带包）：
            [[x_min, y_min, x_max, y_max], ...]

            示例输出（无带包行人）：
            []
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/带包不过安检.png"
        view_tool.detect(view_agent, image_path)


async def test_water_bottle():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个视觉理解助手。请分析输入图像，完成以下任务：

            - 检测图像中所有行人。
            - 判断每个行人是否携带水瓶（包括矿泉水瓶、塑料瓶、玻璃瓶、保温杯、运动水壶等任何形式的可手持或随身携带的水瓶/水壶）。
            - 仅对携带水瓶的行人，输出其边界框（BBOX），格式为 [x_min, y_min, x_max, y_max]，坐标采用绝对坐标。
            - 如果没有行人携带水瓶，则输出空列表。

            输出要求：
            - 仅输出一个 Python 列表（List），包含所有携带水瓶行人的边界框。
            - 不要包含 JSON 对象、键名（如 "bboxes"）、解释、注释或其他任何额外文本。
            - 输出必须是有效的列表字面量，可被 `json.loads()` 或 `ast.literal_eval()` 解析。

            示例输出（有携带水瓶的行人）：
            [[x_min, y_min, x_max, y_max], ...]

            示例输出（无人携带水瓶）：
            []
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/无包识别.png"
        view_tool.detect(view_agent, image_path)


async def test_special_people():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个视觉理解助手。请分析输入图像，完成以下任务：

            - 检测图像中所有行人。
            - 判断其中是否存在“特殊人群”，包括但不限于：
                • 使用轮椅的人
                • 推婴儿车（或手推车中有婴儿）的人
                • 怀抱婴儿的人
                • 明显照顾婴幼儿或行动不便者的行人
            - 仅对属于上述“特殊人群”的行人，输出其人体边界框（BBOX），格式为 [x_min, y_min, x_max, y_max]，坐标采用绝对坐标。
            - 如果图像中没有此类特殊人群，则输出空列表。

            输出要求：
            - 仅输出一个 Python 列表（List），包含所有符合条件的行人的边界框。
            - 不要包含任何键名（如 "bboxes"）、JSON 结构、解释、注释或其他文本。
            - 输出必须是有效的列表字面量，可被 `json.loads()` 或 `ast.literal_eval()` 安全解析。

            示例输出（有特殊人群）：
            [[x_min, y_min, x_max, y_max], ...]

            示例输出（无特殊人群）：
            []
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/无包识别.png"
        view_tool.detect(view_agent, image_path)


async def test_interaction():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个视觉理解助手。请分析输入图像，完成以下任务：

            - 检测图像中所有行人。
            - 判断其中是否有人正在与拍摄者（即“你”）进行直接互动，包括但不限于：
                • 向镜头挥手
                • 面对镜头微笑或做表情
                • 比出“V”字、点赞等面向镜头的手势
                • 正在被拍摄并有明显配合姿态（如摆拍）
                • 直视镜头并做出互动性动作（如指向镜头、举手示意等）
            - 仅对正在进行上述互动行为的行人，输出其人体边界框（BBOX），格式为 [x_min, y_min, x_max, y_max]，坐标采用绝对坐标。
            - 如果无人与拍摄者互动，则输出空列表。

            输出要求：
            - 仅输出一个 Python 列表（List），包含所有互动行人的边界框。
            - 不要包含任何键名（如 "bboxes"）、JSON 结构、解释、注释或其他文本。
            - 输出必须是有效的列表字面量，可被 `json.loads()` 或 `ast.literal_eval()` 安全解析。

            示例输出（有人互动）：
            [[x_min, y_min, x_max, y_max], ...]

            示例输出（无人互动）：
            []
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/无包识别.png"
        view_tool.detect(view_agent, image_path)


async def test_four_featrues():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个面向人群场景的精准视觉分析助手。请分析输入图像，并检测其中出现的每一个人。

            对每个人，请按以下顺序判断四个二值属性（是则为 1，否则为 0）：

            1. 是否携带包（如背包、手提包、单肩包、托特包等）；
            2. 是否手持或携带饮料容器（如水瓶、塑料杯、咖啡杯、保温杯、易拉罐等）；
            3. 是否正在做出交互动作（如挥手、拍照、指物、举着手机通话等）；
            4. 是否属于特殊人群（如使用轮椅、推行婴儿车、怀抱婴儿、或有婴幼儿随行等）。

            **输出要求：**

            - 仅为连续的多行文本，每行是一个 4 位二进制字符串（例如 `1000`），每人一行，按你检测到的顺序输出。
            - **不要使用方括号、逗号、引号、JSON、空格或任何额外文字**。
            - 每行必须且仅包含四个字符，每个字符为 `0` 或 `1`。
            - 如果图像中未检测到任何人，请**不输出任何内容**（返回空响应）。

            **示例：**

            若检测到两人，第一人仅带包，第二人仅携带饮料：
            1000
            0100

            若一人无任何上述特征：
            0000

            若无人：
            （无输出）
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/带包不过安检.png"
        view_tool.detect(view_agent, image_path)
        view_tool.detect(view_agent, image_path)


async def test_people_amount():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一个视觉理解助手。请分析输入图像，并完成以下任务：

            - 估算图像中出现的人的数量。
            - 不需要精确定位或检测每个人，只需给出一个合理的整数估计值（例如：0、1、3、10、20+ 等）。
            - 如果图像中没有人，输出 0。
            - 输出必须仅为一个非负整数，不要包含任何其他文字、标点、单位或解释。

            示例输出：
            5
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        image_path = f"{DATA_DIR}/带包不过安检.png"
        view_tool.detect(view_agent, image_path)
        view_tool.detect(view_agent, image_path)


async def test_retrograde():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs, with_robot_agent=False) as ctx:
        time.sleep(1.0)
        inst = dedent("""
            你是一位交通监控员，负责分析单帧图像中的行人行为。

            背景信息：
            - 图像中道路的正常通行方向是【↑】（向上）。

            任务要求：
            1. 分析图像中的每个人，并给出其“身体朝向”（用箭头表示：↑↓←→↗↘↖↙）。
            2. 如果能识别到人脸，则额外给出“脸朝向”（同样用箭头表示）。
            3. 根据身体或脸朝向与道路正常方向之间的夹角判断是否为“疑似逆行”。如果夹角大于90度，则标记为“疑似逆行”；否则标记为“正常”。

            输出格式：
            每个行人一行，格式如下：
            person_X: 身体[箭头] 脸[箭头] [状态]
            其中：
            - person_X 表示第X个人（从0开始编号）。
            - 状态只能是“正常”或“疑似逆行”。
            - 如果无法确定脸的方向，则省略“脸[箭头]”。

            示例输出：
            person_0: 身体↑ 脸↑ 正常
            person_1: 身体↓ 脸↓ 疑似逆行
            person_2: 身体← 正常

            注意：
            - 所有箭头必须是以下之一：↑↓←→↗↘↖↙。
            - 输出应严格遵循指定格式，不包含其他解释或注释。
        """).strip()
        view_agent = create_view_agent(ctx, inst)
        view_tool = VisionToolkit(ctx, frame_size=(640, 480))
        video_path = f"{DATA_DIR}/逆行.mp4"
        video_fps = get_fps(video_path)
        print(f"视频帧数：{video_fps}")
        frame_idx = 300
        frame = read_frame(video_path, frame_idx)
        if frame is not None:
            image_path = f"{DATA_DIR}/逆行_{frame_idx}.png"
            cv2.imwrite(image_path, frame)
            print(f"已保存视频帧：{image_path}")
        view_tool.detect(view_agent, image_path)


async def main(args):
    #await test_bag()
    #await test_water_bottle()
    #await test_special_people()
    #await test_interaction()
    #await test_four_featrues()
    await test_people_amount()
    #await test_retrograde()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run RabbitBot workflow example.')
    parser.add_argument('--patch', action='store_true', help='Enable patching for bot and VLN agent.')
    args = parser.parse_args()
    asyncio.run(main(args))
