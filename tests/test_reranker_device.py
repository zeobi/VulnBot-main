import importlib
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch


class RerankerDeviceTests(unittest.TestCase):
    def make_reranker(self, *, cuda_available: bool):
        sys.modules.pop("rag.reranker.reranker", None)
        package = sys.modules.get("rag.reranker")
        if package is not None and hasattr(package, "reranker"):
            delattr(package, "reranker")

        sentence_transformers = types.ModuleType("sentence_transformers")
        sentence_transformers.CrossEncoder = Mock()

        langchain_documents = types.ModuleType("langchain_core.documents")
        langchain_documents.Document = dict

        torch_module = types.ModuleType("torch")
        torch_module.cuda = types.SimpleNamespace(is_available=lambda: cuda_available)

        modules = {
            "sentence_transformers": sentence_transformers,
            "langchain_core.documents": langchain_documents,
            "torch": torch_module,
        }
        with patch.dict(sys.modules, modules):
            module = importlib.import_module("rag.reranker.reranker")
            module.LangchainReranker(name_or_path="test-reranker")
            return sentence_transformers.CrossEncoder

    def test_uses_cuda_when_available(self):
        with patch.dict(os.environ, {}, clear=True):
            cross_encoder = self.make_reranker(cuda_available=True)

        cross_encoder.assert_called_once_with(
            model_name="test-reranker", max_length=512, device="cuda"
        )

    def test_env_device_overrides_auto_detection(self):
        with patch.dict(os.environ, {"VULNBOT_RERANKER_DEVICE": "cuda:1"}, clear=True):
            cross_encoder = self.make_reranker(cuda_available=False)

        cross_encoder.assert_called_once_with(
            model_name="test-reranker", max_length=512, device="cuda:1"
        )

    def test_offline_mode_uses_local_files_only(self):
        with patch.dict(os.environ, {"HF_HUB_OFFLINE": "1"}, clear=True):
            cross_encoder = self.make_reranker(cuda_available=True)

        cross_encoder.assert_called_once_with(
            model_name="test-reranker",
            max_length=512,
            device="cuda",
            local_files_only=True,
        )


if __name__ == "__main__":
    unittest.main()
