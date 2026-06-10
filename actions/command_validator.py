import json
import re
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field

from config.config import Configs
from server.chat.chat import _chat
from utils.log_common import build_logger

logger = build_logger()


class ValidationResult(BaseModel):
    approved: bool = False
    reason: str = ""
    safe_commands: list[str] = Field(default_factory=list)
    suggestion: Optional[str] = None


class CommandValidator(Protocol):
    def validate(self, commands: list[str], task: Any, context: dict) -> ValidationResult:
        ...


class AllowAllCommandValidator:
    def validate(self, commands: list[str], task: Any, context: dict) -> ValidationResult:
        return ValidationResult(
            approved=True,
            reason="Command validation is disabled.",
            safe_commands=commands,
        )


class LLMCommandValidator:
    def __init__(self, conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id

    def validate(self, commands: list[str], task: Any, context: dict) -> ValidationResult:
        if not commands:
            return ValidationResult(approved=False, reason="No executable commands were generated.")

        prompt = self._build_prompt(commands, task, context)
        response = _chat(query=prompt, conversation_id=self.conversation_id, summary=False)
        if isinstance(response, tuple):
            response_text, self.conversation_id = response
        else:
            response_text = response

        logger.info(f"command_validation_response: {response_text}")
        return self._parse_response(response_text, commands)

    def _build_prompt(self, commands: list[str], task: Any, context: dict) -> str:
        task_instruction = getattr(task, "instruction", "")
        task_action = getattr(task, "action", "")
        role_name = context.get("role_name", "")
        next_task = context.get("next_task", "")
        init_description = context.get("init_description", "")
        previous_rejection = context.get("previous_rejection", "")

        return f"""You are a command validator for an authorized penetration-testing lab.
Decide whether the proposed shell commands correctly and safely implement the current task.

Validation rules:
1. Approve only commands that are directly relevant to the current task and target scope.
2. Reject commands that are unrelated, malformed, missing a target, destructive beyond the task, or likely to break the shared shell.
3. If a command can be fixed, return the corrected command in safe_commands and explain the change.
4. Return only JSON. Do not wrap it in markdown.

Expected JSON schema:
{{
  "approved": true,
  "reason": "short reason",
  "safe_commands": ["command to execute"],
  "suggestion": null
}}

Initial task description:
{init_description}

Role:
{role_name}

Task action:
{task_action}

Task instruction:
{task_instruction}

Detailed next task:
{next_task}

Previous validator feedback:
{previous_rejection}

Proposed commands:
{json.dumps(commands, ensure_ascii=False)}
"""

    def _parse_response(self, response_text: str, original_commands: list[str]) -> ValidationResult:
        try:
            payload = json.loads(self._extract_json(response_text))
        except Exception as exc:
            return ValidationResult(
                approved=False,
                reason=f"Validator returned invalid JSON: {exc}",
                suggestion="Regenerate commands and return only executable commands wrapped in <execute> tags.",
            )

        result = ValidationResult.model_validate(payload)
        if result.approved and not result.safe_commands:
            result.safe_commands = original_commands
        return result

    def _extract_json(self, response_text: str) -> str:
        text = response_text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return text


def build_command_validator() -> CommandValidator:
    config = getattr(Configs.basic_config, "command_validator", {}) or {}
    if not config.get("enabled", True):
        return AllowAllCommandValidator()
    return LLMCommandValidator(conversation_id=config.get("model_conversation_id"))
