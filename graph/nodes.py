from typing import Optional

from actions.command_validator import ValidationResult, build_command_validator
from actions.execute_task import ExecuteTask
from actions.plan_summary import PlannerSummary
from actions.planner import Planner
from actions.write_code import WriteCode
from config.config import Configs
from db.models.plan_model import Plan
from db.repository.plan_repository import add_plan_to_db, get_planner_by_id
from db.repository.task_repository import add_task_to_plan
from prompts.prompt import DeepPentestPrompt
from roles.collector import Collector
from roles.exploiter import Exploiter
from roles.scanner import Scanner
from server.chat.chat import _chat
from utils.log_common import RoleType, build_logger

from graph.state import PentestGraphState

logger = build_logger()

ROLE_CLASSES = {
    RoleType.COLLECTOR.value: Collector,
    RoleType.SCANNER.value: Scanner,
    RoleType.EXPLOITER.value: Exploiter,
}

ROLE_ORDER = [
    RoleType.COLLECTOR.value,
    RoleType.SCANNER.value,
    RoleType.EXPLOITER.value,
]


def init_role(state: PentestGraphState) -> PentestGraphState:
    session = state["session"]
    console = state["console"]
    max_interactions = state["max_interactions"]
    role_name = session.current_role_name or RoleType.COLLECTOR.value
    role_cls = ROLE_CLASSES.get(role_name, Collector)
    role = role_cls(console=console, max_interactions=max_interactions)

    if session.current_planner_id:
        planner = Planner(
            current_plan=get_planner_by_id(session.current_planner_id),
            init_description=session.init_description,
        )
    else:
        with console.status("[bold green] Initializing DeepPentest Sessions..."):
            context = PlannerSummary(history_planner_ids=session.history_planner_ids).get_summary()
            _, plan_chat_id = _chat(
                query=role.prompt.init_plan_prompt.format(
                    init_description=session.init_description,
                    goal=role.goal,
                    tools=role.tools,
                    context=context,
                )
            )
            _, react_chat_id = _chat(query=role.prompt.init_reasoning_prompt)

        plan = Plan(
            goal=role.goal,
            plan_chat_id=plan_chat_id,
            react_chat_id=react_chat_id,
            current_task_sequence=0,
        )
        plan = add_plan_to_db(plan)
        session.current_planner_id = plan.id
        planner = Planner(current_plan=plan, init_description=session.init_description)
        console.print("Plan Initialized.", style="bold green")

    role.planner = planner
    return {
        "role": role,
        "planner": planner,
        "validator": state.get("validator") or build_command_validator(),
        "interaction_count": 0,
        "validation_retries": 0,
        "previous_rejection": "",
        "next_task": None,
        "finished": False,
    }


def plan_task(state: PentestGraphState) -> PentestGraphState:
    planner = state["planner"]
    next_task = planner.plan()
    return {"next_task": next_task}


def generate_commands(state: PentestGraphState) -> PentestGraphState:
    planner = state["planner"]
    next_task = state.get("next_task")
    if not next_task or planner.current_plan.current_task is None:
        return {"commands": [], "command_instruction": ""}

    if state.get("previous_rejection"):
        next_task = (
            f"{next_task}\n\nThe previous command proposal was rejected by the validator. "
            f"Fix the issue before generating commands.\nValidator feedback: {state['previous_rejection']}"
        )

    writer = WriteCode(next_task=next_task, action=planner.current_plan.current_task.action)
    instruction = writer.generate()
    executor = ExecuteTask(action=planner.current_plan.current_task.action, instruction=instruction, code=[])
    commands = executor.parse_response()

    logger.info(f"generated_commands: {commands}")
    return {
        "command_instruction": instruction,
        "commands": commands,
    }


def validate_commands(state: PentestGraphState) -> PentestGraphState:
    planner = state["planner"]
    validator = state["validator"]
    commands = state.get("commands", [])
    context = {
        "role_name": state["role"].name,
        "next_task": state.get("next_task", ""),
        "init_description": state["session"].init_description,
        "previous_rejection": state.get("previous_rejection", ""),
    }
    result = validator.validate(commands, planner.current_plan.current_task, context)
    logger.info(f"command_validation_result: {result.model_dump()}")
    return {"validation_result": result}


