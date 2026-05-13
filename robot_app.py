
import os
from typing import Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import JSONResponse
from rabbitbot.robots import create_robot
from rabbitbot.robots.constants import MoveType, NavigationStatus
import ast
import tempfile
import traceback
import logging
import json
import time
from datetime import datetime
import requests
from urllib.parse import urljoin
from requests.exceptions import Timeout


enable_into_tts = False

app = FastAPI()


def _robot_app_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _robot_app_elapsed(start_time):
    return f"{time.perf_counter() - start_time:.3f}s"


class NavigationQuery(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.status = NavigationStatus.PENDING

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status


class TTSAgent:
    def __init__(self, host_url):
        print(f"TTSAgent: host_url {host_url}")
        self.host_url = host_url

    def run(self, input_dict_str: str) -> str:
        data = {"task": input_dict_str}
        try:
            resp = requests.post(urljoin(self.host_url, 'exec'), data=data, timeout=10)
            resp_dict = json.loads(resp.text)
            return resp_dict['out_text']
        except Timeout:
            print('TTSAgent: Timeout')
        except Exception as exc:
            print(f'TTSAgent: request failed: {exc}')
        return ""


def create_tts_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_TTS_AGENT_URL', 'http://127.0.0.1:8001')
    return TTSAgent(host_url)


def tts_sound(tts_agent, text, lang):
    input_dict = {"task": "text_to_speech", "lang": lang, "text": text, "timeout": 30}
    print(input_dict)
    tts_index = tts_agent.run(json.dumps(input_dict))
    return int(tts_index) if tts_index else -1


tts_agent = create_tts_agent()
if enable_into_tts:
    #tts_sound(tts_agent, "，，夸父机器人屁四二八控制模块加载完毕", "zh")
    tts_sound(tts_agent, "，，夸父机器人劈 4 2 8 控制模块加载完毕", "zh")

with open('kuavo_configs.json', 'r', encoding='utf-8') as file:
    config = json.load(file)
    enable_ros = config["kuavo_robot_ros"]
    enable_vln = config["kuavo_robot_vln"]
    camera_type = (os.getenv("RABBITBOT_ROBOT_CAMERA") or config["kuavo_robot_camera"]).strip().lower()
    enable_ros = True if enable_ros == "enable" else False
    enable_vln = True if enable_vln == "enable" else False

if camera_type not in {"gemini", "null"}:
    raise ValueError(f"Unsupported RABBITBOT_ROBOT_CAMERA/kuavo_robot_camera: {camera_type}")
print(f"robot_app camera_type: {camera_type}")

workspace = "workspace"
robot_kwargs = {"robot_type": 'kuavo',
                "anolog_stick_factor": 0.5,
                "camera_types": [camera_type],
                "enable_ros": enable_ros,
                "enable_vln": enable_vln,}

if enable_into_tts:
    if robot_kwargs["enable_ros"]:
        tts_sound(tts_agent, "，，已经开启”哀欧哀思“控制，请注意", "zh")
    else:
        tts_sound(tts_agent, "，，尚未开启”哀欧哀思“控制，请放心测试", "zh")

    # if robot_kwargs["enable_vln"]:
    #     tts_sound(tts_agent, "，，已经开启“威阿恩“动态导航，请注意", "zh")
    # else:
    #     tts_sound(tts_agent, "，，尚未开启“威阿恩“动态导航，请放心测试", "zh")

    camera_name = {
        "gemini": "基米奶",
        "null": "未连接",
    }.get(robot_kwargs['camera_types'][0], "未连接")
    tts_sound(tts_agent, f"，，相机：{camera_name}", "zh")

robot = create_robot(
    image_buffer_dir=os.path.join(workspace, 'robot'),
    **robot_kwargs,
)

navi_query = NavigationQuery()

robot.start()

print("Kuavo robot started!")

robot_app_configs = {"disable_go_to_func": False}


@app.post("/go_to_async")
async def go_to_async_api(task: str = Form(...)):
    try:
        print("===== go_to_async =====")
        print(f"Get data")
        print(task)
        point = ast.literal_eval(task)
        print(f"Go to: {point}")
        navi_query.reset()
        #robot.go_to_async(point=point, query=navi_query)
        if not robot_app_configs['disable_go_to_func']:
            await robot.go_to(point=point, query=navi_query)
        else:
            await robot.go_to_fake(point=point, query=navi_query)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/go_to_status")
async def go_to_status_api(task: str = Form(...)):
    try:
        print("===== go_to_status =====")
        print(f"Get data")
        print(task)
        print(f"Query go to status")
        status = navi_query.get_status()
        print(status)
        debug_status = robot.get_navigation_debug_status()

        return JSONResponse(content={"status": str(status.value), **debug_status})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/reset_go_to_status")
async def reset_go_to_status_api(task: str = Form(...)):
    try:
        print("===== reset_go_to_status =====")
        print(f"Get data")
        print(task)
        print(f"Reset go to status")
        navi_query.reset()
        status = navi_query.get_status()

        return JSONResponse(content={"status": str(status.value)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_arm_async")
async def do_arm_async_api(task: str = Form(...)):
    request_start = time.perf_counter()
    timing = {
        "http_api_received_at": _robot_app_timestamp(),
    }
    try:
        print("===== do_arm_async =====")
        print(f"Get data")
        print(task)
        action_name = task
        print(f"Do arm: {action_name}")
        timing["before_robot_do_arm_at"] = _robot_app_timestamp()
        result = robot.do_arm(action_name)
        timing["after_robot_do_arm_at"] = _robot_app_timestamp()
        timing["robot_do_arm_elapsed"] = _robot_app_elapsed(request_start)
        if result is None:
            result = {"success": True, "message": ""}
        if isinstance(result, dict):
            result["robot_agent_timing"] = timing
        return JSONResponse(content=result)

    except Exception as e:
        timing["exception_at"] = _robot_app_timestamp()
        timing["total_elapsed"] = _robot_app_elapsed(request_start)
        return JSONResponse(content={"error": str(e), "robot_agent_timing": timing}, status_code=500)


@app.post("/do_head_async")
async def do_head_async_api(task: str = Form(...)):
    try:
        print("===== do_head_async =====")
        print(f"Get data")
        print(task)
        yaw, pitch = ast.literal_eval(task)
        print(f"Do head: yaw {yaw}, pitch {pitch}")
        robot.do_head(yaw, pitch)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_finger_async")
async def do_finger_async_api(task: str = Form(...)):
    try:
        print("===== do_finger_async =====")
        print(f"Get data")
        print(task)
        x, y, z = ast.literal_eval(task)
        print(f"Do finger: x {x}, y {y}, z {z}")
        robot.do_finger(x, y, z)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_finger_status_async")
async def do_finger_status_async_api(task: str = Form(...)):
    try:
        print("===== do_finger_status_async =====")
        print(f"Get data")
        print(task)
        status = robot.do_finger_status()

        return JSONResponse(content={"status": str(status)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_grab_status_async")
async def do_grab_status_async_api(task: str = Form(...)):
    try:
        print("===== do_grab_status_async =====")
        print(f"Get data")
        print(task)
        status = robot.do_grab_status()

        return JSONResponse(content={"status": str(status)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_handshake_async")
async def do_handshake_async_api(task: str = Form(...)):
    try:
        print("===== do_handshake_async =====")
        print(f"Get data")
        print(task)
        x, y, z = ast.literal_eval(task)
        print(f"Do handshake: x {x}, y {y}, z {z}")
        robot.do_handshake(x, y, z)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_grab_async")
async def do_grab_async_api(task: str = Form(...)):
    try:
        print("===== do_grab_async =====")
        print(f"Get data")
        print(task)
        x, y, z = ast.literal_eval(task)
        print(f"Do grab: x {x}, y {y}, z {z}")
        robot.do_grab(x, y, z)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/do_grab_cancel_async")
async def do_grab_cancel_async_api(task: str = Form(...)):
    try:
        print("===== do_grab_cancel_async =====")
        print(f"Get data")
        print(task)
        print(f"Do grab cancel: True")
        robot.do_grab_cancel()

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/get_camera_info")
async def get_camera_info_api(task: str = Form(...)):
    try:
        print("===== get_camera_info =====")
        print(f"Get data")
        print(task)
        task = ast.literal_eval(task)
        info_type = task["info_type"]
        if "params" in task:
            params = task["params"]
            print(params)
        try:
            if info_type == "view_2d":
                frame_size = params["frame_size"]
                image = robot.view_2d(output_size=frame_size)
                output = image.tolist()
            elif info_type == "depth_frame":
                depth = robot.get_depth_camera().get_depth_frame()
                output = depth.tolist()
            elif info_type == "real_depth":
                depth = float(params["depth"])
                print("depth:", depth)
                real_depth = robot.get_depth_camera().get_real_depth(depth)
                output = real_depth
            elif info_type == "hfov":
                hfov = robot.get_depth_camera().hfov
                output = hfov
            elif info_type == "get_location":
                text = params["text"]
                location = robot.get_depth_camera().get_location(text)
                output = str(location)
            elif info_type == "detect_key_point_pixel":
                location = robot.get_depth_camera().detect_key_point_pixel()
                output = str(location)
            elif info_type == "detect_hand_location":
                location = robot.get_depth_camera().detect_hand_location()
                output = str(location)
            elif info_type == "start_record":
                robot.get_depth_camera().start_record()
                output = "start_recorded"
            elif info_type == "stop_record":
                robot.get_depth_camera().stop_record()
                output = "stop_recorded: "
        except Exception:
            traceback.print_exc()
            raise

        return JSONResponse(content={"output": output})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/vln")
async def vln_api(task: str = Form(...)):
    try:
        print("===== vln =====")
        print(f"Get data")
        print(task)
        print(f"VLN: task {task}")
        robot.vln(task, tts_agent)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/move")
async def move_api(task: str = Form(...)):
    try:
        print("===== move =====")
        print(f"Get data")
        print(task)
        print(f"Move: task {task}")
        action_idx = int(task)
        action = MoveType(action_idx)
        robot.jazzy_control_sync(action)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/view")
async def view_api(task: str = Form(...)):
    try:
        print("===== view =====")
        print(f"Get data")
        print(task)
        output = robot.view(task)

        return JSONResponse(content={"output": str(output)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("未捕获的异步异常：")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


def test_vln():
    tts_sound(tts_agent, "，，准备开始动态导航单元测试，请注意", "zh")
    tts_sound(tts_agent, "，，目标是寻找穿着紫色衣服的人", "zh")
    input("请按回车键开启动态导航单元测试")
    task = "Walk to the person in purple and then stop."
    robot.vln(task, tts_agent)


def test_view():
    task = "请告诉我桌面上有什么？"
    output = robot.view(task)
    print(output)


if __name__ == '__main__':
    test_view()
