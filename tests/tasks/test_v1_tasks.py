import unittest
import os

import cv2
from qwen_agent.llm.schema import Message

from rabbitbot.provider import compose_agents, get_llm
from rabbitbot.robots import get_robot
from .utils import patch_vln, patch_bot, is_vln_available, RESOURCE_DIR


class NaviThingsTestCase(unittest.TestCase):

    def test_navi_still_refrig(self):
        with patch_bot(), patch_vln():
            agent = compose_agents(get_llm())
            messages = [Message('user', '去透明冰箱前面')]
            for response in agent.run(messages=messages):
                continue
            self.assertEqual(response[-1].content, '任务完成')

    @unittest.skipIf(not is_vln_available(), 'VLN Service Unavailable')
    def test_navi_moving_trash_can(self):
        pass


class MultiStepTestCase(unittest.TestCase):

    def _test_check_drinks(self, mock_bot, mock_vln):
        def _check_called_navi_refig(call_args_list: list):
            for call in call_args_list:
                task = call.kwargs.get('task', call.args[1])
                if 'fridge' in task or 'refrigerator' in task:
                    return True
            return False

        robot = mock_bot.return_value
        vln_agent = mock_vln.return_value
        agent = compose_agents(get_llm())
        messages = [Message('user', '去冰箱看看有哪些种类的饮料')]
        for response in agent.run(messages=messages):
            continue
        self.assertEqual(robot.get_location(), '水房')
        self.assertIn("牛奶", response[-2].content)
        self.assertIn("可乐", response[-2].content)
        self.assertTrue(_check_called_navi_refig(vln_agent.act.call_args_list))
        self.assertEqual(response[-1].content, '任务完成')
        return response

    def test_check_available_drinks_in_refrig(self):
        with patch_bot({
            'view_2d.return_value': cv2.imread(os.path.join(RESOURCE_DIR, 'frig.jpg')),
        }) as mock_bot, patch_vln() as mock_vln:
            self._test_check_drinks(mock_bot, mock_vln)

    def test_check_available_drinks_in_refrig_unseen(self):
        with patch_bot({
            'view_2d.side_effect': [
                cv2.imread(os.path.join(RESOURCE_DIR, 'default.jpg')),   # dynamic navi
                cv2.imread(os.path.join(RESOURCE_DIR, 'default.jpg')),   # view
                cv2.imread(os.path.join(RESOURCE_DIR, 'default.jpg')),   # dynamic navi
                cv2.imread(os.path.join(RESOURCE_DIR, 'frig.jpg')),      # view
            ]
        }) as mock_bot, patch_vln() as mock_vln:
            response = self._test_check_drinks(mock_bot, mock_vln)
            dynamic_navigation_called_times = sum(
                1 for resp in response
                if resp.name == 'dynamic_navigation'
            )
            self.assertEqual(dynamic_navigation_called_times, 2)
