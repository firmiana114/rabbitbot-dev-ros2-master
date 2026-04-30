
import time
import json
import random
import asyncio
import threading
from agno.workflow.v2 import (
    Workflow,
    Loop,
    Router,
    StepInput,
    Step,
    StepOutput,
    Workflow
)
from agno.run.v2.workflow import WorkflowRunResponseEvent
from agno.agent import Agent
from rabbitbot.agno_agents.sound import RealtimeSTT, RealtimeTTS
from rabbitbot.tools.logging import logger as file_logger

from .models import (
    CompletionCheckModel,
    StaticOrDynamicNavigationModel,
    SimpleDelegationTaskModel,
    DelegationTaskModel,
    #ActionModel,
)
from .prompts import (
    get_inst_plan,
    get_inst_navi_check,
    get_inst_chat,
    get_inst_search_check,
    get_inst_ctoe_translate
)
from .chat import ChatQueue
from rabbitbot.robots.constants import MoveType, NavigationStatus
from rabbitbot.tools.navi_agno import NavigationToolkit, NavigationQuery, is_navigating
from rabbitbot.tools.sound_agno import (
    tts_sound, tts_wait, tts_stop, tts_fast, tts_get_wav_count,
    tts_long_text_with_stt_stop,
    tts_long_text,
    action_with_tts, wait_with_tts,
    audio_input_execute,
    audio_input_execute_timeout,
    audio_input_execute_timeout_navi,
    audio_input_yes_or_no,
    audio_input_stop_chat,
    yes_or_no_quick_match,
    identify_think_type,
    build_guide_go_to_text,
    build_stt_prompt_by_list
)
from rabbitbot.tools.detect_agno import DetectToolkit

from typing import Any, List, AsyncIterator, Union
from textwrap import dedent
from rich.console import Console
from rich.pretty import pprint
from rich.prompt import Prompt
from agno.exceptions import StopAgentRun
import numpy as np


class WorkflowTimePoints:
    PLAN_START = -1
    PLAN_END = -1
    NAVI_CHECK_START = -1
    NAVI_CHECK_END = -1
    CHAT_START = -1
    CHAT_FIRST_TEXT_START = -1
    CHAT_END = -1


workflow_configs = {
    "max_chat_history": 5,
    "max_chat_steps": 1
}

PLAN_SESSION_ID = 0
NAVI_CHECK_SESSION_ID = 1
CHAT_SESSION_ID = 2
last_chat_text = ""
chat_queue = ChatQueue(10)
before_text = ""


