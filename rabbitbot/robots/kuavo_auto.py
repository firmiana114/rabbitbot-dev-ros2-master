import os
import threading
import math
import time
import asyncio
import json
import atexit
import signal
import sys
import ast
import traceback
import cv2
import numpy as np
from textwrap import dedent

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from .kuavo_action_client import (
    NaviForwardActionClient,
    NaviRotateActionClient,
    NaviWayPointActionClient,
    NaviArmActionClient,
    NaviHeadActionClient,
    NaviFingerActionClient,
    NaviHandshakeActionClient,
    NaviGrabClient,
    NaviGrabCancelClient
)
from tf2_ros import Buffer, TransformListener
from geometry_msgs.msg import PoseStamped
from actionlib_msgs.msg import GoalStatusArray
from std_msgs.msg import UInt8, Bool, String

from .constants import MoveType, NavigationStatus
from .meta import RobotMeta
from .cameras import CameraFactory, BaseCamera


def tts_sound(tts_agent, text, lang):
    input_dict = {"task": "text_to_speech", "lang": lang, "text": text, "timeout": 30}
    print(input_dict)
    tts_index = tts_agent.run(json.dumps(input_dict))
    return int(tts_index) if tts_index else -1


class KuavoNavigator(object):

    def __init__(
        self,
        forward_client,
        rotate_client,
        way_point_client,
        anolog_stick_factor: float = 0.5,
        move_step: float = 0.25,
        rotate_step: float = 30.0
    ):
        super().__init__()

        self.forward_client = forward_client
        self.rotate_client = rotate_client
        self.way_point_client = way_point_client

        self.anolog_stick_factor = anolog_stick_factor
        self.move_step = move_step
        self.rotate_step = rotate_step

        self.move_time = 1.1 * self.move_step / self.anolog_stick_factor
        self.rotate_time = 0.0155 * self.rotate_step / self.anolog_stick_factor

    async def jazzy_control(self, move_type: MoveType):
        if move_type == MoveType.FORWARD:
            self.forward_client.send_goal(self.move_step, spin=False)
        elif move_type == MoveType.LEFT:
            self.rotate_client.send_goal(self.rotate_step, spin=False)
        elif move_type == MoveType.RIGHT:
            self.rotate_client.send_goal(-self.rotate_step, spin=False)

    def jazzy_control_sync(self, move_type: MoveType):
        print(f"jazzy_control_sync: move_type {move_type}")
        if move_type == MoveType.FORWARD:
            self.forward_client.send_goal(self.move_step)
        elif move_type == MoveType.LEFT:
            self.rotate_client.send_goal(self.rotate_step)
        elif move_type == MoveType.RIGHT:
            self.rotate_client.send_goal(-self.rotate_step)



class TfOdomBaseLink(Node):
    def __init__(self):
        super().__init__('tf_odom_base_link')
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.timer = self.create_timer(0.1, self.echo)
        self.cur_pose = (0, 0, 0, 0.0)
        self.debug = False

    def echo(self):
        try:
            #t = self.tf_buffer.lookup_transform('odom', 'base_link', rclpy.time.Time())
            t = self.tf_buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            trans = t.transform.translation
            rot   = t.transform.rotation

            x = trans.x
            y = trans.y
            z = trans.z

            def _quat_to_yaw(x, y, z, w):
                siny_cosp = 2.0 * (w * z + x * y)
                cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
                yaw = math.atan2(siny_cosp, cosy_cosp)
                return yaw

            yaw = _quat_to_yaw(rot.x, rot.y, rot.z, rot.w)

            self.cur_pose = (x, y, z, yaw)
            if self.debug:
                print(f"TfOdomBaseLink: Set pose (pose={self.cur_pose})")

        except Exception as e:
            self.get_logger().warn(f'Could not get transform: {e}')

    def get_pose(self):
        if self.debug:
            print(f"TfOdomBaseLink: Get pose")
        return self.cur_pose


