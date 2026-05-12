import os
import shutil
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional, Tuple
import math
from datetime import datetime
import asyncio
from rclpy.node import Node
from sensor_msgs.msg import Image

import cv2
import numpy as np
#import gi
#gi.require_version('Gst', '1.0')
#from gi.repository import Gst, GLib
from qwen_agent.log import logger

from .utils import transform_360_image_to_2d, frame_to_bgr_image
from openai import OpenAI
from datetime import datetime
import base64
from io import BytesIO
from textwrap import dedent
from typing import Union, List, Optional, Dict, Any
import re
import json
from scipy.spatial.distance import cdist

class BaseCamera(ABC):
    """Base class for all camera implementations."""
    has_depth = False
    has_360_view = False
    hfov = 90.0
    yaw_offset = 0.0

    def __init__(
        self,
        fps: int = 10,
        image_buffer_size: int = 20,
        image_buffer_dir: Optional[str] = None,
        record_frame_size: Tuple[int, int] = (1280, 720),
        identifier: str = 'camera',
        robot=None
    ):
        self.fps = fps
        self.image_buffer_size = image_buffer_size
        self.image_dir = image_buffer_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'image_buffer')
        )
        self.record_frame_size = record_frame_size
        self.identifier = identifier

        self._frame_buffer = deque(maxlen=image_buffer_size)
        self._depth_buffer = deque(maxlen=image_buffer_size)
        self._started = False
        self._recording = False
        self._video_writer = None
        self._pipeline_thread = None
        self._recording_lock = threading.Lock()
        self.robot = robot
        self.sample_rate = 60
        self.frame_num = 0
        self._create_memory_map = False

    @abstractmethod
    def _start_pipeline(self):
        """Start the camera pipeline. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def _stop_pipeline(self):
        """Stop the camera pipeline. Must be implemented by subclasses."""
        pass

    def view_2d(
        self,
        yaw: float = 0.0,
        pitch: float = 0.0,
        fov: float = 90.0,
        output_size: Tuple[int, int] = (800, 600)
    ) -> Optional[np.ndarray]:
        """Get a 2D perspective view from the camera.

        Args:
            yaw: Horizontal rotation in degrees
            pitch: Vertical rotation in degrees
            fov: Field of view in degrees
            output_size: Output image size as (width, height)

        Returns:
            2D perspective image or None if no frame available
        """
        print(f"BaseCamera: view_2d")
        frame = self.get_frame()
        if frame is None:
            return None

        if self.has_360_view:
            # For 360-degree cameras, transform the image based on yaw, pitch, fov
            return transform_360_image_to_2d(frame, yaw, pitch, fov, output_size)
        else:
            # For regular cameras, simply resize the frame
            return cv2.resize(frame, output_size)

    def start(self):
        """Start the camera."""
        if self._started:
            return
        self._started = True

        self._setup_image_directory()

        self._pipeline_thread = threading.Thread(target=self._start_pipeline, daemon=False)
        self._pipeline_thread.start()

    def stop(self):
        """Stop the camera."""
        if not self._started:
            return
        self._started = False
        self.stop_record()
        self._stop_pipeline()
        if self._pipeline_thread:
            self._pipeline_thread.join(timeout=1)

    def start_record(self, task_count: int = 0):
        """Start recording video."""
        with self._recording_lock:
            if self._recording:
                return
            video_dir = os.environ.get("RABBITBOT_VIDEO_DIR", os.path.join(self.image_dir, "video_data"))
            os.makedirs(video_dir, exist_ok=True)
            video_name = f'task{task_count}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.mp4'
            print(video_name)
            self._video_writer = cv2.VideoWriter(
                filename=os.path.join(video_dir, video_name),
                fourcc=cv2.VideoWriter_fourcc(*'mp4v'),
                fps=self.fps,
                frameSize=self.record_frame_size,
            )
            self._recording = True

    def stop_record(self):
        """Stop recording video."""
        with self._recording_lock:
            if self._recording and self._video_writer:
                self._recording = False
                self._video_writer.release()
                self._video_writer = None

    def wait_for_camera(self, timeout: int = 10):
        """Wait for the camera to initialize."""
        if len(self._frame_buffer) == 0:
            logger.info('Camera uninitialized, block waiting...')
        else:
            return

        start = time.time()
        while time.time() - start < timeout:
            if len(self._frame_buffer) > 0:
                logger.info('Camera initialized')
                return

        logger.warning('Camera still uninitialized after timeout')

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest frame from the buffer."""
        print(f"BaseCamera: get_frame (len={len(self._frame_buffer)})")
        if len(self._frame_buffer) == 0:
            return None
        return self._frame_buffer[-1]

    def get_depth_frame(self) -> Optional[np.ndarray]:
        """Get the latest depth frame from the buffer."""
        if len(self._depth_buffer) == 0:
            print("no depth image!")
            return None
        print("depth image exist!")
        return self._depth_buffer[-1]

    def _setup_image_directory(self):
        """Setup the image directory."""
        if os.path.exists(self.image_dir):
            shutil.rmtree(self.image_dir)
        os.makedirs(self.image_dir, exist_ok=True)

    def _add_frame(self, frame: np.ndarray):
        """Add a frame to the buffer."""
        self._frame_buffer.append(frame)
        with self._recording_lock:
            if self._recording and self._video_writer:
                if self.has_360_view:
                    frame = transform_360_image_to_2d(frame, output_size=self.record_frame_size)
                else:
                    frame = cv2.resize(frame, self.record_frame_size)
                self._video_writer.write(frame)

    def _add_depth_frame(self, depth_frame: np.ndarray):
        """Add a depth frame to the buffer."""
        self._depth_buffer.append(depth_frame)

    def get_real_depth(self, depth):
        """Convert raw depth data to real-world depth values."""
        if not self.has_depth:
            logger.warning("Camera does not support depth measurement")
            return 0
        return depth

    @property
    def is_started(self) -> bool:
        """Check if the camera is started."""
        return self._started

    @property
    def is_recording(self) -> bool:
        """Check if the camera is recording."""
        with self._recording_lock:
            return self._recording