def create_main_workflow(ctx: Any) -> Workflow:
    """
    Create the main workflow for the RabbitBot agents.
    """
    # Initialize toolkits
    navi_tools = NavigationToolkit(ctx)
    detect_tools = DetectToolkit(ctx)
    # Define agents
    model = ctx.agno_model
    quant_model =  ctx.agno_quant_model
    plan_agent = Agent(
        name='Plan Agent',
        role='Planner',
        instructions=get_inst_plan(ctx.entity_lst),
        # instructions=dedent(f"""\
        #     你是智元机器人公司的具身机器人规划智能体。
        #     给定一个任务，你必须规划完成该任务的下一步操作。
        #     每个子任务应该是以下之一：
        #     - navigation: 寻找或前往某个位置/房间/实体
        #     - chat: 与用户聊天对话，特别是介绍智元公司相关信息
        #     如果任务是寻找或前往某个位置/房间/实体或者需要你介绍智元公司相关的信息，你应该输出"navigation"并输出subtask_description："<位置/房间/实体的名称>"。
        #     如果任务是与用户聊天、询问问题，你应该输出"chat"。
        #     如果子任务无法由任何智能体完成，你应该向用户寻求帮助。
        #     """),
        #response_model=SimpleDelegationTaskModel,
        model=model,
        debug_mode=False,
        add_history_to_messages=False,
        num_history_runs=4,
    )

    navi_check_agent = Agent(
        name='Navigation Plan Agent',
        role='Planner',
        instructions=get_inst_navi_check(ctx.entity_lst),
        model=model,
        debug_mode=False,
        add_history_to_messages=True,
        num_history_runs=5,
    )

    entity_check_agent = Agent(
        name='Entity Check Agent',
        role='Entity checker',
        instructions=dedent("""\
            你是一个实体检查智能体。请根据用户给定的查询请求，从实体列表中选择最相关的实体。实体列表是一个字典类型的数据，包含"""),
        model=model,
    )

    location_name="教育场景"
    node_names= ctx.education_entity_lst
    node_summary=ctx.education_summary_lst
    search_check_agent = Agent(
        name='Search Check Agent',
        role='Search Checker',
        instructions=get_inst_search_check(node_names,node_summary),
        model=model,
        debug_mode=True,
    )

    ctoe_translate_agent = Agent(
        name='English to Chinese Translate Agent',
        role='Translator',
        instructions=get_inst_ctoe_translate(),
        model=model,
        debug_mode=False,
    )

    entity_reranker_agent = Agent(
        name='Entity Reranker Agent',
        role='Entity reranker',
        instructions=dedent("""\
            You are an entity reranker agent.
            Given a task and a list of entities:
                - if there is not any relevant entity, you should output "nothing relevant".
                - if there are multiple relevant entities, you should output the name of the most relevant one.
            Taken the name and description of the entity into account."""),
        model=model,
    )

    task_completion_check_agent = Agent(
        name='Task Completion Check Agent',
        role='Task completion checker',
        instructions=dedent("""\
            You are a task completion checker agent.
            Given the task and all previous step outputs, you must determine if the task is completed"""),
        response_model=CompletionCheckModel,
        model=model,
    )

    #stt_agent = Agent(
    #    name="STT Agent",
    #    model=RealtimeSTT(id="base", modalities=["text"]),
    #)
    #stt_agent = None

    stt_agent = ctx.stt_agent

    #tts_agent = Agent(
    #    name="TTS Agent",
    #    model=RealtimeTTS(id="base", modalities=["text"]),
    #)
    tts_agent = ctx.tts_agent

    chat_bot_name = "机二机器人"

    max_chat_history = workflow_configs["max_chat_history"]
    chat_agent = Agent(
        name='Chat Agent',
        role='Assistant',
        instructions=get_inst_chat(ctx.entity_lst),
        model=model,
        #model=quant_model,
        read_chat_history=False,
        add_history_to_messages=True,
        num_history_runs=max_chat_history,
    )

    def audio_input_executor(step_input):
        original_task = step_input.message or ''
        previous_steps = step_input.get_all_previous_content()
        print("original_task:", original_task)
        print("previous_steps:", previous_steps)

        text = original_task
        #text = previous_steps.split("===")[-1]
        #text = text[1:]
        print("text:", text)

        #tts_sound(tts_agent, f"{before_text}我准备好了，您需要帮助吗？", "zh")
        #tts_sound(tts_agent, "You can chat with me now", "en")
        #tts_fast(tts_agent, "ready")

        text = "请介绍一下深圳这座城市"
        time.sleep(1)
        #out_text = audio_input_execute(stt_agent, "speech_to_text", timeout=300)
        out_text = audio_input_execute_timeout(stt_agent, timeout=30, text="")
        while out_text == "<REC_TIMEOUT>":
            tts_sound(tts_agent, f"{before_text}你好，请问你需要我做什么吗？", "zh")
            out_text = audio_input_execute_timeout(stt_agent, timeout=30, text="")
        chat_queue.put(out_text, "用户")

        #tts_sound(tts_agent, f"{before_text}我听到了，但是可能要思考一会。请稍等片刻", "zh")
        think_type = identify_think_type(out_text)
        tts_fast(tts_agent, think_type)

        WorkflowTimePoints.PLAN_START = time.time()

        return StepOutput(content=f"{out_text}")

    audio_input_step = Step(
        name='audio_input_step',
        description='Audio input from the user.',
        executor=audio_input_executor,
    )

    plan_step = Step(
        name='plan_step',
        agent=plan_agent,
        description='Plan the next step to complete the task.',
    )

    async def plan_executor(step_input):
        previous_steps = step_input.get_all_previous_content()
        print("previous_steps:", previous_steps)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")

        print("in_text:", text)
        history_text = chat_queue.build_history()
        text =  history_text
        print("in_text:", text)
        start_time = time.time()
        #run_response = plan_agent.run(text, session_id=str(PLAN_SESSION_ID))
        #out_text = run_response.content
        response_stream = plan_agent.run(
            text, stream=True, stream_intermediate_steps=False,
            session_id=str(PLAN_SESSION_ID)
        )
        out_text = ""
        for event in response_stream:
            if event.event == "RunResponseContent":
                #print(f"Content: {event.content}")
                out_text += event.content
            elif event.event == "ToolCallStarted":
                print(f"Tool call started: {event.tool}")
            elif event.event == "ReasoningStep":
                print(f"Reasoning step: {event.content}")
            if len(out_text) > 0:
                break
        duration  = time.time() - start_time
        print("out_text:", out_text)
        log_text = f"plan_executor: plan_duration {duration:.3f}, text {out_text}"
        print(log_text)
        file_logger.debug(log_text)

        if out_text[0] == "C":
            response = await chat_executor(step_input)
        elif out_text[0] == "N":
            response = await navi_check_executor(step_input)
        else:
            response = await unknown_executor(step_input)

        return response

    plan_step_v2 = Step(
        name='plan_step',
        description='Plan the next step to complete the task.',
        executor=plan_executor,
    )

    def is_chinese(s):
        #return all('\u4e00' <= ch <= '\u9fff' for ch in s)
        return '\u4e00' <= s[0] <= '\u9fff'

    def is_english(s):
        #return all('a' <= ch.lower() <= 'z' for ch in s if ch.isalpha())
        return 'a' <= s[0].lower() <= 'z'

    async def chat_execute(text, sess_idx=None, navi_tools=None):
        print(f"chat_execute: text {text}")
        if is_chinese(text): lang = "zh"
        elif is_english(text): lang = "en"
        else:
            lang = "zh"
            #print(f"Unkown lanugage")
            #out_text = "<CHAT_UNKOWN_LANG>"
            #return StepOutput(content=f"{out_text}")
        print("lang:", lang)
        if text == "<REC_TIMEOUT>":
            out_text = text
            return StepOutput(content=f"{out_text}")

        tts_wait(tts_agent)

        WorkflowTimePoints.CHAT_START = time.time()
        if sess_idx is not None:
            print(f"chat_agent: session_id {str(sess_idx)}")
            print(f"chat_agent: text {text}")
            response_stream = chat_agent.run(
                text, stream=True, stream_intermediate_steps=False,
                session_id=str(sess_idx)
            )
        else:
            response_stream = chat_agent.run(
                text, stream=True, stream_intermediate_steps=False,
            )

        speecher_start_event = threading.Event()
        speecher_stop_event = threading.Event()
        listener_stop_event = threading.Event()

        def stop_task():
            while True:
                time.sleep(1)
                while not speecher_start_event.is_set():
                    time.sleep(1)
                print("聊天正式开始，可以输入停止命令了") if lang == "zh" else print("You can say stop now")
                if False:
                    #text = "停止说话"
                    #input_dict = {"task": "speech_to_text_async", "lang": lang, "text": "", "timeout": 60}

                    #run_response = stt_agent.run(
                    #   json.dumps(input_dict), stream=False, stream_intermediate_steps=False,
                    #)
                    #out_text = run_response.content

                    #out_text = stt_agent.run(json.dumps(input_dict))

                    out_text = audio_input_execute_timeout(stt_agent, timeout=30)
                    #out_text = ""

                    print("收到命令：", out_text) if lang == "zh" else print("Got command:", out_text)
                    if out_text.startswith("停止") or "停" in out_text or "stop" in out_text.lower():
                        speecher_stop_event.set()
                        break
                if listener_stop_event.is_set():
                    print("监听线程收到信号量，退出")
                    break
                if True:
                    resp_msg = audio_input_stop_chat(stt_agent)
                    if resp_msg == "<STOP_CHAT>":
                        print("收到停止口令，退出")
                        speecher_stop_event.set()
                        break
                if listener_stop_event.is_set():
                    print("监听线程收到信号量，退出")
                    break

        speecher_stop_thread = threading.Thread(target=stop_task)
        speecher_stop_thread.start()

        global last_chat_text
        out_text = ""
        last_chat_text = ""
        num_setence = 0
        for event in response_stream:
            if event.event == "RunResponseContent":
                #print(f"Content: {event.content}")
                out_text += event.content
            elif event.event == "ToolCallStarted":
                print(f"Tool call started: {event.tool}")
            elif event.event == "ReasoningStep":
                print(f"Reasoning step: {event.content}")

            if speecher_stop_event.is_set():
                tts_stop(tts_agent)
                time.sleep(0.5)
                tts_sound(tts_agent, f"{before_text}好，我停止说话了", "zh")
                print("已经停止说话了") if lang == "zh" else print("Chatting stopped")
                break
            if navi_tools is not None:
                if not await is_navigating(navi_tools):
                    print("导航达到，停止生成文本")
                    break

            #print(f"OutText: {out_text}")
            out_text = out_text
            if out_text.endswith("，") or out_text.endswith("；") or \
                out_text.endswith("。") or out_text.endswith("？") or out_text.endswith("！") or \
                out_text.endswith(".") or out_text.endswith("!") or out_text.endswith("\n"):
                print(f"out_text: {out_text}")
                action_name = None

                if out_text.startswith("[A:"):
                    ei = out_text.index("]")
                    text_len = len(out_text[ei+1:])
                else:
                    text_len = len(out_text)

                print(f"text_len: {text_len}")
                if text_len < 8:
                    continue

                if out_text.startswith("[A:"):
                    ei = out_text.index("]")
                    print(f"ei: {ei}")
                    action_name = out_text[3:ei]
                    print(f"action_name: {action_name}")
                    out_text = out_text[ei+1:]
                    print(f"out_text: {out_text}")
                #time.sleep(10)

                if is_chinese(out_text):
                    lang = "zh"
                elif is_english(out_text):
                    lang = "en"
                else:
                    lang = "zh"
                    print(f"Unkown lanugage: {lang}")
                WorkflowTimePoints.CHAT_FIRST_TEXT_START = time.time()
                first_infer_time = WorkflowTimePoints.CHAT_FIRST_TEXT_START - WorkflowTimePoints.CHAT_START
                WorkflowTimePoints.CHAT_START = WorkflowTimePoints.CHAT_FIRST_TEXT_START
                log_text = f"chat_executor: seq_idx {num_setence}, infer_time {first_infer_time:.3f}, text {out_text}"
                print(log_text)
                file_logger.debug(log_text)
                #tts_index = tts_sound(tts_agent, f"{before_text}" + out_text.strip(), lang)
                tts_index = tts_sound(tts_agent, out_text.strip(), lang)
                speecher_start_event.set()
                if navi_tools is not None:
                    go_to_status = await navi_tools.go_to_status()
                    if go_to_status == NavigationStatus.PENDING or go_to_status == NavigationStatus.SUCCEEDED:
                        if action_name is not None:
                            if action_name  == "握手":
                                #await handshake_execute_v2(ctx)
                                action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                            else:
                                action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                else:
                    if action_name is not None:
                        if action_name  == "握手":
                            #await handshake_execute_v2(ctx)
                            action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                        else:
                            action_with_tts(ctx.robot, action_name, tts_agent, tts_index)
                last_chat_text += out_text
                out_text = ""
                num_setence += 1
                #if num_setence > 3:
                #    break

        if False:
            go_to_status = await navi_tools.go_to_status()
            if go_to_status == NavigationStatus.PENDING or go_to_status == NavigationStatus.SUCCEEDED:
                if "自我介绍" in text or "你好" in text or "您好" in text:
                    time.sleep(0.6)
                    await ctx.robot.do_arm_async("打招呼")

        #out_text = run_response.content
        chat_queue.put(last_chat_text, "机器人")
        out_text = ""
        #print(f"OutText: {out_text}")

        #tts_wait(tts_agent)
        while True:
            time.sleep(0.5)
            if speecher_stop_event.is_set():
                print("收到停止命令，准备退出聊天")
                tts_stop(tts_agent)
                while tts_get_wav_count(tts_agent) > 0:
                    time.sleep(0.5)
                break
            if navi_tools is not None:
                if not await is_navigating(navi_tools):
                    print("导航达到，停止等待语音")
                    break
            if tts_get_wav_count(tts_agent) == 0:
                print("WAV播完，退出聊天")
                break
        listener_stop_event.set()
        speecher_start_event.set()
        #audio_input_execute(stt_agent, "stop")
        audio_input_execute(stt_agent, "stop_async")
        speecher_stop_thread.join()

        return out_text

    class ChatSessionInfo:
        sess_idx: int = CHAT_SESSION_ID

    async def chat_loop_execute(text, navi_tools=None):
        max_chat_steps = workflow_configs["max_chat_steps"]
        for i in range(max_chat_steps):
            if text is None:
                if navi_tools is None:
                    text = audio_input_execute_timeout(stt_agent, timeout=60)
                else:
                    text = await audio_input_execute_timeout_navi(stt_agent, 60, navi_tools)
            if text == "<REC_TIMEOUT>" or text == "<NAVI_REACH>":
                break
            if "停止聊天" in text:
                break
            #if i > 0:
            #    think_type = identify_think_type(text)
            #    tts_fast(tts_agent, think_type)
            await chat_execute(text, ChatSessionInfo.sess_idx, navi_tools)
            text = None
        out_text = "Chat loop finish"
        #ChatSessionInfo.sess_idx += 1
        return out_text

    async def chat_executor(step_input):
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        print(f"chat_executor: plan_time: {plan_time:.3f}")
        original_task = step_input.message or ''
        previous_step = step_input.get_last_step_content()
        previous_steps = step_input.get_all_previous_content()
        print("original_task:", original_task)
        print("previous_step:", previous_step)
        print("previous_steps:", previous_steps)

        #text = previous_step.split("=")[2][1:-1]
        #text = previous_step.subtask_description
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")
        print("chat_input_text:", text)
        #text = str(previous_step)
        #text = text.split("=")[2][1:-1]
        #text = str(original_task)
        #text = ""
        #print("text:", text)

        #out_text = await chat_execute(text)
        out_text = await chat_loop_execute(text)

        return StepOutput(content=f"{out_text}")

    async def vln_execute(ctx):
        tts_sound(tts_agent, f"{before_text}下面我将展示我的动态导航功能", "zh")
        while True:
            tts_sound(tts_agent, f"{before_text}请告诉我你想让我找什么？", "zh")
            audio_input_text = audio_input_execute_timeout(stt_agent, 300)
            task = audio_input_text
            print("task: ", task)

            run_response = ctoe_translate_agent.run(task)
            out_text = run_response.content
            print("out_text:", out_text)

            task = out_text
            print("task: ", task)
            await ctx.robot.vln(task)

    async def view_execute(ctx):
        tts_sound(tts_agent, f"{before_text}下面我将展示我的视觉理解能力", "zh")
        while True:
            tts_sound(tts_agent, f"{before_text}请告诉我你想让我看什么？", "zh")
            audio_input_text = audio_input_execute_timeout(stt_agent, 300)
            task = audio_input_text
            print("task: ", task)

            print("task: ", task)
            out_text = await ctx.robot.view(task)
            tts_sound(tts_agent, f"{before_text}{out_text}", "zh")

    async def move_execute(ctx):
        tts_sound(tts_agent, f"{before_text}下面我将展示我的转向能力", "zh")
        while True:
            tts_sound(tts_agent, f"{before_text}请按回车键向左转", "zh")
            input("请按回车键继续")
            out_text = await ctx.robot.move(2)
            tts_sound(tts_agent, f"{before_text}请按回车键向右转", "zh")
            input("请按回车键继续")
            out_text = await ctx.robot.move(3)

    async def sound_execute(ctx):
        tts_sound(tts_agent, f"下面我将展示我的语音说话功能，我会重复你说的话", "zh")
        while True:
            audio_input_text = audio_input_execute_timeout(stt_agent, 300)
            tts_sound(tts_agent, f"{audio_input_text}", "zh")

    async def vln_executor(step_input):
        await vln_execute(ctx)
        response = 'VLN completed.'
        yield StepOutput(
            content=response,
        )

    async def view_executor(step_input):
        await view_execute(ctx)
        response = 'VLM completed.'
        yield StepOutput(
            content=response,
        )

    async def move_executor(step_input):
        await move_execute(ctx)
        response = 'Move completed.'
        yield StepOutput(
            content=response,
        )

    async def sound_executor(step_input):
        await sound_execute(ctx)
        response = 'Sound completed.'
        yield StepOutput(
            content=response,
        )

    async def unknown_executor(step_input):
        #tts_fast(tts_agent, "sorry")
        arm_lst = ["否定拒绝", "双手平摊开掌心向上"]
        n = len(arm_lst)
        rand_n = random.randint(0, n-1)
        await ctx.robot.do_arm_async(arm_lst[rand_n])
        tts_fast(tts_agent, "unknown")
        out_text = "<WORKFLOW_UNKOWN>"
        return StepOutput(content=f"{out_text}")

    navigation_routines = {
        'slam_vln': dedent("""\
            1. call go_to with the (x, y) of the target entity
            2. call dynamic_navigation to get close and face the target entity"""),
        'vln': dedent("""\
            1. call dynamic_navigation to complete the task"""),
    }
    navigation_agents: dict[str, Agent] = {}
    for routine, instruction in navigation_routines.items():
        navigation_agents[routine] = Agent(
            name='Navigation Agent ({})'.format(routine),
            role='Navigator',
            instructions=dedent("""\
                You are a navigation agent of a embodied robot.
                Given a task, you must use the navigation tool to complete.
                Routine:
                """ + instruction),
            tools=[navi_tools],
            model=model,
            show_tool_calls=True,
        )

    async def navi_execute(
        subtask_description
    ):
        nodes = await ctx.memory.query(query=subtask_description, group_name="展点", limit=5)
        print("nodes:", nodes)
        #import pdb; pdb.set_trace()
        entities = [{
            'name': node.name,
            'summary': node.summary,
            'location': node.attributes.get('location', ''),
            'description': node.attributes.get('description', ''),
        } for node in nodes]

        rerank_prompt = dedent("""\
            Task: "{task_description}"
            Entities: {entities}""").format(
            task_description=subtask_description,
            entities=entities,
        )
        print("rerank_prompt:", rerank_prompt)
        # response_iterator = await entity_reranker_agent.arun(
        #     rerank_prompt, stream=True, stream_intermediate_steps=True,
        # )
        # async for event in response_iterator:
        #     yield event

        # response = entity_reranker_agent.run_response
        # entity_name = response.content.strip()
        entity_name = nodes[0].name
        print("entity_name:", entity_name)
        entity = next(
            (e for e in entities if e['name'] == entity_name), None
        )
        if entity:
            entity = {
                'name': entity['name'],
                'summary': entity['summary'],
                'location': entity['location'],
                'description': entity['description']
            }
            navigation_prompt = dedent("""\
                Task: "{task_description}"
                Target: {entity}""").format(
                task_description=subtask_description,
                entity=entity,
            )
            #import pdb; pdb.set_trace()
            console = ctx.console
            # Get the live display instance from the console
            #live = console._live

            # Stop the live display temporarily so we can ask for user confirmation
            #live.stop()  # type: ignore

            # Ask for confirmation
            #tts_sound(tts_agent, f"{before_text}你是否想去往{entity['name']}", "zh")
            #tts_sound(tts_agent, f"{before_text}要不要我带你去{entity['name']}看看吧", "zh")
            guide_go_to_text = build_guide_go_to_text(entity['name'])
            tts_sound(tts_agent, guide_go_to_text, "zh")
            #message = (
            #    Prompt.ask("Do you want to go to the {}?".format(entity['name']), choices=["y", "n"], default="y")
            #    .strip()
            #    .lower()
            #)
            #live.start()
            message = audio_input_yes_or_no(stt_agent)
            #message = input("请输入 y/n 来开启或取消导航：")
            while message != "y" and message != "n":
                #tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你是否想去往{entity['name']}", "zh")
                tts_fast(tts_agent, "sorry")
                tts_sound(tts_agent, guide_go_to_text, "zh")
                message = audio_input_yes_or_no(stt_agent)

            #import pdb; pdb.set_trace()
            # If the user does not want to continue, raise a StopExecution exception
            if message != "y":
                #live.stop()
                # Ask for confirmation
                #message = (
                #    Prompt.ask("I cannot find the target in my memory. Do you want to go to the target by dynamic navigation?", choices=["y", "n"], default="y")
                #    .strip()
                #    .lower()
                #)
                chat_queue.put("不用了。", "用户")
                tts_fast(tts_agent, "cancel")
                #tts_sound(tts_agent, f"{before_text}那需要我动态寻找{entity['name']}吗", "zh")
                #message = audio_input_yes_or_no(stt_agent)
                message = "n"
                while message != "y" and message != "n":
                    tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。我不知道{entity['name']}在哪里，需要我动态寻找吗", "zh")
                    message = audio_input_yes_or_no(stt_agent)
                if message == "y":
                    navigation_prompt = subtask_description
                    #response = await navigation_tools.dynamic_navigation(navigation_prompt)
                    response = 'Dynamic navigation completed.'
                    tts_sound(tts_agent, f"{before_text}动态寻找已完成", "zh")
                    #live.start()
                else:
                    response = "Unable to reach the place the user wants to go!"
            else:
                entity_name = entity['name']
                #tts_sound(tts_agent, f"{before_text}好的，我即将前往{entity_name}", "zh")
                #tts_sound(tts_agent, f"{before_text}我已经知道了{entity_name}在哪里了，下面我带你去", "zh")
                #tts_sound(tts_agent, f"{before_text}好的，下面我带你去{entity_name}", "zh")
                tts_fast(tts_agent, "naviguide")
                print("entity['location']", entity['location'])
                location = entity['location']
                x, y, ox, oy, oz, ow = location[0], location[1], location[2], location[3], location[4], location[5]
                enable_navi = False
                if enable_navi:
                    # v1
                    #response = await navigation_tools.go_to(x, y, yaw)
                    # v2
                    navi_query = NavigationQuery()
                    await navi_tools.go_to_async(x, y, ox, oy, oz, ow, navi_query)
                    # v3
                    #await navigation_tools.go_to(x, y, ox, oy, oz, ow)

                    #navi_status = navi_query.get_status()
                    enable_chat = False
                    while await is_navigating(navi_tools):
                        if enable_chat:
                            #tts_sound(tts_agent, f"{before_text}现在你可以和我聊天哟", "zh")
                            tts_fast(tts_agent, "navichat")
                            #audio_input_text = audio_input_execute(stt_agent, "speech_to_text_async", timeout=30)
                            audio_input_text = await audio_input_execute_timeout_navi(stt_agent, 30, navi_tools)
                            if audio_input_text != "<REC_TIMEOUT>" and audio_input_text != "<NAVI_REACH>":
                                #tts_sound(tts_agent, f"{before_text}我听到了，让我想一想", "zh")
                                think_type = identify_think_type(audio_input_text)
                                tts_fast(tts_agent, think_type)
                                #await chat_execute(audio_input_text)
                                await chat_loop_execute(audio_input_text, navi_tools)
                        #navi_status = navi_query.get_status()

                    navi_status = await navi_tools.go_to_status()
                else:
                    #time.sleep(10.0)
                    navi_status = NavigationStatus.SUCCEEDED
                if navi_status == NavigationStatus.SUCCEEDED and "礼品" not in entity['name']:
                    enable_intro_description = True
                    if enable_intro_description:
                        input("按回车开始介绍")
                        #tts_sound(tts_agent, f"{before_text}我已经到达了，一会再聊", "zh")
                        #tts_sound(tts_agent, f"{before_text}下面我为你介绍{entity_name}", "zh")
                        time.sleep(0.1)
                        #tts_index = tts_sound(tts_agent, f"{before_text}请往这边看", "zh")
                        time.sleep(0.5)
                        #tts_sound(tts_agent, f"{before_text}{entity['description']}", "zh")
                        #action_with_tts(ctx.robot, "右手摆动（先内向后向外）", tts_agent, tts_index)
                        #text = f"{before_text}{entity['description']}"
                        text = f"{entity['description']}"
                        tts_long_text_with_stt_stop(tts_agent, text, stt_agent, ctx.robot, before_text)
                        #time.sleep(4.0)
                        #await ctx.robot.do_arm_async("右手摆动（先内向后向外）")

                        #tts_sound(tts_agent, f"{before_text}我介绍完了", "zh")

                    #target_group_name = "教育场景"
                    target_group_name = "人形机器人科研场景"
                    enable_game_execute = True
                    if target_group_name in entity['name'] and enable_game_execute:
                        location_name = target_group_name
                        entity_lst = await ctx.memory.get_group_names(location_name)
                        summary_lst= await ctx.memory.get_group_summary(location_name)
                        #recommand_entity_lst = random.sample(entity_lst, 3)
                        recommand_entity_lst = random.sample(entity_lst, 2)
                        entity_prompt = build_stt_prompt_by_list(recommand_entity_lst)
                        #tts_sound(tts_agent, f"{before_text}除了我刚才的介绍，这里还有{entity_prompt}等具体板块，需要我为再做详细的介绍吗？", "zh")
                        #message = audio_input_yes_or_no(stt_agent)
                        message = "y"
                        while message != "y" and message != "n":
                            #tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你是否想去往{entity['name']}", "zh")
                            tts_fast(tts_agent, "sorry")
                            tts_sound(tts_agent, f"{before_text}还需要我为您详细介绍这个地方吗？", "zh")
                            message = audio_input_yes_or_no(stt_agent)
                        if message == "y":
                            #tts_sound(tts_agent, f"{before_text}下面我和你玩个小游戏", "zh")
                            await game_execute(ctx, target_group_name)
                            await thank_chat_execute(ctx)
                            input("请按回车键带用户去礼品处")
                            tts_sound(tts_agent, f"{before_text}好啊，没问题，跟我来", "zh")

                    #tts_sound(tts_agent, f"{before_text}我可以带你继续参观，你有想去的地方吗？或者和我聊天也可以。", "zh")
                    #tts_sound(tts_agent, f"{before_text}我们继续吧", "zh")

                    response = 'Navigation to ({}, {}) successful.'.format(x, y)
                    await navi_tools.reset_go_to_status()
                elif navi_status == NavigationStatus.SUCCEEDED and "礼品" in entity['name']:
                    tts_sound(tts_agent, f"{before_text}我马上到达了，一会再聊", "zh")
                    #await grab_execute(ctx)
                    response = 'Navigation to ({}, {}) successful.'.format(x, y)
                    await navi_tools.reset_go_to_status()
                else:
                    tts_sound(tts_agent, f"{before_text}很抱歉，我无法到达目的地", "zh")
                    response = 'Navigation to ({}, {}) failed.'.format(x, y)
            print("response", response)
        else:
            console = ctx.console
            # Get the live display instance from the console
            #live = console._live

            # Stop the live display temporarily so we can ask for user confirmation
            #live.stop()  # type: ignore

            # Ask for confirmation
            #message = (
            #    Prompt.ask("Do you want to go to the target by dynamic navigation?", choices=["y", "n"], default="y")
            #    .strip()
            #    .lower()
            #)
            #live.start()
            #tts_sound(tts_agent, f"{before_text}你需要我去动态寻找吗", "zh")
            #message = audio_input_yes_or_no(stt_agent)
            message = "n"
            while message != "y" and message != "n":
                tts_sound(tts_agent, f"{before_text}抱歉，我不理解你的回答。你需要我去动态寻找吗", "zh")
                message = audio_input_yes_or_no(stt_agent)

            # If the user does not want to continue, raise a StopExecution exception
            if message != "y":
                response = "Unable to reach the place the user wants to go!"
            else:
                navigation_prompt = task.subtask_description
                #response = await navigation_tools.dynamic_navigation(navigation_prompt)
                response = 'Dynamic navigation completed.'
                tts_sound(tts_agent, f"{before_text}动态寻找已完成", "zh")
        return response

    async def navi_executor(
        step_input: StepInput,
    ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        #task: DelegationTaskModel = step_input.previous_step_content
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        print(f"chat_executor: plan_time: {plan_time:.3f}")

        previous_steps = step_input.get_all_previous_content()
        print("previous_steps:", previous_steps)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")
        #subtask_description = task.subtask_description
        subtask_description = text

        response = await navi_execute(subtask_description)

        yield StepOutput(
            content=response,
        )

    async def navi_check_execute(input_text):
        WorkflowTimePoints.PLAN_END = time.time()
        plan_time = WorkflowTimePoints.PLAN_END - WorkflowTimePoints.PLAN_START
        print(f"chat_executor: plan_time: {plan_time:.3f}")

        global last_chat_text
        print("last_chat_text:", last_chat_text)
        #print("input_text:", "机器人："  + last_chat_text + "用户："  + input_text)
        #input_text_with_chat = "机器人："  + last_chat_text + "用户："  + input_text
        history_text = chat_queue.build_history(max_count=4)
        input_text_with_chat = history_text
        print("input_text_with_chat:", input_text_with_chat)
        run_response = navi_check_agent.run(input_text_with_chat, session_id=str(NAVI_CHECK_SESSION_ID))
        out_text = run_response.content
        print("out_text:", out_text)
        out_text = out_text.split("\n")[0]
        WorkflowTimePoints.NAVI_CHECK_END = time.time()
        navi_check_time = WorkflowTimePoints.NAVI_CHECK_END - WorkflowTimePoints.NAVI_CHECK_START
        print(f"navi_check_execute: navi_check_time: {navi_check_time:.3f}")

        num_entity = 1
        recommand_entity_lst = random.sample(ctx.entity_lst, num_entity)

        if out_text[0] == "A":
            try:
                if len(out_text) > 1:
                    out_text = out_text[1:]
                    if out_text[0].isdigit():
                        entity_idx = int(out_text)
                        # 添加边界检查
                        if entity_idx < len(ctx.entity_lst):
                            out_text = ctx.entity_lst[entity_idx]
                            # 注意：不在这里放入队列，navi_execute 会处理确认询问
                        else:
                            out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
                else:
                    out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
            except (ValueError, IndexError) as exc:
                out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
        elif out_text[0].isdigit():
            entity_idx = int(out_text)
            if entity_idx < len(ctx.entity_lst):
                out_text = ctx.entity_lst[entity_idx]
            else:
                out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
        elif out_text[0] == "B":
            out_text = f"{before_text}抱歉，我不太清楚你想去的地方，我们这里有 {recommand_entity_lst} 等板块可以参观"
            chat_queue.put(out_text, "机器人")
        elif out_text[0] == "D":
            out_text = f"{before_text}请告诉我你想去什么地方？这里有 {recommand_entity_lst} 等板块可以参观"
            chat_queue.put(out_text, "机器人")
        elif out_text[0] == "C":
            n = len(ctx.entity_lst)
            rand_n = random.randint(0, n-1)
            out_text = ctx.entity_lst[rand_n]
            # 注意：不在这里放入队列，navi_execute 会处理确认询问
        print("out_text:", out_text)

        if out_text in ctx.entity_lst:
            response = await navi_execute(out_text)
        else:
            tts_sound(tts_agent, f"{out_text}", "zh")
            response = out_text

        return response

    async def navi_check_executor(step_input):
        WorkflowTimePoints.NAVI_CHECK_START = time.time()
        previous_steps = step_input.get_all_previous_content()
        print("previous_steps:", previous_steps)
        text_lst = previous_steps.split("===")
        assert text_lst[1].replace(" ", "") == "audio_input_step"
        text = text_lst[2].replace("\n", "")

        #think_type = identify_think_type(text)
        #tts_fast(tts_agent, think_type)
        out_text = await navi_check_execute(text)

        return StepOutput(content=f"{out_text}")

    async def game_execute(ctx: Any, location_name: str, entity_name = None):
        # TODO: Navigate to the game location
        entity_lst = await ctx.memory.get_group_names(location_name)
        summary_lst= await ctx.memory.get_group_summary(location_name)
        entity_prompt = build_stt_prompt_by_list(entity_lst)

        # TODO: while循环等待用户提问
        tts_index = -1
        while True:
            # TODO: 语音等待用户提问
            #tts_sound(tts_agent, f"{before_text}请告诉我你想要找什么", "zh")
            if tts_index >= 0:
                wait_with_tts(tts_agent, tts_index)
            if entity_name is None:
                tts_fast(tts_agent, "introguide")
                tts_sound(tts_agent, f"{before_text}您还需要我介绍什么吗？", "zh")
                audio_input_text = audio_input_execute_timeout(stt_agent, 30, entity_prompt)
            else:
                audio_input_text = entity_name
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                continue
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                break
            # TODO: 如果用户结束游戏，则退出循环
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            audio_input_text = audio_input_text.replace("原", "圆")
            print(audio_input_text)

            # 异步调用语音：例如：“我听到了，让我来找一找”、“我听到了，让我来想一想”
            answer_templates = [
                f"{before_text}好嘞，我听到了，让我来介绍一下",
                f"{before_text}好呀，请往这里看，我来给你讲讲",
                f"{before_text}明白了，我来给你介绍这个",
                f"{before_text}没问题，我来详细介绍一下",
                f"{before_text}明白，我来给你讲解一下这个"
            ]
            answer_template = np.random.choice(answer_templates)
            tts_sound(tts_agent, f"{answer_template}", "zh")

            # 添加查询检查
            search_response = search_check_agent.run(audio_input_text)

            search_response_text = search_response.content
            print(f"Agent判断的名称为：{search_response_text}")

            # 根据用户提问调用detect_tool.detect_location，并返回结果
            # audio_input_text = ctx.vlm_openai.prepare_correction_text_message_for_vllm(audio_input_text)
            # 异步执行memory查询
            memory_query_task = asyncio.create_task(ctx.memory.query(query=search_response_text, group_name=location_name, limit=1))
            # 在do_finger之前同步等待memory查询结果
            nodes = await memory_query_task
            memory_node = nodes[0]
            if memory_node.name == '异常结点':
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我无法找到你想要找的物品", "zh")
                continue

            #{round(location[0], 1)}, {round(location[1], 1)}, {round(location[2], 1)}
            #tts_index = tts_sound(tts_agent, f"{before_text}太好了，我找到了！下面我给你介绍{memory_node.name}", "zh")
            description = memory_node.attributes.get('description', '')
            #tts_sound(tts_agent, f"找到了哦，我指给你看，{description}", "zh")
            #tts_long_text_with_stt_stop(tts_agent, description, stt_agent, ctx.robot, before_text)
            tts_long_text(tts_agent, description, stt_agent, ctx.robot, before_text)
            #tts_index = tts_sound(tts_agent, f"{before_text}我介绍完了", "zh")

            summary = memory_node.summary
            print("summary", summary)
            location = detect_tools.detect_location({'task': summary})
            # 判断是否没有识别到或者识别到多个物品
            if location[0] == 0 or location[1] == 0 or location[2] == 0:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我无法找到你想要找的物品", "zh")
                continue
            elif location[0] == -1 or location[1] == -1 or location[2] == -1:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找到了多个相似物品，可以再描述一下吗", "zh")
                continue
            # TODO: 根据location[0], location[1], location[2]，调用ctx.robot.do_finger
            ctx.robot.do_finger(location[0], location[1], location[2])
            do_finger_check = False
            if do_finger_check:
                time.sleep(0.5)
                finger_status = await ctx.robot.do_finger_status_async()
                print(f"finger_status: {finger_status}")
                while finger_status == -1:
                    time.sleep(0.5)
                    finger_status = await ctx.robot.do_finger_status_async()
                    print(f"finger_status: {finger_status}")
                if finger_status == 1:
                    tts_index = tts_sound(tts_agent, f"{before_text}太好了，逆解成功了！", "zh")
                elif finger_status == 0:
                    tts_index = tts_sound(tts_agent, f"{before_text}糟糕，逆解失败了。", "zh")

            if entity_name is not None:
                break

            #input("请按回车键描述衣服")
            #time.sleep(1)
            #tts_index = tts_sound(tts_agent, f"{before_text}您穿的是青色衣服，显得很有活力！", "zh")

            #message = input("请按 y/n 开启或退出下一轮识别：")
            message = "y"
            if message == "y":
                break

    async def game_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await game_execute(ctx, "人形机器人科研场景")
        response = 'Game completed.'
        yield StepOutput(
            content=response,
        )

    navigation_check_step = Step(
        name='navigation_check_step',
        description='Check navigation goal.',
        executor=navi_check_executor,
    )

    navigation_check_step = Step(
        name='navigation_check_step',
        description='Check navigation goal.',
        executor=navi_check_executor,
    )

    async def grab_execute(ctx: Any, yaw=0, pitch=25):
        while True:
            # tts_fast(tts_agent, "introguide")
            #tts_sound(tts_agent, f"{before_text}下面我来展示抓篮子功能，我准备好了！请按回车键继续", "zh")
            #audio_input_text = audio_input_execute_timeout(stt_agent, 120)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            audio_input_text = input("按回车键继续")
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                return
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                return
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            # tts_sound(tts_agent, f"{before_text}有的，请您挑选", "zh")
            await ctx.robot.do_head_async(yaw=0, pitch=25)
            # time.sleep(5)
            await asyncio.sleep(2)
            locations = detect_tools.detect_key_point_pixel({'task': ''})
            #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

            await ctx.robot.do_grab_async(locations[0], locations[1], locations[2])
            # Wait and monitor location changes for 5 seconds
            start_time = time.time()
            old_location = locations
            threshold = 0.2  # Distance threshold for location change detection

            catch_status = await ctx.robot.do_grab_status_async()
            while time.time() - start_time < 30 and catch_status != 1:
                await asyncio.sleep(1)

                new_location = detect_tools.detect_key_point_pixel({'task': ''})
                print(time.time(), new_location[1], old_location[1])
                # Calculate distance between old and new locations
                distance = abs(new_location[1] - old_location[1])
                print(f"distance: {distance}, threshold: {threshold}, new_location: {new_location}, old_location: {old_location}")
                if distance > threshold and new_location[2] - old_location[2] < 0.2 and new_location[0] - old_location[0] > -0.2:
                    print(f"Location changed significantly (distance: {distance}), re-grabbing...")
                    #tts_sound(tts_agent, f"{before_text}唉,有人在捣乱，让我重新定位并抓取一下", "zh")
                    tts_sound(tts_agent, f"{before_text}唉，有人在捣乱！", "zh")
                    # TODO: 发送停止指令
                    await ctx.robot.do_grab_cancel_async()
                    await asyncio.sleep(4)

                    new_location = detect_tools.detect_key_point_pixel({'task': ''})
                    await ctx.robot.do_grab_async(new_location[0], new_location[1], new_location[2])
                    old_location = new_location
                    await asyncio.sleep(4)
                    break
                catch_status = await ctx.robot.do_grab_status_async()
            # tts_sound(tts_agent, f"{before_text}我要开抓", "zh")
            tts_sound(tts_agent, f"{before_text}这是给您的小礼物 ，欢迎您再次来智元参观", "zh")
            await asyncio.sleep(1)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            await asyncio.sleep(1)
            await ctx.robot.do_head_async(yaw=30, pitch=0)
            await asyncio.sleep(3)
            await ctx.robot.do_head_async(yaw=0, pitch=0)
            input("请按回车键开启下一轮抓取测试")

    async def grab_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await grab_execute(ctx)
        response = 'Grab completed.'
        yield StepOutput(
            content=response,
        )

    grab_step = Step(
        name='grab_step',
        description='Grab the object.',
        executor=grab_executor,
    )

    async def handshake_execute(ctx: Any, yaw=0, pitch=25):
        while True:
            # tts_fast(tts_agent, "introguide")
            tts_sound(tts_agent, f"{before_text}下面我来展示握手功能，我准备好了！我等你的命令", "zh")
            audio_input_text = audio_input_execute_timeout(stt_agent, 120)
            print(audio_input_text)
            if audio_input_text == "<REC_TIMEOUT>":
                return
            flag = yes_or_no_quick_match(audio_input_text)
            if flag == "n":
                return
            if "结束" in audio_input_text or "没有" in audio_input_text:
                break
            tts_sound(tts_agent, f"{before_text}好的", "zh")
            # await ctx.robot.do_head_async(yaw=yaw, pitch=pitch)
            # time.sleep(5)
            locations = detect_tools.detect_hand_location()
            #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

            if locations[0] == 0 or locations[1] == 0 or locations[2] == 0:
                tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找不到你的手呢", "zh")
                continue

            await ctx.robot.do_handshake_async(locations[0], locations[1], locations[2] + 0.1)
            input("请按回车键开启下一轮握手测试")

    async def handshake_execute_v2(ctx: Any, yaw=0, pitch=25):
        # await ctx.robot.do_head_async(yaw=yaw, pitch=pitch)
        # time.sleep(5)
        locations = detect_tools.detect_hand_location()
        #tts_sound(tts_agent, f"{before_text}找到了，让我把他拿起来", "zh")

        if locations[0] == 0 or locations[1] == 0 or locations[2] == 0:
            tts_index = tts_sound(tts_agent, f"{before_text}抱歉，我找不到你的手呢", "zh")
        else:
            await ctx.robot.do_handshake_async(locations[0], locations[1], locations[2] + 0.1)

    async def handshake_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await handshake_execute(ctx)
        response = 'Handshake completed.'
        yield StepOutput(
            content=response,
        )

    handshake_step = Step(
        name='handshake_step',
        description='Handshake with man.',
        executor=handshake_executor,
    )

    navigation_step = Step(
        name='navigation_step',
        description='Use static or dynamic navigation to complete the task.',
        executor=navi_executor,
    )

    game_step = Step(
        name='game_step',
        description='Play a game with the user.',
        executor=game_executor,
    )

    chat_step = Step(
        name='chat_step',
        description='Chat with the user.',
        executor=chat_executor,
    )

    vln_step = Step(
        name='vln_step',
        description='Navigation with VLN.',
        executor=vln_executor,
    )

    view_step = Step(
        name='view_step',
        description='View.',
        executor=view_executor,
    )

    move_step = Step(
        name='move_step',
        description='Move.',
        executor=move_executor,
    )

    sound_step = Step(
        name='sound_step',
        description='Sound.',
        executor=sound_executor,
    )

    unknown_step = Step(
        name='unknown_step',
        description='Unkown what to do.',
        executor=unknown_executor,
    )

    async def thank_chat_execute(ctx):
        input("请按回车键夸奖用户")
        await ctx.robot.do_arm_async("比耶")
        tts_sound(tts_agent, f"{before_text}感谢你的夸奖！很高兴能为你导览。", "zh")
        tts_sound(tts_agent, f"{before_text}您今天的青色衣服也太帅了！", "zh")

    async def thank_chat_executor(step_input: StepInput) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        await thank_chat_execute(ctx)
        response = 'Chat completed.'
        yield StepOutput(
            content=response,
        )

    thank_chat_step = Step(
        name='thank_chat_step',
        description='Chat with the user.',
        executor=thank_chat_executor,
    )

    def simple_delegate_task(step_input: StepInput) -> List[Step]:
        task: SimpleDelegationTaskModel = step_input.previous_step_content

        if task.t == 'N':
            #return [navigation_step]
            return [navigation_check_step]
        # elif task.t == 'vision':
        #     return [vision_step]
        elif task.t == 'C':
            return [chat_step]
        elif task.t == 'G':
            return [game_step]
        elif task.t == 'O':
            return [unknown_step]

    def delegate_task(step_input: StepInput) -> List[Step]:
        task: DelegationTaskModel = step_input.previous_step_content

        if task.agent_name == 'navigation':
            return [navigation_step]
        # elif task.agent_name == 'vision':
        #     return [vision_step]
        elif task.agent_name == 'chat':
            return [chat_step]
        elif task.agent_name == 'game':
            return [game_step]

    router_step = Router(
        name='task_router',
        selector=simple_delegate_task,
        choices=[navigation_step, chat_step, game_step],
        description="Delegate the task to the appropriate agent based on the task description.",
    )

    async def task_completion_check(
        step_input: StepInput,
    ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
        original_task = step_input.message or ''
        previous_steps = step_input.get_all_previous_content()

        prompt = dedent("""\
            Task: "{task_description}"
            Previous Steps: {previous_steps}""").format(
            task_description=original_task,
            previous_steps=previous_steps,
        )

        return await task_completion_check_agent.arun(
            prompt, stream=True, stream_intermediate_steps=True,
        )

    def loop_breaker(outputs: List[StepOutput]) -> bool:
        if not outputs:
            return False

        for output in outputs:
            if isinstance(output.content, CompletionCheckModel):
                if output.content.task_completed:
                    return True

        return False

    return Workflow(
        name='RabbitBot Main Workflow',
        description='Workflow for general tasks',
        steps=[
            Loop(
                name='Task Loop',
                steps=[
                    #vln_step,
                    #game_step,
                    #grab_step,
                    #view_step,
                    #handshake_step,
                    #move_step,
                    #sound_step,
                    #thank_chat_step,
                    audio_input_step,
                    #plan_step,
                    #router_step,
                    plan_step_v2,
                    task_completion_check,
                ],
                max_iterations=100,
                end_condition=loop_breaker,
            )
        ],
    )

    # - action: If the prompt mentions "action", to perform an action such as wavehands, greet, ask a question, etc.
    # If the task is to perform an action such as wavehands, greet, ask a question, etc, you should output "action".
    # action_chooser_agent = Agent(
    #     name='Action Chooser Agent',
    #     role='Action chooser',
    #     instructions=dedent("""\
    #         You are an action chooser agent.
    #         Given the action task, you must choose whether to use action such as wavehands, greet to complete the task."""),
    #     response_model=ActionModel,
    #     model=model,
    # )

    # async def action_executor(
    #     step_input: StepInput,
    # ) -> AsyncIterator[Union[WorkflowRunResponseEvent, StepOutput]]:
    #     task: DelegationTaskModel = step_input.previous_step_content
    #     await action_chooser_agent.arun(task.subtask_description)
    #     response = action_chooser_agent.run_response
    #     choice: ActionModel = action_chooser_agent.run_response.content
    #     print(choice.choice)
    #     if choice.choice == 'wavehands':
    #         pass
    #         return StepOutput(
    #             content=choice.choice,
    #             response=response,
    #         )
    #     elif choice.choice == 'greet':
    #         pass
    #         return StepOutput(
    #             content=choice.choice,
    #             response=response,
    #         )

    # action_step = Step(
    #     name='action_step',
    #     description='Use action executor to complete the task.',
    #     executor=action_executor,
    # )
