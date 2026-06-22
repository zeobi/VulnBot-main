import json
import re
from typing import List, Dict

from pydantic import BaseModel

from config.config import Configs
from prompts.prompt import DeepPentestPrompt
from db.models.plan_model import Plan
from db.models.task_model import TaskModel, Task
from llm.chat import _chat


class WritePlan(BaseModel):
    plan_chat_id: str

    @staticmethod
    def _extract_json(response: str) -> str | None:
        match = re.search(r'<json>(.*?)</json>', response, re.DOTALL)
        return match.group(1) if match else None

    def _validate_or_repair(self, response: str) -> str:
        try:
            parse_plan_json(response)
            return response
        except (json.JSONDecodeError, ValueError) as error:
            repair_response = _chat(
                query=(
                    "Correct the malformed plan below and return only the complete "
                    "strict JSON array wrapped in <json></json>. Preserve its meaning "
                    "and escape all quotes and backslashes required by JSON.\n"
                    f"Parser error: {error}\nMalformed plan:\n{response}"
                ),
                conversation_id=self.plan_chat_id,
                summary=False,
            )
            repaired = self._extract_json(repair_response)
            if repaired is None:
                raise ValueError("LLM JSON repair response omitted <json> tags") from error
            parse_plan_json(repaired)
            return repaired

    def run(self, init_description) -> str:
        rsp = _chat(query=DeepPentestPrompt.write_plan, conversation_id=self.plan_chat_id, kb_name=Configs.kb_config.kb_name, kb_query=init_description)

        code = self._extract_json(rsp)
        if code is not None:
            return self._validate_or_repair(code)

    def update(self, task_result, success_task, fail_task, init_description) -> str:
        rsp = _chat(
            query=DeepPentestPrompt.update_plan.format(current_task=task_result.instruction,
                                                      init_description=init_description,
                                                      current_code=task_result.code,
                                                      task_result=task_result.result,
                                                      success_task=success_task,
                                                      fail_task=fail_task),
            conversation_id=self.plan_chat_id,
            kb_name=Configs.kb_config.kb_name,
            kb_query=task_result.instruction
        )
        if rsp == "":
            return rsp

        code = self._extract_json(rsp)
        if code is not None:
            return self._validate_or_repair(code)


def parse_tasks(response: str, current_plan: Plan):
    response = parse_plan_json(response)

    tasks = import_tasks_from_json(current_plan.id, response)

    current_plan.tasks = tasks

    return current_plan

def preprocess_json_string(json_str: str) -> str:
    """Escape bare backslashes that are invalid inside JSON strings."""
    result = []
    index = 0
    in_string = False
    simple_escapes = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't'}

    while index < len(json_str):
        char = json_str[index]
        if char == '"':
            in_string = not in_string
            result.append(char)
            index += 1
            continue

        if char != '\\' or not in_string:
            result.append(char)
            index += 1
            continue

        next_char = json_str[index + 1] if index + 1 < len(json_str) else ''
        if next_char in simple_escapes:
            result.extend((char, next_char))
            index += 2
            continue

        unicode_escape = json_str[index + 2:index + 6]
        if next_char == 'u' and len(unicode_escape) == 4 and all(
            digit in '0123456789abcdefABCDEF' for digit in unicode_escape
        ):
            result.append(json_str[index:index + 6])
            index += 6
            continue

        result.append('\\\\')
        index += 1

    return ''.join(result)


def parse_plan_json(response: str) -> List[Dict]:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Plan response is empty")

    processed_response = preprocess_json_string(response.strip())
    parsed = json.loads(processed_response)
    if not isinstance(parsed, list):
        raise ValueError("Plan response must be a JSON array")
    return parsed

def merge_tasks(response: str, current_plan: Plan):
    response = parse_plan_json(response)

    tasks = merge_tasks_from_json(current_plan.id, response, current_plan.tasks)

    current_plan.tasks = tasks

    return current_plan


def import_tasks_from_json(plan_id: str, tasks_json: List[Dict]) -> List[TaskModel]:
    tasks = []
    for idx, task_data in enumerate(tasks_json):
        task = Task(
            plan_id=plan_id,
            sequence=idx,
            action=task_data['action'],
            instruction=task_data['instruction'],
            dependencies=[i for i, t in enumerate(tasks_json)
                          if t['id'] in task_data['dependent_task_ids']]
        )

        tasks.append(task)
    return tasks


def merge_tasks_from_json(plan_id: str, new_tasks_json: List[Dict], old_tasks: List[Task]) -> List[Task]:
    # 获取所有已完成且成功的任务
    completed_tasks_map = {
        task.instruction: task
        for task in old_tasks
        if task.is_finished and task.is_success
    }

    merged_tasks = []

    for instruction, completed_task in completed_tasks_map.items():
        found = False
        for task_data in new_tasks_json:
            if task_data['instruction'] == instruction:
                found = True
                break
        if not found:
            completed_task.sequence = len(merged_tasks)
            completed_task.dependencies = []
            merged_tasks.append(completed_task)

    new_task_id_to_idx = {
        task_data.get('id'): idx+len(merged_tasks)
        for idx, task_data in enumerate(new_tasks_json)
    }
    for idx, task_data in enumerate(new_tasks_json):
        instruction = task_data['instruction']
        sequence = len(merged_tasks)

        if instruction in completed_tasks_map:
            existing_task = completed_tasks_map[instruction]
            existing_task.sequence = sequence
            existing_task.dependencies = [
                new_task_id_to_idx[dep_id]
                for dep_id in task_data['dependent_task_ids']
                if dep_id in new_task_id_to_idx
            ]
            merged_tasks.append(existing_task)
        else:
            new_task = Task(
                plan_id=plan_id,
                sequence=sequence,
                action=task_data['action'],
                instruction=task_data['instruction'],
                dependencies=[
                    new_task_id_to_idx[dep_id]
                    for dep_id in task_data['dependent_task_ids']
                    if dep_id in new_task_id_to_idx
                ],
            )
            merged_tasks.append(new_task)

    return merged_tasks
