from __future__ import annotations

import uuid
from typing import Iterable, Optional

from benchmarks.autopenbench_adapter import AutoPenBenchTask
from db.models.benchmark_model import (
    BenchmarkRun,
    BenchmarkRunModel,
    BenchmarkStep,
    BenchmarkStepModel,
    BenchmarkTask,
    BenchmarkTaskModel,
)
from db.session import with_session


def _to_model(task: AutoPenBenchTask) -> BenchmarkTaskModel:
    return BenchmarkTaskModel(
        id=task.task_id,
        benchmark="autopenbench",
        level=task.level,
        category=task.category,
        task_index=task.index,
        target=task.target,
        vulnerability=task.vulnerability,
        alias=task.alias,
        task_text=task.task,
        flag=task.flag,
        command_milestones=list(task.command_milestones),
        stage_milestones=list(task.stage_milestones),
    )


@with_session
def upsert_benchmark_tasks(session, tasks: Iterable[AutoPenBenchTask]) -> int:
    count = 0
    for task in tasks:
        session.merge(_to_model(task))
        count += 1
    return count


@with_session
def list_benchmark_tasks(session, benchmark: str = "autopenbench") -> list[BenchmarkTask]:
    rows = (
        session.query(BenchmarkTaskModel)
        .filter(BenchmarkTaskModel.benchmark == benchmark)
        .order_by(BenchmarkTaskModel.level, BenchmarkTaskModel.category, BenchmarkTaskModel.task_index)
        .all()
    )
    return [BenchmarkTask.model_validate(row) for row in rows]


@with_session
def create_benchmark_run(
    session,
    benchmark_task_id: str,
    model_name: str,
    max_steps: int,
) -> BenchmarkRun:
    row = BenchmarkRunModel(
        id=uuid.uuid4().hex,
        benchmark_task_id=benchmark_task_id,
        model_name=model_name,
        status="created",
        score={"max_steps": max_steps},
    )
    session.add(row)
    session.flush()
    return BenchmarkRun.model_validate(row)


@with_session
def update_benchmark_run(
    session,
    run_id: str,
    *,
    status: Optional[str] = None,
    score: Optional[dict] = None,
    session_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> BenchmarkRun:
    row = session.query(BenchmarkRunModel).filter_by(id=run_id).one()
    if status is not None:
        row.status = status
    if score is not None:
        row.score = score
    if session_id is not None:
        row.session_id = session_id
    if notes is not None:
        row.notes = notes
    session.flush()
    return BenchmarkRun.model_validate(row)


@with_session
def replace_benchmark_steps(session, run_id: str, trace: list[dict]) -> int:
    session.query(BenchmarkStepModel).filter_by(run_id=run_id).delete(synchronize_session=False)
    rows = [
        BenchmarkStepModel(
            id=uuid.uuid4().hex,
            run_id=run_id,
            step_index=int(step.get("step_index", index + 1)),
            role=step.get("role"),
            task=step.get("task"),
            commands=list(step.get("commands") or []),
            approved=bool(step.get("approved")),
            validation=step.get("validation"),
            observation=step.get("observation", ""),
        )
        for index, step in enumerate(trace)
    ]
    session.add_all(rows)
    return len(rows)


@with_session
def append_benchmark_step(session, run_id: str, step: dict) -> BenchmarkStep:
    row = BenchmarkStepModel(
        id=uuid.uuid4().hex,
        run_id=run_id,
        step_index=int(step.get("step_index", 1)),
        role=step.get("role"),
        task=step.get("task"),
        commands=list(step.get("commands") or []),
        approved=bool(step.get("approved")),
        validation=step.get("validation"),
        observation=step.get("observation", ""),
    )
    session.add(row)
    session.flush()
    return BenchmarkStep.model_validate(row)


@with_session
def get_benchmark_run(session, run_id: str) -> tuple[BenchmarkRun, list[BenchmarkStep]]:
    run = session.query(BenchmarkRunModel).filter_by(id=run_id).one()
    steps = (
        session.query(BenchmarkStepModel)
        .filter_by(run_id=run_id)
        .order_by(BenchmarkStepModel.step_index)
        .all()
    )
    return BenchmarkRun.model_validate(run), [BenchmarkStep.model_validate(step) for step in steps]


@with_session
def list_benchmark_runs(
    session,
    *,
    task_id: Optional[str] = None,
    limit: int = 20,
) -> list[BenchmarkRun]:
    query = session.query(BenchmarkRunModel)
    if task_id:
        query = query.filter(BenchmarkRunModel.benchmark_task_id == task_id)
    rows = query.order_by(BenchmarkRunModel.create_time.desc()).limit(limit).all()
    return [BenchmarkRun.model_validate(row) for row in rows]
