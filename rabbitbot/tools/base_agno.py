from agno.tools.toolkit import Toolkit
from agno.utils.log import logger

from typing import Any
import os


class BaseToolkit(Toolkit):
    """
    Base class for toolkits that can be used with the RabbitBot framework.
    This class provides a structure for creating toolkits with configurable tools.
    It also accepts AppContext to access the application context.
    """

    def __init__(self, ctx: Any, name: str = 'toolkit', **kwargs):
        self.ctx = ctx
        self.workspace = os.path.join(self.ctx.workspace, 'tools', name)
        logger.info(f"Initializing Toolkit {name} with workspace: {self.workspace}")
        os.makedirs(self.workspace, exist_ok=True)
        super().__init__(name=name, **kwargs)
