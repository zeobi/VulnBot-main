from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_project_milvus_config() -> dict:
    try:
        from config.config import Configs

        return dict(Configs.kb_config.milvus or {})
    except Exception as exc:
        print(f"[WARN] Failed to load project config: {exc}")
        return {}


def parse_host_port(uri: str) -> tuple[str, int]:
    parsed = urlparse(uri if "://" in uri else f"http://{uri}")
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        raise ValueError(f"URI must include host and port, got: {uri!r}")
    return host, port


def check_tcp(uri: str, timeout: float) -> None:
    host, port = parse_host_port(uri)
    print(f"[1/2] TCP check: {host}:{port}")
    with socket.create_connection((host, port), timeout=timeout):
        print("[OK] TCP port is reachable")


def check_pymilvus(uri: str, user: str, password: str, timeout: float) -> None:
    print(f"[2/2] pymilvus check: {uri}")
    from pymilvus import connections, utility

    kwargs = {
        "alias": "vulnbot_test",
        "uri": uri,
        "timeout": timeout,
    }
    if user:
        kwargs["user"] = user
    if password:
        kwargs["password"] = password

    connections.connect(**kwargs)
    try:
        version = utility.get_server_version(using="vulnbot_test")
        collections = utility.list_collections(using="vulnbot_test")
        print(f"[OK] Connected to Milvus, server version: {version}")
        print(f"[OK] Collections: {collections}")
    finally:
        connections.disconnect("vulnbot_test")


def main() -> int:
    config = load_project_milvus_config()
    parser = argparse.ArgumentParser(description="Test Milvus connectivity for VulnBot.")
    parser.add_argument("--uri", default=config.get("uri") or "", help="Milvus URI, e.g. http://127.0.0.1:19530")
    parser.add_argument("--user", default=config.get("user") or "", help="Milvus username if auth is enabled")
    parser.add_argument("--password", default=config.get("password") or "", help="Milvus password if auth is enabled")
    parser.add_argument("--timeout", type=float, default=8.0, help="Connection timeout in seconds")
    args = parser.parse_args()

    if not args.uri:
        print("[FAIL] No Milvus URI was provided and kb_config.yaml has no milvus.uri.")
        print("       Example: python scripts/check_milvus_connection.py --uri http://127.0.0.1:19530")
        return 2

    try:
        check_tcp(args.uri, args.timeout)
        check_pymilvus(args.uri, args.user, args.password, args.timeout)
    except Exception as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
