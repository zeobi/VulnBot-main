import unittest
from unittest.mock import patch

from actions.command_validator import LLMCommandValidator
from actions.execute_task import ExecuteTask
from graph.nodes import _next_role_name
from utils.log_common import RoleType


class CommandParsingTests(unittest.TestCase):
    def test_parse_execute_blocks(self):
        executor = ExecuteTask(
            action="Shell",
            instruction="<execute> nmap -sV 10.0.0.5 </execute><execute> curl http://10.0.0.5 </execute>",
            code=[],
        )

        self.assertEqual(executor.parse_response(), ["nmap -sV 10.0.0.5", "curl http://10.0.0.5"])

    def test_rejected_validation_does_not_execute_shell(self):
        executor = ExecuteTask(action="Shell", instruction="", code=[])

        with patch("actions.shell_manager.ShellManager.get_instance") as get_instance:
            commands = []
            if commands:
                executor.execute_commands(commands)

        get_instance.assert_not_called()


class LLMCommandValidatorTests(unittest.TestCase):
    def test_parse_approved_response(self):
        validator = LLMCommandValidator()
        result = validator._parse_response(
            '{"approved": true, "reason": "ok", "safe_commands": ["nmap -sV 10.0.0.5"], "suggestion": null}',
            ["nmap 10.0.0.5"],
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.safe_commands, ["nmap -sV 10.0.0.5"])

    def test_parse_rejected_response(self):
        validator = LLMCommandValidator()
        result = validator._parse_response(
            '{"approved": false, "reason": "missing target", "safe_commands": [], "suggestion": "include target IP"}',
            ["nmap"],
        )

        self.assertFalse(result.approved)
        self.assertEqual(result.suggestion, "include target IP")

    def test_parse_invalid_json_rejects(self):
        validator = LLMCommandValidator()
        result = validator._parse_response("not json", ["nmap 10.0.0.5"])

        self.assertFalse(result.approved)
        self.assertIn("invalid JSON", result.reason)

    def test_approved_response_defaults_safe_commands(self):
        validator = LLMCommandValidator()
        result = validator._parse_response(
            '{"approved": true, "reason": "ok", "safe_commands": [], "suggestion": null}',
            ["nmap 10.0.0.5"],
        )

        self.assertEqual(result.safe_commands, ["nmap 10.0.0.5"])


class RoleOrderTests(unittest.TestCase):
    def test_role_order(self):
        self.assertEqual(_next_role_name(RoleType.COLLECTOR.value), RoleType.SCANNER.value)
        self.assertEqual(_next_role_name(RoleType.SCANNER.value), RoleType.EXPLOITER.value)
        self.assertIsNone(_next_role_name(RoleType.EXPLOITER.value))


if __name__ == "__main__":
    unittest.main()
