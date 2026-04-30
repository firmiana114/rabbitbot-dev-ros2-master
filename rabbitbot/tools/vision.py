from qwen_agent.tools.base import BaseToolWithFileAccess, register_tool
from qwen_agent.llm.schema import ContentItem

from typing import Union, List, Optional, Dict
import os

import cv2

from rabbitbot.robots import get_robot
from rabbitbot.prompts import get_prompt_provider


@register_tool('view')
class View(BaseToolWithFileAccess):
    _pp = get_prompt_provider('view')
    description = _pp.description
    parameters = [
    ]

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.frame_size = self.cfg.get('frame_size', (1080, 720))

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        super().call(params=params, files=files)
        os.makedirs(self.work_dir, exist_ok=True)
        cmu_robot = get_robot()
        image = cmu_robot.view_2d(**cmu_robot.get_rotation(), output_size=self.frame_size)
        image_path = os.path.abspath(os.path.join(self.work_dir, 'view.png'))
        cv2.imwrite(image_path, image)

        return [
            ContentItem(image=image_path),
            ContentItem(text=self._pp.return_message.format(image_path=image_path)),
        ]
