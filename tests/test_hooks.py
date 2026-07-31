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
HOOKS_CONFIG = ROOT / "goal-flow" / "hooks" / "hooks.json"
DIMENSIONS = [
    "functional", "negative-boundary", "regression-compatibility", "security-privacy",
    "performance-reliability", "operations-observability", "migration-rollback",
    "documentation-deliverables",
]


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

    def test_plugin_hooks_config_matches_codex_schema(self) -> None:
        payload = json.loads(HOOKS_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"hooks"})
        self.assertEqual(set(payload["hooks"]), {"SessionStart", "Stop"})

    def test_session_start_is_silent_without_goal_and_restores_active_goal(self) -> None:
        self.assertEqual(self.hook(SESSION_HOOK), {})
        self.ctl("init", "--goal-id", "hook-goal", "--title", "Hook Goal", "--goal", "Test hooks", "--mode", "goal-flow")
        payload = self.hook(SESSION_HOOK)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Goal=hook-goal", context)
        self.assertIn("profile=standard", context)
        self.assertIn("status=PLANNING", context)
        self.assertIn("progress=0/0 MUST", context)
        self.assertLessEqual(len(context), 1150)

    def test_stop_continues_execution_but_not_planning_or_repeated_stall(self) -> None:
        self.ctl("init", "--goal-id", "hook-goal", "--title", "Hook Goal", "--goal", "Test hooks", "--mode", "goal-flow")
        self.assertEqual(self.hook(STOP_HOOK), {})
        goal = self.repo / ".goal-flow" / "hook-goal" / "goal.md"
        dimension_lines = []
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary"}:
                rationale = f"{dimension} is covered by the hook acceptance criterion"
                dimension_lines.append(f"- {dimension}: COVERED; {rationale}; REQ-001")
            else:
                rationale = f"{dimension} has no material impact in this isolated hook fixture"
                dimension_lines.append(f"- {dimension}: N_A; {rationale}")
        goal.write_text(
            "# Hook Goal\n\n## Outcome\nTest hooks reliably.\n\n## Non-goals\nNo unrelated work.\n\n"
            "## Context and sources\nRepository hook behavior.\n\n## Approved design\nUse deterministic hooks.\n\n"
            f"## Acceptance dimensions\n{chr(10).join(dimension_lines)}\n\n"
            "## Acceptance criteria\nREQ-001 | MUST | Stop hook continues unfinished work | "
            "The hook prevents an unfinished task from silently stopping | "
            "The hook returns success while required work is incomplete | "
            "The requested long-task continuity behavior | TEST\n\n"
            "Required check TEST: python3 -c 'raise SystemExit(1)'\n\n"
            "## Milestones\nImplement and test.\n\n## Risks, migration, and rollback\nRevert changes.\n",
            encoding="utf-8",
        )
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "python3 -c 'raise SystemExit(1)'",
            "--role", "goal", "--evidence-mode", "real", "--covers-requirement-id", "REQ-001",
            "--proves", "Exercises the real Stop hook continuation path",
            "--limitations", "Does not prove host behavior outside this repository fixture",
        )
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "Stop hook continues unfinished work",
            "--proves", "The hook prevents an unfinished task from silently stopping",
            "--failure-mode", "The hook returns success while required work is incomplete",
            "--basis", "The requested long-task continuity behavior",
            "--verified-by", "TEST",
            "--minimum-evidence-mode", "real",
        )
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary"}:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "COVERED",
                    "--rationale", f"{dimension} is covered by the hook acceptance criterion",
                    "--requirement-id", "REQ-001",
                )
            else:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "N_A",
                    "--rationale", f"{dimension} has no material impact in this isolated hook fixture",
                )
        self.ctl("approve", "--user-approved", "--next-action", "Implement hook behavior")
        self.ctl("bind-worktree")
        self.assertEqual(self.hook(STOP_HOOK)["decision"], "block")
        self.assertEqual(self.hook(STOP_HOOK)["decision"], "block")
        stopped = self.hook(STOP_HOOK)
        self.assertIn("Goal Flow blocked", stopped["systemMessage"])
        status = self.ctl("status")
        self.assertEqual(status["state"]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
