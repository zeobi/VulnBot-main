import unittest
from unittest.mock import patch
from types import SimpleNamespace

from actions.execute_task import ExecuteTask
from graph.nodes import _next_role_name, advance_role, route_after_plan
from db.models.session_model import Session
from utils.log_common import RoleType


class CommandParsingTests(unittest.TestCase):
    def test_parse_execute_blocks(self):
        executor = ExecuteTask(
            action="Shell",
            instruction="<execute> nmap -sV 10.0.0.5 </execute><execute> curl http://10.0.0.5 </execute>",
            code=[],
        )

        self.assertEqual(executor.parse_response(), ["nmap -sV 10.0.0.5", "curl http://10.0.0.5"])

class RoleOrderTests(unittest.TestCase):
    def test_role_order(self):
        self.assertEqual(_next_role_name(RoleType.COLLECTOR.value), RoleType.SCANNER.value)
        self.assertEqual(_next_role_name(RoleType.SCANNER.value), RoleType.EXPLOITER.value)
        self.assertIsNone(_next_role_name(RoleType.EXPLOITER.value))

    def test_global_step_budget_routes_to_finish_current_role(self):
        state = {
            "next_task": "continue",
            "total_interaction_count": 4,
            "max_steps": 4,
            "interaction_count": 1,
            "max_interactions": 10,
        }

        self.assertEqual(route_after_plan(state), "advance_role")

    def test_role_budget_advances_before_global_budget_is_exhausted(self):
        state = {
            "next_task": "continue",
            "total_interaction_count": 8,
            "max_steps": 24,
            "interaction_count": 8,
            "max_interactions": 8,
        }

        self.assertEqual(route_after_plan(state), "advance_role")

    def test_global_step_budget_finishes_without_initializing_another_role(self):
        session = Session(
            current_role_name=RoleType.COLLECTOR.value,
            init_description="authorized test",
            current_planner_id="plan1",
            history_planner_ids=[],
        )
        planner = SimpleNamespace(current_plan=SimpleNamespace(id="plan1", tasks=[]))

        with patch("graph.nodes.add_task_to_plan"):
            result = advance_role(
                {
                    "session": session,
                    "planner": planner,
                    "max_steps": 2,
                    "total_interaction_count": 2,
                }
            )

        self.assertTrue(result["finished"])
        self.assertEqual(session.current_role_name, RoleType.COLLECTOR.value)


if __name__ == "__main__":
    unittest.main()
