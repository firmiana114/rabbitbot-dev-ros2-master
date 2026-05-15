
import os
import time
import requests
import asyncio
from urllib.parse import urljoin
from typing import Dict, Union, Optional
import ast
import json
import base64
from io import BytesIO
from datetime import datetime
import cv2
import numpy as np
from openai import OpenAI
from requests.exceptions import Timeout, RequestException

#from qwen_agent.agents import FnCallAgent
#from qwen_agent.llm import BaseChatModel
#from qwen_agent.log import logger
import logging
logging.basicConfig(level=logging.INFO)   # 把日志打到控制台
logger = logging.getLogger(__name__)     # 新建一个 logger 实例


def _provider_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _provider_log_fields(fields):
    return ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)


def _robot_action_chain_log(stage, action_name=None, **fields):
    field_text = _provider_log_fields(fields)
    suffix = f", {field_text}" if field_text else ""
    print(f"[{_provider_timestamp()}] provider动作链路: stage={stage}, action={action_name}{suffix}")


def _provider_env_float(name, default):
    raw_value = os.getenv(name, str(default))
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        print(f"Invalid {name}={raw_value}, use {default}")
        return float(default)


def _robot_arm_http_timeout(action_name):
    if action_name == "release":
        return _provider_env_float("RABBITBOT_ARM_RELEASE_HTTP_TIMEOUT", 3.0)
    return _provider_env_float("RABBITBOT_ARM_ACTION_HTTP_TIMEOUT", 45.0)


from agno.models.vllm import vLLM

#from rabbitbot.agents import MapAgent, Brain
from rabbitbot.robots.constants import MoveType
from rabbitbot.prompts import get_prompt_provider
try:
    from rabbitbot.memory import AgentMemory
except Exception:
    print("Import AgentMemory failed")
try:
    from graphiti_core.nodes import EntityNode
except Exception:
    print("Import Graphiti failed")
from rabbitbot.grounding import GroundingVLMOpenAI, GeneralVLMOpenAI


def create_agno_model():
    llm_cfg = create_llm()
    return vLLM(
        id=llm_cfg['model'],
        api_key=llm_cfg['api_key'],
        base_url=llm_cfg['model_server'],
        enable_thinking=False,
        temperature=0.1
    )


def create_agno_quant_model():
    llm_cfg = create_quant_llm()
    return vLLM(
        id=llm_cfg['model'],
        api_key=llm_cfg['api_key'],
        base_url=llm_cfg['model_server'],
        enable_thinking=False,
        temperature=0.7
    )


def get_llm(
    model: str = None,
    model_server: str = None,
):
    model = model or os.getenv('RABBITBOT_MODEL', 'Qwen2.5-VL-7B-Instruct')
    model_server = model_server or os.getenv('RABBITBOT_MODEL_SERVER', 'http://localhost:8000/v1')

    return {
        'model_type': 'qwenvl_oai',
        'model': model,
        'model_server': model_server,
        'api_key': 'EMPTY',
        'generate_cfg': {
            'fncall_prompt_type': 'qwen',
        }
    }


