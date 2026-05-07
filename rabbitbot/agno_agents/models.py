from pydantic import BaseModel, Field
from typing import Literal


class StaticOrDynamicNavigationModel(BaseModel):
    choice: Literal['static', 'dynamic']


class SimpleDelegationTaskModel(BaseModel):
    t: Literal['N', 'C', 'V', 'O'] = Field(
        description='The agent to which the subtask should be delegated.'
    )

class DelegationTaskModel(BaseModel):
    agent_name: Literal['navigation', 'chat', 'game'] = Field(
        description='The agent to which the subtask should be delegated.'
    )
    subtask_description: str = Field(
        description='The description of the subtask to be delegated.'
    )

class CompletionCheckModel(BaseModel):
    task_completed: bool
