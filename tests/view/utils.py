
import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Union
from PIL import Image


def read_frame(video_path, frame_number):
    """
    读取视频中指定帧号的图像。

    参数:
        video_path (str): 视频文件路径。
        frame_number (int): 要读取的帧号（从0开始）。

    返回:
        np.ndarray | None: BGR格式的图像数组，若帧不存在则返回None。
    """
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def get_fps(video_path: str) -> float:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps


Number = Union[int, float]
BBox = List[Number]          # 单个框
BBoxes = Union[List[BBox], np.ndarray]  # 多个框

def draw_bboxes(
        bboxes: BBoxes,
        image_path: str,
        out_dir: str,
        color: Union[Tuple[int, int, int], List[Tuple[int, int, int]]] = (0, 255, 0),
        thickness: int = 2
) -> str:
    """
    在图片上画多个 bbox 并保存到指定目录。

    参数
    ----
    bboxes : list[list[int]] 或 np.ndarray, shape=(N,4)
        每个元素为 [xmin, ymin, xmax, ymax]，像素坐标。
    image_path : str
        原始图片路径。
    out_dir : str
        结果保存目录，若不存在则自动创建。
    color : tuple 或 list[tuple], optional
        框颜色，BGR 顺序。默认为红色。
        若给出单个 tuple，则所有框用同一颜色；
        若给出 list，长度需与 bboxes 一致，实现一框一色。
    thickness : int, optional
        线宽，默认 2。

    返回
    ----
    save_path : str
        画框后的图片保存路径。
    """
    # 0. 统一转成 list[list[int]]
    if isinstance(bboxes, np.ndarray):
        bboxes = bboxes.astype(int).tolist()
    if not bboxes:        # 空列表直接拷贝原图
        bboxes = []

    # 1. 读取图片
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"无法读取图片：{image_path}")

    # 2. 颜色处理
    if isinstance(color, tuple):
        colors = [color] * len(bboxes)
    else:
        colors = color
    if len(colors) != len(bboxes):
        raise ValueError("color 列表长度必须与 bboxes 数量一致")

    # 3. 画框
    for (xmin, ymin, xmax, ymax), c in zip(bboxes, colors):
        if xmin >= xmax or ymin >= ymax:
            continue   # 跳过非法框
        cv2.rectangle(img, (int(xmin), int(ymin)), (int(xmax), int(ymax)),
                      color=c, thickness=thickness)

    # 4. 构造保存路径
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(image_path).stem
    ext = Path(image_path).suffix
    save_path = str(out_dir / f"{name}_bbox{ext}")

    # 5. 保存
    cv2.imwrite(save_path, img)
    return save_path

import subprocess
import re

def get_frame_count_h265(filepath):
    print('计算帧数')
    cmd = [
        'ffmpeg', '-i', filepath,
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    # print(result.stderr)  # 打印完整 stderr，查看是否有 frame= 行
    # 使用正则提取所有 frame= 后的数字
    frame_numbers = []
    for line in result.stderr.splitlines():
        match = re.search(r'frame=\s*(\d+)', line)
        if match:
            frame_num = int(match.group(1))
            frame_numbers.append(frame_num)
            # 可选：打印每行匹配（用于调试）
            # print(f"[DEBUG] 匹配到帧数: {frame_num} (来自: {line.strip()})")

    if not frame_numbers:
        print("[WARNING] 未在 FFmpeg 输出中找到任何 frame= 行")
        return None

    total_frames = frame_numbers[-1]  # 取最后一个，即最终帧数
    print(f"[INFO] 总帧数（取最后一行）: {total_frames}")
    return total_frames

def load_h265(file_path: str, frame_number: int) -> Tuple[bool, np.ndarray]:
    """
    使用 FFmpeg 读取 H.265 裸流或封装视频的指定帧（从0开始）

    优势：
      - 支持裸 .h265 / .hevc 流
      - 不依赖 OpenCV 的跳帧功能（对裸流无效）
      - 精准定位帧（即使无关键帧索引）

    返回:
        (True, BGR ndarray) 或抛出异常
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    if not isinstance(frame_number, int) or frame_number < 0:
        raise ValueError(f"帧数必须是非负整数，当前: {frame_number}")

    # 构建 FFmpeg 命令：提取第 frame_number 帧（从0开始）
    # -vf "select=eq(n\,frame_number)" 选择第 n 帧（n 从 0 开始）
    # -vframes 1 只输出一帧
    # -f image2pipe 输出到管道
    # -pix_fmt bgr24 保证输出 BGR 格式，便于 OpenCV 处理
    cmd = [
        'ffmpeg',
        '-y',                     # 覆盖输出（虽然这里是管道）
        '-i', file_path,
        '-vf', f'select=eq(n\\,{frame_number})',
        '-vframes', '1',
        '-f', 'image2pipe',
        '-pix_fmt', 'bgr24',
        '-vcodec', 'rawvideo',
        '-'
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30  # 防止卡死
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg 提取帧超时（帧号: {frame_number}）")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg 未安装或不在 PATH 中")

    if result.returncode != 0:
        # 分析 stderr 判断是否帧超出范围
        err_str = result.stderr.decode('utf-8', errors='ignore')
        if "Select failed" in err_str or "Output file is empty" in err_str:
            raise ValueError(f"请求的帧数 ({frame_number}) 超出视频实际范围")
        else:
            raise RuntimeError(f"FFmpeg 执行失败:\n{err_str}")

    if not result.stdout:
        raise ValueError(f"FFmpeg 未返回图像数据（帧号: {frame_number}）")

    # 获取视频分辨率（需提前知道，或从 FFmpeg stderr 解析）
    # 方案1：先用 ffprobe 获取宽高（推荐）
    width, height = _get_video_resolution(file_path)

    # 方案2：如果已知固定分辨率（如你的数据是 1920x1536），可硬编码
    # width, height = 1920, 1536

    # 将 raw BGR 数据转为 numpy array
    frame_size = width * height * 3
    if len(result.stdout) != frame_size:
        raise RuntimeError(f"图像数据大小不匹配: 期望 {frame_size} 字节，实际 {len(result.stdout)}")

    frame = np.frombuffer(result.stdout, dtype=np.uint8)
    frame = frame.reshape((height, width, 3))  # BGR format

    return True, frame

def _get_video_resolution(file_path: str) -> Tuple[int, int]:
    """使用 ffprobe 获取视频分辨率"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0',
        file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError("无法获取视频分辨率")
        w, h = map(int, result.stdout.strip().split(','))
        return w, h
    except Exception as e:
        # 如果 ffprobe 失败，尝试 fallback 到已知默认值（根据你的数据）
        print(f"[WARNING] 无法获取分辨率，使用默认 1920x1536: {e}")
        return 0, 0

# def load_h265(file_path: str, frame_number: int) -> Tuple[bool, np.ndarray]:
#     """
#     读取 H.265 编码视频文件的指定帧

#     参数:
#         file_path: H.265 视频文件路径（支持 .hevc, .265, .h265, .mp4 等格式）
#         frame_number: 要读取的帧索引（从0开始）

#     返回:
#         Tuple[bool, np.ndarray]: (是否成功读取, 帧数据BGR格式)

#     异常:
#         FileNotFoundError: 文件不存在
#         ValueError: 帧数超出范围或为负数，或视频为空
#         RuntimeError: 无法打开视频文件或读取帧失败
#     """
#     # 检查文件是否存在
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"文件不存在: {file_path}")

