from datetime import datetime, timezone
from typing import Optional

from actions.execute_task import ExecuteTask
from actions.plan_summary import PlannerSummary
from actions.planner import Planner
from actions.write_code import WriteCode
from db.models.plan_model import Plan
from db.repository.plan_repository import add_plan_to_db, get_planner_by_id
from db.repository.task_repository import add_task_to_plan
from prompts.prompt import DeepPentestPrompt
from roles.collector import Collector
from roles.exploiter import Exploiter
from roles.scanner import Scanner
from llm.chat import _chat
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


def _trace_entry(
    state: PentestGraphState,
    *,
    observation: str,
    commands: list[str],
) -> dict:
    planner = state["planner"]
    task = planner.current_plan.current_task
    return {
        "step_index": state.get("total_interaction_count", 0) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": state["role"].name,
        "task": task.instruction if task is not None else state.get("next_task", ""),
        "commands": list(commands),
        "approved": True,
        "validation": None,
        "observation": observation,
    }


def _persist_trace_entry(state: PentestGraphState, entry: dict) -> None:
    run_id = state.get("benchmark_run_id")
    if run_id:
        from db.repository.benchmark_repository import append_benchmark_step

        append_benchmark_step(run_id, entry)


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
        "interaction_count": 0,
        "total_interaction_count": state.get("total_interaction_count", 0),
        "trace": state.get("trace", []),
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

    writer = WriteCode(next_task=next_task, action=planner.current_plan.current_task.action)
    instruction = writer.generate()
    executor = ExecuteTask(action=planner.current_plan.current_task.action, instruction=instruction, code=[])
    commands = executor.parse_response()

    logger.info(f"generated_commands: {commands}")
    return {
        "command_instruction": instruction,
        "commands": commands,
    }


def execute_commands(state: PentestGraphState) -> PentestGraphState:
    planner = state["planner"]
    commands = state.get("commands", [])
    executor = ExecuteTask(
        action=planner.current_plan.current_task.action,
        instruction=state.get("command_instruction", ""),
        code=commands,
    )

    state["console"].print("---------- Execute Result ---------", style="bold green")
    raw_result = executor.execute_commands(commands)
    result = raw_result
    logger.info(raw_result)
    state["console"].print("---------- Execute Result End ---------", style="bold green")

    planner.current_plan.current_task.code = commands
    if len(result) >= 8192:
        result, _ = _chat(query=DeepPentestPrompt.summary_result + str(result), summary=False)
        logger.info(f"result summary: {result}")

    trace_entry = _trace_entry(
        state,
        observation=raw_result,
        commands=commands,
    )
    _persist_trace_entry(state, trace_entry)
    return {
        "execution_result": result,
        "interaction_count": state.get("interaction_count", 0) + 1,
        "total_interaction_count": state.get("total_interaction_count", 0) + 1,
        "trace": [
            *state.get("trace", []),
            trace_entry,
        ],
    }


def update_plan(state: PentestGraphState) -> PentestGraphState:
    next_task = state["planner"].update_plan(state.get("execution_result", ""))
    return {"next_task": next_task}


def advance_role(state: PentestGraphState) -> PentestGraphState:
    session = state["session"]
    planner = state["planner"]
    if planner.current_plan is not None:
        add_task_to_plan(planner.current_plan.tasks)

    max_steps = state.get("max_steps")
    if max_steps is not None and state.get("total_interaction_count", 0) >= max_steps:
        return {"finished": True}

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
    max_steps = state.get("max_steps")
    if max_steps is not None and state.get("total_interaction_count", 0) >= max_steps:
        return "advance_role"
    if state.get("interaction_count", 0) >= state.get("max_interactions", 0):
        return "advance_role"
    return "generate_commands"


def route_after_advance_role(state: PentestGraphState) -> str:
    if state.get("finished"):
        return "finish"
    return "init_role"