class ThetaCamera(BaseCamera):
    """Theta 360-degree camera implementation."""
    has_360_view = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pipeline = None
        self._loop = None

    def _start_pipeline(self):
        """Start the Theta camera pipeline using GStreamer."""
        Gst.init(None)

        desc = (
            f'thetauvcsrc mode=4K name=src ! queue ! h264parse ! nvv4l2decoder '
            f'! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR '
            f'! videorate ! video/x-raw,framerate={self.fps}/1 ! queue max-size-buffers=1 leaky=downstream '
            f'! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false'
        )
        self._pipeline = Gst.parse_launch(desc)
        sink = self._pipeline.get_by_name('sink')
        sink.connect('new-sample', self._on_new_sample)
        self._pipeline.set_state(Gst.State.PLAYING)
        self._loop = GLib.MainLoop()
        try:
            self._loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            self._pipeline.set_state(Gst.State.NULL)

    def _stop_pipeline(self):
        """Stop the Theta camera pipeline."""
        if self._loop:
            self._loop.quit()
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)

    def _on_new_sample(self, sink):
        """Handle new sample from GStreamer pipeline."""
        sample = sink.emit('pull-sample')
        if not sample:
            return Gst.FlowReturn.ERROR
        buf = sample.get_buffer()
        caps = sample.get_caps()
        struct = caps.get_structure(0)
        height = struct.get_value('height')
        channels = 3
        success, mapinfo = buf.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.ERROR
        data = mapinfo.data
        buf.unmap(mapinfo)
        total = len(data)
        width = total // (height * channels)
        arr = np.frombuffer(data, dtype=np.uint8)

        try:
            arr = arr.reshape((height, width, channels))
        except Exception:
            return Gst.FlowReturn.ERROR

        self._add_frame(arr)
        return Gst.FlowReturn.OK


class DaiCamera(BaseCamera):
    """DepthAI camera implementation for OAK cameras."""
    has_depth = True
    hfov = 70.0
    yaw_offset = math.radians(90)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._device = None
        # hyperparams, need explanation
        self.fx = 441.25
        self.baseline = 7.5

    def _start_pipeline(self):
        """Start the DepthAI camera pipeline for both RGB and depth."""
        try:
            import depthai as dai
        except ImportError:
            logger.error("DepthAI library not found. Please install depthai.")
            return

        pipeline = dai.Pipeline()

        # Setup color camera
        colorCam = pipeline.createColorCamera()
        colorCam.setBoardSocket(dai.CameraBoardSocket.RGB)
        colorCam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_4_K)
        colorCam.initialControl.setManualFocus(30)
        colorCam.setFps(self.fps)

        # Setup mono cameras for stereo depth
        left = pipeline.createMonoCamera()
        left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_480_P)
        left.setBoardSocket(dai.CameraBoardSocket.LEFT)

        right = pipeline.createMonoCamera()
        right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_480_P)
        right.setBoardSocket(dai.CameraBoardSocket.RIGHT)

        # Setup stereo depth
        depth = pipeline.createStereoDepth()
        depth.setConfidenceThreshold(200)
        left.out.link(depth.left)
        right.out.link(depth.right)

        # Setup video output
        xoutVideo = pipeline.createXLinkOut()
        xoutVideo.setStreamName("video")
        xoutVideo.input.setBlocking(False)
        xoutVideo.input.setQueueSize(1)
        colorCam.video.link(xoutVideo.input)

        # Setup depth output
        xoutDepth = pipeline.createXLinkOut()
        xoutDepth.setStreamName("depth")
        xoutDepth.input.setBlocking(False)
        xoutDepth.input.setQueueSize(1)
        depth.disparity.link(xoutDepth.input)

        with dai.Device(pipeline) as device:
            self._device = device
            video = device.getOutputQueue(name="video", maxSize=1, blocking=False)
            depth_queue = device.getOutputQueue(name="depth", maxSize=1, blocking=False)

            while self._started:
                videoIn = video.get()
                if videoIn:
                    rgb_frame = videoIn.getCvFrame()
                    self._add_frame(rgb_frame)

                in_depth = depth_queue.get()
                if in_depth:
                    depth_frame = in_depth.getFrame()
                    self._add_depth_frame(depth_frame)

    def _stop_pipeline(self):
        """Stop the DepthAI camera pipeline."""
        # Device context manager handles cleanup
        pass

    def get_real_depth(self, depth):
        return self.baseline * self.fx / depth / 1000.0

