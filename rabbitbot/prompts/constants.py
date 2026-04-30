from .register import register_prompt_provider

from dataclasses import dataclass


@register_prompt_provider
@dataclass(init=False, frozen=True)
class ViewPrompt:
    name = 'view'
    description = '摄像头：查看机器人摄像头，得到所在场景的图片。'
    return_message = '''(身前图片的URL是 {image_path})'''


@register_prompt_provider
@dataclass(init=False, frozen=True)
class GoToPrompt:
    name = 'go_to'
    description = '导航：使机器人自动前往一个坐标'
    param_location = '坐标，以 "x,y" 的形式'
    return_message_success = '''已到达'''
    return_message_failed = '该地点无法到达'
    return_message_not_in_map = '该地点不在地图中'
    return_message_discarded = '请求被丢弃，机器人正在处理其他移动任务'


@register_prompt_provider
@dataclass(init=False, frozen=True)
class DynamicNavigationPrompt:
    name = 'dynamic_navigation'
    description = '动态导航：使机器人完成一个动态的导航任务。例如，前往某个东西前方，向前走到垃圾桶，等等，可以不在地图中'
    param_task = '任务描述(英文)'
    return_message = '已到达'
    return_message_failed = '导航失败'
    return_message_discarded = '请求被丢弃，机器人正在处理其他移动任务'


@register_prompt_provider
@dataclass(init=False, frozen=True)
class BrainPrompt:
    name = 'brain'
    complete_message = '任务完成'
    system_message = '''你是一个负责完成用户指令的机器人的大脑。遵循以下要求：
- 请计划下一步计划
- 每次只计划一步
- 只将计划内容以文本输出
- 你只具有导航/移动/定位功能和视觉功能，分别对应以下计划格式：
    - 前往任意物品
    - 进行任意移动动作，通过提取用户指令中移动相关的部分获得，例如"前往走廊尽头并左转"等等
    - 查看xxx
- 只能以以上计划格式输出内容
- 如果你认为已经完成用户指令{command}的所有内容，请直接回答"''' + complete_message + '''"
'''


@register_prompt_provider
@dataclass(init=False, frozen=True)
class MapPrompt:
    name = 'navigation'
    description = '完成任意移动任务'
    system_message = '''你是一个导航Agent，根据用户指令完成移动任务。
根据地图记录，和用户指令可能相关物品有: {entities}。
- 如果你认为相关物品很匹配用户指令，请调用go_to前往该物品。
- 如果你认为相关物品不匹配用户指令，请调用dynamic_navigation完成任务。
'''


@register_prompt_provider
@dataclass(init=False, frozen=True)
class VisionPrompt:
    name = 'vision'
    description = '查看机器人摄像头获取当前机器人视觉图像，调用前请确保面向目标'


@register_prompt_provider
@dataclass(init=False, frozen=True)
class MemoryMapPrompt:
    name = 'memorymap'
    description = '将机器人周围所有实体录入记忆中'
    system_message = """你是一名基于视觉的信息提取和目标检测专家。你的任务是分析一系列帧并提取**所有可见物品**并提取**物品的边界框**。请按照以下步骤逐步操作，并确保输出严格遵循指定的JSON格式。
---
### 步骤1：提取可见物品
1. 尽可能识别帧中**所有独特、可见且详细的物品**，例如：
    - 人类、动物、物体、文本元素或任何其他视觉上可区分的物品。
    - 如果同一物品类型有多个实例且实例之间有明显区别，将它们视为不相同的物品。
    - 不需要输出地板、墙壁、天花板等背景物体。
2. 对每个实体进行**简要描述**，要求简明流畅，包括：
    - 物理属性（如：大小、形状、颜色、材质等）。
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
}
"""
    system_message_bbox = """你是一名基于目标检测专家。你的任务是分析一个帧并提取**以下JSON文本中描述的物品的边界框**。请按照以下步骤逐步操作，并确保输出严格遵循指定的JSON格式。
---
### 步骤1：检测目标
检测当前帧内是否存在JSON中描述的物品。如果存在，则返回True，否则返回False。
---

### 步骤2：检测目标
检测当前帧内存在的物品，并返回边界框的坐标。

### 步骤3：返回结构化输出
以以下**JSON格式**输出目标的边界框，entity_name和entity_description是步骤1中提取的物品名称和描述：
如果步骤1中检测到目标，则返回步骤2中检测到的边界框的坐标，否则返回空列表。
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
}
"""
    return_message = '已录入记忆'
