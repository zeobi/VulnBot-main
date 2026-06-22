import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from benchmarks.autopenbench_adapter import AutoPenBenchTask
from db.repository.benchmark_repository import (
    create_benchmark_run,
    get_benchmark_run,
    replace_benchmark_steps,
    upsert_benchmark_tasks,
)
from db.session import Base


class BenchmarkRepositoryTests(unittest.TestCase):
    def test_run_and_steps_round_trip(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        local_sessions = sessionmaker(bind=engine)
        task = AutoPenBenchTask(
            task_id="autopenbench:in-vitro/access_control/vm0",
            level="in-vitro",
            category="access_control",
            index=0,
            task="Find the flag",
            target="in-vitro_access_control_vm0",
            vulnerability="",
            flag="flag",
        )

        with patch("db.session.SessionLocal", local_sessions):
            upsert_benchmark_tasks([task])
            run = create_benchmark_run(task.task_id, "test-model", 4)
            replace_benchmark_steps(
                run.id,
                [{"step_index": 1, "commands": ["id"], "observation": "uid=0", "approved": True}],
            )
            stored_run, steps = get_benchmark_run(run.id)

        self.assertEqual(stored_run.benchmark_task_id, task.task_id)
        self.assertEqual(steps[0].commands, ["id"])
        self.assertEqual(steps[0].observation, "uid=0")


if __name__ == "__main__":
    unittest.main()
