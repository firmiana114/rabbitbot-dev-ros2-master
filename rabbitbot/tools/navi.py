from qwen_agent.tools.base import BaseTool, BaseToolWithFileAccess, register_tool
from qwen_agent.log import logger

import cv2

from rabbitbot.robots.constants import MoveType
from rabbitbot.robots import get_robot
from rabbitbot.robots.task_manager import get_task_manager, ConflictStrategy
from rabbitbot.provider import get_vln
from rabbitbot.prompts import get_prompt_provider

from typing import Union, List, Optional, Dict
from functools import partial
import os
import time
import threading
import ast


@register_tool('go_to')
class GoTo(BaseTool):
    _pp = get_prompt_provider('go_to')
    description = _pp.description
    parameters = [
        {
            'name': 'location',
            'type': 'string',
            'description': _pp.param_location,
            'required': True
        },
        # TODO: use default strategy for now. uncomment after prompt engineering
        # {
        #     'name': 'conflict_strategy',
        #     'type': 'string',
        #     'description': 'How to handle conflicts: discard, queue, or force',
        #     'required': False,
        #     'enum': ['discard', 'queue', 'force']
        # }
    ]

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        params = self._verify_json_format_args(params)
        task_manager = get_task_manager('movement')

        # if 'conflict_strategy' in params:
        #     strategy = ConflictStrategy(params['conflict_strategy'])
        #     get_movement_manager().set_strategy(strategy)

        # cmu_robot = get_robot()
        # if params['location'] not in cmu_robot.get_all_locations():
        #     return self._pp.return_message_not_in_map

        result = {'ret_val': None}
        event = task_manager.submit_request(
            partial(self._call, params),
            result,
        )
        if event is None:
            return self._pp.return_message_discarded
        event.wait()
        if result['ret_val'] is None:
            return self._pp.return_message_failed
        return result['ret_val']

    def _call(self, params: dict, cancellation: threading.Event) -> bool:
        cmu_robot = get_robot()
        point = ast.literal_eval(params['location'])
        point = (point[0], point[1], 0)
        if cmu_robot.go_to(point=point):
            # cmu_robot.set_location(params['location'])
            return self._pp.return_message_success
        else :
            return self._pp.return_message_failed


