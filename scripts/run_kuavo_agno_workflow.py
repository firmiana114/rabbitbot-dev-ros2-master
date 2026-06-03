from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
import cv2
import os
from pathlib import Path
import sys
import time
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rabbitbot.agno_agents.workflow import create_main_workflow, guide_opening_speech
from rabbitbot.context import AppContext
from rabbitbot.robots.constants import MoveType
from rabbitbot.tools.sound_agno import tts_sound


TEST_RESOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'tasks', 'resources')


def patch_bot():
    bot_default_cfg = {
        'view_2d.return_value': cv2.imread(os.path.join(TEST_RESOURCE_DIR, 'frig.jpg')),
        'start_record.return_value': None,
        'stop_record.return_value': None,
        'start.return_value': None,
        'stop.return_value': None,
        'go_to.return_value': (0, 0),
        'move_with_jazzy.return_value': None,
        'jazzy_control_sync.return_value': None,
    }
    return patch('rabbitbot.robots.kuavo_auto.KuavoAutonomyBot', spec=True, **bot_default_cfg)


def patch_vln():
    vln_default_cfg = {
        'act.return_value': MoveType.STOP,
        'reset.return_value': None,
    }
    return patch('rabbitbot.provider.VLNAgent', spec=True, **vln_default_cfg)


def _gate_log(stage: str, **fields):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    details = ', '.join(f'{key}={value}' for key, value in fields.items() if value is not None)
    if details:
        print(f'[{timestamp}] workflow启动闸门: stage={stage}, {details}', flush=True)
    else:
        print(f'[{timestamp}] workflow启动闸门: stage={stage}', flush=True)


async def _wait_for_start_gate():
    gate_file = os.getenv('RABBITBOT_WORKFLOW_START_GATE_FILE')
    ready_file = os.getenv('RABBITBOT_WORKFLOW_START_GATE_READY_FILE')
    poll_seconds = float(os.getenv('RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS', '0.05'))
    if not gate_file:
        return

    gate_path = Path(gate_file)
    ready_path = Path(ready_file) if ready_file else None
    start_time = time.perf_counter()
    try:
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        if ready_path:
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            ready_path.write_text(f'ready\npid={os.getpid()}\ntime={datetime.now().isoformat()}\n')
        _gate_log('ready_wait_go', gate_file=gate_path, ready_file=ready_path, poll=f'{poll_seconds:.3f}s')
        while True:
            if gate_path.exists():
                command = gate_path.read_text(errors='ignore').strip()[:32]
                try:
                    gate_path.unlink()
                except FileNotFoundError:
                    pass
                elapsed = time.perf_counter() - start_time
                _gate_log('released', command=command or 'go', elapsed=f'{elapsed:.3f}s')
                return
            await asyncio.sleep(poll_seconds)
    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        _gate_log('error', error_type=type(exc).__name__, error=str(exc), elapsed=f'{elapsed:.3f}s')
        raise


async def main(args):
    with ExitStack() as stack:
        if args.patch:
            stack.enter_context(patch_vln())
        robot_kwargs = {
            'robot_type': 'kuavo',
            'anolog_stick_factor': 0.5,
            'camera_types': ['null'],
        }
        async with AppContext(robot_kwargs) as ctx:
            await _wait_for_start_gate()
            if os.getenv('RABBITBOT_ENABLE_GUIDE_OPENING', '1') == '1':
                await guide_opening_speech(ctx)
            else:
                tts_sound(ctx.tts_agent, f'，，流程开始，请各就各位', 'zh')
                time.sleep(1.0)
            workflow = create_main_workflow(ctx)
            prompt = '等待用户说话'
            try:
                await workflow.aprint_response(
                    prompt,
                    stream=True,
                    stream_intermediate_steps=True,
                    console=ctx.console,
                )
            except KeyboardInterrupt:
                from rabbitbot.tools.sound_agno import audio_input_execute
                audio_input_execute(ctx.stt_agent, 'stop_async')
                ctx.robot.get_camera_info('stop_record', {})
            if os.getenv('RABBITBOT_WORKFLOW_FINISH_SPEECH', '0') == '1':
                tts_sound(ctx.tts_agent, f'，，流程测试完成', 'zh')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='运行 RabbitBot workflow。')
    parser.add_argument('--patch', action='store_true', help='启用机器人和 VLN 的测试替身。')
    args = parser.parse_args()
    asyncio.run(main(args))
