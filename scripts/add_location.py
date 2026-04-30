from rabbitbot.robots import get_robot
from argparse import ArgumentParser

import json
import os


if __name__ == "__main__":
    parser = ArgumentParser(description="Add a new location to the robot's map")
    parser.add_argument("name", type=str, help="Name of the location")
    parser.add_argument("--map_file", type=str, help="Path to the map file", default="")
    args = parser.parse_args()

    with get_robot(use_360_camera=True) as robot:
        point = robot.get_point()
        map = robot.map_data
        map[args.name] = point
        map_file = args.map_file or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'robots', 'map.json')
        with open(args.map_file, 'w') as f:
            json.dump(map, f, indent=4, ensure_ascii=False)
