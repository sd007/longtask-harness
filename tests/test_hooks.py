from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "goal-flow" / "skills" / "goal-flow" / "scripts" / "goalctl.py"
SESSION_HOOK = ROOT / "goal-flow" / "hooks" / "session_start.py"
STOP_HOOK = ROOT / "goal-flow" / "hooks" / "stop.py"


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Goal Flow Test")
        self.git("config", "user.email", "goal-flow@example.invalid")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "initial")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def ctl(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.repo), *args],
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def hook(self, path: Path) -> dict:
        result = subprocess.run(
            [sys.executable, str(path)],
            input=json.dumps({"cwd": str(self.repo), "hook_event_name": path.stem}),
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def test_session_start_is_silent_without_goal_and_restores_active_goal(self) -> None:
        self.assertEqual(self.hook(SESSION_HOOK), {})
        self.ctl("init", "--goal-id", "hook-goal", "--title", "Hook Goal", "--goal", "Test hooks")
        payload = self.hook(SESSION_HOOK)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Goal=hook-goal", context)
        self.assertIn("status=PLANNING", context)

    def test_stop_continues_execution_but_not_planning_or_repeated_stall(self) -> None:
        self.ctl("init", "--goal-id", "hook-goal", "--title", "Hook Goal", "--goal", "Test hooks")
        self.assertEqual(self.hook(STOP_HOOK), {})
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "false",
        )
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "Hook works", "--verified-by", "TEST",
        )
        self.ctl("approve", "--user-approved", "--next-action", "Implement hook behavior")
        self.assertEqual(self.hook(STOP_HOOK)["decision"], "block")
        self.assertEqual(self.hook(STOP_HOOK)["decision"], "block")
        stopped = self.hook(STOP_HOOK)
        self.assertIn("Goal Flow blocked", stopped["systemMessage"])
        status = self.ctl("status")
        self.assertEqual(status["state"]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
