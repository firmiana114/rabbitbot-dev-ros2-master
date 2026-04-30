from openai import OpenAI

import cv2
import base64
from io import BytesIO
from textwrap import dedent


instructions = dedent("""\
    你是一名基于视觉的信息提取和目标检测专家。你的任务是分析一系列帧并提取**所有可见物品**并提取**物品的边界框**。请按照以下步骤逐步操作，并确保输出严格遵循指定的JSON格式。
    ---
    ### 步骤1：提取可见物品
    1. 尽可能识别帧中**所有独特、可见且详细的物品**，例如：
        - 人类、动物、物体、文本元素或任何其他视觉上可区分的物品。
        - 如果同一物品类型有多个实例且实例之间有明显区别，将它们视为不相同的物品。
        - 不需要输出地板、墙壁、天花板等背景物体。
    2. 对每个实体进行**简要描述**，要求简明流畅，包括：
        - 物理属性（如：大小、形状、颜色、材质等）。
        - 画面中的位置
    3. 检测到可见物体的边界框的坐标。
    ---

    ### 步骤2：返回结构化输出
    以以下**JSON格式**输出提取的信息。如果未找到实体或关系，则为相应字段返回空列表：

    ```json
    {
        "Entities": [
        {
            "Entity_name": "[物品名称]",
            "Entity_description": "[物品描述]",
            "Entity_bbox": "[物品边界框]",
        },
        ...
        ],
    }""")

instructions_vision_memory = dedent("""\
    你是一名专业的视觉目标匹配和定位专家。你的任务是提取**需要匹配的物品的边界框**，需要匹配的物品描述是：[一个黑色的盒子]。
    以以下**JSON格式**输出提取的信息。如果未找到实体或关系，则为相应字段返回空列表：
    ```json
    {
        "Entity_bbox": "[物品边界框]",
    }
    ```
    """)


class GroundingVLMOpenAI:

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.prompt = instructions_vision_memory

    def prepare_video_message_for_vllm(self, images: list):
        # TODO: encode images as base64 video
        base64_frames = []
        for image in images:
            output_buffer = BytesIO()
            _, buffer = cv2.imencode('.jpg', image)
            output_buffer.write(buffer)
            byte_data = output_buffer.getvalue()
            base64_str = base64.b64encode(byte_data).decode("utf-8")
            base64_frames.append(base64_str)
        video_message = {
            "type": "video_url",
            "video_url": {
                "url": f"data:video/jpeg;base64,{','.join(base64_frames)}"
            },
        }
        return [{
            "role": "user",
            "content": [video_message] + [{"type": "text", "text": self.prompt}],
        }], {"fps": [1]}

    def prepare_message_for_vllm(self, images):
        image_contents = []
        for image in images:
            _, buffer = cv2.imencode('.jpg', image)
            encoded_image = base64.b64encode(buffer).decode('utf-8')
            base64_qwen = f"data:image;base64,{encoded_image}"
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": base64_qwen
                },
            })
        return [{
            "role": "user",
            "content": image_contents + [{"type": "text", "text": self.prompt}],
        }], {"fps": [1]}

    def prepare_correction_text_message_for_vllm(self, text):
        prompt = dedent(f"""\
            用户描述通常去寻找以下物品之一：{{红色把手的白色篮子；圆柱状黑色电子零件，底座是黑色的上面放有一个芯片；黑色的机器人腿部，长条状黑色；银色金属材质的架子；白色的篮子，有木制把手}}。请根据这些物品的描述，纠正用户输入的语音文字并匹配到相关物体。
            用户输入：{text}
            请直接输出纠正后的简短的物品描述。
            """)
        return [{
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }]

    def get_chat_response(self, messages, extra_body):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            extra_body=extra_body,
            stream=True,
        )
        stream_message = ""
        for chunk in response:
            try:
                stream_message += chunk.choices[0].delta.content
                print(chunk.choices[0].delta.content, end='')
            except AttributeError as e:
                if "'str' object has no attribute 'choices'" in str(e):
                    pass
                else:
                    raise
            # yield stream_message
        return stream_message


class GeneralVLMOpenAI:

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.prompt = instructions_vision_memory

    def prepare_message_for_vllm(self, images, prompt):
        image_contents = []
        for image in images:
            _, buffer = cv2.imencode('.jpg', image)
            encoded_image = base64.b64encode(buffer).decode('utf-8')
            base64_qwen = f"data:image;base64,{encoded_image}"
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": base64_qwen
                },
            })
        return [{
            "role": "user",
            "content": image_contents + [{"type": "text", "text": prompt}],
        }], {"fps": [1]}

    def get_chat_response(self, messages, extra_body):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            extra_body=extra_body,
            stream=True,
        )
        stream_message = ""
        for chunk in response:
            try:
                stream_message += chunk.choices[0].delta.content
                print(chunk.choices[0].delta.content, end='')
            except AttributeError as e:
                if "'str' object has no attribute 'choices'" in str(e):
                    pass
                else:
                    raise
            # yield stream_message
        return stream_message