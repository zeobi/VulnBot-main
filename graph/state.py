from typing import Any, Optional, TypedDict

from actions.planner import Planner
from db.models.session_model import Session
from roles.role import Role


class PentestGraphState(TypedDict, total=False):
    session: Session
    console: Any
    max_interactions: int
    max_steps: Optional[int]
    benchmark_run_id: Optional[str]
    role: Role
    planner: Planner
    next_task: Optional[str]
    command_instruction: str
    commands: list[str]
    execution_result: str
    interaction_count: int
    total_interaction_count: int
    trace: list[dict[str, Any]]
    finished: bool