class RealsenseCamera(BaseCamera):
    """Intel RealSense camera implementation."""
    has_depth = True
    hfov = 70.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pipeline = None

    def _start_pipeline(self):
        """Start the RealSense camera pipeline for both color and depth frames."""
        try:
            import pyrealsense2 as rs
        except ImportError:
            logger.error("pyrealsense2 library not found. Please install pyrealsense2.")
            return

        self._pipeline = rs.pipeline()
        config = rs.config()
        print("fps:", self.fps)
        self.fps = 30
        #config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, self.fps)
        #config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, self.fps)

        _ = self._pipeline.start(config)

        try:
            while self._started:
                frames = self._pipeline.wait_for_frames()

                color_frame = frames.get_color_frame()
                if color_frame:
                    rgb_frame = np.asanyarray(color_frame.get_data())
                    self._add_frame(rgb_frame)

                # depth_frame = frames.get_depth_frame()
                # if depth_frame:
                #     depth_data = np.asanyarray(depth_frame.get_data())
                #     self._add_depth_frame(depth_data)
        finally:
            if self._pipeline:
                self._pipeline.stop()

    def _stop_pipeline(self):
        """Stop the RealSense camera pipeline."""
        if self._pipeline:
            self._pipeline.stop()

    def get_real_depth(self, depth):
        return depth / 1000.0


