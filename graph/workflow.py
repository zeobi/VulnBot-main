from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    advance_role,
    execute_commands,
    generate_commands,
    init_role,
    plan_task,
    record_validation_retry,
    route_after_advance_role,
    route_after_plan,
    route_after_validation,
    update_plan,
    update_plan_as_failed,
    validate_commands,
)
from graph.state import PentestGraphState


def finish(state: PentestGraphState) -> PentestGraphState:
    return state


def build_pentest_graph():
    graph = StateGraph(PentestGraphState)
    graph.add_node("init_role", init_role)
    graph.add_node("plan_task", plan_task)
    graph.add_node("generate_commands", generate_commands)
    graph.add_node("validate_commands", validate_commands)
    graph.add_node("record_validation_retry", record_validation_retry)
    graph.add_node("execute_commands", execute_commands)
    graph.add_node("update_plan", update_plan)
    graph.add_node("update_plan_as_failed", update_plan_as_failed)
    graph.add_node("advance_role", advance_role)
    graph.add_node("finish", finish)

    graph.add_edge(START, "init_role")
    graph.add_edge("init_role", "plan_task")
    graph.add_conditional_edges(
        "plan_task",
        route_after_plan,
        {
            "generate_commands": "generate_commands",
            "advance_role": "advance_role",
        },
    )
    graph.add_edge("generate_commands", "validate_commands")
    graph.add_conditional_edges(
        "validate_commands",
        route_after_validation,
        {
            "execute_commands": "execute_commands",
            "record_validation_retry": "record_validation_retry",
            "update_plan_as_failed": "update_plan_as_failed",
        },
    )
    graph.add_edge("record_validation_retry", "generate_commands")
    graph.add_edge("execute_commands", "update_plan")
    graph.add_conditional_edges(
        "update_plan",
        route_after_plan,
        {
            "generate_commands": "generate_commands",
            "advance_role": "advance_role",
        },
    )
    graph.add_conditional_edges(
        "update_plan_as_failed",
        route_after_plan,
        {
            "generate_commands": "generate_commands",
            "advance_role": "advance_role",
        },
    )
    graph.add_conditional_edges(
        "advance_role",
        route_after_advance_role,
        {
            "init_role": "init_role",
            "finish": "finish",
        },
    )
    graph.add_edge("finish", END)
    return graph.compile()


def run_pentest_graph(session, console, max_interactions: int):
    app = build_pentest_graph()
    return app.invoke(
        {
            "session": session,
            "console": console,
            "max_interactions": max_interactions,
        },
        config={"recursion_limit": max(100, max_interactions * 20)},
    )