def create_llm(
    model: str = None,
    model_server: str = None,
):
    model = model or os.getenv('RABBITBOT_MODEL', 'Qwen2.5-VL-7B-Instruct')
    #model_server = model_server or os.getenv('RABBITBOT_MODEL_SERVER', 'http://localhost:8000/v1')
    with open('kuavo_configs.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
        model_server = config["edge_vlm_host_url"]
    if model_server is None or model_server == "":
        model_server = model_server or os.getenv('RABBITBOT_MODEL_SERVER', 'http://localhost:8000/v1')
    print(f"model_server: {model_server}")

    return {
        'model_type': 'qwenvl_oai',
        'model': model,
        'model_server': model_server,
        'api_key': 'EMPTY',
        'generate_cfg': {
            'fncall_prompt_type': 'qwen',
        }
    }


def create_quant_llm(
    model: str = None,
    model_server: str = None,
):
    model = model or os.getenv('RABBITBOT_QUANT_MODEL', 'Qwen2.5-VL-7B-Instruct')
    #model_server = model_server or os.getenv('RABBITBOT_MODEL_SERVER', 'http://localhost:8000/v1')
    with open('kuavo_configs.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
        model_server = config["edge_quant_vlm_host_url"]
    if model_server is None or model_server == "":
        model_server = model_server or os.getenv('RABBITBOT_QUANT_MODEL_SERVER', 'http://localhost:8000/v1')

    return {
        'model_type': 'qwenvl_oai',
        'model': model,
        'model_server': model_server,
        'api_key': 'EMPTY',
        'generate_cfg': {
            'fncall_prompt_type': 'qwen',
        }
    }


# def compose_agents(llm: Union[Dict, BaseChatModel], tool_cfg: Optional[Dict] = None):
#     if tool_cfg is None:
#         tool_cfg = {}

#     def _get_tool_cfg(name):
#         return {
#             'name': name,
#             **tool_cfg.get(name, {}),
#         }

#     map_agent = MapAgent(
#         llm=llm,
#         name='navigation',
#         description=get_prompt_provider('navigation').description,
#         function_list=[
#             _get_tool_cfg('go_to'),
#             _get_tool_cfg('dynamic_navigation'),
#         ],
#     )

#     vision_agent = FnCallAgent(
#         llm=llm,
#         name='vision',
#         description=get_prompt_provider('vision').description,
#         function_list=[_get_tool_cfg('view')],
#     )

#     brain = Brain(
#         llm=llm,
#         agents=[
#             map_agent,
#             vision_agent,
#         ],
#         max_steps=100,
#     )

#     return brain


class VLNAgent:
    def __init__(self, host_url: str):
        self.host_url = host_url

    def reset(self):
        print(f"VLNAgent: {self.host_url}/reset")
        requests.post(urljoin(self.host_url, 'reset'))

    def act(self, image_path: str, task: str):
        with open(image_path, 'rb') as image_file:
            data = {
                'task': task,
            }
            files = {
                'image': image_file,
            }
            print(f"VLNAgent: {self.host_url}/act")
            resp = requests.post(urljoin(self.host_url, 'act'), data=data, files=files)
            try:
                action = MoveType(json.loads(resp.text)['action'])
            except:
                logger.warning(f"Can't parse action from {resp.text}")
                action = MoveType.STOP
        return action


def get_vln(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_VLN_URL', 'http://127.0.0.1:8001')
    return VLNAgent(host_url)


def create_vln(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_VLN_URL', 'http://127.0.0.1:8001')
    return VLNAgent(host_url)


class VLMOpenAI:

    def __init__(self, model: str, api_key: str, base_url: str, prompt: str, bbox_prompt: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.prompt = prompt
        self.bbox_prompt = bbox_prompt

    def prepare_bbox_message_for_vllm(self, image, json_content):
        image_contents = []
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
            "content": image_contents + [{"type": "text", "text": self.bbox_prompt + json_content}],
        }]


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


    def get_chat_response(self, messages, extra_body):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
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


def get_vlm_openai(
    model: str = None,
    model_server: str = None,
    **kwargs,
):
    llm_cfg = get_llm(model, model_server)
    return VLMOpenAI(
        model=llm_cfg['model'],
        api_key=llm_cfg['api_key'],
        base_url=llm_cfg['model_server'],
        **kwargs
    )


def create_vlm_openai(
    model: str = None,
    model_server: str = None,
    **kwargs,
):
    llm_cfg = create_llm(model, model_server)
    return GroundingVLMOpenAI(
        model=llm_cfg['model'],
        api_key=llm_cfg['api_key'],
        base_url=llm_cfg['model_server'],
        **kwargs
    )


def create_general_vlm_openai(
    model: str = None,
    model_server: str = None,
    **kwargs,
):
    llm_cfg = create_llm(model, model_server)
    return GeneralVLMOpenAI(
        model=llm_cfg['model'],
        api_key=llm_cfg['api_key'],
        base_url=llm_cfg['model_server'],
        **kwargs
    )


def get_memory_layer(
    model: str = None,
    model_server: str = None,
    neo4j_url: str = None,
    neo4j_user: str = None,
    neo4j_password: str = None,
    embd_model: str = None,
    embd_model_url: str = None,
    rerank_model: str = None,
    rerank_model_url: str = None,
):
    """
    Get or create an AgentMemory singleton instance.

    Note: AgentMemory is implemented as a singleton, so subsequent calls to this function
    will return the same instance regardless of the parameters passed.
    """
    llm_cfg = get_llm(model, model_server)
    neo4j_url = neo4j_url or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = neo4j_user or os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = neo4j_password or os.getenv('NEO4J_PASSWORD', 'your_password')
    embd_model = embd_model or os.getenv('GRAPHITI_EMBD_MODEL', 'Qwen3-Embedding-0.6B')
    embd_model_url = embd_model_url or os.getenv('GRAPHITI_EMBD_MODEL_URL', 'http://localhost:8005/v1')
    rerank_model = rerank_model or os.getenv('GRAPHITI_RERANK_MODEL', llm_cfg['model'])
    rerank_model_url = rerank_model_url or os.getenv('GRAPHITI_RERANK_MODEL_URL', 'http://localhost:8004/v1')

    return AgentMemory(
        llm_cfg=llm_cfg,
        neo4j_url=neo4j_url,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        embd_model=embd_model,
        embd_model_url=embd_model_url,
        rerank_model=rerank_model,
        rerank_model_url=rerank_model_url,
    )


def create_memory_layer(
    model: str = None,
    model_server: str = None,
    neo4j_url: str = None,
    neo4j_user: str = None,
    neo4j_password: str = None,
    embd_model: str = None,
    embd_model_url: str = None,
    rerank_model: str = None,
    rerank_model_url: str = None,
):
    return get_memory_layer(
        model, model_server,
        neo4j_url, neo4j_user, neo4j_password,
        embd_model, embd_model_url, rerank_model, rerank_model_url
    )


with open('kuavo_configs.json', 'r', encoding='utf-8') as file:
    config = json.load(file)
    enable_remote_memory_agent = True if config["enable_remote_memory_agent"] == "true" else False
    enable_remote_robot_agent = True if config["enable_remote_robot_agent"] == "true" else False
    provider_configs = {
        "enable_remote_memory_agent": enable_remote_memory_agent,
        "enable_remote_robot_agent": enable_remote_robot_agent
    }

class MemoryAgent:
    def __init__(self, host_url: str):
        self.host_url = host_url

    async def query_sync(self, query: str, group_name: str):
        task = {'query': query, 'group_name': group_name}
        data = {'task': str(task)}
        print(f"Task: {task}")
        resp = requests.post(urljoin(self.host_url, 'query'), data=data)
        try:
            entity = json.loads(resp.text)
            print("entity", entity)
            if "error" in entity:
                raise ValueError(entity["error"])
            uuid = entity.get('uuid')
            name = entity.get('name')
            group_id = entity.get('group_id')
            summary = entity.get('summary')
            attributes = entity.get('attributes') or {}
            if not uuid or not name or not summary:
                raise ValueError(f"invalid memory node: {entity}")
            location = attributes['location'] if 'location' in attributes else (0, 0, 0, 0, 0, 0)
            description = attributes['description'] if 'description' in attributes else ""
            image_path = attributes['image_path'] if 'image_path' in attributes else ""
            #location = ast.literal_eval(location)
            print(f"Recv: name {name}, location {location}, summary {summary}, description {description}")
        except Exception as exc:
            logger.warning(f"Can't parse node from {resp.text}: {exc}")
            uuid = None
            name = None
            location = None
            summary = None
            description = None
            image_path = None
        return uuid, name, location, summary, description, image_path

    async def query(self, query: str, group_name: str, limit: int = 1):
        if provider_configs['enable_remote_memory_agent']:
            entity_uuid, name, location, summary, description, image_path = await self.query_sync(query, group_name)
        else:
            entity_uuid = "000000000"
            name = "公司简介"
            location = (0, 0, 0, 0, 0, 0)
            summary = "公司简介总结"
            description = "公司简介描述"
            image_path = "leju.jpg"
        if not entity_uuid or not name or not summary:
            return []
        return [EntityNode(
            uuid=entity_uuid,
            name=name,
            group_id="",
            summary=summary,
            attributes={
                'location': location,
                'image_path': image_path,
                'description': description,
            },
        )]

    async def update_sync(self, entity: Dict):
        print(f"MemoryAgent: Update sync")
        print(str(entity))
        data = {'task': str(entity)}
        resp = requests.post(urljoin(self.host_url, 'update'), data=data)
        print(f"MemoryAgent: Get resp")
        print(resp.text)

    async def update(self, entity: Dict):
        await self.update_sync(entity)

    async def get_all_names(self):
        if provider_configs['enable_remote_memory_agent']:
            data = {'task': ""}
            resp = requests.post(urljoin(self.host_url, 'get_all_names'), data=data)
            try:
                name_lst = ast.literal_eval(resp.text)
                print("name_lst", name_lst)
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                name_lst = None
            return name_lst
        else:
            return ["公司简介", "教育场景", "公司业务", "关怀聚焦"]

    async def get_group_names(self, group_name):
        if provider_configs['enable_remote_memory_agent']:
            data = {'task': group_name}
            resp = requests.post(urljoin(self.host_url, 'get_group_names'), data=data)
            try:
                name_lst = ast.literal_eval(resp.text)
                print("name_lst", name_lst)
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                name_lst = None
            return name_lst
        else:
            if group_name == "展点":
                return ["公司简介", "教育场景", "关怀聚焦", "家庭服务", "工业智造", "商业与科研"]
            elif group_name == "教学场景":
                return ["教辅资源", "教学载体", "潜在独角兽企业", "理事单位"]

    async def get_group_summary(self, group_name):
        if provider_configs['enable_remote_memory_agent']:
            data = {'task': group_name}
            resp = requests.post(urljoin(self.host_url, 'get_group_summary'), data=data)
            try:
                summary_lst = ast.literal_eval(resp.text)
                print("summary_lst", summary_lst)
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                summary_lst = None
            return summary_lst

    def get_event_loop(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as e:
            if 'There is no current event loop in thread' in str(e):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                raise e
        return loop

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.get_event_loop().run_until_complete(self.close())


def get_memory_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_MEMORY_AGENT_URL', 'http://127.0.0.1:8001')
    return MemoryAgent(host_url)


def create_memory_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_MEMORY_AGENT_URL', 'http://127.0.0.1:8001')
    return MemoryAgent(host_url)


class RobotAgent:
    def __init__(self, host_url):
        self.host_url = host_url

    async def go_to_async(self, x, y, ox, oy, oz, ow, waypoints=None):
        if not provider_configs['enable_remote_robot_agent']:
            return
        task = str(waypoints if waypoints else (x, y, ox, oy, oz, ow))
        data = {'task': task}
        print(f"Task: go to {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'go_to_async'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'go_to_async: request failed: {e}')

    def _post_arm_action(self, action_name, call_type):
        if not provider_configs['enable_remote_robot_agent']:
            _robot_action_chain_log("remote_robot_agent_disabled", action_name, mode=call_type)
            return
        data = {'task': action_name}
        url = urljoin(self.host_url, 'do_arm_async')
        timeout_seconds = _robot_arm_http_timeout(action_name)
        total_start = time.perf_counter()
        print(f"Task: do arm {action_name}")
        _robot_action_chain_log("http_request_prepare", action_name, mode=call_type, url=url, timeout=timeout_seconds)
        try:
            http_start = time.perf_counter()
            _robot_action_chain_log("http_post_start", action_name, mode=call_type, url=url, timeout=timeout_seconds)
            resp = requests.post(url, data=data, timeout=timeout_seconds)
            http_elapsed = time.perf_counter() - http_start
            _robot_action_chain_log(
                "http_response_received",
                action_name,
                mode=call_type,
                status_code=resp.status_code,
                http_elapsed=f"{http_elapsed:.3f}s",
            )
            try:
                result = resp.json()
            except Exception:
                result = {"success": resp.ok, "message": resp.text}
            total_elapsed = time.perf_counter() - total_start
            success = result.get("success", "未知") if isinstance(result, dict) else "未知"
            _robot_action_chain_log(
                "http_response_parsed",
                action_name,
                mode=call_type,
                success=success,
                total_elapsed=f"{total_elapsed:.3f}s",
            )
            if isinstance(result, dict):
                robot_agent_timing = result.get("robot_agent_timing")
                arm_action_timing = result.get("arm_action_timing")
                if robot_agent_timing:
                    _robot_action_chain_log("robot_agent_timing", action_name, mode=call_type, timing=robot_agent_timing)
                if arm_action_timing:
                    _robot_action_chain_log("arm_action_timing", action_name, mode=call_type, timing=arm_action_timing)
            return result
        except (Timeout, RequestException) as e:
            total_elapsed = time.perf_counter() - total_start
            _robot_action_chain_log(
                "http_request_failed",
                action_name,
                mode=call_type,
                total_elapsed=f"{total_elapsed:.3f}s",
                error=e,
            )
            print(f'do_arm{"_async" if call_type == "async" else ""}: request failed: {e}')
            return {"success": False, "message": str(e)}

    def do_arm(self, action_name):
        return self._post_arm_action(action_name, "sync")

    async def do_arm_async(self, action_name):
        return self._post_arm_action(action_name, "async")

    async def do_head_async(self, yaw, pitch):
        if not provider_configs['enable_remote_robot_agent']:
            return
        param = (yaw, pitch)
        data = {'task': str(param)}
        print(f"Task: do head ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_head_async'), data=data, timeout=10)
        except Timeout as e:
            print('do_head_async: Timeout')

    def do_finger(self, x, y, z):
        if not provider_configs['enable_remote_robot_agent']:
            return
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do finger ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_finger_async'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'do_finger: request failed: {e}')

    async def do_finger_async(self, x, y, z):
        if not provider_configs['enable_remote_robot_agent']:
            return
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do finger ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_finger_async'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'do_finger_async: request failed: {e}')

    async def do_finger_status_async(self):
        if not provider_configs['enable_remote_robot_agent']:
            return 0
        param = ""
        data = {'task': str(param)}
        print(f"Task: do finger status ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_finger_status_async'), data=data, timeout=10)
            try:
                resp_dict = json.loads(resp.text)
                print("resp_dict", resp_dict)
                status = resp_dict['status']
                status = int(status)
                print(f"Recv: status {status}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                status = 0
        except Timeout as e:
            print('do_finger_status_async: Timeout')
            status = 0
        return status

    async def do_grab_status_async(self):
        if not provider_configs['enable_remote_robot_agent']:
            return 0
        param = ""
        data = {'task': str(param)}
        print(f"Task: do catch status ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_grab_status_async'), data=data, timeout=10)
            try:
                resp_dict = json.loads(resp.text)
                print("resp_dict", resp_dict)
                status = resp_dict['status']
                status = int(status)
                print(f"Recv: status {status}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                status = 0
        except Timeout as e:
            print('do_grab_status_async: Timeout')
            status = 0
        return status

    def do_handshake(self, x, y, z):
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do handshake ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_handshake_async'), data=data, timeout=10)
        except Timeout as e:
            print('do_handshake: Timeout')

    async def do_handshake_async(self, x, y, z):
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do handshake ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_handshake_async'), data=data, timeout=10)
        except Timeout as e:
            print('do_handshake_async: Timeout')

    def do_grab(self, x, y, z):
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do grab ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_grab_async'), data=data, timeout=10)
        except Timeout as e:
            print('do_grab: Timeout')

    async def do_grab_async(self, x, y, z):
        param = (x, y, z)
        data = {'task': str(param)}
        print(f"Task: do grab ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_grab_async'), data=data, timeout=10)
        except Timeout as e:
            print('do_grab_async: Timeout')

    async def do_grab_cancel_async(self):
        param = ""
        data = {'task': str(param)}
        print(f"Task: do grab cancel ({param})")
        try:
            resp = requests.post(urljoin(self.host_url, 'do_grab_cancel_async'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'do_grab_cancel_async: request failed: {e}')

    async def go_to_status(self):
        if not provider_configs['enable_remote_robot_agent']:
            return -1
        task = "get go to status"
        data = {'task': task}
        print(f"Task: {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'go_to_status'), data=data, timeout=10)
            try:
                resp_dict = json.loads(resp.text)
                print("resp_dict", resp_dict)
                status = resp_dict['status']
                status = int(status)
                print(f"Recv: status {status}")
                if all(key in resp_dict for key in ("last_status", "next_status", "sub")):
                    print(
                        f"last_status {resp_dict['last_status']}, "
                        f"next_status {resp_dict['next_status']}, "
                        f"sub {resp_dict['sub']}"
                    )
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                status = -1
        except (Timeout, RequestException) as e:
            print(f'go_to_status: request failed: {e}')
            status = -1
        return status

    def get_camera_info(self, info_type, params=None):
        if not provider_configs['enable_remote_robot_agent']:
            return None
        task = f"get camera info (type={info_type})"
        print(f"Task: {task}")
        task = {'info_type': info_type}
        if params is not None:
            task['params'] = params
        print(f"Task: {task}")
        data = {'task': str(task)}
        try:
            resp = requests.post(urljoin(self.host_url, 'get_camera_info'), data=data, timeout=60)
            try:
                resp_dict = json.loads(resp.text)
                #print("resp_dict", resp_dict)
                output = resp_dict['output']
                if info_type == "view_2d":
                    output = np.array(output, dtype=np.uint8)
                elif info_type == "depth_frame":
                    output = np.array(output, dtype=np.float32)
                elif info_type == "real_depth":
                    output = float(output)
                    print(f"Recv: output {output}")
                elif info_type == "hfov":
                    output = float(output)
                    print(f"Recv: output {output}")
                elif info_type == "get_location":
                    output = ast.literal_eval(output)
                    print(f"Recv: output {output}")
                elif info_type == "detect_key_point_pixel":
                    output = ast.literal_eval(output)
                    print(f"Recv: output {output}")
                elif info_type == "detect_hand_location":
                    output = ast.literal_eval(output)
                    print(f"Recv: output {output}")
                elif info_type == "start_record":
                    output = str(output)
                    print(f"Recv: output {output}")
                elif info_type == "stop_record":
                    output = str(output)
                    print(f"Recv: output {output}")
                #print(f"Recv: output {output}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                output = None
        except (Timeout, RequestException) as e:
            print(f'get_camera_info: request failed: {e}')
            output = None
        return output

    async def reset_go_to_status(self):
        if not provider_configs['enable_remote_robot_agent']:
            return
        task = "reset go to status"
        data = {'task': task}
        print(f"Task: {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'reset_go_to_status'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'reset_go_to_status: request failed: {e}')

    async def vln(self, task):
        if not provider_configs['enable_remote_robot_agent']:
            return
        data = {'task': task}
        print(f"Task: {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'vln'), data=data, timeout=600)
        except (Timeout, RequestException) as e:
            print(f'vln: request failed: {e}')

    async def move(self, action_idx):
        if not provider_configs['enable_remote_robot_agent']:
            return
        task = str(action_idx)
        data = {'task': task}
        print(f"Task: {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'move'), data=data, timeout=10)
        except (Timeout, RequestException) as e:
            print(f'move: request failed: {e}')

    async def view(self, task):
        if not provider_configs['enable_remote_robot_agent']:
            return
        data = {'task': task}
        print(f"Task: {task}")
        try:
            resp = requests.post(urljoin(self.host_url, 'view'), data=data, timeout=10)
            try:
                resp_dict = json.loads(resp.text)
                print("resp_dict", resp_dict)
                output = resp_dict['output']
                print(f"Recv: output {output}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                output = None
        except (Timeout, RequestException) as e:
            print(f'view: request failed: {e}')
            output = None
        return output

    def get_event_loop(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as e:
            if 'There is no current event loop in thread' in str(e):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            else:
                raise e
        return loop

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        #self.get_event_loop().run_until_complete(self.close())
        pass


def create_robot_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_ROBOT_AGENT_URL', 'http://127.0.0.1:8001')
    return RobotAgent(host_url)


class STTAgent:

    def __init__(self, host_url):
        self.host_url = host_url
        self.last_utterance_id = 0

    def run(self, input_dict_str: str) -> str:
        data = {"task": input_dict_str}
        try:
            start_time = time.time()
            resp = requests.post(urljoin(self.host_url, 'exec'), data=data, timeout=10)
            duration = time.time() - start_time
            #print(f"STTAgent: post_duration {duration:.3f}")
            try:
                resp_dict = json.loads(resp.text)
                out_text = resp_dict['out_text']
                utterance_id = resp_dict.get('utterance_id')
                if utterance_id is not None:
                    try:
                        self.last_utterance_id = int(utterance_id)
                    except (TypeError, ValueError):
                        logger.warning(f"Can't parse utterance_id from {utterance_id}")
                #print(f"Recv: out_text {out_text}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                out_text = ""
        except Timeout as e:
            print('STTAgent: Timeout')
            out_text = ""
        return out_text


def create_stt_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_STT_AGENT_URL', 'http://127.0.0.1:8001')
    return STTAgent(host_url)


class TTSAgent:

    def __init__(self, host_url):
        print(f"TTSAgent: host_url {host_url}")
        self.host_url = host_url

    def run(self, input_dict_str: str) -> str:
        data = {"task": input_dict_str}
        try:
            start_time = time.time()
            resp = requests.post(urljoin(self.host_url, 'exec'), data=data, timeout=10)
            duration = time.time() - start_time
            #print(f"TTSAgent: post_duration {duration:.3f}")
            try:
                resp_dict = json.loads(resp.text)
                out_text = resp_dict['out_text']
                #print(f"Recv: out_text {out_text}")
            except:
                logger.warning(f"Can't parse node from {resp.text}")
                out_text = ""
        except Timeout:
            print('TTSAgent: Timeout')
            out_text = ""
        except RequestException as e:
            print(f'TTSAgent: request failed: {e}')
            out_text = ""
        return out_text


def create_tts_agent(host_url: str = None):
    host_url = host_url or os.getenv('RABBITBOT_TTS_AGENT_URL', 'http://127.0.0.1:8001')
    return TTSAgent(host_url)
