from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def mask_secret(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    from openai import OpenAI
    from config.config import Configs

    cfg = Configs.llm_config

    parser = argparse.ArgumentParser(description="Test LLM connectivity for VulnBot.")
    parser.add_argument("--api-key", default=cfg.api_key, help="Override API key")
    parser.add_argument("--base-url", default=cfg.base_url, help="Override OpenAI-compatible base URL")
    parser.add_argument("--model", default=cfg.llm_model_name, help="Override model name")
    parser.add_argument("--timeout", type=float, default=float(cfg.timeout), help="Request timeout in seconds")
    args = parser.parse_args()

    print("[Config]")
    print(f"  base_url: {args.base_url!r}")
    print(f"  model: {args.model!r}")
    print(f"  api_key: {mask_secret(args.api_key)}")
    print(f"  timeout: {args.timeout}")

    if not args.api_key:
        print("[FAIL] api_key is empty.")
        return 2
    if not args.base_url:
        print("[FAIL] base_url is empty.")
        return 2
    if not args.model:
        print("[FAIL] model is empty.")
        return 2

    try:
        client = OpenAI(
            api_key=args.api_key,
            base_url=args.base_url,
            timeout=args.timeout,
        )
        print("[1/1] Sending a minimal chat completion request...")
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "You are a connectivity test endpoint."},
                {"role": "user", "content": "Reply with exactly: pong"},
            ],
            temperature=0,
            max_tokens=8,
        )
        content = response.choices[0].message.content
        print("[OK] LLM request succeeded.")
        print(f"[OK] Response: {content!r}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
