
import os
import cv2
from pathlib import Path

from utils import load_h265


REPO_DIR = Path(__file__).resolve().parents[2]
PROJECTS_DIR = REPO_DIR.parent
TEST_DATA_ROOT = Path(os.environ.get("RABBITBOT_TEST_DATA_ROOT", PROJECTS_DIR / "downloads"))


def test_load_h265():
    """
    load_h265 函数的调用示例和测试

    说明:
        1. 需要安装 opencv-python: pip install opencv-python
        2. 如果读取 .hevc 裸流文件，可能需要安装 ffmpeg 并配置好环境变量
        3. 返回的帧是 BGR 格式 (OpenCV 默认格式)
    """
    print("=" * 60)
    print("load_h265 函数使用示例")
    print("=" * 60)

    # ========== 示例 1: 基本使用 ==========
    print("\n【示例 1】基本调用方式:")
    print("""
    try:
        success, frame = load_h265("path/to/video.hevc", 100)
        if success:
            # frame 是 numpy 数组，形状为 (height, width, 3)，BGR 格式
            print(f"成功读取，帧形状: {frame.shape}")

            # 如果需要转换为 RGB 格式（用于 matplotlib 等）
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 保存为图片
            cv2.imwrite("output_frame.jpg", frame)
    except Exception as e:
        print(f"错误: {e}")
    """)

    # ========== 示例 2: 批量读取 ==========
    print("\n【示例 2】批量读取多帧:")
    print("""
    def batch_load_frames(file_path, frame_indices):
        frames = []
        for idx in frame_indices:
            try:
                success, frame = load_h265(file_path, idx)
                if success:
                    frames.append(frame)
            except ValueError as e:
                print(f"跳过无效帧 {idx}: {e}")
                break
        return frames

    # 读取第 0, 10, 20, 30 帧
    frames = batch_load_frames("video.hevc", [0, 10, 20, 30])
    """)

    # ========== 示例 3: 获取视频信息 ==========
    print("\n【示例 3】先获取视频信息再读取:")
    print("""
    def get_video_info(file_path):
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None

        info = {
            'total_frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'duration': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / cap.get(cv2.CAP_PROP_FPS)
        }
        cap.release()
        return info

    # 使用
    info = get_video_info("video.hevc")
    if info:
        print(f"视频总帧数: {info['total_frames']}")
        print(f"帧率: {info['fps']}")
        print(f"分辨率: {info['width']}x{info['height']}")

        # 安全读取最后一帧
        last_frame_idx = info['total_frames'] - 1
        success, frame = load_h265("video.hevc", last_frame_idx)
    """)

    # ========== 示例 4: 异常处理最佳实践 ==========
    print("\n【示例 4】完整的异常处理:")
    print("""
    def safe_load_frame(file_path, frame_number):
        try:
            success, frame = load_h265(file_path, frame_number)
            return success, frame
        except FileNotFoundError:
            print(f"错误: 文件不存在 - {file_path}")
            return False, None
        except ValueError as e:
            print(f"错误: 参数错误 - {e}")
            return False, None
        except RuntimeError as e:
            print(f"错误: 视频读取失败 - {e}")
            return False, None
        except Exception as e:
            print(f"未知错误: {e}")
            return False, None

    # 使用
    success, frame = safe_load_frame("video.hevc", 9999)
    if not success:
        print("读取失败，使用默认处理")
    """)

    # ========== 实际测试（如果存在测试文件）==========
    print("\n" + "=" * 60)
    print("实际测试（需要有效的 H.265 文件）")
    print("=" * 60)

    # 请修改为你的实际文件路径进行测试
    DATA_DIR = Path(os.environ.get("RABBITBOT_SUBWAY_V2_DATA_DIR", TEST_DATA_ROOT / "agi-robot-subway-v2"))
    test_file = DATA_DIR / "agi_data_small" / "94149" / "9bf125ab-e3ff-43ac-aa11-ba4e4eca3831" / "camera" / "head_stereo_right" / "head_stereo_right.h265"

    if test_file.exists():
        try:
            # 先获取信息
            cap = cv2.VideoCapture(str(test_file))
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            print(f"✓ 找到测试文件，总帧数: {total}")

            # 读取第一帧
            success, frame = load_h265(str(test_file), 0)
            print(f"✓ 成功读取第0帧，形状: {frame.shape}")
            if success:
                OUTPUT_DIR = "workspace/tools/vision_tools"
                cv2.imwrite(f"{OUTPUT_DIR}/h265_output.png", frame)
                input("Press ENTER to get next frame")

            # 尝试读取超出范围的帧
            try:
                load_h265(str(test_file), total + 100)
            except ValueError as e:
                print(f"✓ 正确捕获超出范围异常: {e}")

        except Exception as e:
            print(f"✗ 测试失败: {e}")
    else:
        print(f"未找到测试文件: {test_file}")
        print("请将 test_file 变量修改为你的 H.265 文件路径进行测试")

    print("\n" + "=" * 60)
    print("提示：")
    print("1. H.265 文件扩展名通常是 .hevc, .265, .h265 或封装在 .mp4/.mkv 中")
    print("2. 如果无法打开 .hevc 裸流文件，可能需要安装 ffmpeg")
    print("3. Ubuntu/Debian: sudo apt-get install libheif-examples")
    print("4. 或使用 conda: conda install -c conda-forge x265")
    print("=" * 60)


if __name__ == "__main__":
    test_load_h265()
