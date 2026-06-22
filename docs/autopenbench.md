# AutoPenBench Benchmark Guide

The benchmark runner is restricted to task and service names loaded from the local AutoPenBench checkout.
Use it only with the authorized local lab under `data/benchmarks/auto-pen-bench`.

## Prerequisites

- Docker Desktop running Linux containers with the `docker compose` command available.
- The project `.venv` installed from `requirements.txt`.
- A configured OpenAI-compatible model endpoint and API key.
- The AutoPenBench checkout at `data/benchmarks/auto-pen-bench`.

For GLM, set the model key in the current CMD session without committing it:

```bat
set "ZHIPUAI_API_KEY=your-key"
```

PowerShell equivalent:

```powershell
$env:ZHIPUAI_API_KEY = "your-key"
```

Provider-specific variables `ZHIPUAI_API_KEY`, `BIGMODEL_API_KEY`, and `ZAI_API_KEY` are also supported.

## Preflight

```powershell
.\.venv\Scripts\python.exe scripts\autopenbench.py preflight `
  autopenbench:in-vitro/access_control/vm0
```

Preflight checks the model configuration, Docker Compose installation, compose files, and target services.
It does not start the target.

## Run One Task

```powershell
.\.venv\Scripts\python.exe scripts\autopenbench.py run `
  autopenbench:in-vitro/access_control/vm0 `
  --max-steps 24 `
  --max-interactions 8 `
  --timeout 3600
```

The runner performs this lifecycle:

1. Validate that the task target is a declared Compose service.
2. Remove the previous benchmark Compose project.
3. Build and start `kali_master`, the target, and known dependent services.
4. Wait for Kali SSH on `127.0.0.1:2223`.
5. Run VulnBot in an isolated child process with a global step budget.
6. Persist every command and raw observation.
7. Score the hidden flag and private milestones after execution.
8. Stop and remove the Compose project in a `finally` block.

`--max-interactions` retains the original VulnBot meaning: it limits each role independently. `--max-steps`
is an additional benchmark-wide safety cap. Benchmark workers force `mode=auto` and `temperature=0` without changing the normal YAML files. Reports record
the model name, VulnBot revision, AutoPenBench revision, and dirty-worktree state.

Use `--no-build` after the required images have already been built. Use `--skip-milestones` to run
deterministic flag scoring without additional evaluator-model calls.

## Run a Suite

Suites run sequentially so fixed benchmark subnets and the Kali SSH port cannot collide.

```powershell
.\.venv\Scripts\python.exe scripts\autopenbench.py suite `
  --level in-vitro `
  --category access_control `
  --max-steps 24 `
  --timeout 3600
```

Add `--limit 1` for a smoke test or `--stop-on-error` to stop after the first infrastructure failure.

## Reports

```powershell
# Recent runs
.\.venv\Scripts\python.exe scripts\autopenbench.py report

# One run with its complete trajectory
.\.venv\Scripts\python.exe scripts\autopenbench.py report --run-id RUN_ID --json
```

Run summaries are stored in `benchmark_runs`; step trajectories are stored in `benchmark_steps`.
The local SQLite database remains under the ignored `data/` directory.

## Kali Connection Overrides

The included Compose override maps `kali_master` SSH to `127.0.0.1:2223`. These options can override it:

```powershell
--kali-host 127.0.0.1 --kali-port 2223 --kali-user root --kali-password root
```

Equivalent environment variables are `AUTOPENBENCH_KALI_HOST`, `AUTOPENBENCH_KALI_PORT`,
`AUTOPENBENCH_KALI_USER`, and `AUTOPENBENCH_KALI_PASSWORD`.
