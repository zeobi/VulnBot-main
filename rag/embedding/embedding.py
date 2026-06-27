
import os
from functools import lru_cache
from pathlib import Path


PENTEST_ROOT = Path(os.environ.get("PENTEST_ROOT", ".")).resolve()
HF_HOME = PENTEST_ROOT / "data" / "hf_cache"
os.environ.setdefault("HF_HOME", str(HF_HOME))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_HOME / "hub"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings

from langchain_community.embeddings import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings

from config.config import Configs


from utils.log_common import build_logger

logger = build_logger()

@lru_cache(maxsize=None)
def get_embeddings(
        embed_model: str = None,
) -> Embeddings:

    try:
        if Configs.llm_config.embedding_type == "openai":
            # TODO
            return OpenAIEmbeddings()
        elif Configs.llm_config.embedding_type == "ollama":
            return OllamaEmbeddings(
                base_url=Configs.llm_config.embedding_url,
                model=embed_model,
            )
        else:
            device = os.environ.get("VULNBOT_EMBEDDING_DEVICE")
            if not device:
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    device = "cpu"
            return HuggingFaceEmbeddings(
                model_name=embed_model,
                cache_folder=str(HF_HOME),
                model_kwargs=_huggingface_model_kwargs(device),
            )
    except Exception as e:
        logger.exception(f"failed to create Embeddings for model: {embed_model}.")
        raise RuntimeError(f"failed to create Embeddings for model: {embed_model}") from e


def _huggingface_model_kwargs(device: str) -> dict:
    kwargs = {"device": device}
    if _hf_offline_enabled():
        kwargs["local_files_only"] = True
    return kwargs


def _hf_offline_enabled() -> bool:
    return any(
        os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
        for name in ("VULNBOT_HF_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    )