@register_tool('dynamic_navigation')
class DynamicNavigation(BaseToolWithFileAccess):
    _pp = get_prompt_provider('dynamic_navigation')
    description = _pp.description
    parameters = [
        {
            'name': 'task',
            'type': 'string',
            'description': _pp.param_task,
            'required': True
        },
        # {
        #     'name': 'conflict_strategy',
        #     'type': 'string',
        #     'description': 'How to handle conflicts: discard, queue, or force',
        #     'required': False,
        #     'enum': ['discard', 'queue', 'force']
        # }
    ]

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.vln = get_vln()
        self.do_async = self.cfg.get('do_async', False)
        self.frame_size = self.cfg.get('frame_size', (960, 540))
        self.crop_ratio = self.cfg.get('crop_ratio', 0.95)

    def crop_and_resize(self, image):
        h, w, _ = image.shape
        start_y = int(h * (1 - self.crop_ratio) // 2)
        start_x = int(w * (1 - self.crop_ratio) // 2)
        cropped_image = image[start_y:h-start_y, start_x:w-start_x]
        image = cv2.resize(cropped_image, (w, h))
        return image

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        params = self._verify_json_format_args(params)
        task_manager = get_task_manager('movement', strategy=ConflictStrategy.QUEUE)

        # if 'conflict_strategy' in params:
        #     strategy = ConflictStrategy(params['conflict_strategy'])
        #     get_movement_manager().set_strategy(strategy)

        result = {'ret_val': None}
        event = task_manager.submit_request(
            partial(self._call, params),
            result,
        )
        if event is None:
            return self._pp.return_message_discarded
        event.wait()
        if result['ret_val'] is None:
            return self._pp.return_message_failed
        return result['ret_val']

    def _call(self, params: dict, cancellation: threading.Event):
        os.makedirs(self.work_dir, exist_ok=True)
        params = self._verify_json_format_args(params)
        self.vln.reset()

        cmu_robot = get_robot()
        image = cmu_robot.view_2d(output_size=self.frame_size)
        while not cancellation.is_set():
            image_path = os.path.join(self.work_dir, 'navi.png')
            cv2.imwrite(image_path, image)
            action = self.vln.act(image_path, params['task'])

            logger.info(action.name)
            if action == MoveType.STOP:
                cmu_robot.move_with_joystick(action, blocking=not self.do_async)
                break

            if not self.do_async:
                cmu_robot.move_with_joystick(action, blocking=True)
                image = cmu_robot.view_2d(output_size=self.frame_size)
            else:
                cmu_robot.move_with_joystick(action, blocking=False)
                if action == MoveType.FORWARD:
                    image = cmu_robot.view_2d(output_size=self.frame_size)
                    # Forward prediction
                    image = self.crop_and_resize(image)
                else:
                    rotation = cmu_robot.rotate_step if action == MoveType.RIGHT else -cmu_robot.rotate_step
                    # Rotate prediction
                    image = cmu_robot.view_2d(yaw=rotation, output_size=self.frame_size)

        return self._pp.return_message


@register_tool('kuavo_dynamic_navigation')
class KuavoDynamicNavigation(BaseToolWithFileAccess):
    _pp = get_prompt_provider('dynamic_navigation')
    description = _pp.description
    parameters = [
        {
            'name': 'task',
            'type': 'string',
            'description': _pp.param_task,
            'required': True
        },
        # {
        #     'name': 'conflict_strategy',
        #     'type': 'string',
        #     'description': 'How to handle conflicts: discard, queue, or force',
        #     'required': False,
        #     'enum': ['discard', 'queue', 'force']
        # }
    ]

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.vln = get_vln()
        self.do_async = self.cfg.get('do_async', False)
        self.frame_size = self.cfg.get('frame_size', (960, 540))
        self.crop_ratio = self.cfg.get('crop_ratio', 0.95)

    def crop_and_resize(self, image):
        h, w, _ = image.shape
        start_y = int(h * (1 - self.crop_ratio) // 2)
        start_x = int(w * (1 - self.crop_ratio) // 2)
        cropped_image = image[start_y:h-start_y, start_x:w-start_x]
        image = cv2.resize(cropped_image, (w, h))
        return image

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        params = self._verify_json_format_args(params)
        task_manager = get_task_manager('movement', strategy=ConflictStrategy.QUEUE)

        # if 'conflict_strategy' in params:
        #     strategy = ConflictStrategy(params['conflict_strategy'])
        #     get_movement_manager().set_strategy(strategy)

        result = {'ret_val': None}
        event = task_manager.submit_request(
            partial(self._call, params),
            result,
        )
        if event is None:
            return self._pp.return_message_discarded
        event.wait()
        if result['ret_val'] is None:
            return self._pp.return_message_failed
        return result['ret_val']

    def _call(self, params: dict, cancellation: threading.Event):
        os.makedirs(self.work_dir, exist_ok=True)
        params = self._verify_json_format_args(params)
        tts_engine = params.get("tts_engine")
        assert tts_engine is not None
        self.vln.reset()

        robot = get_robot(robot_type="kuavo")
        image = robot.view_2d(output_size=self.frame_size)
        while not cancellation.is_set():
            #proj_dir = "/root/rabbitbot/"
            image_path = os.path.join(self.work_dir, 'navi.png')
            print(f"KuavoDynamicNavigation: Write image (path={image_path})")
            cv2.imwrite(image_path, image)
            action = self.vln.act(image_path, params['task'])
            print(f"KuavoDynamicNavigation: Get action (action={action})")
            #import pdb; pdb.set_trace()

            if action == MoveType.FORWARD:
                tts_engine.sound("，，前进")
            elif action == MoveType.LEFT:
                tts_engine.sound("，，向左转")
            elif action == MoveType.RIGHT:
                tts_engine.sound("，，向右转")
            else:
                tts_engine.sound("，，已到达")

            logger.info(action.name)
            if action == MoveType.STOP:
                break

            if not self.do_async:
                robot.jazzy_control_sync(action)
                image = robot.view_2d(output_size=self.frame_size)
                pass
            else:
                robot.jazzy_control(action)
                if action == MoveType.FORWARD:
                    image = robot.view_2d(output_size=self.frame_size)
                    # Forward prediction
                    image = self.crop_and_resize(image)
                else:
                    rotation = robot.rotate_step if action == MoveType.RIGHT else -robot.rotate_step
                    # Rotate prediction
                    image = robot.view_2d(yaw=rotation, output_size=self.frame_size)

        return self._pp.return_message


class MovementControl(BaseTool):
    """leave this class for future use , as a placeholder for movement control commands"""
    description = "Control robot movement system"
    parameters = [
        {
            'name': 'command',
            'type': 'string',
            'description': 'Control command: status, clear_queue, set_strategy',
            'required': True,
            'enum': ['status', 'clear_queue', 'set_strategy']
        },
        {
            'name': 'strategy',
            'type': 'string',
            'description': 'Strategy for set_strategy command',
            'required': False,
            'enum': ['discard', 'queue', 'force']
        }
    ]

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        params = self._verify_json_format_args(params)
        movement_manager = get_task_manager()

        if params['command'] == 'status':
            status = movement_manager.get_status()
            return f"request queue status: {status}"

        elif params['command'] == 'clear_queue':
            movement_manager.clear_queue()
            return "request queue has been cleared"

        elif params['command'] == 'set_strategy':
            if 'strategy' not in params:
                return "we need a strategy to set, please provide one"
            strategy = ConflictStrategy(params['strategy'])
            movement_manager.set_strategy(strategy)
            return f"conflict strategy has been set to: {strategy.value}"

        return "unknown command, please use status, clear_queue, or set_strategy"
