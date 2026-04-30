import os
import threading
import math
import time
from typing import Optional
import queue
import json

import numpy as np
from qwen_agent.log import logger
import cv2

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PointStamped
from sensor_msgs.msg import Joy
from std_msgs.msg import Header
from geometry_msgs.msg import Point

from .utils import euler_from_quaternion
from .constants import MoveType
from .meta import RobotMeta
from .cameras import CameraFactory, BaseCamera


class StateEstimationListener(Node):

    def __init__(self, speed_threshold=0.10):
        super().__init__('state_estimation_listener')
        self.current_pose = None
        self.current_linear = None
        self.current_angular = None
        self.stopped_times = 0
        self.speed_threshold = speed_threshold
        self.create_subscription(Odometry, '/state_estimation', self._odom_callback, 5)

    def _odom_callback(self, msg: Odometry):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        z = msg.pose.pose.position.z
        q = msg.pose.pose.orientation
        _, _, yaw = euler_from_quaternion(q.x, q.y, q.z, q.w)
        self.current_pose = (x, y, z, yaw)
        self.current_linear = msg.twist.twist.linear
        self.current_angular = msg.twist.twist.angular
        if self.is_stopped():
            self.stopped_times += 1
        else:
            self.stopped_times = 0

    def get_pose(self):
        return self.current_pose

    def get_point(self, distance: float = 0.0, angle_deg: float = 0.0):
        if not self.current_pose:
            return None
        x0, y0, z0, yaw0 = self.current_pose
        total_yaw = yaw0 - math.radians(angle_deg)
        x = x0 + math.cos(total_yaw) * distance
        y = y0 + math.sin(total_yaw) * distance
        return x, y, z0

    def is_stopped(self):
        return (
            self.current_linear is None
            or self.current_angular is None
            or all(map(lambda x: x < self.speed_threshold, [
                self.current_linear.x, self.current_linear.y, self.current_linear.z,
                self.current_angular.x, self.current_angular.y, self.current_angular.z,
            ]))
        )