def execute_commands(state: PentestGraphState) -> PentestGraphState:
    planner = state["planner"]
    validation_result = state["validation_result"]
    commands = validation_result.safe_commands if validation_result else []
    executor = ExecuteTask(
        action=planner.current_plan.current_task.action,
        instruction=state.get("command_instruction", ""),
        code=commands,
    )

    state["console"].print("---------- Execute Result ---------", style="bold green")
    result = executor.execute_commands(commands)
    logger.info(result)
    state["console"].print("---------- Execute Result End ---------", style="bold green")

    planner.current_plan.current_task.code = commands
    if len(result) >= 8192:
        result, _ = _chat(query=DeepPentestPrompt.summary_result + str(result), summary=False)
        logger.info(f"result summary: {result}")

    return {
        "execution_result": result,
        "interaction_count": state.get("interaction_count", 0) + 1,
        "validation_retries": 0,
        "previous_rejection": "",
    }


def update_plan(state: PentestGraphState) -> PentestGraphState:
    next_task = state["planner"].update_plan(state.get("execution_result", ""))
    return {"next_task": next_task}


def update_plan_as_failed(state: PentestGraphState) -> PentestGraphState:
    validation = state.get("validation_result") or ValidationResult(reason="Command validation failed.")
    commands = state.get("commands", [])
    result = (
        "Command validation failed before execution.\n"
        f"Reason: {validation.reason}\n"
        f"Suggestion: {validation.suggestion or ''}\n"
        f"Rejected commands: {commands}"
    )
    planner = state["planner"]
    if planner.current_plan.current_task is not None:
        planner.current_plan.current_task.code = commands
    next_task = planner.update_plan(result)
    return {
        "execution_result": result,
        "next_task": next_task,
        "interaction_count": state.get("interaction_count", 0) + 1,
        "validation_retries": 0,
        "previous_rejection": "",
    }


def record_validation_retry(state: PentestGraphState) -> PentestGraphState:
    validation = state.get("validation_result") or ValidationResult(reason="Command validation failed.")
    feedback = validation.reason
    if validation.suggestion:
        feedback = f"{feedback}\nSuggestion: {validation.suggestion}"
    return {
        "validation_retries": state.get("validation_retries", 0) + 1,
        "previous_rejection": feedback,
    }


def advance_role(state: PentestGraphState) -> PentestGraphState:
    session = state["session"]
    planner = state["planner"]
    if planner.current_plan is not None:
        add_task_to_plan(planner.current_plan.tasks)

    next_role = _next_role_name(session.current_role_name)
    if next_role is None:
        return {"finished": True}

    session.history_planner_ids.append(planner.current_plan.id)
    session.current_role_name = next_role
    session.current_planner_id = ""
    return {
        "finished": False,
        "next_task": None,
        "interaction_count": 0,
        "validation_retries": 0,
        "previous_rejection": "",
    }


def _next_role_name(current_role_name: Optional[str]) -> Optional[str]:
    if current_role_name not in ROLE_ORDER:
        return ROLE_ORDER[0]
    index = ROLE_ORDER.index(current_role_name)
    if index + 1 >= len(ROLE_ORDER):
        return None
    return ROLE_ORDER[index + 1]


def route_after_plan(state: PentestGraphState) -> str:
    if state.get("next_task") is None:
        return "advance_role"
    if state.get("interaction_count", 0) >= state.get("max_interactions", 0):
        return "advance_role"
    return "generate_commands"


def route_after_validation(state: PentestGraphState) -> str:
    result = state.get("validation_result")
    if result and result.approved:
        return "execute_commands"

    config = getattr(Configs.basic_config, "command_validator", {}) or {}
    max_retries = int(config.get("max_retries", 2))
    if result and result.suggestion and state.get("validation_retries", 0) < max_retries:
        return "record_validation_retry"
    return "update_plan_as_failed"


def route_after_advance_role(state: PentestGraphState) -> str:
    if state.get("finished"):
        return "finish"
    return "init_role"
