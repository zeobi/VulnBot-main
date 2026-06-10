from typing import Any, Optional, TypedDict

from actions.command_validator import ValidationResult
from actions.planner import Planner
from db.models.session_model import Session
from roles.role import Role


class PentestGraphState(TypedDict, total=False):
    session: Session
    console: Any
    max_interactions: int
    role: Role
    planner: Planner
    validator: Any
    next_task: Optional[str]
    command_instruction: str
    commands: list[str]
    validation_result: Optional[ValidationResult]
    execution_result: str
    interaction_count: int
    validation_retries: int
    previous_rejection: str
    finished: bool
