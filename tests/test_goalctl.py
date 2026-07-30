from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "goal-flow" / "skills" / "goal-flow" / "scripts" / "goalctl.py"


class GoalCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Goal Flow Test")
        self.git("config", "user.email", "goal-flow@example.invalid")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "initial")
        self.ctl("init", "--goal-id", "test-goal", "--title", "Test Goal", "--goal", "Ship it")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo, text=True, capture_output=True, check=True
        )
        return result.stdout.strip()

    def ctl(self, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.repo), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def register_and_approve(self, check_command: str = "test -f feature.txt") -> None:
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", check_command,
        )
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "Feature works", "--verified-by", "TEST",
        )
        self.ctl("approve", "--user-approved", "--next-action", "Implement feature")

    def commit_product(self, content: str = "done\n") -> str:
        (self.repo / "feature.txt").write_text(content, encoding="utf-8")
        self.git("add", "feature.txt")
        self.git("commit", "-qm", "implement feature")
        return self.git("rev-parse", "HEAD")

    def record_complete_evidence(self, sha: str) -> None:
        verified = self.ctl("verify", "--id", "TEST")
        self.assertEqual(verified["status"], "PASS")
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "VERIFIED", "--statement", "Feature works",
            "--evidence", "Verified by the executed TEST receipt", "--git-sha", sha,
        )

    def test_approval_requires_must_requirement(self) -> None:
        payload = self.ctl("approve", "--user-approved", "--next-action", "Implement", expected=2)
        self.assertIn("MUST", payload["error"])

    def test_approval_requires_explicit_user_flag(self) -> None:
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "true",
        )
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "Feature works", "--verified-by", "TEST",
        )
        payload = self.ctl("approve", "--next-action", "Implement", expected=2)
        self.assertIn("Explicit user approval", payload["error"])

    def test_approved_design_drift_stops_gate(self) -> None:
        self.register_and_approve()
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        goal.write_text(goal.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        payload = self.ctl("gate")
        self.assertEqual(payload["gate"], "WAIT")
        self.assertIn("changed", payload["reasons"][0])

    def test_gate_allows_audit_commits_but_invalidates_product_changes(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        ready = self.ctl("gate", "--apply")
        self.assertEqual(ready["gate"], "READY_FOR_REVIEW")
        self.assertEqual(ready["status"], "READY_FOR_ACCEPTANCE")

        self.git("add", ".goal-flow")
        self.git("commit", "-qm", "record goal evidence")
        still_ready = self.ctl("gate")
        self.assertEqual(still_ready["gate"], "READY_FOR_REVIEW")

        (self.repo / "feature.txt").write_text("changed after verification\n", encoding="utf-8")
        stale = self.ctl("gate", "--apply")
        self.assertEqual(stale["gate"], "CONTINUE")
        self.assertEqual(stale["status"], "VERIFYING")
        self.assertEqual(stale["must_requirement_coverage"], 0)

    def test_approval_requires_a_required_check(self) -> None:
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "Feature works", "--verified-by", "TEST",
        )
        payload = self.ctl("approve", "--user-approved", "--next-action", "Implement", expected=2)
        self.assertIn("required PENDING check", payload["error"])

    def test_controller_executes_checks_and_rejects_self_reported_pass(self) -> None:
        self.register_and_approve(check_command="false")
        denied = self.ctl(
            "record", "check", "--id", "TEST", "--status", "PASS",
            "--command", "true", "--evidence", "claimed pass", expected=2,
        )
        self.assertIn("Use verify", denied["error"])
        executed = self.ctl("verify", "--id", "TEST", expected=1)
        self.assertEqual(executed["status"], "FAIL")
        self.assertIn("exit=1", executed["summary"])
        self.assertEqual(self.ctl("gate")["gate"], "CONTINUE")

    def test_check_command_cannot_run_before_approval(self) -> None:
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "true",
        )
        denied = self.ctl("verify", "--id", "TEST", expected=2)
        self.assertIn("before explicit design approval", denied["error"])

    def test_approved_contract_cannot_be_weakened(self) -> None:
        self.register_and_approve()
        denied = self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "should",
            "--status", "UNVERIFIED", "--statement", "Weaker feature", expected=2,
        )
        self.assertIn("frozen", denied["error"])
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-001"]["kind"] = "should"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertTrue(self.ctl("status")["design_drift"])

    def test_final_acceptance_requires_explicit_user_flag(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl("gate", "--apply")
        denied = self.ctl("accept", expected=2)
        self.assertIn("Explicit user acceptance", denied["error"])
        accepted = self.ctl("accept", "--user-accepted", "--accepted-by", "test-user")
        self.assertEqual(accepted["state"]["status"], "ACCEPTED")
        immutable = self.ctl(
            "update", "--goal-id", "test-goal", "--next-action", "Mutate accepted goal", expected=2,
        )
        self.assertIn("immutable", immutable["error"])
        self.assertIsNone(json.loads((self.repo / ".goal-flow" / "active.json").read_text())["goal_id"])

    def test_acceptance_rechecks_freshness(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl("gate", "--apply")
        (self.repo / "feature.txt").write_text("stale before acceptance\n", encoding="utf-8")
        denied = self.ctl("accept", "--user-accepted", expected=2)
        self.assertIn("no longer satisfied", denied["error"])

    def test_accepted_risk_requires_identity(self) -> None:
        denied = self.ctl(
            "record", "risk", "--id", "RISK-001", "--status", "ACCEPTED",
            "--severity", "medium", "--statement", "Known limitation", expected=2,
        )
        self.assertIn("--accepted-by", denied["error"])
        accepted = self.ctl(
            "record", "risk", "--id", "RISK-001", "--status", "ACCEPTED",
            "--severity", "medium", "--statement", "Known limitation",
            "--accepted-by", "test-user",
        )
        self.assertEqual(accepted["state"]["risks"]["RISK-001"]["accepted_by"], "test-user")

    def test_serious_risk_mitigation_requires_fresh_check_receipt(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "OPEN",
            "--severity", "critical", "--statement", "Critical failure mode",
        )
        self.assertEqual(self.ctl("gate")["gate"], "CONTINUE")
        denied = self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "MITIGATED",
            "--evidence", "Agent says fixed", expected=2,
        )
        self.assertIn("fresh PASS", denied["error"])
        mitigated = self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "MITIGATED",
            "--evidence", "Covered by executed TEST", "--verified-by", "TEST",
        )
        self.assertEqual(mitigated["state"]["risks"]["RISK-CRITICAL"]["severity"], "critical")
        self.assertEqual(self.ctl("gate")["gate"], "READY_FOR_REVIEW")

    def test_replan_invalidates_approval_and_evidence(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        payload = self.ctl("replan", "--reason", "Public API changed")
        state = payload["state"]
        self.assertEqual(state["goal_revision"], 2)
        self.assertFalse(state["approved"])
        self.assertEqual(state["requirements"]["REQ-001"]["status"], "UNVERIFIED")
        self.assertEqual(state["checks"]["TEST"]["status"], "PENDING")

    def test_pause_and_resume(self) -> None:
        self.register_and_approve()
        paused = self.ctl("pause", "--reason", "Waiting for environment")
        self.assertEqual(paused["state"]["status"], "PAUSED")
        self.assertEqual(self.ctl("gate")["gate"], "WAIT")
        resumed = self.ctl("resume")
        self.assertEqual(resumed["state"]["status"], "EXECUTING")

    def test_stop_loop_breaker_waits_after_three_unchanged_attempts(self) -> None:
        self.register_and_approve()
        first = self.ctl("gate", "--stop-event")
        second = self.ctl("gate", "--stop-event")
        third = self.ctl("gate", "--stop-event")
        self.assertEqual(first["gate"], "CONTINUE")
        self.assertEqual(second["gate"], "CONTINUE")
        self.assertEqual(third["gate"], "WAIT")
        self.assertEqual(third["status"], "BLOCKED")
        self.assertIn("No observable state progress", third["reasons"][0])


if __name__ == "__main__":
    unittest.main()