class LioPoseTopic(Node):

    def __init__(self):
        super().__init__('lio_topic_pose')
        self.cur_pose = None
        self.debug = False

    def start(self):
        self.topic = "/lio_pose"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            PoseStamped, self.topic, self.pose_callback, 10
        )
        print(f'LioTopicPose: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'LioTopicPose: Stopped')

    def pose_callback(self, msg: PoseStamped) -> None:
        x = msg.pose.position.x
        y = msg.pose.position.y
        z = msg.pose.position.z

        qx = msg.pose.orientation.x
        qy = msg.pose.orientation.y
        qz = msg.pose.orientation.z
        qw = msg.pose.orientation.w

        def _quat_to_yaw(x, y, z, w):
            siny_cosp = 2.0 * (w * z + x * y)
            cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
            yaw = math.atan2(siny_cosp, cosy_cosp)
            return yaw

        yaw = _quat_to_yaw(qx, qy, qz, qw)

        self.cur_pose = (x, y, z, yaw)
        if self.debug:
            print(f"LioTopicPose: Set pose (pose={self.cur_pose})")

    def get_pose(self):
        if self.debug:
            print(f"LioTopicPose: Get pose")
        return self.cur_pose

class GoalReachTopic(Node):

    def __init__(self):
        super().__init__('goal_reach')
        self.cur_status = -1
        self.debug = True

    def start(self):
        self.topic = "/move_base/status"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            GoalStatusArray, self.topic, self.move_status_callback, 10
        )
        print(f'GoalReachTopic: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'GoalReachTopic: Stopped')

    def move_status_callback(self, msg: GoalStatusArray) -> None:
        if self.debug:
            print(f"msg {msg}")
        status_list = msg.status_list
        if self.debug:
            print(f"status_list_len {len(status_list)}")

        if len(status_list) > 0:
            self.cur_status = status_list[0].status
            if self.debug:
                print(f"GoalReachTopic: Set status (status={self.cur_status})")

    def get_status(self):
        if self.debug:
            print(f"GoalReachTopic: Get status")
        return self.cur_status

class GoalReachTopicV2(Node):

    def __init__(self):
        super().__init__('goal_reach')
        self.cur_status = -1
        self.debug = True  # 开启调试日志

    def start(self):
        self.topic = "/kuavo_navigation_state"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            UInt8, self.topic, self.move_status_callback, 10
        )
        print(f'[DEBUG] GoalReachTopicV2: Started, subscribing to {self.topic}')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'[DEBUG] GoalReachTopicV2: Stopped')

    def move_status_callback(self, msg: UInt8) -> None:
        old_status = self.cur_status
        self.cur_status = int(msg.data)
        if self.debug or old_status != self.cur_status:
            print(f"[DEBUG] GoalReachTopicV2: Status changed {old_status} -> {self.cur_status}")
        if self.debug:
            print(f"msg {msg}")

    def get_status(self):
        if self.debug:
            print(f"[DEBUG] GoalReachTopicV2: get_status() returning {self.cur_status}")
        return self.cur_status


