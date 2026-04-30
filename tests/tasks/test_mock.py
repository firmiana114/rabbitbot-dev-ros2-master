import unittest
import numpy as np

from rabbitbot.provider import get_vln
from rabbitbot.robots.constants import MoveType
from rabbitbot.robots import cmu_auto

from .utils import patch_vln, patch_bot


class MockTestCase(unittest.TestCase):

    def test_mock_vln(self):
        with patch_vln():
            vln = get_vln()
            self.assertEqual(vln.act('', ''), MoveType.STOP)

    def test_mock_bot(self):
        with patch_bot():
            bot = cmu_auto.CMUAutonomyBot()
            self.assertIsInstance(bot.view_2d(), np.ndarray)
