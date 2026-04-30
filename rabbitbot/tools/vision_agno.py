
import os
import cv2
import json
import time
import base64
from typing import Any
from uuid import uuid4

from .base_agno import BaseToolkit

from agno.agent import Agent
from agno.media import Image, ImageArtifact


class VisionToolkit(BaseToolkit):
    """
    A toolkit for viewing images from the robot's camera.
    This toolkit provides a method to capture images from the robot's vision.
    """

    def __init__(self, ctx: Any, frame_size: tuple = (1080, 720), **kwargs):
        self.frame_size = frame_size
        tools = [self.capture_image]
        super().__init__(ctx, name='vision_tools', tools=tools, **kwargs)

    def capture_image(self, agent: Agent) -> str:
        """Capture an image from the robot's camera."""
        robot = self.ctx.robot
        image = robot.view_2d(**robot.get_rotation(), output_size=self.frame_size)
        # base64 encode the numpy array image
        _, image = cv2.imencode(".png", image)
        image = image.tobytes()
        base64_encoded_image = base64.b64encode(image)

        agent.add_image(ImageArtifact(
            id=str(uuid4()),
            content=base64_encoded_image,
            original_prompt="Captured image of robot's camera",
            mime_type="image/png",
        ))

        return 'Captured successfully.'

    def detect(self, agent, image_path=None, last_detect_text=None):
        if image_path is None:
            robot = self.ctx.robot
            image = robot.view_2d(output_size=self.frame_size)
            depth_frame = self.ctx.robot.get_depth_frame()
            image_filename = "object.png"
            image_path = os.path.join(self.workspace, image_filename)
            cv2.imwrite(image_path, image)

        imgs = []
        if isinstance(image_path, list):
            for img_path in image_path:
                img = Image(id=str(uuid4()), filepath=img_path)
                imgs.append(img)
        elif isinstance(image_path, str):
            img = Image(id=str(uuid4()), filepath=image_path)
            imgs = [img]

        if last_detect_text is not None:
            text = f"\n上一次的检测结果为：\n{last_detect_text}"
        else:
            text = ""
        #text = f"请根据图像分析需求："
        #agent.print_response(text, images=[img])
        print(f"in_text: {text}")
        start_time = time.time()
        response_stream = agent.run(text, images=imgs, stream=False, stream_intermediate_steps=True)
        out_text = response_stream.content
        # print(response_stream.content)
        # for event in response_stream:
        #     if event.event == "RunResponseContent":
        #         #print(f"Content: {event.content}")
        #         out_text += event.content  # type: ignore
        #         agent_time = time.time() - start_time
        #         print(f"out_text: {out_text}")
        #         print(f"out_text_len: {len(out_text)}")
        #         print(f"agent_time: {agent_time:.3f}")
        #     elif event.event == "ToolCallStarted":
        #         print(f"Tool call started: {event.tool}")  # type: ignore
        #     elif event.event == "ReasoningStep":
        #         print(f"Reasoning step: {event.content}")
        #     if out_text.endswith("]"):
        #         break
        agent_time = time.time() - start_time

        entity_bbox = []
        real_depth = 0.0
        if out_text is not None and len(out_text) > 2:
            if out_text.startswith("["):
                if not out_text.startswith("[["):
                    out_text = f"[{out_text}]"
                bboxes = json.loads(out_text)
                for bbox in bboxes:
                    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                    new_image = cv2.imread(image_path)
                    cv2.rectangle(new_image, (x1, y1), (x2, y2), (0, 255, 0), 2)  # type: ignore
                    cv2.putText(new_image, f'Entity', (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)  # type: ignore
                    image_filename = "entity.png"
                    image_path = os.path.join(self.workspace, image_filename)
                    cv2.imwrite(image_path, new_image)  # type: ignore
                    print(f"已保存新图像：{image_path}")

        print(f"agent_time {agent_time:.3f}")
        return out_text
