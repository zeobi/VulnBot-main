from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import paramiko

from benchmarks.autopenbench_adapter import AutoPenBenchTask


SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

DEPENDENT_SERVICES = {
    "in-vitro_web_security_vm3": ["in-vitro_web_security_vm3_database"],
    "in-vitro_web_security_vm4": ["in-vitro_web_security_vm4_database"],
    "in-vitro_network_security_vm5": ["in-vitro_network_security_vm5b"],
}


class BenchmarkEnvironmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class LabConnection:
    host: str = "127.0.0.1"
    port: int = 2223
    username: str = "root"
    password: str = "root"


class AutoPenBenchLifecycle:
    """Owns one sequential AutoPenBench Docker Compose lab lifecycle."""

    def __init__(
        self,
        root: Path | str,
        *,
        connection: LabConnection | None = None,
        project_name: str = "vulnbot-benchmark",
        startup_timeout: float = 180.0,
    ):
        self.root = Path(root).resolve()
        self.connection = connection or LabConnection()
        self.project_name = project_name
        self.startup_timeout = startup_timeout
        self.override_file = Path(__file__).with_name("docker-compose.override.yml").resolve()
        self._compose_prefix: list[str] | None = None
        self._docker_build_proxy: dict[str, str] | None = None

    def preflight(self, task: AutoPenBenchTask | None = None) -> None:
        if not self.root.is_dir():
            raise BenchmarkEnvironmentError(f"AutoPenBench root does not exist: {self.root}")
        self._compose_prefix = self._detect_compose()
        if task is not None:
            self._validate_task(task)
            services = self._run_compose(task, ["config", "--services"], capture=True).splitlines()
            required = [task.target, *DEPENDENT_SERVICES.get(task.target, [])]
            missing = [service for service in required if service not in services]
            if missing:
                raise BenchmarkEnvironmentError(f"Compose services not found: {missing}")

    def reset(self, task: AutoPenBenchTask, *, build: bool = True) -> LabConnection:
        self.preflight(task)
        self.cleanup(task, check=False)
        services = ["kali_master", task.target, *DEPENDENT_SERVICES.get(task.target, [])]
        if build:
            self._run_compose(task, ["build", *services])
        self._run_compose(task, ["up", "-d", "--no-build", *services])
        self._wait_for_ssh()
        return self.connection

    def cleanup(self, task: AutoPenBenchTask, *, check: bool = False) -> None:
        if self._compose_prefix is None:
            self._compose_prefix = self._detect_compose()
        self._run_compose(task, ["down", "--remove-orphans"], check=check)

    def _detect_compose(self) -> list[str]:
        docker = _find_docker_executable()
        if docker:
            env = _docker_subprocess_env(docker)
            result = subprocess.run(
                [docker, "compose", "version"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            if result.returncode == 0:
                return [docker, "compose"]
        legacy = shutil.which("docker-compose")
        if legacy:
            return [legacy]
        raise BenchmarkEnvironmentError(
            "Docker Compose is unavailable. Install Docker Desktop with Linux-container support "
            "or add its resources\\bin directory to PATH."
        )

    def _compose_files(self, task: AutoPenBenchTask) -> list[Path]:
        machines = self.root / "benchmark" / "machines"
        files = [
            machines / "docker-compose.yml",
            machines / task.level / task.category / "docker-compose.yml",
            self.override_file,
        ]
        category_override = (
            Path(__file__).with_name("compose_overrides")
            / task.level
            / f"{task.category}.yml"
        ).resolve()
        if category_override.is_file():
            files.append(category_override)
        missing = [str(path) for path in files if not path.is_file()]
        if missing:
            raise BenchmarkEnvironmentError(f"Compose files not found: {missing}")
        return files

    def _run_compose(
        self,
        task: AutoPenBenchTask,
        args: Sequence[str],
        *,
        check: bool = True,
        capture: bool = False,
    ) -> str:
        self._validate_task(task)
        prefix = self._compose_prefix or self._detect_compose()
        command = [*prefix, "--project-name", self.project_name]
        for compose_file in self._compose_files(task):
            command.extend(["-f", str(compose_file)])
        env = os.environ.copy()
        env = _docker_subprocess_env(prefix[0], env)
        effective_args = list(args)
        if effective_args and effective_args[0] == "build":
            proxy_values = self._get_docker_build_proxy(prefix[0], env)
            for key, value in proxy_values.items():
                env.setdefault(key, value)
            proxy_args: list[str] = []
            for env_name, build_arg_name in (
                ("VULNBOT_DOCKER_HTTP_PROXY", "HTTP_PROXY"),
                ("VULNBOT_DOCKER_HTTPS_PROXY", "HTTPS_PROXY"),
                ("VULNBOT_DOCKER_NO_PROXY", "NO_PROXY"),
            ):
                if value := proxy_values.get(env_name):
                    proxy_args.extend(["--build-arg", f"{build_arg_name}={value}"])
            effective_args[1:1] = proxy_args
        command.extend(effective_args)
        env["VULNBOT_KALI_SSH_BIND"] = self.connection.host
        env["VULNBOT_KALI_SSH_PORT"] = str(self.connection.port)
        result = subprocess.run(
            command,
            cwd=self.root,
            env=env,
            capture_output=capture,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            details = (
                result.stderr
                or result.stdout
                or f"Docker Compose failed with exit code {result.returncode}; see the build output above."
            ).strip()
            raise BenchmarkEnvironmentError(details)
        return result.stdout if capture else ""

    def _get_docker_build_proxy(self, docker: str, env: dict[str, str]) -> dict[str, str]:
        if self._docker_build_proxy is not None:
            return self._docker_build_proxy

        self._docker_build_proxy = {}
        try:
            result = subprocess.run(
                [
                    docker,
                    "info",
                    "--format",
                    "{{.HTTPProxy}}|{{.HTTPSProxy}}|{{.NoProxy}}",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return self._docker_build_proxy

        if result.returncode != 0:
            return self._docker_build_proxy
        values = result.stdout.strip().split("|", 2)
        if len(values) != 3:
            return self._docker_build_proxy

        http_proxy, https_proxy, no_proxy = values
        if http_proxy:
            self._docker_build_proxy["VULNBOT_DOCKER_HTTP_PROXY"] = _normalize_proxy_url(http_proxy)
        if https_proxy:
            self._docker_build_proxy["VULNBOT_DOCKER_HTTPS_PROXY"] = _normalize_proxy_url(https_proxy)
        if no_proxy:
            self._docker_build_proxy["VULNBOT_DOCKER_NO_PROXY"] = no_proxy
        return self._docker_build_proxy

    def _validate_task(self, task: AutoPenBenchTask) -> None:
        for value, label in (
            (task.level, "level"),
            (task.category, "category"),
            (task.target, "target"),
        ):
            if not SERVICE_NAME_PATTERN.fullmatch(value) or ".." in value:
                raise BenchmarkEnvironmentError(f"Unsafe benchmark {label}: {value!r}")

    def _wait_for_ssh(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    self.connection.host,
                    port=self.connection.port,
                    username=self.connection.username,
                    password=self.connection.password,
                    timeout=2.0,
                    auth_timeout=2.0,
                    banner_timeout=10.0,
                    allow_agent=False,
                    look_for_keys=False,
                )
                return
            except paramiko.AuthenticationException as exc:
                raise BenchmarkEnvironmentError(
                    "Kali SSH authentication failed for "
                    f"{self.connection.username}@{self.connection.host}:{self.connection.port}."
                ) from exc
            except (OSError, paramiko.SSHException) as exc:
                last_error = exc
                time.sleep(1.0)
            finally:
                client.close()
        detail = f" Last error: {last_error}" if last_error else ""
        raise BenchmarkEnvironmentError(
            f"Kali SSH did not become ready at {self.connection.host}:{self.connection.port}.{detail}"
        )


def _find_docker_executable() -> str | None:
    docker = shutil.which("docker")
    if docker:
        return docker

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidate = (
            Path(program_files)
            / "Docker"
            / "Docker"
            / "resources"
            / "bin"
            / "docker.exe"
        )
        if candidate.is_file():
            return str(candidate)
    return None


def _docker_subprocess_env(
    docker: str,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    child_env = dict(env or os.environ)
    docker_path = Path(docker)
    if not docker_path.is_absolute():
        return child_env

    docker_dir = str(docker_path.parent)
    path_entries = child_env.get("PATH", "").split(os.pathsep)
    normalized_entries = {os.path.normcase(entry) for entry in path_entries if entry}
    if os.path.normcase(docker_dir) not in normalized_entries:
        child_env["PATH"] = os.pathsep.join([docker_dir, *path_entries])
    return child_env


def _normalize_proxy_url(value: str) -> str:
    value = value.strip()
    if value and "://" not in value:
        return f"http://{value}"
    return value
