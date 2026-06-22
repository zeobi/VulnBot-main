import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import RateLimitError
from tenacity import stop_after_attempt, wait_none

from llm.chat import OpenAIChat


class OpenAIChatTests(unittest.TestCase):
    def test_rate_limit_is_retried_and_then_propagated(self):
        chat = OpenAIChat.__new__(OpenAIChat)
        chat.client = Mock()
        chat.model_name = "test-model"
        chat.config = SimpleNamespace(temperature=0)
        response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
        error = RateLimitError("rate limited", response=response, body={"code": "1302"})
        chat.client.chat.completions.create.side_effect = error

        retrying_chat = OpenAIChat.chat.retry_with(
            stop=stop_after_attempt(2),
            wait=wait_none(),
        )
        with self.assertRaises(RateLimitError):
            retrying_chat(chat, [])

        self.assertEqual(chat.client.chat.completions.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
