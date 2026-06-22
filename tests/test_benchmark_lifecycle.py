import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paramiko

from benchmarks.autopenbench_adapter import AutoPenBenchTask
from benchmarks.lifecycle import (
    AutoPenBenchLifecycle,
    BenchmarkEnvironmentError,
    _docker_subprocess_env,
    _find_docker_executable,
    _normalize_proxy_url,
)


class BenchmarkLifecycleTests(unittest.TestCase):
    def test_ssh_readiness_reports_authentication_failure(self):
        lifecycle = AutoPenBenchLifecycle(".", startup_timeout=1)
        with patch("benchmarks.lifecycle.paramiko.SSHClient") as client_type:
            client_type.return_value.connect.side_effect = paramiko.AuthenticationException()
            with self.assertRaisesRegex(BenchmarkEnvironmentError, "authentication failed"):
                lifecycle._wait_for_ssh()

    def test_normalizes_docker_desktop_proxy(self):
        self.assertEqual(
            _normalize_proxy_url("http.docker.internal:3128"),
            "http://http.docker.internal:3128",
        )

    def test_docker_helpers_are_available_to_child_process(self):
        docker = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
        env = _docker_subprocess_env(str(docker), {"PATH": "C:\\Windows"})

        self.assertEqual(env["PATH"].split(";")[0], str(docker.parent))

    def test_finds_docker_desktop_outside_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "Docker/Docker/resources/bin/docker.exe"
            docker.parent.mkdir(parents=True)
            docker.touch()

            with (
                patch("benchmarks.lifecycle.shutil.which", return_value=None),
                patch.dict("os.environ", {"ProgramFiles": tmp}),
            ):
                self.assertEqual(_find_docker_executable(), str(docker))

    def test_rejects_path_like_task_fields(self):
        task = AutoPenBenchTask(
            task_id="bad",
            level="in-vitro",
            category="..",
            index=0,
            task="bad",
            target="target",
            vulnerability="",
            flag="flag",
        )

        with self.assertRaises(BenchmarkEnvironmentError):
            AutoPenBenchLifecycle(".")._validate_task(task)

    def test_reset_uses_scoped_compose_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            machines = root / "benchmark/machines"
            category = machines / "in-vitro/access_control"
            category.mkdir(parents=True)
            (machines / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
            (category / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
            task = AutoPenBenchTask(
                task_id="autopenbench:in-vitro/access_control/vm0",
                level="in-vitro",
                category="access_control",
                index=0,
                task="Find the flag",
                target="in-vitro_access_control_vm0",
                vulnerability="",
                flag="flag",
            )
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                stdout = ""
                if command[-2:] == ["config", "--services"]:
                    stdout = "kali_master\nin-vitro_access_control_vm0\n"
                elif "info" in command:
                    stdout = "http.docker.internal:3128|http.docker.internal:3128|localhost\n"
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

            lifecycle = AutoPenBenchLifecycle(root)
            with (
                patch("benchmarks.lifecycle.shutil.which", side_effect=lambda name: "docker" if name == "docker" else None),
                patch("benchmarks.lifecycle.subprocess.run", side_effect=fake_run),
                patch.object(lifecycle, "_wait_for_ssh"),
            ):
                lifecycle.reset(task)

            commands = [call[0] for call in calls]
            up_command = next(command for command in commands if "up" in command)
            build_command = next(command for command in commands if "build" in command)
            self.assertNotIn("--build", up_command)
            self.assertIn("--no-build", up_command)
            self.assertIn("kali_master", up_command)
            self.assertIn(task.target, up_command)
            self.assertIn("--build-arg", build_command)
            self.assertTrue(all("shell" not in kwargs for _, kwargs in calls))
            build_env = next(kwargs["env"] for command, kwargs in calls if "build" in command)
            self.assertEqual(
                build_env["VULNBOT_DOCKER_HTTPS_PROXY"],
                "http://http.docker.internal:3128",
            )


if __name__ == "__main__":
    unittest.main()
