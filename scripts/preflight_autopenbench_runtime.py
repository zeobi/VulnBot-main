from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def configure_runtime(args: argparse.Namespace) -> None:
    os.environ.setdefault("PENTEST_ROOT", str(PROJECT_ROOT))
    os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / "data" / "hf_cache"))
    os.environ.setdefault(
        "HUGGINGFACE_HUB_CACHE", str(PROJECT_ROOT / "data" / "hf_cache" / "hub")
    )
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if args.offline:
        os.environ["VULNBOT_HF_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("VULNBOT_EMBEDDING_DEVICE", args.device)
    os.environ.setdefault("VULNBOT_RERANKER_DEVICE", args.device)


def check_python() -> bool:
    print("\n[Python]")
    print(f"executable: {sys.executable}")
    print(f"version: {sys.version.split()[0]}")
    if ".venv" not in sys.executable:
        warn("python executable is not inside project .venv")
    else:
        ok("using project .venv")
    return True


def check_imports() -> bool:
    print("\n[Core Imports]")
    modules = [
        "paramiko",
        "langgraph",
        "pymilvus",
        "torch",
        "sentence_transformers",
        "langchain_huggingface",
    ]
    passed = True
    for module in modules:
        try:
            __import__(module)
            ok(f"{module}")
        except Exception as exc:
            passed = False
            fail(f"{module}: {exc.__class__.__name__}: {exc}")
    return passed


def check_cuda(require_gpu: bool) -> bool:
    print("\n[CUDA]")
    try:
        import torch
    except Exception as exc:
        fail(f"torch import failed: {exc}")
        return False

    available = torch.cuda.is_available()
    print(f"cuda available: {available}")
    print(f"device count: {torch.cuda.device_count()}")
    if available:
        for index in range(torch.cuda.device_count()):
            print(f"gpu[{index}]: {torch.cuda.get_device_name(index)}")
        ok("CUDA is available")
        return True
    if require_gpu:
        fail("CUDA is required but not available")
        return False
    warn("CUDA is not available; CPU fallback would be used")
    return True


def check_hf_models(run_inference: bool) -> bool:
    print("\n[HuggingFace Local Models]")
    from config.config import Configs
    from rag.embedding.embedding import get_embeddings
    from rag.reranker.reranker import LangchainReranker

    print(f"HF_HOME: {os.environ.get('HF_HOME')}")
    print(f"HF_HUB_OFFLINE: {os.environ.get('HF_HUB_OFFLINE')}")
    print(f"TRANSFORMERS_OFFLINE: {os.environ.get('TRANSFORMERS_OFFLINE')}")
    print(f"embedding device: {os.environ.get('VULNBOT_EMBEDDING_DEVICE')}")
    print(f"reranker device: {os.environ.get('VULNBOT_RERANKER_DEVICE')}")

    try:
        embeddings = get_embeddings(Configs.llm_config.embedding_models)
        ok(f"embedding model loaded: {Configs.llm_config.embedding_models}")
        if run_inference:
            vector = embeddings.embed_query("autopenbench runtime preflight")
            ok(f"embedding inference ok, dim={len(vector)}")
    except Exception as exc:
        fail(f"embedding model failed: {exc.__class__.__name__}: {exc}")
        return False

    try:
        reranker = LangchainReranker(
            top_n=1,
            name_or_path=Configs.llm_config.rerank_model,
        )
        ok(f"reranker model loaded: {Configs.llm_config.rerank_model}")
        print(f"reranker device: {reranker.device}")
        if run_inference:
            docs = [
                {"page_content": "SSH weak password sudo privilege escalation.", "metadata": {}},
                {"page_content": "Unrelated document.", "metadata": {}},
            ]
            result = reranker.compress_documents(docs, "ssh sudo escalation")
            ok(f"reranker inference ok, returned={len(result)}")
    except Exception as exc:
        fail(f"reranker model failed: {exc.__class__.__name__}: {exc}")
        return False

    return True


def parse_host_port(uri: str) -> tuple[str, int]:
    parsed = urlparse(uri if "://" in uri else f"http://{uri}")
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Milvus URI must include host and port: {uri!r}")
    return parsed.hostname, parsed.port


def check_milvus() -> bool:
    print("\n[Milvus]")
    from config.config import Configs
    from pymilvus import Collection, connections, utility

    uri = (Configs.kb_config.milvus or {}).get("uri", "")
    kb_name = Configs.kb_config.kb_name
    if not uri:
        fail("kb_config.milvus.uri is empty")
        return False
    if not kb_name:
        fail("kb_config.kb_name is empty")
        return False

    try:
        host, port = parse_host_port(uri)
        with socket.create_connection((host, port), timeout=8):
            ok(f"TCP reachable: {host}:{port}")
    except Exception as exc:
        fail(f"Milvus TCP check failed: {exc.__class__.__name__}: {exc}")
        return False

    try:
        connections.connect(alias="preflight", **Configs.kb_config.milvus)
        try:
            version = utility.get_server_version(using="preflight")
            ok(f"Milvus connected, version={version}")
            exists = utility.has_collection(kb_name, using="preflight")
            print(f"collection {kb_name!r}: {exists}")
            if not exists:
                fail(f"collection does not exist: {kb_name}")
                return False
            collection = Collection(kb_name, using="preflight")
            print(f"num_entities: {collection.num_entities}")
            if collection.num_entities <= 0:
                fail(f"collection is empty: {kb_name}")
                return False
            ok("Milvus collection is ready")
            return True
        finally:
            connections.disconnect("preflight")
    except Exception as exc:
        fail(f"Milvus check failed: {exc.__class__.__name__}: {exc}")
        return False


def check_rag(query: str) -> bool:
    print("\n[RAG Retrieval]")
    from config.config import Configs
    from rag.kb.api.kb_doc_api import search_docs
    from rag.reranker.reranker import LangchainReranker

    try:
        docs = search_docs(
            query=query,
            knowledge_base_name=Configs.kb_config.kb_name,
            top_k=Configs.kb_config.top_k,
            score_threshold=Configs.kb_config.score_threshold,
        )
        print(f"retrieved docs: {len(docs)}")
        reranker = LangchainReranker(
            top_n=Configs.kb_config.top_n,
            name_or_path=Configs.llm_config.rerank_model,
        )
        reranked = reranker.compress_documents(docs, query)
        print(f"reranked docs: {len(reranked)}")
        ok("RAG retrieval and rerank succeeded")
        return True
    except Exception as exc:
        fail(f"RAG check failed: {exc.__class__.__name__}: {exc}")
        return False


def check_llm() -> bool:
    print("\n[LLM]")
    from openai import OpenAI
    from config.config import Configs, resolve_llm_api_key

    cfg = Configs.llm_config
    api_key = resolve_llm_api_key(cfg)
    if not api_key:
        fail("LLM API key is empty")
        return False
    if not cfg.base_url:
        fail("LLM base_url is empty")
        return False
    if not cfg.llm_model_name:
        fail("LLM model name is empty")
        return False
    try:
        client = OpenAI(api_key=api_key, base_url=cfg.base_url, timeout=cfg.timeout)
        response = client.chat.completions.create(
            model=cfg.llm_model_name,
            messages=[{"role": "user", "content": "Reply exactly: pong"}],
            temperature=0,
            max_tokens=32,
        )
        content = (response.choices[0].message.content or "").strip()
        print(f"response: {content!r}")
        ok("LLM request succeeded")
        return True
    except Exception as exc:
        fail(f"LLM check failed: {exc.__class__.__name__}: {exc}")
        return False


def run_command(command: list[str], *, cwd: Path | None = None) -> bool:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            fail(f"command failed: {' '.join(command)}")
            return False
        return True
    except Exception as exc:
        fail(f"command failed: {' '.join(command)}: {exc.__class__.__name__}: {exc}")
        return False


def check_docker_compose() -> bool:
    print("\n[Docker Compose]")
    docker = shutil.which("docker")
    docker_compose = shutil.which("docker-compose")
    if docker:
        if not run_command([docker, "version", "--format", "{{.Server.Version}}"]):
            return False
        if run_command([docker, "compose", "version"]):
            ok("docker compose is available")
        elif docker_compose and run_command([docker_compose, "version"]):
            ok("docker-compose is available")
        else:
            fail("Docker Compose is unavailable")
            return False
    elif docker_compose:
        if not run_command([docker_compose, "version"]):
            return False
        ok("docker-compose is available")
    else:
        fail("docker CLI is unavailable")
        return False

    sock = Path("/var/run/docker.sock")
    if sock.exists():
        ok("/var/run/docker.sock exists")
    else:
        warn("/var/run/docker.sock does not exist")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight checks before rerunning AutoPenBench with VulnBot."
    )
    parser.add_argument("--device", default="cuda", help="Device for local HF models")
    parser.add_argument(
        "--allow-hf-network",
        action="store_true",
        help="Allow HuggingFace network access instead of offline cache-only checks",
    )
    parser.add_argument("--no-require-gpu", action="store_true")
    parser.add_argument("--skip-inference", action="store_true")
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument(
        "--query",
        default="ssh weak password sudo privilege escalation",
        help="Query used for RAG retrieval preflight",
    )
    args = parser.parse_args()
    args.offline = not args.allow_hf_network

    configure_runtime(args)

    checks = [
        check_python(),
        check_imports(),
        check_cuda(require_gpu=not args.no_require_gpu),
        check_hf_models(run_inference=not args.skip_inference),
        check_milvus(),
    ]
    if not args.skip_rag:
        checks.append(check_rag(args.query))
    if not args.skip_llm:
        checks.append(check_llm())
    if not args.skip_docker:
        checks.append(check_docker_compose())

    if all(checks):
        print("\n[READY] AutoPenBench runtime checks passed.")
        return 0
    print("\n[BLOCKED] Fix failed checks before rerunning AutoPenBench.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