class NavStatusTopic(Node):

    def __init__(self, callback):
        super().__init__('nav_status_topic')
        self.callback = callback
        self.debug = True

    def start(self):
        self.topic = "/nav_status"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            String, self.topic, self.nav_status_callback, 10
        )
        print(f'NavStatusTopic: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'NavStatusTopic: Stopped')

    def nav_status_callback(self, msg: String) -> None:
        status = (msg.data or "").strip()
        if self.debug:
            print(f"NavStatusTopic: recv status={status}")
        self.callback(status)


class FingerStatus(Node):

    def __init__(self):
        super().__init__('finger_status')
        self.cur_status = -1
        self.debug = False

    def start(self):
        self.topic = "/ik_arm_state"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            Bool, self.topic, self.move_status_callback, 10
        )
        print(f'FingerStatus: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'FingerStatus: Stopped')

    def move_status_callback(self, msg: Bool) -> None:
        if self.debug:
            print(f"msg {msg}")
        self.cur_status = int(msg.data)
        if self.debug:
            print(f"FingerStatus: Set status (status={self.cur_status})")

    def reset_status(self):
        self.cur_status = -1

    def get_status(self):
        if self.debug:
            print(f"FingerStatus: Get status")
        return self.cur_status

class GrabStatus(Node):

    def __init__(self):
        super().__init__('grab_status')
        self.cur_status = -1
        self.debug = True

    def start(self):
        self.topic = "/catch"
        assert self.topic is not None, "topic cannot be none"

        self.subscription = self.create_subscription(
            Bool, self.topic, self.move_status_callback, 10
        )
        print(f'GrabStatus: Started')

    def stop(self):
        self.destroy_subscription(self.subscription)
        print(f'GrabStatus: Stopped')

    def move_status_callback(self, msg: Bool) -> None:
        if self.debug:
            print(f"msg {msg}")
        self.cur_status = int(msg.data)
        if self.debug:
            print(f"GrabStatus: Set status (status={self.cur_status})")

    def reset_status(self):
        self.cur_status = -1

    def get_status(self):
        if self.debug:
            print(f"GrabStatus: Get status")
        return self.cur_status

class AutonomyBot(metaclass=RobotMeta):

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
        crop_frame_size: tuple = (960, 540),
        crop_frame_ratio: float = 0.95,
        anolog_stick_factor: float = 0.5,
        enable_ros: bool = True,
        enable_vln: bool = True
    ):
        with open(os.path.join(os.path.dirname(__file__), 'map.json'), 'r', encoding='utf-8') as f:
            self.map_data = json.load(f)

        # Default to single realsense camera if no camera types provided
        if camera_types is None:
            camera_types = ['theta']

        # Camera setup - initialize multiple cameras
        if 'ros2topicrgb' in camera_types or 'ros2topicdepth' in camera_types:
            rclpy.init()
        if 'realsense' in camera_types or 'gemini' in camera_types or 'null' in camera_types:
            rclpy.init()
        self._cameras: list[BaseCamera] = []
        for camera_type in camera_types:
            print(f"AutonomyBot: Create camera (type={camera_type})")
            camera = CameraFactory.create_camera(
                camera_type=camera_type,
                fps=fps,
                image_buffer_size=image_buffer_size,
                image_buffer_dir=image_buffer_dir,
                record_frame_size=record_frame_size,
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
        self.crop_frame_size = crop_frame_size
        self.crop_frame_ratio = crop_frame_ratio
        self.started = False
        self.anolog_stick_factor = anolog_stick_factor
        self.enable_ros = enable_ros
        self.enable_vln = enable_vln

    def start(self):
        if self.started:
            return
        self.started = True

        #rclpy.init()

        # Start all cameras
        for camera in self._cameras:
            camera.start()

        self._task_count = 0
        #self.start_record()

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
            #self.stop_record()
            camera.stop()

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
        print(f"AutonomyBot: View 2D")
        self.wait_for_camera()
        # Delegate to the first camera's view_2d method
        return self._cameras[0].view_2d(yaw, pitch, fov, output_size)

    def get_depth_camera(self):
        """Get the first camera that supports depth."""
        for camera in self._cameras:
            if camera.has_depth:
                return camera
        raise ValueError("No depth camera available")

    def try_get_depth_camera(self):
        for camera in self._cameras:
            if camera.has_depth:
                return camera
        return None

    async def wait_until_stopped(self):
        pass

    async def go_to(
        self,
        location: str = None,
        point: tuple = None,
    ):
        pass

    def forward(self, distance: float):
        pass

    def wait_for_camera(self, timeout=10):
        for camera in self._cameras:
            camera.wait_for_camera(timeout)

    @property
    def recording(self) -> bool:
        """Check if any camera is currently recording."""
        return any(camera.is_recording for camera in self._cameras)

    def get_point(self):
        pass

    def get_pose(self):
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        return True


class KuavoAutonomyBot(AutonomyBot):

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
        crop_frame_size: tuple = (960, 540),
        crop_frame_ratio: float = 0.95,
        anolog_stick_factor: float = 0.5,
        enable_ros: bool = True,
        enable_vln: bool = True
    ):
        super().__init__(
            image_buffer_dir,
            image_buffer_size,
            fps,
            stopped_check_times,
            move_step,
            rotate_step,
            camera_types,
            record_frame_size,
            crop_frame_size,
            crop_frame_ratio,
            anolog_stick_factor,
            enable_ros,
            enable_vln
        )
        atexit.register(self.exit)
        signal.signal(signal.SIGINT, self._signal_handler)
        print(f'KuavoAutonomyBot: Created')

    def start(self):
        super().start()

        if self.enable_ros:
            #print("Kuavo ROS is enabled, please check!")
            #input("Press ENTER to continue or Ctrl+C to stop")
            self.forward_client = NaviForwardActionClient()
            self.rotate_client = NaviRotateActionClient()
            self.way_point_client = NaviWayPointActionClient()
            self.arm_client = NaviArmActionClient()
            self.head_client = NaviHeadActionClient()
            self.finger_client = NaviFingerActionClient()
            self.handshake_client = NaviHandshakeActionClient()
            self.grab_client = NaviGrabClient()
            self.grab_cancel_client = NaviGrabCancelClient()
            self._navigator = KuavoNavigator(
                forward_client=self.forward_client,
                rotate_client=self.rotate_client,
                way_point_client=self.way_point_client,
                move_step=self.move_step,
                rotate_step=self.rotate_step,
                anolog_stick_factor=self.anolog_stick_factor,
            )
            #self.tf_odom_base_link = TfOdomBaseLink()
            self.lio_pose = LioPoseTopic()
            #self.goal_reach = GoalReachTopic()
            self.goal_reach = GoalReachTopicV2()
            self.nav_status = NavStatusTopic(self._handle_nav_status)
            self.finger_status = FingerStatus()
            self.grab_status = GrabStatus()
            self._waypoint_lock = threading.Lock()
            self._waypoints = []
            self._waypoint_index = 0
            self._last_nav_status = ""
            self._last_navigation_last_status = -1
            self._last_navigation_next_status = -1
            self._pending_arrival_transition = False
            self._nav_status_final_arrived = False
            self._nav_status_arm_ready = False
            self.lio_pose.start()
            self.goal_reach.start()
            self.nav_status.start()
            self.finger_status.start()
            self.grab_status.start()

            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self.forward_client)
            self._executor.add_node(self.rotate_client)
            self._executor.add_node(self.way_point_client)
            self._executor.add_node(self.arm_client)
            self._executor.add_node(self.head_client)
            self._executor.add_node(self.finger_client)
            self._executor.add_node(self.handshake_client)
            self._executor.add_node(self.grab_client)
            self._executor.add_node(self.grab_cancel_client)
            # for i in range(len(self._cameras)):
            #     self._executor.add_node(self._cameras[i])
            # self._executor.add_node(self.tf_odom_base_link)
            self._executor.add_node(self.lio_pose)
            self._executor.add_node(self.goal_reach)
            self._executor.add_node(self.nav_status)
            self._executor.add_node(self.finger_status)
            self._executor.add_node(self.grab_status)
            self._spin_thread = threading.Thread(target=self._spin_executor, args=(), daemon=True)
            self._spin_thread.start()
        else:
            print(f'KuavoAutonomyBot: ROS is disabled')
            self.forward_client = None
            self.rotate_client = None
            self.way_point_client = None
            self.arm_client = None
            self.head_client = None
            self.finger_client = None
            self.handshake_client = None
            self.grab_client = None
            self.grab_cancel_client = None
            self._navigator = None
            self.tf_odom_base_link = None
            self.lio_pose = None
            self.goal_reach = None
            self.nav_status = None
            self._spin_thread = None

        if self.enable_vln:
            from rabbitbot.provider import get_vln
            self.vln_agent = get_vln()

        self.vlm_openai = None

        time.sleep(5)
        print(f'KuavoAutonomyBot: Started')
        depth_camera = self.try_get_depth_camera()
        if depth_camera is not None:
            depth_camera.start_record()
            # print(f'KuavoAutonomyBot: Depth camera recording started')
        else:
            print(f'KuavoAutonomyBot: No depth camera, skip recording')

    def _spin_executor(self):
        while rclpy.ok():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except Exception:
                if not rclpy.ok():
                    break
                print("KuavoAutonomyBot: Spin exception")
                traceback.print_exc()
                time.sleep(0.1)

    def stop(self):
        super().stop()
        if hasattr(self, '_move_task'):
            self._move_task.cancel()
        rclpy.shutdown()
        if self._spin_thread is not None:
            self._spin_thread.join()
        print(f'KuavoAutonomyBot: Stopped')
        depth_camera = self.try_get_depth_camera()
        if depth_camera is not None and depth_camera._recording:
            depth_camera.stop_record()
            print(f'KuavoAutonomyBot: Recording stopped')

    def jazzy_control_sync(self, move_type: MoveType):
        if self._navigator is not None:
            self._navigator.jazzy_control_sync(move_type)

    def _jazzy_done_callback(self, _):
        pass

    async def move_with_jazzy(self, move_type: MoveType, blocking: bool = True):
        asyncio.new_event_loop
        if blocking:
            if self._navigator is not None:
                self._navigator.jazzy_control_sync(move_type)
            return

        if move_type == MoveType.STOP:
            await self._move_task
            return

        if hasattr(self, '_move_task'):
            #self._move_task.remove_done_callback(self._jazzy_done_callback)
            await self._move_task
        # Ensure intermediate execution
        if self._navigator is not None:
            self._move_task = asyncio.get_running_loop().run_in_executor(
                None, self._navigator.jazzy_control_sync, move_type)
        #self._move_task.add_done_callback(self._jazzy_done_callback)

    async def move_with_joystick(self, move_type: MoveType, blocking: bool = True):
        pass

    def get_point(self):
        print(f"KuavoAutonomyBot: Get point")
        #if self.tf_odom_base_link is not None:
        #    return self.tf_odom_base_link.get_pose()
        if self.lio_pose is not None:
            return self.lio_pose.get_pose()
        else:
            return (0.0, 0.0)

    def get_pose(self):
        print(f"KuavoAutonomyBot: Get pose")
        #if self.tf_odom_base_link is not None:
        #    return self.tf_odom_base_link.get_pose()
        if self.lio_pose is not None:
            return self.lio_pose.get_pose()
        else:
            return (0.0, 0.0, 0.0, 0.0)

    def is_go_to_complete(self, old_pose: tuple, new_pose: tuple):
        x0, y0, _, _ = old_pose
        x1, y1, _, _ = new_pose
        dx, dy = x1 - x0, y1 - y0
        distance_threshold = 0.2
        return math.sqrt(dx * dx + dy * dy) <= distance_threshold

    def _get_navigation_float_env(self, name, default):
        raw_value = os.getenv(name, str(default))
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            print(f"Invalid {name}={raw_value}, use {default}")
            return float(default)

    def is_go_to_complete_v2(self, last_status):
        next_status = self.goal_reach.get_status() if self.goal_reach is not None else -1
        #if last_status == 1 and next_status == 3:
        with self._waypoint_lock:
            nav_status = self._last_nav_status
            nav_status_final_arrived = self._nav_status_final_arrived
            nav_status_arm_ready = self._nav_status_arm_ready
            self._last_navigation_last_status = last_status
            self._last_navigation_next_status = next_status
        print(f"last_status {last_status}, next_status {next_status}, sub {nav_status}")
        if nav_status_final_arrived and nav_status_arm_ready:
            return True, NavigationStatus.SUCCEEDED.value
        if last_status == 1 and next_status == 2:
            return self._handle_navigation_arrival_transition(next_status)
        else:
            return False, next_status

    def get_navigation_debug_status(self):
        with self._waypoint_lock:
            return {
                "last_status": self._last_navigation_last_status,
                "next_status": self._last_navigation_next_status,
                "sub": self._last_nav_status,
            }

    def _normalize_waypoints(self, point):
        if point is None:
            return []
        if isinstance(point, str):
            try:
                point = ast.literal_eval(point)
            except (SyntaxError, ValueError):
                return []
        if isinstance(point, dict):
            point = [
                point.get("x"),
                point.get("y"),
                point.get("ox"),
                point.get("oy"),
                point.get("oz"),
                point.get("ow"),
            ]
        if not isinstance(point, (list, tuple)):
            return []

        if len(point) >= 6 and not isinstance(point[0], (list, tuple, dict)):
            point = [point]

        waypoints = []
        for item in point:
            if isinstance(item, dict):
                values = [
                    item.get("x"),
                    item.get("y"),
                    item.get("ox"),
                    item.get("oy"),
                    item.get("oz"),
                    item.get("ow"),
                ]
            elif isinstance(item, (list, tuple)) and len(item) >= 6:
                values = item[:6]
            else:
                continue
            try:
                waypoints.append(tuple(float(value) for value in values))
            except (TypeError, ValueError):
                continue
        return waypoints

    def _send_waypoint(self, index):
        if self.way_point_client is None:
            print("[DEBUG] _send_waypoint: way_point_client is None, cannot send!")
            return False
        with self._waypoint_lock:
            if index < 0 or index >= len(self._waypoints):
                print(f"[DEBUG] _send_waypoint: index {index} out of range!")
                return False
            self._waypoint_index = index
            x, y, ox, oy, oz, ow = self._waypoints[index]
        print(f"[DEBUG] _send_waypoint: Sending waypoint {index + 1}/{len(self._waypoints)} to navi_way_point action")
        print(f"[DEBUG] _send_waypoint: Position: x={x:.4f}, y={y:.4f}")
        print(f"[DEBUG] _send_waypoint: Orientation: ox={ox:.4f}, oy={oy:.4f}, oz={oz:.4f}, ow={ow:.4f}")
        self.way_point_client.send_goal(x, y, ox, oy, oz, ow, spin=False)
        print("[DEBUG] _send_waypoint: send_goal() called")
        return True

    def _handle_navigation_arrival_transition(self, next_status):
        next_index = None
        with self._waypoint_lock:
            nav_status = self._last_nav_status
            if nav_status == "arrived":
                self._pending_arrival_transition = False
                self._nav_status_final_arrived = True
                print("KuavoAutonomyBot: nav_status arrived, reached final waypoint, wait arm_ready")
                return False, next_status
            if nav_status == "mid_arrived":
                current_index = self._waypoint_index
                next_index = current_index + 1
                self._pending_arrival_transition = False
                self._last_nav_status = ""
                print(
                    f"KuavoAutonomyBot: nav_status mid_arrived, "
                    f"reached mid waypoint {current_index + 1}/{len(self._waypoints)}"
                )
            else:
                self._pending_arrival_transition = True
                print("KuavoAutonomyBot: recv 1->2, wait nav_status sub")
                return False, next_status

        if next_index is not None:
            if self._send_waypoint(next_index):
                print(f"KuavoAutonomyBot: arrived at mid waypoint, go to waypoint {next_index + 1}")
            else:
                with self._waypoint_lock:
                    self._nav_status_final_arrived = True
                print("KuavoAutonomyBot: mid_arrived but no next waypoint, wait arm_ready")
            return False, -1

        return False, next_status

    def _handle_nav_status(self, status):
        if status not in {"arrived", "mid_arrived", "arm_ready"}:
            return

        next_index = None
        with self._waypoint_lock:
            self._last_nav_status = status
            print(f"KuavoAutonomyBot: recv nav_status {status}")
            if status == "arm_ready":
                self._nav_status_arm_ready = True
                if self._nav_status_final_arrived:
                    print("KuavoAutonomyBot: nav_status arm_ready, final waypoint ready")
                else:
                    print("KuavoAutonomyBot: nav_status arm_ready before final arrived")
                return
            if not self._pending_arrival_transition:
                return
            if status == "arrived":
                self._pending_arrival_transition = False
                self._nav_status_final_arrived = True
                print("KuavoAutonomyBot: nav_status arrived after 1->2, reached final waypoint, wait arm_ready")
                return
            if status == "mid_arrived":
                current_index = self._waypoint_index
                next_index = current_index + 1
                self._pending_arrival_transition = False
                self._last_nav_status = ""
                print(
                    f"KuavoAutonomyBot: nav_status mid_arrived after 1->2, "
                    f"reached mid waypoint {current_index + 1}/{len(self._waypoints)}"
                )
        if next_index is not None:
            if self._send_waypoint(next_index):
                print(f"KuavoAutonomyBot: arrived at mid waypoint, go to waypoint {next_index + 1}")
            else:
                with self._waypoint_lock:
                    self._nav_status_final_arrived = True
                print("KuavoAutonomyBot: mid_arrived but no next waypoint, wait arm_ready")

    def _go_to(
        self,
        location: str = None,
        point: tuple = None,
        query = None
    ):
        if self.way_point_client is None:
            print("[DEBUG] _go_to: way_point_client is None, using fake navigation")
            return self._go_to_fake(location, point, query)

        print(f"[DEBUG] _go_to: Starting navigation to point={point}")
        query.set_status(NavigationStatus.ACTIVE)
        waypoints = self._normalize_waypoints(point)
        if not waypoints:
            print(f"[DEBUG] _go_to: no valid waypoint from {point}, aborting!")
            query.set_status(NavigationStatus.ABORTED)
            return
        with self._waypoint_lock:
            self._waypoints = waypoints
            self._waypoint_index = 0
            self._last_nav_status = ""
            self._last_navigation_last_status = -1
            self._last_navigation_next_status = -1
            self._pending_arrival_transition = False
            self._nav_status_final_arrived = False
            self._nav_status_arm_ready = False
        print(f"[DEBUG] _go_to: waypoints normalized, count={len(waypoints)}")
        self._send_waypoint(0)
        print("[DEBUG] _go_to: Waiting for navigation to complete...")
        time.sleep(5)
        is_completed = False
        last_status = self.goal_reach.get_status() if self.goal_reach is not None else -1
        print(f"[DEBUG] _go_to: Initial goal_reach status = {last_status}")
        loop_count = 0
        while not is_completed:
            loop_count += 1
            is_completed, last_status = self.is_go_to_complete_v2(last_status)
            if loop_count % 10 == 0:  # 每5秒打印一次
                debug_status = self.get_navigation_debug_status()
                print(f"[DEBUG] _go_to: loop={loop_count}, is_completed={is_completed}, status={debug_status}")
            time.sleep(0.5)
        print(f"[DEBUG] _go_to: Navigation completed! Setting status to SUCCEEDED")
        query.set_status(NavigationStatus.SUCCEEDED)

    async def go_to(
        self,
        location: str = None,
        point: tuple = None,
        query = None
    ):
        self._go_to_thread = threading.Thread(target=self._go_to, args=(location, point, query))
        self._go_to_thread.start()
        return True

    def _go_to_fake(
        self,
        location: str = None,
        point: tuple = None,
        query = None
    ):
        print(f"Run go to (fake): {point}")
        query.set_status(NavigationStatus.ACTIVE)
        time.sleep(5)
        print("Reached")
        query.set_status(NavigationStatus.SUCCEEDED)

    async def go_to_fake(
        self,
        location: str = None,
        point: tuple = None,
        query = None
    ):
        self._go_to_thread = threading.Thread(target=self._go_to_fake, args=(location, point, query))
        self._go_to_thread.start()
        return True

    def go_to_async(
        self,
        location: str = None,
        point: tuple = None,
        query = None
    ):
        print(f"[DEBUG] go_to_async called: location={location}, point={point}")
        print(f"[DEBUG] go_to_async: way_point_client = {self.way_point_client}")
        print("[DEBUG] go_to_async: Creating navigation thread")
        self._go_to_thread = threading.Thread(target=self._go_to, args=(location, point, query))
        print("[DEBUG] go_to_async: Thread created, starting thread")
        self._go_to_thread.start()
        print("[DEBUG] go_to_async: Thread started")
        return True

    def _do_arm(self, action_name: str):
        if self.arm_client is not None:
            return self.arm_client.send_goal(action_name)
        return {"success": False, "message": "arm client is not available"}

    def do_arm(self, action_name: str):
        return self._do_arm(action_name)


    def do_head(self, yaw: float, pitch: float):
        if self.head_client is not None:
            self.head_client.send_goal(yaw, pitch)

    def _do_finger(self, x: float, y: float, z: float):
        if self.finger_status is not None:
            self.finger_status.reset_status()
        if self.finger_client is not None:
            self.finger_client.send_goal(x, y, z)

    def do_finger(self, x: float, y: float, z: float):
        self.do_finger_thread = threading.Thread(target=self._do_finger, args=(x, y, z))
        self.do_finger_thread.start()

    def do_finger_status(self):
        if self.finger_status is not None:
            return self.finger_status.get_status()
        else:
            return None

    def do_grab_status(self):
        if self.grab_status is not None:
            return self.grab_status.get_status()
        else:
            return None

    def _do_handshake(self, x: float, y: float, z: float):
        if self.handshake_client is not None:
            self.handshake_client.send_goal(x, y, z)

    def do_handshake(self, x: float, y: float, z: float):
        self.do_handshake_thread = threading.Thread(target=self._do_handshake, args=(x, y, z))
        self.do_handshake_thread.start()

    def _do_grab(self, x: float, y: float, z: float):
        if self.grab_status is not None:
            self.grab_status.reset_status()
        if self.grab_client is not None:
            print(f"_do_grab: x {x}, y {y}, z {z}")
            self.grab_client.send_goal(x, y, z)

    def do_grab(self, x: float, y: float, z: float):
        print(f"do_grab: x {x}, y {y}, z {z}")
        self.do_grab_thread = threading.Thread(target=self._do_grab, args=(x, y, z))
        self.do_grab_thread.start()

    def _do_grab_cancel(self):
        if self.grab_cancel_client is not None:
            self.grab_cancel_client.send_goal()

    def do_grab_cancel(self):
        self.do_grab_cancel_thread = threading.Thread(target=self._do_grab_cancel, args=())
        self.do_grab_cancel_thread.start()

    def crop_and_resize(self, image):
        h, w, _ = image.shape
        start_y = int(h * (1 - self.crop_frame_ratio) // 2)
        start_x = int(w * (1 - self.crop_frame_ratio) // 2)
        cropped_image = image[start_y:h-start_y, start_x:w-start_x]
        image = cv2.resize(cropped_image, (w, h))
        return image

    def vln(self, task: str, tts_agent):
        if not self.enable_vln:
            tts_sound(tts_agent, "，，“威阿恩“尚未开启，请检查配置文件，是否开启了“威阿恩“", "zh")
            return
        tts_sound(tts_agent, "，，“威阿恩“动态导航即将开始，注意避让！", "zh")
        tts_sound(tts_agent, "，，三！二 ！一！开始！", "zh")
        self.vln_agent.reset()

        ASYNC_ACTION = False
        MAX_VLN_STEPS = 64
        WORK_DIR = "workspace/tools/navigation_tools"
        num_steps = 0
        image = self.view_2d(output_size=self.crop_frame_size)
        while num_steps < MAX_VLN_STEPS:
            #proj_dir = "/root/rabbitbot/"
            image_path = os.path.join(WORK_DIR, 'navi.png')
            print(f"KuavoDynamicNavigation: Write image (path={image_path})")
            cv2.imwrite(image_path, image)
            start_time = time.time()
            action = self.vln_agent.act(image_path, task)
            act_time = time.time() - start_time
            print(f"KuavoDynamicNavigation: Get action (action={action}, time={act_time:.3f})")
            #import pdb; pdb.set_trace()

            if action == MoveType.FORWARD:
                tts_sound(tts_agent, "，，前进", "zh")
            elif action == MoveType.LEFT:
                tts_sound(tts_agent, "，，向左转", "zh")
            elif action == MoveType.RIGHT:
                tts_sound(tts_agent, "，，向右转", "zh")
            else:
                tts_sound(tts_agent, "，，已到达", "zh")

            print(f"action: {action.name}")
            if action == MoveType.STOP:
                break

            if not ASYNC_ACTION:
                print(f"KuavoDynamicNavigation: 同步控制")
                self.jazzy_control_sync(action)
                print(f"KuavoDynamicNavigation: 获取图像")
                image = self.view_2d(output_size=self.crop_frame_size)
            else:
                '''
                self.jazzy_control(action)
                if action == MoveType.FORWARD:
                    image = self.view_2d(output_size=self.frame_size)
                    # Forward prediction
                    image = self.crop_and_resize(image)
                else:
                    rotation = self.rotate_step if action == MoveType.RIGHT else -robot.rotate_step
                    # Rotate prediction
                    image = self.view_2d(yaw=rotation, output_size=self.frame_size)
                '''
                pass
            num_steps += 1
        if num_steps == MAX_VLN_STEPS:
            tts_sound(tts_agent, "，，抱歉，已经达到威阿恩最大执行步数，动态导航终止", "zh")

    def get_inst_view(self):
        VISION_FEATURE_EXTRACTOR_PROMPT = dedent(f"""\
            你是一个视觉识别助手，任务是根据用户的问题，从当前图片中提取指定物体的**具体视觉特征值**。

            ## 任务规则
            - 用户的问题通常关于颜色、衣物、动作、物品持有等可见属性
            - 你的回答必须：
                1. **只输出一个最准确的特征值**
                2. **不要解释、不要完整句、不要多余文字**
                3. **保持极简：如“白色”、“坐着”、“戴眼镜”**
                4. 如果无法确定，输出“未知”

            ## 示例
            - 问：图片里的人穿着什么颜色的衣服？
            答：白色

            - 问：这个人戴帽子了吗？
            答：是

            - 问：他手里拿着什么？
            答：咖啡杯

            - 问：图片中的人是什么性别？
            答：男

            - 问：她在做什么？
            答：微笑

            ## 注意
            - 不要说“图片中的人穿的是白色衣服”这种完整句子
            - 只输出关键词或短语
            - 区分事实描述与推测，不确定时回答“未知”

            当前图片和问题如下：
        """)
        return VISION_FEATURE_EXTRACTOR_PROMPT

    def view(self, task: str):
        if self.vlm_openai is None:
            from rabbitbot.provider import create_general_vlm_openai
            self.vlm_openai = create_general_vlm_openai()
        inst = self.get_inst_view()
        prompt = f"{inst}\n{task}"
        image = self.view_2d()
        image_message, video_kwargs = self.vlm_openai.prepare_message_for_vllm([image], prompt)
        response_text = self.vlm_openai.get_chat_response(
            messages=image_message,
            extra_body={
                "mm_processor_kwargs": video_kwargs
            }
        )
        return response_text

    def __del__(self):
        self.stop()

    def exit(self):
        print("Kuavo程序退出，正在清理资源...")
        self.stop()

    def _signal_handler(self, signum, frame):
        print(f"\n接收到信号 {signum}，开始清理...")
        self.exit()
        sys.exit(0)  # 手动退出，确保 atexit 也被触发
