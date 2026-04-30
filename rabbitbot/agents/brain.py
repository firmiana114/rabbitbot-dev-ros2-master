from qwen_agent.agents import Router, Agent
from qwen_agent.llm.schema import CONTENT, ROLE, Message, ASSISTANT, USER, FUNCTION, NAME
from qwen_agent.llm import BaseChatModel
from qwen_agent.log import logger
from qwen_agent.utils.utils import format_as_text_message

from typing import List, Iterator, Union, Dict, Optional, Literal
import copy

from rabbitbot.robots import get_robot
from rabbitbot.prompts import get_prompt_provider
from .utils import prepend_system_message


class Brain(Agent):

    def __init__(self,
                 llm: Optional[Union[Dict, BaseChatModel]] = None,
                 agents: Optional[List[Agent]] = None,
                 max_steps: int = 8,
                 **kwargs):
        super().__init__(llm=llm, **kwargs)

        self.router = Router(
            llm=llm,
            agents=agents,
        )
        self.max_steps = max_steps
        self._pp = get_prompt_provider('brain')

    def _check_completion(self, output: List[Message]):
        return output[-1].content == self._pp.complete_message

    def _extract_user_prompts(self, messages: List[Message]):
        for msg in reversed(messages):
            if msg.role == USER:
                # TODO: deal with other content types
                return format_as_text_message(msg, add_upload_info=False).content
        return ''

    def _run(self, messages: List[Message], lang: Literal['en', 'zh'] = 'en', **kwargs) -> Iterator[List[Message]]:
        messages = copy.deepcopy(messages)
        user_prompt = self._extract_user_prompts(messages)

        extra_generate_cfg = {'lang': lang}
        if kwargs.get('seed') is not None:
            extra_generate_cfg['seed'] = kwargs['seed']

        cmu_robot = get_robot()
        cmu_robot.start_record()

        response = []
        for _ in range(self.max_steps):
            prepend_system_message(messages, self._pp.system_message, command=user_prompt)
            logger.info(messages)
            output_stream = self._call_llm(messages=messages,
                                           functions=[func.function for func in self.function_map.values()],
                                           extra_generate_cfg=extra_generate_cfg)
            output: List[Message] = []
            for output in output_stream:
                if output:
                    yield response + output
            if output:
                response.extend(output)
                if self._check_completion(output):
                    break
                messages.extend(output)
                command = copy.deepcopy(output)
                assert len(command) >= 1 and command[0][ROLE] == ASSISTANT
                command[0][ROLE] = USER
                for rsp in self.router.run(messages=command):
                    yield response + rsp
                response.extend(rsp)
                logger.info(response)
                msg = Message(
                    role=FUNCTION,
                    name=rsp[-1][NAME],
                    content=rsp[-1][CONTENT],
                )
                messages.append(msg)

        cmu_robot.stop_record()
        yield response
