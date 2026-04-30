from rabbitbot.robots import create_robot
from rabbitbot.provider import (
    create_vlm_openai,
    create_vln,
    #create_memory_layer,
    create_memory_agent,
    create_agno_model,
    create_agno_quant_model,
    create_robot_agent,
    create_stt_agent,
    create_tts_agent,
)
from rich.console import Console
import os


class AppContext:
    """
    Context manager for the application and agents, ensuring proper initialization and cleanup.
    """
    def __init__(
        self,
        robot_kwargs: dict = None,
        workspace: str = None,
        with_memory: bool = True,
        with_robot_agent: bool = True
    ):
        if robot_kwargs is None:
            robot_kwargs = {}
        workspace = workspace or os.getenv('RABBITBOT_WORKSPACE', 'workspace')
        self.workspace = os.path.abspath(workspace)
        #self.robot = create_robot(
        #    image_buffer_dir=os.path.join(self.workspace, 'robot'),
        #    **robot_kwargs,
        #)
        self.robot = create_robot_agent()
        self.vln = create_vln()
        if with_memory:
            #self.memory = create_memory_layer()
            self.memory = create_memory_agent()
            self.vlm_openai = create_vlm_openai()
        self.agno_model = create_agno_model()
        self.agno_quant_model = create_agno_quant_model()
        self.stt_agent = create_stt_agent()
        self.tts_agent = create_tts_agent()
        self.console = Console()

    async def __aenter__(self):
        self.robot.__enter__()
        if hasattr(self, 'memory'):
            #self.entity_lst = await self.memory.get_all_names()
            #all_name = "展点"
            #target_group_name = "教育场景"
            all_name = "展点"
            target_group_name = "人形机器人科研场景"
            self.entity_lst = await self.memory.get_group_names(all_name)
            self.education_entity_lst = await self.memory.get_group_names(target_group_name)
            self.education_summary_lst = await self.memory.get_group_summary(target_group_name)
            await self.memory.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.robot.__exit__(exc_type, exc_value, traceback)
        if hasattr(self, 'memory'):
            await self.memory.__aexit__(exc_type, exc_value, traceback)
