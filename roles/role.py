from typing import Any, ClassVar

from pydantic import Field, BaseModel

from actions.planner import Planner


class Role(BaseModel):
    """Configuration shared by each role in the LangGraph workflow."""

    name: str
    goal: str
    tools: str
    prompt: ClassVar
    max_interactions: int = 5
    planner: Planner = Field(default_factory=Planner)
    console: Any = None
