
import time
import asyncio
import argparse
from rabbitbot.context import AppContext
from rabbitbot.provider import create_memory_layer


async def test_slam():
    memory = create_memory_layer()
    name = "起点"
    entity_list = await memory.query(name, "")
    entity = entity_list[0]
    print("entity:", entity.name)
    location = entity.attributes.get('location', '')
    print("location:", location)

    robot_kwargs = {
        "robot_type": 'agi_g2',
        "anolog_stick_factor": 0.5
    }
    async with AppContext(robot_kwargs) as ctx:
        time.sleep(1.0)
        robot = ctx.robot
        x, y, z, ox, oy, oz, ow = location
        input("Press ENTER to go to")
        location = await robot.go_to_async(x, y, z, ox, oy, oz, ow)


async def main(args):
    await test_slam()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run RabbitBot workflow example.')
    parser.add_argument('--patch', action='store_true', help='Enable patching for bot and VLN agent.')
    args = parser.parse_args()
    asyncio.run(main(args))
