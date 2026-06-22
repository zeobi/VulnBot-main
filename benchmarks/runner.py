from __future__ import annotations

import multiprocessing as mp
import os
import queue
import subprocess
import time
import traceback
from dataclasses import dataclass
from typing import Callable

from rich.console import Console

from actions.shell_manager import ShellManager
from benchmarks.autopenbench_adapter import AutoPenBenchAdapter, AutoPenBenchTask
from benchmarks.lifecycle import AutoPenBenchLifecycle, LabConnection
from benchmarks.scoring import BenchmarkScorer
from config.config import Configs
from db.models.session_model import Session
from db.repository.benchmark_repository import (
    create_benchmark_run,
    get_benchmark_run,
    replace_benchmark_steps,
    update_benchmark_run,
    upsert_benchmark_tasks,
)
from db.repository.session_repository import add_session_to_db
from db.session import create_tables
from config.config import is_valid_env_var_name, resolve_llm_api_key
from utils.log_common import RoleType


class BenchmarkRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchmarkOutcome:
    run_id: str
    task_id: str
    status: str
    score: dict
    session_id: str | None = None
    error: str | None = None


GraphExecutor = Callable[[Session, int, int, LabConnection, float, str], dict]
ROLE_COUNT = 3


class AutoPenBenchRunner:
    def __init__(
        self,
        adapter: AutoPenBenchAdapter,
        *,
        lifecycle: AutoPenBenchLifecycle | None = None,
        scorer: BenchmarkScorer | None = None,
        graph_executor: GraphExecutor | None = None,
    ):
        self.adapter = adapter
        self.lifecycle = lifecycle or AutoPenBenchLifecycle(adapter.root)
        self.scorer = scorer or BenchmarkScorer()
        self.graph_executor = graph_executor or execute_graph_subprocess

    def preflight(self, task: AutoPenBenchTask) -> None:
        config = Configs.llm_config
        if not config.llm_model_name:
            raise BenchmarkRunError("llm_model_name is empty.")
        if not config.base_url:
            raise BenchmarkRunError("The configured LLM base_url is empty.")
        if config.llm_model == "openai" and not resolve_llm_api_key(config):
            key_hint = (
                config.api_key_env
                if is_valid_env_var_name(config.api_key_env)
                else "api_key or a valid api_key_env"
            )
            raise BenchmarkRunError(
                f"No LLM API key is configured. Set {key_hint} in the current shell."
            )
        self.lifecycle.preflight(task)

    def run_task(
        self,
        task_id: str,
        *,
        max_steps: int = 24,
        max_interactions: int = 8,
        timeout: float = 3600.0,
        build: bool = True,
    ) -> BenchmarkOutcome:
        if max_steps < ROLE_COUNT:
            raise ValueError("max_steps must be at least 3 so every role can execute")
        if max_interactions <= 0:
            raise ValueError("max_interactions must be greater than zero")
        task = self.adapter.get_task(task_id)
        create_tables()
        upsert_benchmark_tasks([task])
        run = create_benchmark_run(
            task.task_id,
            Configs.llm_config.llm_model_name,
            max_steps,
        )
        trace: list[dict] = []
        session_id = None
        lab_started = False

        try:
            self.preflight(task)
            update_benchmark_run(run.id, status="preparing")
            lab_started = True
            connection = self.lifecycle.reset(task, build=build)
            update_benchmark_run(run.id, status="running")

            session = Session(
                current_role_name=RoleType.COLLECTOR.value,
                init_description=self.adapter.to_vulnbot_description(task, max_steps=max_steps),
                current_planner_id="",
                history_planner_ids=[],
            )
            result = self.graph_executor(
                session, max_steps, max_interactions, connection, timeout, run.id
            )
            trace = list(result.get("trace") or [])
            replace_benchmark_steps(run.id, trace)

            final_session = Session.model_validate(result.get("session") or session.model_dump())
            final_session.name = f"benchmark:{task.task_id}:{run.id[:8]}"
            session_id = add_session_to_db(final_session)

            score = self.scorer.score(task, trace, max_steps=max_steps)
            score["metadata"] = self._run_metadata()
            update_benchmark_run(
                run.id,
                status="completed",
                score=score,
                session_id=session_id,
            )
            return BenchmarkOutcome(
                run_id=run.id,
                task_id=task.task_id,
                status="completed",
                score=score,
                session_id=session_id,
            )
        except (Exception, KeyboardInterrupt) as exc:
            if not trace:
                try:
                    _, stored_steps = get_benchmark_run(run.id)
                    trace = [step.model_dump(mode="json") for step in stored_steps]
                except Exception:
                    trace = []
            if trace:
                replace_benchmark_steps(run.id, trace)
            error = f"{exc.__class__.__name__}: {exc}"
            failure_score = {
                "success": False,
                "score": 0.0,
                "steps_executed": len(trace),
                "max_steps": max_steps,
                "metadata": self._run_metadata(),
            }
            update_benchmark_run(
                run.id,
                status="failed",
                score=failure_score,
                session_id=session_id,
                notes=error,
            )
            return BenchmarkOutcome(
                run_id=run.id,
                task_id=task.task_id,
                status="failed",
                score=failure_score,
                session_id=session_id,
                error=error,
            )
        finally:
            ShellManager.get_instance().clear_configuration()
            if lab_started:
                try:
                    self.lifecycle.cleanup(task, check=False)
                except Exception:
                    pass

    def _run_metadata(self) -> dict:
        project_root = Configs.PENTEST_ROOT
        return {
            "model_provider": Configs.llm_config.llm_model,
            "model_name": Configs.llm_config.llm_model_name,
            "temperature": 0,
            "vulnbot_revision": _git_revision(project_root),
            "vulnbot_dirty": _git_dirty(project_root),
            "autopenbench_revision": _git_revision(self.adapter.root),
            "autopenbench_dirty": _git_dirty(self.adapter.root),
            "kali_profile": os.environ.get("VULNBOT_KALI_PROFILE", "full"),
        }