class Navigator(Node):

    def __init__(
        self,
        listener: StateEstimationListener,
        anolog_stick_factor: float = 0.5,
        move_step: float = 0.25,
        rotate_step: float = 30,
        check_interval: float = 0.05,
        check_through_pose: bool = True,
    ):
        super().__init__('navigator')
        self.way_point_publisher = self.create_publisher(PointStamped, "way_point", 5)
        self.joy_publisher = self.create_publisher(Joy, "joy", 5)
        self.anolog_stick_factor = anolog_stick_factor
        self.move_step = move_step
        self.rotate_step = rotate_step
        self.listener = listener
        self.check_interval = check_interval
        self.check_through_pose = check_through_pose

        self.move_time = 1.1 * self.move_step / self.anolog_stick_factor
        self.rotate_time = 0.0155 * self.rotate_step / self.anolog_stick_factor

    def navigate_to(self, point: tuple):
        header = Header(
            stamp=self.get_clock().now().to_msg(),
            frame_id='map',
        )
        point_stamped = PointStamped(
            header=header,
            point=Point(x=float(point[0]), y=float(point[1]), z=float(point[2])),
        )
        self.way_point_publisher.publish(point_stamped)
        self.way_point_publisher.publish(point_stamped)
        header = Header(
            stamp=self.get_clock().now().to_msg(),
            frame_id='teleop_panel',
        )
        joy = Joy(
            header=header,
            axes=[0,0,-1,0,1,1,0,0],
            buttons=[0,0,0,0,0,0,0,1,0,0,0],
        )
        self.joy_publisher.publish(joy)

    def joy_control(self, move_type: MoveType):
        header = Header(
            stamp=self.get_clock().now().to_msg(),
            frame_id='teleop_panel',
        )
        sleep_time = 0
        if move_type == MoveType.FORWARD:
            # TODO: refactor: map button to index and place in constants.py
            # Manual mode
            joy = Joy(
                header=header,
                axes=[0,0,1,0,self.anolog_stick_factor,-1,0,0],
                buttons=[0,0,0,0,0,0,0,0,0,0,0],
            )
            sleep_time = self.move_time
        elif move_type == MoveType.LEFT:
            joy = Joy(
                header=header,
                axes=[self.anolog_stick_factor,0,1,0,0,-1,0,0],
                buttons=[0,0,0,0,0,0,0,0,0,0,0],
            )
            sleep_time = self.rotate_time
        elif move_type == MoveType.RIGHT:
            joy = Joy(
                header=header,
                axes=[-self.anolog_stick_factor,0,1,0,0,-1,0,0],
                buttons=[0,0,0,0,0,0,0,0,0,0,0],
            )
            sleep_time = self.rotate_time
        elif move_type == MoveType.STOP:
            joy = Joy(
                header=header,
                axes=[0,0,1,0,0,1,0,0],
                buttons=[0,0,0,0,0,0,0,0,0,0,0],
            )
            sleep_time = 0
        old_pose = self.listener.get_pose()
        self.joy_publisher.publish(joy)

        if move_type == MoveType.STOP:
            return

        if self.check_through_pose:
            while not self.check_completion(old_pose, self.listener.get_pose(), move_type):
                time.sleep(self.check_interval)
        else:
            time.sleep(sleep_time)

    def check_completion(self, old_pose: tuple, new_pose: tuple, move_type: MoveType):
        x0, y0, z0, yaw0 = old_pose
        x1, y1, z1, yaw1 = new_pose
        dx, dy, dz, dyaw = x1 - x0, y1 - y0, z1 - z0, yaw1 - yaw0
        dyaw = dyaw % (2 * math.pi)
        if move_type == MoveType.FORWARD:
            return math.sqrt(dx * dx + dy * dy + dz * dz) >= self.move_step
        elif move_type == MoveType.LEFT:
            return 2 * math.radians(self.rotate_step) > dyaw >= math.radians(self.rotate_step)
        elif move_type == MoveType.RIGHT:
            return 2 * math.pi - 2 * math.radians(self.rotate_step) < dyaw <= 2 * math.pi -math.radians(self.rotate_step)
        else:
            return True


