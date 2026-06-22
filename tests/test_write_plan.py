import json

import pytest
from unittest.mock import patch

from actions.write_plan import WritePlan, parse_plan_json, preprocess_json_string


def test_preprocess_json_string_repairs_bare_shell_backslashes():
    response = r'[{"instruction":"run sed \d and inspect C:\Users\logs","id":"1"}]'

    parsed = json.loads(preprocess_json_string(response))

    assert parsed[0]["instruction"] == r"run sed \d and inspect C:\Users\logs"


def test_preprocess_json_string_preserves_valid_json_escapes():
    response = r'[{"instruction":"line1\nline2\t\u4f60\u597d","id":"1"}]'

    assert preprocess_json_string(response) == response


def test_preprocess_json_string_preserves_escaped_backslash_before_apostrophe():
    response = r'''[{"instruction":"python3 -c \"print(\\'PYTHON_OUTPUT\\')\""}]'''

    assert preprocess_json_string(response) == response
    assert json.loads(preprocess_json_string(response))[0]["instruction"] == (
        "python3 -c \"print(\\'PYTHON_OUTPUT\\')\""
    )


def test_parse_plan_json_rejects_non_array_response():
    with pytest.raises(ValueError, match="JSON array"):
        parse_plan_json('{"tasks": []}')


def test_write_plan_repairs_unescaped_quote_in_model_json():
    malformed = (
        '[{"id":"1","dependent_task_ids":[],"instruction":"echo '
        '\\"start\\" and echo \\"end\"","action":"Shell"}]'
    )
    repaired = (
        '<json>[{"id":"1","dependent_task_ids":[],"instruction":'
        '"echo \\"start\\" and echo \\"end\\"","action":"Shell"}]</json>'
    )

    with patch("actions.write_plan._chat", return_value=repaired) as chat:
        result = WritePlan(plan_chat_id="plan-chat")._validate_or_repair(malformed)

    assert parse_plan_json(result)[0]["instruction"] == 'echo "start" and echo "end"'
    chat.assert_called_once()
