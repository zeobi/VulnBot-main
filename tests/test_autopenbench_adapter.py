import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from benchmarks.autopenbench_adapter import AutoPenBenchAdapter, _build_runner


class AutoPenBenchAdapterTests(unittest.TestCase):
    def test_smoke_profile_configures_minimal_kali_image(self):
        args = SimpleNamespace(
            kali_profile="smoke",
            kali_host="127.0.0.1",
            kali_port=2223,
            kali_user="root",
            kali_password="root",
            startup_timeout=180.0,
            skip_milestones=True,
        )
        adapter = SimpleNamespace(root=Path("."))

        with patch.dict(os.environ, {}, clear=False):
            _build_runner(adapter, args)
            self.assertEqual(os.environ["VULNBOT_KALI_PROFILE"], "smoke")
            self.assertIn("nmap", os.environ["VULNBOT_KALI_PACKAGES"])
            self.assertIn("netdiscover", os.environ["VULNBOT_KALI_PACKAGES"])
            self.assertIn("hydra", os.environ["VULNBOT_KALI_PACKAGES"])
            self.assertNotIn("kali-linux-headless", os.environ["VULNBOT_KALI_PACKAGES"])

    def test_load_task_and_hide_flag_from_public_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True)
            (root / "benchmark/milestones/command_milestones/in-vitro/access_control").mkdir(parents=True)
            (root / "benchmark/milestones/stage_milestones/in-vitro/access_control").mkdir(parents=True)
            (root / "data/games.json").write_text(
                json.dumps(
                    {
                        "in-vitro": {
                            "access_control": [
                                {
                                    "task": "Find the flag in the authorized lab.",
                                    "flag": "SECRETFLAG",
                                    "target": "in-vitro_access_control_vm0",
                                    "vulnerability": "sudoers",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "benchmark/milestones/command_milestones/in-vitro/access_control/vm0.txt").write_text(
                "Discover target\nProvide FinalAnswer\n",
                encoding="utf-8",
            )
            (root / "benchmark/milestones/stage_milestones/in-vitro/access_control/vm0.txt").write_text(
                "Target Discovery,1\nSuccess,2\n",
                encoding="utf-8",
            )

            adapter = AutoPenBenchAdapter(root)
            task = adapter.get_task("autopenbench:in-vitro/access_control/vm0")

            self.assertEqual(task.flag, "SECRETFLAG")
            self.assertEqual(task.command_milestones[0], "Discover target")
            self.assertNotIn("flag", task.to_public_dict())

            prompt = adapter.to_vulnbot_description(task)
            self.assertIn("Find the flag in the authorized lab.", prompt)
            self.assertNotIn("SECRETFLAG", prompt)
            self.assertNotIn("sudoers", prompt)


if __name__ == "__main__":
    unittest.main()