class CMUAutonomyBot(metaclass=RobotMeta):

    def __init__(
        self,
        image_buffer_dir: str = None,
        image_buffer_size: int = 20,
        fps: int = 10,
        stopped_check_times: int = 50,
        move_step: float = 0.25,
        rotate_step: float = 30,
        camera_types: list = None,  # list of camera types: 'theta', 'dai', or 'realsense'
        record_frame_size: tuple = (1920, 1080),
        anolog_stick_factor: float = 0.5,
    ):
        with open(os.path.join(os.path.dirname(__file__), 'map.json'), 'r', encoding='utf-8') as f:
            self.map_data = json.load(f)

        # Default to single realsense camera if no camera types provided
        if camera_types is None:
            camera_types = ['theta']

        # Camera setup - initialize multiple cameras
        self._cameras: list[BaseCamera] = []
        for camera_type in camera_types:
            camera = CameraFactory.create_camera(
                camera_type=camera_type,
                fps=fps,
                image_buffer_size=image_buffer_size,
                image_buffer_dir=image_buffer_dir,
                record_frame_size=record_frame_size,
                robot=self
            )
            self._cameras.append(camera)
        self.camera_types = camera_types

        # TODO: refactor as RobotConfig
        self.fps = fps
        self.stopped_check_times = stopped_check_times
        self.move_step = move_step
        self.rotate_step = rotate_step
        self.reset_states()
        self.record_frame_size = record_frame_size
        self.started = False
        self.anolog_stick_factor = anolog_stick_factor

    def start(self):
        if self.started:
            return
        self.started = True

        rclpy.init()

        # Start all cameras
        for camera in self._cameras:
            camera.start()

        self._listener = StateEstimationListener()
        self._listener_thread = threading.Thread(target=rclpy.spin, args=(self._listener,), daemon=True)
        self._listener_thread.start()

        self._navigator = Navigator(
            listener=self._listener,
            move_step=self.move_step,
            rotate_step=self.rotate_step,
            anolog_stick_factor=self.anolog_stick_factor,
        )

        self._task_count = 0
        time.sleep(5)

    def start_record(self):
        for camera in self._cameras:
            camera.start_record(self._task_count)
        self._task_count += 1

    def stop_record(self):
        for camera in self._cameras:
            camera.stop_record()

    def __del__(self):
        self.stop()

    def stop(self):
        if not self.started:
            return
        self.started = False
        for camera in self._cameras:
            camera.stop()
        rclpy.shutdown()
        self._listener_thread.join()

    def reset_states(self):
        self.states = {
            'location': '工位',
            'rotation': {
                'yaw': 0.0,
                'pitch': 0.0,
                'fov': 90.0,
            }
        }
        self.reset_rotation()

    def get_all_locations(self):
        return self.map_data.keys()

    def get_location(self):
        return self.states['location']

    def set_location(self, location):
        self.states['location'] = location

    def reset_rotation(self):
        self.states['rotation']['yaw'] = 0.0
        self.states['rotation']['pitch'] = 0.0
        self.states['rotation']['fov'] = 120.0

    def rotate(self, yaw: float = 0.0, pitch: float = 0.0, fov: float = 0.0):
        self.states['rotation']['yaw'] += yaw
        self.states['rotation']['pitch'] += pitch
        self.states['rotation']['fov'] += fov

    def get_rotation(self):
        return self.states['rotation']

    def view_2d(
        self,
        yaw: float = 0.0,
        pitch: float = 0.0,
        fov: float = 90.0,
        output_size: tuple = (800, 600)
    ) -> np.ndarray:
        self.wait_for_camera()
        # Delegate to the first camera's view_2d method
        return self._cameras[0].view_2d(yaw, pitch, fov, output_size)

    def get_depth_camera(self):
        """Get the first camera that supports depth."""
        for camera in self._cameras:
            if camera.has_depth:
                return camera
        raise ValueError("No depth camera available")

    def wait_until_stopped(self):
        while True:
            time.sleep(0.5)
            if self._listener.stopped_times >= self.stopped_check_times:
                break

    def go_to(
        self,
        location: str = None,
        point: tuple = None,
    ):
        point = self.map_data.get(location, point)
        self._navigator.navigate_to(point)

        self.wait_until_stopped()
        return True

    def forward(self, distance: float):
        point = self._listener.get_point(distance, self.get_rotation()['yaw'])
        self.go_to(point=point)
        self.reset_rotation()

    def move_with_joystick(self, move_type: MoveType, blocking: bool = True):
        if blocking:
            self._navigator.joy_control(move_type)
            self._navigator.joy_control(MoveType.STOP)
            return

        def _worker():
            while True:
                item = self._move_queue.get()
                self._navigator.joy_control(item)
                self._move_queue.task_done()
                if self._move_queue.empty():
                    self._navigator.joy_control(MoveType.STOP)

        if not hasattr(self, '_move_thread'):
            self._move_queue = queue.Queue(maxsize=1)
            self._move_thread = threading.Thread(target=_worker, daemon=True)
            self._move_thread.start()

        if move_type == MoveType.STOP:
            self._move_queue.join()
            self._navigator.joy_control(MoveType.STOP)
            return

        self._move_queue.put(move_type)
        # wait until the current job start processing
        if self._move_queue.full():
            with self._move_queue.not_full:
                self._move_queue.not_full.wait()

    def wait_for_camera(self, timeout=10):
        for camera in self._cameras:
            camera.wait_for_camera(timeout)

    @property
    def recording(self) -> bool:
        """Check if any camera is currently recording."""
        return any(camera.is_recording for camera in self._cameras)

    def get_point(self):
        return self._listener.get_pose()[:3]

    def get_pose(self):
        return self._listener.get_pose()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        return True