def execute_graph_subprocess(
    session: Session,
    max_steps: int,
    max_interactions: int,
    connection: LabConnection,
    timeout: float,
    run_id: str,
) -> dict:
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_graph_worker,
        args=(
            session.model_dump(),
            max_steps,
            max_interactions,
            connection,
            run_id,
            result_queue,
        ),
        name=f"VulnBot benchmark {session.current_role_name}",
    )
    process.start()
    try:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.terminate()
                process.join(10)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                raise TimeoutError(f"Benchmark exceeded the {timeout:.0f}s timeout")
            try:
                result = result_queue.get(timeout=min(0.5, remaining))
                break
            except queue.Empty:
                if not process.is_alive():
                    raise BenchmarkRunError(
                        f"Benchmark worker exited without a result (exit code {process.exitcode})"
                    )
        process.join(10)
        if not result.get("ok"):
            raise BenchmarkRunError(result.get("error") or "Benchmark worker failed")
        return result
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        result_queue.close()


def _graph_worker(
    session_data: dict,
    max_steps: int,
    max_interactions: int,
    connection: LabConnection,
    run_id: str,
    result_queue,
) -> None:
    previous_mode = os.environ.get("MODE")
    previous_temperature = os.environ.get("TEMPERATURE")
    manager = ShellManager.get_instance()
    try:
        os.environ["MODE"] = "auto"
        os.environ["TEMPERATURE"] = "0"
        from graph.workflow import run_pentest_graph

        manager.configure(
            {
                "hostname": connection.host,
                "port": connection.port,
                "username": connection.username,
                "password": connection.password,
            }
        )
        session = Session.model_validate(session_data)
        final_state = run_pentest_graph(
            session=session,
            console=Console(),
            max_interactions=max_interactions,
            max_steps=max_steps,
            benchmark_run_id=run_id,
        )
        final_session = final_state.get("session", session)
        result_queue.put(
            {
                "ok": True,
                "session": final_session.model_dump(),
                "trace": final_state.get("trace", []),
                "steps_executed": final_state.get("total_interaction_count", 0),
            }
        )
    except Exception:
        result_queue.put({"ok": False, "error": traceback.format_exc()})
    finally:
        manager.clear_configuration()
        if previous_mode is None:
            os.environ.pop("MODE", None)
        else:
            os.environ["MODE"] = previous_mode
        if previous_temperature is None:
            os.environ.pop("TEMPERATURE", None)
        else:
            os.environ["TEMPERATURE"] = previous_temperature


def _git_revision(path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_dirty(path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return bool(result.stdout.strip()) if result.returncode == 0 else None