class Ros2TopicCamera(Node):
    
    def __init__(self,
                 fps: int = 10,
                 image_buffer_size: int = 20,
                 image_buffer_dir: Optional[str] = None,
                 record_frame_size: Tuple[int, int] = (1920, 1080),
                 identifier: str = 'camera') -> None:
        super().__init__("camera_listener")
        self.topic = None
        self.img_channels = 3
        self.subscription = None
        self.has_360_view = False
        self.has_depth = False
        self._frame_buffer = deque(maxlen=image_buffer_size)
        self._depth_buffer = deque(maxlen=image_buffer_size)
        self.yaw_offset = 0.0
        print(f'ROS2TopicCamera: Created')

    def start(self):
        assert self.topic is not None, "topic cannot be none"
        self.subscription = self.create_subscription(
            Image, self.topic, self.image_callback, 10
        )
        print(f'ROS2TopicCamera: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'ROS2TopicCamera: Stopped')

    def wait_for_camera(self, timeout: int = 10):
        print(f'ROS2TopicCamera: Wait for camera')
        time.sleep(5)

    #@staticmethod
    #def get_timestamp(msg: CompressedImage) -> int:
    #    return int(msg.header.stamp.sec * 1e6 + msg.header.stamp.nanosec / 1e3)

    @staticmethod
    def get_size(msg: Image) -> Tuple:
        height = msg.height
        width = msg.width
        return height, width

    @staticmethod
    def serialize_message(msg: Image) -> bytes:
        return bytes(msg.data)

    def image_callback(self, msg: Image) -> None:
        #self.get_logger().info(f'Received image, storing to frame buffer')
        #print(f'ROS2TopicCamera: Received image, storing to frame buffer (has_depth={self.has_depth})')
        height, width = self.get_size(msg)
        binary_data = self.serialize_message(msg)

        if not self.has_depth:
            frame = np.frombuffer(binary_data, dtype=np.uint8).reshape((height, width, self.img_channels))
            frame = frame[:, :, ::-1]
            self._frame_buffer.append(frame)
            #print(f'ROS2TopicCamera: Append frame buffer')
        else:
            frame = np.frombuffer(binary_data, dtype=np.uint16).reshape((height, width))
            self._depth_buffer.append(frame)
            #print(f'ROS2TopicCamera: Append depth buffer')

    def get_frame(self):
        buffer_size = len(self._frame_buffer)
        print(f'ROS2TopicCamera: Get frame (buffer_size={buffer_size})')
        if len(self._frame_buffer) == 0:
            return None
        return self._frame_buffer[-1]

    def get_depth_frame(self):
        buffer_size = len(self._depth_buffer)
        print(f'ROS2TopicCamera: Get depth frame (buffer_size={buffer_size})')
        if len(self._depth_buffer) == 0:
            return None
        return self._depth_buffer[-1]

    def view_2d(
        self,
        yaw: float = 0.0,
        pitch: float = 0.0,
        fov: float = 90.0,
        output_size: Tuple[int, int] = (800, 600)
    ) -> Optional[np.ndarray]:
        print(f'ROS2TopicCamera: View 2D')
        frame = self.get_frame()
        if frame is None:
            return None

        if self.has_360_view:
            # For 360-degree cameras, transform the image based on yaw, pitch, fov
            #return transform_360_image_to_2d(frame, yaw, pitch, fov, output_size)
            pass
        else:
            # For regular cameras, simply resize the frame
            return cv2.resize(frame, output_size)


class Ros2TopicRgbCamera(Ros2TopicCamera):

    def __init__(self,
                 fps = 10,
                 image_buffer_size = 20,
                 image_buffer_dir = None,
                 record_frame_size = (1920, 1080),
                 identifier = 'camera'):
        super().__init__(fps, image_buffer_size, image_buffer_dir, record_frame_size, identifier)
        self.topic = "/camera/color/image_raw"
        self.has_depth = False
        self.img_channels = 3


class Ros2TopicDepthCamera(Ros2TopicCamera):

    def __init__(self,
                 fps = 10,
                 image_buffer_size = 20,
                 image_buffer_dir = None,
                 record_frame_size = (1920, 1080),
                 identifier = 'camera'):
        super().__init__(fps, image_buffer_size, image_buffer_dir, record_frame_size, identifier)
        self.topic = "/camera/depth/image_rect_raw"
        self.has_depth = True
        self.img_channels = 1
        self.hfov = 87.0

    def get_real_depth(self, depth):
        return depth / 1000.0

class GeminiCamera(BaseCamera):
    """Gemini camera implementation."""
    has_depth = True
    hfov = 94.0
    ESC_KEY = 27
    PRINT_INTERVAL = 1  # seconds
    MIN_DEPTH = 20  # 20mm
    MAX_DEPTH = 10000  # 10000mm
    

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pipeline = None
        self.vlm_openai = None

    def _get_vlm_openai(self):
        if self.vlm_openai is None:
            from rabbitbot.provider import create_vlm_openai
            self.vlm_openai = create_vlm_openai()
        return self.vlm_openai
        
    def _start_pipeline(self):
        """Start the Genimi camera pipeline for both color and depth frames."""
        try:
            from pyorbbecsdk import Context, OBLogLevel, Pipeline, Config
            from pyorbbecsdk import OBSensorType, OBFormat, OBStreamType
            from pyorbbecsdk import AlignFilter, PointCloudFilter, OBError, OBPointCloudFrame
        except ImportError:
            logger.error("pyorbbecsdk library not found. Please install pyorbbecsdk.")
            return

        try:
            context = Context()
            context.set_logger_level(OBLogLevel.NONE)
        except Exception as e:
            logger.error(f"Failed to initialize Orbbec SDK context: {e}")
            return

        self._pipeline = Pipeline()
        config = Config()
        try:
            profile_list = self._pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
            assert profile_list is not None
            depth_profile = profile_list.get_default_video_stream_profile()
            assert depth_profile is not None
            config.enable_stream(depth_profile)
        except Exception as e:
            print(e)
            return
        try:
            profile_list = self._pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            print(profile_list)
            try:
                color_profile = profile_list.get_video_stream_profile(1280, 720, OBFormat.RGB, 10)
            except OBError as e:
                print(e)
                color_profile = profile_list.get_default_video_stream_profile()
            config.enable_stream(color_profile)
        except Exception as e:
            print(e)
            return
        self._pipeline.enable_frame_sync()
        self._pipeline.start(config)
        camera_param = self._pipeline.get_camera_param()
        align_filter = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
        point_cloud_filter = PointCloudFilter()
        point_cloud_filter.set_camera_param(camera_param)

        try:
            while True:
                frames = self._pipeline.wait_for_frames(100)
                if frames is None:
                    continue
                depth_frame = frames.get_depth_frame()
                if depth_frame is None:
                    continue
                color_frame = frames.get_color_frame()
                if color_frame is None:
                    continue
                frame = align_filter.process(frames)
                # print("align_filter")
                scale = depth_frame.get_depth_scale()
                # print("scale test:", scale)
                start = time.time()
                
                color_image = frame_to_bgr_image(color_frame)
                color_image = cv2.rotate(color_image, cv2.ROTATE_180)
                self._frame_buffer.append(color_image)
                if self._recording:
                    color_image = cv2.resize(color_image, self.record_frame_size)
                    self._video_writer.write(color_image)
                # get depth frame
                # import pdb; pdb.set_trace()
                # self._depth_buffer.append(frames)
                point_cloud_filter.set_position_data_scaled(scale)
                point_cloud_filter.set_create_point_format(
                    OBFormat.RGB_POINT if color_frame is not None else OBFormat.POINT)
                point_cloud_frame = point_cloud_filter.process(frame)
                points = point_cloud_filter.calculate(point_cloud_frame)
                depth_data = points[:, :3]
                depth_data = depth_data.reshape(720, 1280, 3)
                depth_data = np.rot90(depth_data, 2)
                self._depth_buffer.append(depth_data)
                self.frame_num += 1
                if self.frame_num % (self.fps * 1) == 0:  # 每5秒输出一次
                    print("frame time: ", time.time())
                # print("frame time: ", time.time())

        finally:
            if self._pipeline:
                self._pipeline.stop()

    # def get_point_cloud(self):
    #     if len(self._depth_buffer) != 0:
    #         self.point_cloud_filter.set_position_data_scaled(1.0)
    #         self.point_cloud_filter.set_create_point_format(
    #             OBFormat.RGB_POINT if color_frame is not None else OBFormat.POINT)
    #         point_cloud_frame = self.point_cloud_filter.process(frame)
    #         points = self.point_cloud_filter.calculate(point_cloud_frame)
    #         depth_data = points[:, :3]
    #         depth_data = depth_data.reshape(800, 1280, 3)
    #         depth_data = np.rot90(depth_data, 2)
    #         return depth_data
    #     else:
    #         return None

    def get_foreground_object_center_simplified(self, point_cloud_patch: np.ndarray) -> Optional[np.ndarray]:
        """
        简化版：获取点云中前景物体的中心坐标，通过前景/背景分离和主要物体识别实现。

        Args:
            point_cloud_patch (np.ndarray): 表示点云片段的numpy数组，
                                          形状为 (height, width, 3) 或 (N, 3)，每个元素是 [x, y, z] 坐标。

        Returns:
            Optional[np.ndarray]: 前景主要物体的中心坐标，如果没有找到有效点则返回None。
        """
        # print("log 1")
        if point_cloud_patch.size == 0:
            print("return none 1")
            return (0,0,0)
            
        # 将输入重塑为点列表
        if len(point_cloud_patch.shape) == 3:
            points = point_cloud_patch.reshape(-1, 3)
        else:
            points = point_cloud_patch
        # print("log 2")
        # 步骤1: 过滤无效点
        valid_mask = np.any(points != 0, axis=1)
        valid_points = points[valid_mask]
        # print("log 3")
        if valid_points.shape[0] == 0:
            print("return none 2")
            return None
        elif valid_points.shape[0] < 20:  # 点数太少，直接返回平均值
            print("return avg")
            return np.mean(valid_points, axis=0)
        # print("log 4")
        if points.shape[0] > 4000:
            print("too large, return mean")
            return np.mean(valid_points, axis=0)
        try:
            # 步骤2: 基于深度的前景/背景分离
            depths = np.linalg.norm(valid_points, axis=1)
            depth_median = np.median(depths)
            depth_std = np.std(depths)
            
            # 前景筛选：选择距离适中的点
            foreground_threshold = depth_median - 0.5 * depth_std
            background_threshold = depth_median + 1.0 * depth_std
            foreground_mask = (depths < background_threshold) & (depths > foreground_threshold * 0.3)
            
            # 如果前景点太少，使用更宽松的阈值
            if np.sum(foreground_mask) < 10:
                foreground_mask = depths < depth_median + 0.5 * depth_std
            
            foreground_points = valid_points[foreground_mask]
            
            # 如果前景分离失败，使用备用方法
            if foreground_points.shape[0] < 10:
                print("前景分离失败，使用备用方法")
                distances = np.linalg.norm(valid_points, axis=1)
                lower_bound = np.percentile(distances, 25)
                upper_bound = np.percentile(distances, 75)
                filtered_points = valid_points[(distances >= lower_bound) & (distances <= upper_bound)]
                return np.mean(filtered_points, axis=0) if filtered_points.shape[0] > 0 else np.mean(valid_points, axis=0)
            
            # 步骤3: 主要物体识别 - 使用密度聚类
            if foreground_points.shape[0] >= 20:
                # 计算点的局部密度
                distances = cdist(foreground_points, foreground_points)
                radius = np.percentile(distances[distances > 0], 10)
                neighbor_counts = np.sum(distances < radius, axis=1)
                
                # 选择密度较高的点
                density_threshold = np.percentile(neighbor_counts, 60)
                dense_points_mask = neighbor_counts >= density_threshold
                
                if np.sum(dense_points_mask) < 10:
                    density_threshold = np.percentile(neighbor_counts, 40)
                    dense_points_mask = neighbor_counts >= density_threshold
                
                main_object_points = foreground_points[dense_points_mask]
                
                # 如果密度方法失败，使用空间聚类
                if main_object_points.shape[0] < 10:
                    center = np.mean(foreground_points, axis=0)
                    distances_to_center = np.linalg.norm(foreground_points - center, axis=1)
                    distance_threshold = np.percentile(distances_to_center, 70)
                    main_object_points = foreground_points[distances_to_center <= distance_threshold]
                    
                    if main_object_points.shape[0] < 5:
                        main_object_points = foreground_points
            else:
                main_object_points = foreground_points
            
            # 步骤4: 去噪和中心计算
            if main_object_points.shape[0] < 5:
                final_center = np.mean(main_object_points, axis=0)
            else:
                # 移除异常值
                center_estimate = np.median(main_object_points, axis=0)
                distances = np.linalg.norm(main_object_points - center_estimate, axis=1)
                
                q75, q25 = np.percentile(distances, [75, 25])
                iqr = q75 - q25
                upper_bound = q75 + 1.5 * iqr
                
                clean_mask = distances <= upper_bound
                clean_points = main_object_points[clean_mask]
                
                if clean_points.shape[0] < 3:
                    clean_points = main_object_points
                
                # 使用加权平均计算最终中心
                if clean_points.shape[0] > 10:
                    center_refined = np.median(clean_points, axis=0)
                    distances_refined = np.linalg.norm(clean_points - center_refined, axis=1)
                    weights = 1.0 / (distances_refined + 1e-6)
                    weights = weights / np.sum(weights)
                    final_center = np.average(clean_points, axis=0, weights=weights)
                else:
                    final_center = np.mean(clean_points, axis=0)
            
            print(f"前景物体中心: {final_center}")
            return final_center
            
        except Exception as e:
            print(f"处理失败，使用简单平均: {e}")
            return np.mean(valid_points, axis=0)

    def _get_point_cloud_center(self, point_cloud_patch: np.ndarray) -> Optional[np.ndarray]:
        """
        Calculates the center of a point cloud patch after basic filtering.

        Args:
            point_cloud_patch (np.ndarray): A numpy array representing the point cloud patch,
                                            with shape (height, width, 3), where each element
                                            is an [x, y, z] coordinate.

        Returns:
            Optional[np.ndarray]: The center of the filtered point cloud as a numpy array,
                                  or None if no valid points are found.
        """
        if point_cloud_patch.size == 0:
            return None
        if len(point_cloud_patch.shape) == 3:
            # Reshape the patch into a list of points
            points = point_cloud_patch.reshape(-1, 3)
        else:
            points = point_cloud_patch
        # Filter out invalid points (e.g., [0, 0, 0] where depth is missing)
        valid_points = points[np.any(points != 0, axis=1)]

        if valid_points.shape[0] < 10:  # Not enough points to process
            return np.mean(valid_points, axis=0) if valid_points.shape[0] > 0 else None

        # Use percentile-based filtering to remove outliers.
        # This is more robust for points that are not normally distributed.
        distances = np.linalg.norm(valid_points, axis=1)
        lower_bound = np.percentile(distances, 30)
        upper_bound = np.percentile(distances, 70)

        # Keep points within the 10th and 90th percentile of distances
        main_object_points = valid_points[(distances >= lower_bound) & (distances <= upper_bound)]

        if main_object_points.shape[0] == 0:
            # Fallback to all valid points if filtering removes everything
            main_object_points = valid_points

        # Calculate the center of the main object points
        center = np.mean(main_object_points, axis=0)
        print("center", center)
        return center

    def get_location(self, text):
        # TODO: 根据text到vllm获取bbox
        try:
            image = self.get_frame()
            vlm_openai = self._get_vlm_openai()
            vlm_openai.prompt = dedent(f"""\
                你是一名专业的视觉目标匹配和定位专家。你的任务是根据物品的描述，在画面中找到最相似的一个物品并提取其边界框。
                需要识别的物品描述如下：{text}。
                **输出要求：**
                请以下格式输出，不要包含任何其他文字，并按照物品顺序输出：

                ```
                {{
                    "[x1,y1,x2,y2]",
                }}
                ```
                """)
            start_time = time.time()
            image_message, video_kwargs = vlm_openai.prepare_message_for_vllm([image])
            json_content = vlm_openai.get_chat_response(
                messages=image_message,
                extra_body={
                    "mm_processor_kwargs": video_kwargs
                }
            )
            print("cost time:",time.time()-start_time)
            print("json_content", json_content)
            entity = json_content.strip('```json\n').strip('```')
            print("entity", entity)
            # 兼容多种格式
            entity_bbox_str = re.findall(r'"Entity_bbox":\s*"\[([^\]]+)\]"', entity)
            entity_bbox_array = re.findall(r'"Entity_bbox":\s*\[\s*\[([^\]]+)\]\s*\]', entity)
            # 支持新格式：{"bbox_2d": [0, 34, 581, 496], "label": "描述"}
            entity_bbox_dict = re.findall(r'"bbox_2d":\s*\[([^\]]+)\]', entity)
            # 兼容格式："Entity_bbox": [198,173,330,456]
            entity_bbox_direct = re.findall(r'"Entity_bbox":\s*\[([^\]]+)\]', entity)
            # 兼容JSON数组格式：["[154,160,178,193]"]
            entity_bbox_json_array = re.findall(r'"\[([^\]]+)\]"', entity)
            # 兼容JSON数组格式：["{154,160,178,193}"]
            entity_bbox_others_array = re.findall(r'"\{([^\}]+)\}"', entity)
            
            if entity_bbox_str:
                entity_bbox = entity_bbox_str
            elif entity_bbox_array:
                entity_bbox = entity_bbox_array
            elif entity_bbox_dict:
                entity_bbox = entity_bbox_dict
            elif entity_bbox_direct:
                entity_bbox = entity_bbox_direct
            elif entity_bbox_json_array:
                entity_bbox = entity_bbox_json_array
            elif entity_bbox_others_array:
                entity_bbox = entity_bbox_others_array
            else:
                entity_bbox = []
            print("test is exec!!!!!!!", entity_bbox)
            
            bbox = list(map(int, entity_bbox[0].split(',')))
            x1, y1, x2, y2 = min(1280, bbox[0]), min(720, bbox[1]), min(1280, bbox[2]), min(720, bbox[3])
            # 在图像上可视化边界框
            new_image = image.copy()
            cv2.rectangle(new_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(new_image, f'Entity', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(f'entity.jpg', new_image)
            depth_image = self.get_depth_frame()
            print(depth_image.shape)
            print(y1,y2,x1,x2)
            depth_object = depth_image[y1:y2, x1:x2]
            print(depth_object.shape)
            # center = self._get_point_cloud_center(depth_object)
            center = self.get_foreground_object_center_simplified(depth_object)
            print(center)
            x_offset = center[2] /1000.0
            y_offset = center[0] /1000.0
            z_offset = center[1] /1000.0
            # x_offset_new = x_offset*math.cos(math.radians(25)) - z_offset*math.sin(math.radians(25))
            # z_offset_new = x_offset*math.sin(math.radians(25)) + z_offset*math.cos(math.radians(25))
            # location = (x_offset_new, y_offset, z_offset_new)
            location = (x_offset, y_offset, z_offset)
            # 判断bbox数目
            if len(entity_bbox) == 0:
                return (0, 0, 0)
            # elif len(entity_bbox) > 1:
            #     return (-1, -1, -1)
            print("test is successed!!!!!!!", location)
            return location
        except Exception as e:
            print("识别错误")
            return (0,0,0)

    def get_red_area(self, image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_red = np.array([130, 140, 100])
        upper_red = np.array([255, 255, 255])
        mask = cv2.inRange(hsv, lower_red, upper_red)
        
        # 查找轮廓并保留最大的红色区域
        # contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # if contours:
        #     # 找到面积最大的轮廓
        #     largest_contour = max(contours, key=cv2.contourArea)
        #     # 创建新的mask，只保留最大的红色区域
        #     mask = np.zeros_like(mask)
        #     cv2.fillPoly(mask, [largest_contour], 255)
        cv2.imwrite("entity.jpg", image)
        cv2.imwrite('red_area.jpg', mask)
        return mask

    def detect_hand_location(self) -> str:
    # TODO: 根据text到vllm获取bbox
        try:
            image = self.get_frame()
            vlm_openai = self._get_vlm_openai()
            vlm_openai.prompt = dedent(f"""\
                你是一名专业的视觉目标匹配和定位专家。你的任务是定位画面中最近的用户的手部位置，并返回目标框。
            **输出要求：**
            请以下格式输出，不要包含任何其他文字：
                ```
                {{
                    "[x1,y1,x2,y2]",
                }}
                ```
                """)
            start_time = time.time()
            image_message, video_kwargs = vlm_openai.prepare_message_for_vllm([image])
            json_content = vlm_openai.get_chat_response(
                messages=image_message,
                extra_body={
                    "mm_processor_kwargs": video_kwargs
                }
            )
            print("cost time:",time.time()-start_time)
            print("json_content", json_content)
            entity = json_content.strip('```json\n').strip('```')
            print("entity", entity)
            # 兼容多种格式
            entity_bbox_str = re.findall(r'"Entity_bbox":\s*"\[([^\]]+)\]"', entity)
            entity_bbox_array = re.findall(r'"Entity_bbox":\s*\[\s*\[([^\]]+)\]\s*\]', entity)
            # 支持新格式：{"bbox_2d": [0, 34, 581, 496], "label": "描述"}
            entity_bbox_dict = re.findall(r'"bbox_2d":\s*\[([^\]]+)\]', entity)
            # 兼容格式："Entity_bbox": [198,173,330,456]
            entity_bbox_direct = re.findall(r'"Entity_bbox":\s*\[([^\]]+)\]', entity)
            # 兼容JSON数组格式：["[154,160,178,193]"]
            entity_bbox_json_array = re.findall(r'"\[([^\]]+)\]"', entity)
            # 兼容JSON数组格式：["{154,160,178,193}"]
            entity_bbox_others_array = re.findall(r'"\{([^\}]+)\}"', entity)
            
            if entity_bbox_str:
                entity_bbox = entity_bbox_str
            elif entity_bbox_array:
                entity_bbox = entity_bbox_array
            elif entity_bbox_dict:
                entity_bbox = entity_bbox_dict
            elif entity_bbox_direct:
                entity_bbox = entity_bbox_direct
            elif entity_bbox_json_array:
                entity_bbox = entity_bbox_json_array
            elif entity_bbox_others_array:
                entity_bbox = entity_bbox_others_array
            else:
                entity_bbox = []
            print("test is exec!!!!!!!", entity_bbox)
            
            bbox = list(map(int, entity_bbox[0].split(',')))
            x1, y1, x2, y2 = min(1280, bbox[0]), min(720, bbox[1]), min(1280, bbox[2]), min(720, bbox[3])
            # 在图像上可视化边界框
            new_image = image.copy()
            cv2.rectangle(new_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(new_image, f'Entity', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(f'entity.jpg', new_image)
            depth_image = self.get_depth_frame()
            print(depth_image.shape)
            print(y1,y2,x1,x2)
            depth_object = depth_image[y1:y2, x1:x2]
            print(depth_object.shape)
            # center = self._get_point_cloud_center(depth_object)
            center = self.get_foreground_object_center_simplified(depth_object)
            print(center)
            x_offset = center[2] /1000.0
            y_offset = center[0] /1000.0
            z_offset = center[1] /1000.0
            # x_offset_new = x_offset*math.cos(math.radians(25)) - z_offset*math.sin(math.radians(25))
            # z_offset_new = x_offset*math.sin(math.radians(25)) + z_offset*math.cos(math.radians(25))
            # location = (x_offset_new, y_offset, z_offset_new)
            location = (x_offset, y_offset, z_offset)
            # 判断bbox数目
            if len(entity_bbox) == 0:
                return (0, 0, 0)
            # elif len(entity_bbox) > 1:
            #     return (-1, -1, -1)
            print("test is successed!!!!!!!", location)
            return location
        except Exception as e:
            print("识别错误")
            print(e)
            return (0,0,0)

    def detect_key_point_pixel(self) -> str:
        image = self.get_frame()
        depth_image = self.get_depth_frame()
        mask = self.get_red_area(image)
        
        # Get point cloud data corresponding to the mask
        depth_object = depth_image[mask > 0]
        print("depth_object", depth_object.shape)
        # import pdb; pdb.set_trace()
        # Get the center of the point cloud
        center = self._get_point_cloud_center(depth_object)
        
        if center is None:
            location = (0, 0, 0)
        else:
            x_offset = center[2] / 1000.0
            y_offset = center[0] / 1000.0
            z_offset = center[1] / 1000.0
            location = (x_offset, y_offset, z_offset)

        print(f"Detected key point center: {location}")
        return location

    def _start_pipeline_old(self):
        """Start the Genimi camera pipeline for both color and depth frames."""
        try:
            from pyorbbecsdk import Context, OBLogLevel, Pipeline, Config
            from pyorbbecsdk import OBSensorType, OBFormat, OBStreamType, AlignFilter
        except ImportError:
            logger.error("pyorbbecsdk library not found. Please install pyorbbecsdk.")
            return

        context = Context()
        context.set_logger_level(OBLogLevel.NONE)

        class TemporalFilter:
            def __init__(self, alpha):
                self.alpha = alpha
                self.previous_frame = None

            def process(self, frame):
                if self.previous_frame is None:
                    result = frame
                else:
                    result = cv2.addWeighted(frame, self.alpha, self.previous_frame, 1 - self.alpha, 0)
                self.previous_frame = result
                return result

        self._pipeline = Pipeline()
        config = Config()
        try:
            profile_list = self._pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            color_profile = profile_list.get_video_stream_profile(1280, 0, OBFormat.RGB, 10)
            print("color_profile: ", color_profile)
            config.enable_stream(color_profile)
            profile_list = self._pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
            depth_profile = profile_list.get_video_stream_profile(848, 0, OBFormat.Y16, 10)
            print("depth_profile: ", depth_profile)
            config.enable_stream(depth_profile)
        except Exception as e:
            print(e)
            return    
        try:
            self._pipeline.start(config)
        except Exception as e:
            print(e)
            return

        align_filter = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
        time_start = time.time()
        while True:
            try:
                frames = self._pipeline.wait_for_frames(100)
                print("frame time: ", time.time())
                if not frames:
                    continue
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue
                frames = align_filter.process(frames)
                if not frames:
                    continue
                frames  = frames.as_frame_set()
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue
                color_image = frame_to_bgr_image(color_frame)
                color_image = cv2.rotate(color_image, cv2.ROTATE_180)
                self._frame_buffer.append(color_image)
                with self._recording_lock:
                    if self._recording and self._video_writer:
                        color_image = cv2.resize(color_image, self.record_frame_size)
                        self._video_writer.write(color_image)
                # get depth frame
                width = depth_frame.get_width()
                height = depth_frame.get_height()
                scale = depth_frame.get_depth_scale()
                depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
                depth_data = depth_data.reshape((height, width))
                depth_data = depth_data.astype(np.float32) * scale
                depth_data = np.where((depth_data > self.MIN_DEPTH) & (depth_data < self.MAX_DEPTH), depth_data, 0)
                depth_data = depth_data.astype(np.uint16)
                depth_data = np.rot90(depth_data, 2)
                self._depth_buffer.append(depth_data)
                print("frame time: ", time.time())
            except Exception as e:
                if self._pipeline:
                    print(f"GeminiCamera: Stop pipeline")
                    self.stop_record()
                    self._pipeline.stop()

    def _stop_pipeline(self):
        """Stop the Gemini camera pipeline."""
        if self._pipeline:
            self._pipeline.stop()

    def get_real_depth(self, depth):
        return depth / 1000.0


class NullCamera(BaseCamera):
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pipeline = None

    def _start_pipeline(self):
        pass

    def _stop_pipeline(self):
        pass

    def get_real_depth(self, depth):
        return 0


class CameraFactory:
    """Factory class for creating camera instances."""

    CAMERA_TYPES = {
        'theta': ThetaCamera,
        'dai': DaiCamera,
        'realsense': RealsenseCamera,
        'ros2topicrgb': Ros2TopicRgbCamera,
        'ros2topicdepth': Ros2TopicDepthCamera,
        'gemini': GeminiCamera,
        'null': NullCamera,
    }

    @classmethod
    def create_camera(cls, camera_type: str, **kwargs) -> BaseCamera:
        """Create a camera instance based on the camera type.

        Args:
            camera_type: Type of camera ('theta', 'dai', 'realsense')
            **kwargs: Additional arguments to pass to the camera constructor

        Returns:
            Camera instance

        Raises:
            ValueError: If camera_type is not supported
        """
        if camera_type not in cls.CAMERA_TYPES:
            raise ValueError(f"Unsupported camera type: {camera_type}. "
                           f"Supported types: {list(cls.CAMERA_TYPES.keys())}")

        camera_class = cls.CAMERA_TYPES[camera_type]
        return camera_class(**kwargs, identifier=camera_type)
