import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config.config import is_valid_env_var_name, resolve_llm_api_key


class ModelConfigTests(unittest.TestCase):
    def test_api_key_is_not_accepted_as_an_environment_variable_name(self):
        self.assertFalse(is_valid_env_var_name("sk-secret"))
        config = SimpleNamespace(api_key="", api_key_env="sk-secret")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_llm_api_key(config), "")

    def test_profile_key_does_not_fall_back_to_another_provider(self):
        config = SimpleNamespace(api_key="", api_key_env="DEEPSEEK_API_KEY")

        with patch.dict(os.environ, {"ZHIPUAI_API_KEY": "glm-key"}, clear=True):
            self.assertEqual(resolve_llm_api_key(config), "")

    def test_profile_reads_its_named_environment_variable(self):
        config = SimpleNamespace(api_key="", api_key_env="DEEPSEEK_API_KEY")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "deepseek-key"}, clear=True):
            self.assertEqual(resolve_llm_api_key(config), "deepseek-key")


if __name__ == "__main__":
    unittest.main()
