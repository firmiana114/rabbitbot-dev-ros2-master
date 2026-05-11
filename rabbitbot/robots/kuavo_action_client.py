
import time
import threading
import os

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from custom_action_interfaces.action import (
    NaviForward, NaviRotate, NaviWayPoint,
    NaviArm, NaviHead,
    NaviIkArm, NaviShakeHands,
    NaviGrab, NaviTargetChanged
)


class NaviForwardActionClient(Node):

    def __init__(self):
        super().__init__('navi_forward_action_client')
        self._action_client = ActionClient(self, NaviForward, 'navi_forward')

    def send_goal(self, distance=0.25, spin=True):
        goal_msg = NaviForward.Goal()
        goal_msg.distance = distance

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Result: {0}'.format(result.delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: {0}'.format(feedback.remaining))

    def __del__(self):
        self.stop()

    def stop(self):
        pass


class NaviRotateActionClient(Node):

    def __init__(self):
        super().__init__('navi_rotate_client')
        self._action_client = ActionClient(self, NaviRotate, 'navi_rotate')

    def send_goal(self, theta, spin=True):
        goal_msg = NaviRotate.Goal()
        goal_msg.theta = float(theta)

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Result: {0}'.format(result.delta))
        #rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: {0}'.format(feedback.remaining))


class NaviWayPointActionClient(Node):

    def __init__(self):
        super().__init__('navi_way_point_action_client')
        self._action_client = ActionClient(self, NaviWayPoint, 'navi_way_point')

    def send_goal(self, x, y, ox, oy, oz, ow, spin=True):
        goal_msg = NaviWayPoint.Goal()
        goal_msg.position_x = float(x)
        goal_msg.position_y = float(y)
        goal_msg.position_z = float(0.0)
        goal_msg.orientation_x = float(ox)
        goal_msg.orientation_y = float(oy)
        goal_msg.orientation_z = float(oz)
        goal_msg.orientation_w = float(ow)

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))


class NaviArmActionClient(Node):

    def __init__(self):
        super().__init__('navi_arm_action_client')
        self._action_client = ActionClient(self, NaviArm, 'navi_arm')

    def _wait_future_done(self, future, timeout_sec):
        start_time = time.time()
        while not future.done():
            if timeout_sec is not None and time.time() - start_time > timeout_sec:
                return False
            time.sleep(0.02)
        return True

    def send_goal(self, action_name, spin=True):
        goal_msg = NaviArm.Goal()
        print(f"NaviArmActionClient: action_name {action_name}")
        goal_msg.action_name = str(action_name)

        server_timeout = float(os.getenv("RABBITBOT_ARM_ACTION_SERVER_TIMEOUT", "5"))
        result_timeout = float(os.getenv("RABBITBOT_ARM_ACTION_RESULT_TIMEOUT", "30"))
        if not self._action_client.wait_for_server(timeout_sec=server_timeout):
            self.get_logger().error(f"NaviArm action server not available for '{action_name}'")
            return {"success": False, "message": "action server not available"}

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            if not self._wait_future_done(self._send_goal_future, result_timeout):
                self.get_logger().error(f"NaviArm goal response timeout for '{action_name}'")
                return {"success": False, "message": "goal response timeout"}
            goal_handle = self._send_goal_future.result()
            if not goal_handle.accepted:
                self.get_logger().info("Goal rejected :(")
                return {"success": False, "message": "goal rejected"}
            self.get_logger().info("Goal accepted :)")
            self._get_result_future = goal_handle.get_result_async()
            if not self._wait_future_done(self._get_result_future, result_timeout):
                self.get_logger().error(f"NaviArm result timeout for '{action_name}'")
                return {"success": False, "message": "result timeout"}
            result = self._get_result_future.result().result
            success = bool(getattr(result, "success", True))
            message = getattr(result, "message", "")
            self.get_logger().info(f"NaviArm action result: success={success}, message={message}")
            return {"success": success, "message": message}
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)
            return {"success": True, "message": "goal sent"}

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))


class NaviHeadActionClient(Node):

    def __init__(self):
        super().__init__('navi_head_action_client')
        self._action_client = ActionClient(self, NaviHead, 'navi_head')

    def send_goal(self, yaw, pitch, spin=True):
        goal_msg = NaviHead.Goal()
        print(f"NaviHeadActionClient: yaw {yaw}, pitch {pitch}")
        goal_msg.yaw = float(yaw)
        goal_msg.pitch = float(pitch)

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))


class NaviFingerActionClient(Node):

    def __init__(self):
        super().__init__('navi_ikarm_action_client')
        self._action_client = ActionClient(self, NaviIkArm, 'navi_ik_arm') # TODO: change to NaviFinger

    def send_goal(self, x, y, z, spin=True):
        goal_msg = NaviIkArm.Goal() # TODO: change to NaviFinger
        print(f"NaviIkArmActionClient: x {x}, y {y}, z {z}")
        goal_msg.position_x = x
        goal_msg.position_y = y
        goal_msg.position_z = z

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))


class NaviHandshakeActionClient(Node):

    def __init__(self):
        super().__init__('navi_handshake_action_client')
        self._action_client = ActionClient(self, NaviShakeHands, 'navi_shake_hands') # TODO: change to NaviFinger

    def send_goal(self, x, y, z, spin=True):
        goal_msg = NaviShakeHands.Goal() # TODO: change to NaviFinger
        print(f"NaviHandshakeActionClient: x {x}, y {y}, z {z}")
        goal_msg.position_x = x
        goal_msg.position_y = y
        goal_msg.position_z = z

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))

class NaviGrabClient(Node):

    def __init__(self):
        super().__init__('navi_grab_action_client')
        self._action_client = ActionClient(self, NaviGrab, 'navi_grab') # TODO: change to NaviFinger

    def send_goal(self, x, y, z, spin=True):
        goal_msg = NaviGrab.Goal() # TODO: change to NaviFinger
        print(f"NaviGrabActionClient: x {x}, y {y}, z {z}")
        goal_msg.position_x = x
        goal_msg.position_y = y
        goal_msg.position_z = z

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))

class NaviGrabCancelClient(Node):

    def __init__(self):
        super().__init__('navi_target_changed')
        self._action_client = ActionClient(self, NaviTargetChanged, 'navi_target_changed') # TODO: change to NaviFinger

    def send_goal(self, spin=True):
        goal_msg = NaviTargetChanged.Goal() # TODO: change to NaviFinger
        print(f"NaviGrabCancelClient: True")
        goal_msg.target_changed = True

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg, feedback_callback=self.feedback_callback)

        if spin:
            rclpy.spin_until_future_complete(self, self._send_goal_future)
        else:
            self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        #self.get_logger().info('Result: ({0},{1})'.format(result.x_delta, result.y_delta))

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        #self.get_logger().info('Received feedback: ({0},{1})'.format(feedback.x_remaining, feedback.y_remaining))
