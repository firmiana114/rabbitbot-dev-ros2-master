import unittest
import os

import cv2

from qwen_agent.llm.schema import Message

from rabbitbot.provider import compose_agents, get_llm
from .utils import patch_vln, patch_bot, is_vln_available, RESOURCE_DIR


class MemoryTestCase(unittest.TestCase):

    def test_memorize_and_navi(self):
        with patch_bot({
            'view_2d.side_effect': [
                # TODO: images
            ],
            'get_point.return_value': (0, 0, 0),
        }) as mock_bot, patch_vln() as mock_vln:
            # TODO: save fridge to map and directly find fridge through go_to
            # e.g., mock_bot.return_value.go_to.assert_called_with('冰箱')
            pass
