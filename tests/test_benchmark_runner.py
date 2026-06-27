import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from benchmarks.autopenbench_adapter import AutoPenBenchTask
from benchmarks.lifecycle import LabConnection
from benchmarks.runner import AutoPenBenchRunner


class FakeAdapter:
    root = "."

    def __init__(self, task):
        self.task = task

    def get_task(self, task_id):
        return self.task

    def to_vulnbot_description(self, task, max_steps=24):
        return f"Authorized task {task.task_id}; max steps {max_steps}"


class BenchmarkRunnerTests(unittest.TestCase):
    def test_full_orchestration_persists_and_cleans_up(self):
        task = AutoPenBenchTask(
            task_id="autopenbench:in-vitro/access_control/vm0",
            level="in-vitro",
            category="access_control",
            index=0,
            task="Find the flag",
            target="in-vitro_access_control_vm0",
            vulnerability="",
            flag="FLAG",
        )
        lifecycle = Mock()
        lifecycle.reset.return_value = LabConnection()
        scorer = Mock()
        scorer.score.return_value = {"success": True, "score": 1.0, "steps_executed": 1}
        graph_executor = Mock(
            return_value={
                "session": {
                    "id": None,
                    "name": None,
                    "init_description": "task",
                    "current_role_name": "Collection",
                    "current_planner_id": "",
                    "history_planner_ids": [],
                },
                "trace": [{"step_index": 1, "commands": ["id"], "observation": "FLAG"}],
            }
        )
        runner = AutoPenBenchRunner(
            FakeAdapter(task),
            lifecycle=lifecycle,
            scorer=scorer,
            graph_executor=graph_executor,
        )

        with (
            patch.object(runner, "preflight"),
            patch.object(runner, "_run_metadata", return_value={}),
            patch("benchmarks.runner.create_tables"),
            patch("benchmarks.runner.upsert_benchmark_tasks"),
            patch("benchmarks.runner.create_benchmark_run", return_value=SimpleNamespace(id="run1")),
            patch("benchmarks.runner.update_benchmark_run"),
            patch("benchmarks.runner.replace_benchmark_steps") as replace_steps,
            patch("benchmarks.runner.add_session_to_db", return_value="session1"),
        ):
            outcome = runner.run_task(task.task_id, max_steps=4, timeout=5)

        self.assertEqual(outcome.status, "completed", outcome.error)
        self.assertIn("started_at", outcome.score)
        self.assertIn("finished_at", outcome.score)
        self.assertGreaterEqual(outcome.score["duration_seconds"], 0)
        replace_steps.assert_called_once()
        lifecycle.cleanup.assert_called_once()
        scorer.score.assert_called_once()

    def test_keyboard_interrupt_is_persisted_as_a_failed_run(self):
        task = AutoPenBenchTask(
            task_id="autopenbench:in-vitro/access_control/vm0",
            level="in-vitro",
            category="access_control",
            index=0,
            task="Find the flag",
            target="in-vitro_access_control_vm0",
            vulnerability="",
            flag="FLAG",
        )
        lifecycle = Mock()
        lifecycle.reset.side_effect = KeyboardInterrupt()
        runner = AutoPenBenchRunner(FakeAdapter(task), lifecycle=lifecycle)

        with (
            patch.object(runner, "preflight"),
            patch.object(runner, "_run_metadata", return_value={}),
            patch("benchmarks.runner.create_tables"),
            patch("benchmarks.runner.upsert_benchmark_tasks"),
            patch("benchmarks.runner.create_benchmark_run", return_value=SimpleNamespace(id="run1")),
            patch("benchmarks.runner.update_benchmark_run") as update_run,
        ):
            outcome = runner.run_task(task.task_id, max_steps=4, timeout=5)

        self.assertEqual(outcome.status, "failed")
        self.assertIn("KeyboardInterrupt", outcome.error)
        self.assertIn("started_at", outcome.score)
        self.assertIn("finished_at", outcome.score)
        self.assertGreaterEqual(outcome.score["duration_seconds"], 0)
        self.assertEqual(update_run.call_args_list[-1].kwargs["status"], "failed")


if __name__ == "__main__":
    unittest.main()