#     # 检查帧数是否为非负整数
#     if not isinstance(frame_number, int) or frame_number < 0:
#         raise ValueError(f"帧数必须是非负整数，当前: {frame_number}")

#     # 打开视频文件
#     cap = cv2.VideoCapture(file_path)

#     if not cap.isOpened():
#         raise RuntimeError(f"无法打开视频文件: {file_path}，请检查文件是否为有效的H.265格式")

#     try:
#         # 尝试获取视频总帧数（某些H.265文件可能返回-1或异常值）
#         total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

#         # 如果总帧数有效且请求的帧数超出范围，提前报错
#         if total_frames > 0 and frame_number >= total_frames:
#             raise ValueError(
#                 f"请求的帧数 ({frame_number}) 超出视频总帧数 ({total_frames})。"
#                 f"有效帧数范围: 0 ~ {total_frames - 1}"
#             )

#         # 方法1: 尝试直接跳转到指定帧（对封装格式有效）
#         # 方法2: 顺序读取到指定帧（对H.265裸流更可靠）

#         current_frame = 0

#         # 如果总帧数有效，尝试使用 set 方法跳转（更快）
#         if total_frames > 0:
#             # 尝试跳转到目标帧附近，然后微调
#             # 对于某些编码，跳转到关键帧更快
#             cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
#             current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

#         # 顺序读取直到目标帧
#         while current_frame < frame_number:
#             ret = cap.grab()  # 只解码不获取图像，更快
#             if not ret:
#                 # 提前到达文件末尾
#                 raise ValueError(
#                     f"请求的帧数 ({frame_number}) 超出视频实际帧数 ({current_frame})。"
#                     f"有效帧数范围: 0 ~ {current_frame - 1}"
#                 )
#             current_frame += 1

#         # 现在读取目标帧
#         ret, frame = cap.read()

#         if not ret or frame is None:
#             raise RuntimeError(f"无法读取第 {frame_number} 帧，文件可能已损坏或帧数不足")

#         return True, frame

#     finally:
#         cap.release()


def concat_images_horizontal(img_path_lst, save_dir):
    """
    将多个图片从左到右横向拼接

    Args:
        img_path_lst: 图片路径列表
        save_dir: 保存目录
    """
    if not img_path_lst:
        print("图片列表为空")
        return

    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)

    # 加载所有图片
    images = []
    for path in img_path_lst:
        if os.path.exists(path):
            img = Image.open(path)
            # 转换为RGB模式（统一处理PNG的透明通道等）
            if img.mode != 'RGB':
                img = img.convert('RGB')
            images.append(img)
        else:
            print(f"警告：文件不存在 {path}")

    if not images:
        print("没有有效的图片")
        return

    # 找到最大高度
    max_height = max(img.height for img in images)

    # 等比例缩放所有图片到相同高度
    resized_images = []
    for img in images:
        # 计算缩放后的宽度，保持宽高比
        ratio = max_height / img.height
        new_width = int(img.width * ratio)
        resized_img = img.resize((new_width, max_height), Image.Resampling.LANCZOS)
        resized_images.append(resized_img)

    # 计算总宽度和最大高度
    total_width = sum(img.width for img in resized_images)

    # 创建新画布（白色背景）
    new_img = Image.new('RGB', (total_width, max_height), (255, 255, 255))

    # 横向拼接
    x_offset = 0
    for img in resized_images:
        new_img.paste(img, (x_offset, 0))
        x_offset += img.width

    # 生成保存文件名（使用最后一个文件名 + _concat）
    last_filename = os.path.basename(img_path_lst[-1])
    name, ext = os.path.splitext(last_filename)
    save_name = f"{name}_concat.jpg"
    save_path = os.path.join(save_dir, save_name)

    # 保存
    new_img.save(save_path, quality=95)
    print(f"已保存: {save_path}")

    return save_path
