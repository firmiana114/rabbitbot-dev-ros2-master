import os
import requests
import cv2
from unittest.mock import patch

from rabbitbot.robots.constants import MoveType
from rabbitbot.robots import get_robot
from rabbitbot.provider import get_vln

RESOURCE_DIR = os.path.join(os.path.dirname(__file__), 'resources')


def patch_bot(bot_cfg: dict = None):
    robot = get_robot()
    bot_default_cfg = {
        'view_2d.return_value': cv2.imread(os.path.join(RESOURCE_DIR, 'frig.jpg')),
        'start_record.return_value': None,
        'stop_record.return_value': None,
        'start.return_value': None,
        'stop.return_value': None,
        'go_to.return_value': True,
        'move_with_joystick.return_value': None,
    }
    if bot_cfg is not None:
        bot_default_cfg.update(bot_cfg)
    return patch('rabbitbot.robots.cmu_auto.CMUAutonomyBot', spec=True, wraps=robot, **bot_default_cfg)


def patch_vln():
    vln_default_cfg = {
        'act.return_value': MoveType.STOP,
    }
    return patch('rabbitbot.provider.VLNAgent', spec=True, **vln_default_cfg)


def is_vln_available():
    vln = get_vln()
    try:
        vln.reset()
    except requests.ConnectionError:
        return False
    return True
