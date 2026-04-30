from rabbitbot.prompts import get_prompt_provider
from .utils import prepend_system_message

from qwen_agent.agents import FnCallAgent
from qwen_agent.llm.schema import Message
from qwen_agent.log import logger

from typing import List, Iterator
import copy


class MapAgent(FnCallAgent):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pp = get_prompt_provider('navigation')

    def _run(self, messages: List[Message], **kwargs) -> Iterator[List[Message]]:
        messages = copy.deepcopy(messages)
        logger.info('Finding target in memory...')
        from rabbitbot.provider import get_memory_layer
        with get_memory_layer() as memory:
            nodes = memory.query_sync(query=messages[-1].content, limit=5)
        entities = [{
            'name': node.name,
            'description': node.summary,
            'location': node.attributes.get('location', ''),
        } for node in nodes]
        logger.info(f'Found {len(entities)} entities in memory: {entities}')
        prepend_system_message(messages, self._pp.system_message, entities=entities)
        for response in super()._run(messages, **kwargs):
            yield response
