
import os
import time
import asyncio
import argparse
from rabbitbot.context import AppContext


async def test_vln():
    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs) as ctx:
        time.sleep(1.0)
        ctx.vln.reset()
        task = "Walk to the person in purple and then stop"
        workspace_dir = "workspace/tools/navigation_tools"
        image_path = os.path.join(workspace_dir, 'navi.png')
        print(f"task: {task}")
        print(f"image_path: {image_path}")
        action = ctx.vln.act(image_path, task)
        print(f"action: {action}")


async def main(args):
    await test_vln()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run RabbitBot workflow example.')
    parser.add_argument('--patch', action='store_true', help='Enable patching for bot and VLN agent.')
    args = parser.parse_args()
    asyncio.run(main(args))
