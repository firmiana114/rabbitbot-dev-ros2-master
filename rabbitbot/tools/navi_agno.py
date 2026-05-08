from rabbitbot.robots.constants import MoveType, NavigationStatus
from .base_agno import BaseToolkit

from agno.utils.log import logger

from typing import Any
import os
import cv2


class NavigationQuery(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.status = NavigationStatus.PENDING

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status


class NavigationToolkit(BaseToolkit):
    """
    A toolkit for navigation tasks, providing tools to navigate the robot to specific locations
    or perform dynamic navigation based on task description.
    """

    def __init__(
        self,
        ctx: Any,
        do_async: bool = True,
        frame_size: tuple = (960, 540),
        crop_ratio: float = 0.95,
        **kwargs
    ):
        self.do_async = do_async
        self.frame_size = frame_size
        self.crop_ratio = crop_ratio
        tools = [self.go_to, self.dynamic_navigation, self.go_to_async]
        super().__init__(ctx, name='navigation_tools', tools=tools, **kwargs)

    def crop_and_resize(self, image):
        h, w, _ = image.shape
        start_y = int(h * (1 - self.crop_ratio) // 2)
        start_x = int(w * (1 - self.crop_ratio) // 2)
        cropped_image = image[start_y:h-start_y, start_x:w-start_x]
        image = cv2.resize(cropped_image, (w, h))
        return image

    async def go_to(self, x: float, y: float, ox: float, oy: float, oz: float, ow: float) -> str:
        """
        Navigate the robot to a specific (x, y) location.

        Args:
            x (float): The x-coordinate.
            y (float): The y-coordinate.
        """
        point = (x, y, ox, oy, oz, ow)
        if self.ctx.robot.go_to(point=point):
            return 'Navigation to ({}, {}) successful.'.format(x, y)
        else :
            return 'Navigation to ({}, {}) failed.'.format(x, y)

    async def go_to_async(self, x: float, y: float, ox: float, oy: float, oz: float, ow: float, query: NavigationQuery, waypoints=None):
        point = waypoints if waypoints else (x, y, ox, oy, oz, ow)
        print(f"go_to_async: {point}")
        #import pdb; pdb.set_trace()
        #self.ctx.robot.go_to_async(point=point, query=query)
        #await self.ctx.robot.go_to_async(point=point, query=query)
        await self.ctx.robot.go_to_async(x, y, ox, oy, oz, ow, waypoints=waypoints)

    async def go_to_status(self):
        status = await self.ctx.robot.go_to_status()
        status = NavigationStatus(status)
        print(f"navi_status: {status}")
        return status

    async def reset_go_to_status(self):
        await self.ctx.robot.reset_go_to_status()
        return True

    async def dynamic_navigation(self, task: str) -> str:
        """
        Perform dynamic navigation based on a task description.

        Args:
            task (str): The task description for navigation.
        """
        self.ctx.vln.reset()

        robot = self.ctx.robot
        image = robot.view_2d(output_size=self.frame_size)
        while True:
            image_path = os.path.join(self.workspace, 'navi.png')
            cv2.imwrite(image_path, image)
            action = self.ctx.vln.act(image_path, task)

            logger.info(action.name)
            if action == MoveType.STOP:
                await robot.move_with_joystick(action, blocking=not self.do_async)
                break

            if not self.do_async:
                await robot.move_with_joystick(action, blocking=True)
                image = robot.view_2d(output_size=self.frame_size)
            else:
                await robot.move_with_joystick(action, blocking=False)
                if action == MoveType.FORWARD:
                    image = robot.view_2d(output_size=self.frame_size)
                    # Forward prediction
                    image = self.crop_and_resize(image)
                else:
                    rotation = robot.rotate_step if action == MoveType.RIGHT else -robot.rotate_step
                    # Rotate prediction
                    image = robot.view_2d(yaw=rotation, output_size=self.frame_size)

        return 'Dynamic navigation completed.'


async def is_navigating(navi_tools):
    status = await navi_tools.go_to_status()
    print(f"navi_status: {status}")
    return status == NavigationStatus.PENDING or status == NavigationStatus.ACTIVE
