from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.autopenbench_adapter import main
from benchmarks.lifecycle import BenchmarkEnvironmentError
from benchmarks.runner import BenchmarkRunError


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkEnvironmentError, BenchmarkRunError, FileNotFoundError, ValueError) as exc:
        print(f"[FAIL] {exc.__class__.__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
