from qwen_agent.llm.schema import Message, ROLE, SYSTEM, CONTENT
from typing import List
from rabbitbot.robots import get_robot


def prepend_system_message(messages: List[Message], system_message: str, **kwargs):
    robot = get_robot()
    system_message = system_message.format(
        all_locations=', '.join(robot.get_all_locations()),
        location=robot.get_location(),
        **kwargs,
    )
    if messages and messages[0][ROLE] == SYSTEM:
        messages[0][CONTENT] = system_message
    else:
        messages.insert(0, Message(SYSTEM, system_message))
