from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "goal-flow" / "skills" / "goal-flow" / "scripts" / "goalctl.py"
DIMENSIONS = [
    "functional",
    "negative-boundary",
    "regression-compatibility",
    "security-privacy",
    "performance-reliability",
    "operations-observability",
    "migration-rollback",
    "documentation-deliverables",
]
CHECK_EVIDENCE_ARGS = [
    "--role", "goal",
    "--evidence-mode", "real",
    "--covers-requirement-id", "REQ-001",
    "--proves", "Exercises the committed observable user outcome end to end",
    "--limitations", "Does not prove behavior outside the declared repository scenario",
]
REQUIREMENT_EVIDENCE_ARGS = ["--minimum-evidence-mode", "real"]


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
        self.ctl("init", "--goal-id", "test-goal", "--title", "Test Goal", "--goal", "Ship it", "--mode", "goal-flow")

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

    def record_check(self, *args: str, expected: int = 0) -> dict:
        return self.ctl("record", "check", *args, *CHECK_EVIDENCE_ARGS, expected=expected)

    def test_status_is_graceful_without_an_active_goal(self) -> None:
        self.ctl("cancel", "--reason", "test status without an active goal")
        payload = self.ctl("status")
        self.assertFalse(payload["active"])
        self.assertIn("No active goal", payload["message"])

    def test_profiles_default_to_standard_and_legacy_goals_remain_strict(self) -> None:
        self.assertEqual(self.ctl("status")["state"]["profile"], "standard")
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.pop("profile")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.ctl("status")["state"]["profile"], "strict")

    def test_classify_recommends_smallest_harness_for_task_shape(self) -> None:
        micro = self.ctl("classify", "--goal", "Fix one typo")
        self.assertEqual(micro["mode"], "micro")
        standard = self.ctl(
            "classify", "--goal", "Add a user-visible feature", "--behavior-change",
            "--files", "3", "--steps", "3", "--task-type", "feature",
        )
        self.assertEqual(standard["mode"], "standard")
        long_task = self.ctl(
            "classify", "--goal", "Migrate tenant data", "--task-type", "migration",
            "--risk-level", "high", "--cross-session",
        )
        self.assertEqual(long_task["mode"], "goal-flow")
        self.assertEqual(long_task["profile"], "strict")

    def test_explicit_harness_mode_is_never_downgraded(self) -> None:
        goal_flow = self.ctl(
            "classify", "--goal", "Add a user-visible feature", "--behavior-change",
            "--files", "3", "--steps", "3", "--default-mode", "goal-flow",
        )
        strict = self.ctl(
            "classify", "--goal", "Add a user-visible feature", "--behavior-change",
            "--files", "3", "--steps", "3", "--default-mode", "strict",
        )
        self.assertEqual(goal_flow["mode"], "goal-flow")
        self.assertEqual(strict["mode"], "goal-flow")
        self.assertEqual(strict["profile"], "strict")
        safety_floor = self.ctl(
            "classify", "--goal", "Migrate tenant data", "--task-type", "migration",
            "--risk-level", "high", "--default-mode", "standard",
        )
        self.assertEqual(safety_floor["profile"], "strict")

    def test_open_chinese_decision_blocks_plan_approval(self) -> None:
        self.write_complete_goal()
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        text = goal.read_text(encoding="utf-8")
        text = text.replace(
            "## Questions requiring user decision\n- None after repository inspection.",
            "## 仍需用户决定\n- 数据保留 7 天还是永久保留？",
        )
        goal.write_text(text, encoding="utf-8")
        self.record_check("--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement()
        self.register_dimensions()
        denied = self.ctl("plan-check", expected=1)
        self.assertEqual(denied["decision_check"]["status"], "pending")
        self.assertTrue(any("Decision Check" in item for item in denied["reasons"]))

    def test_project_context_is_scaffolded_and_readable(self) -> None:
        context_path = self.repo / ".goal-flow" / "context.md"
        self.assertFalse(context_path.exists())
        created = self.ctl("context", "--init")
        self.assertTrue(created["created"])
        loaded = self.ctl("context")
        self.assertTrue(loaded["exists"])
        self.assertIn("Goal Flow project context", loaded["excerpt"])
        existing = self.ctl("context", "--init")
        self.assertFalse(existing["created"])

    def test_micro_mode_does_not_initialize_full_goal_flow(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        denied = self.ctl(
            "init", "--goal-id", "micro-goal", "--title", "Micro", "--goal", "Fix one typo",
            "--mode", "micro", expected=2,
        )
        self.assertIn("do not initialize Goal Flow", denied["error"])
        self.assertFalse((self.repo / ".goal-flow" / "micro-goal").exists())

    def test_init_does_not_silently_replace_active_goal(self) -> None:
        denied = self.ctl(
            "init", "--goal-id", "second-goal", "--title", "Second", "--goal", "Another task", expected=2,
        )
        self.assertIn("pass --switch", denied["error"])
        self.assertEqual(self.ctl("status")["goal_id"], "test-goal")
        switched = self.ctl(
            "init", "--goal-id", "second-goal", "--title", "Second", "--goal", "Another task", "--switch",
        )
        self.assertEqual(switched["state"]["goal_id"], "second-goal")
        old_state = json.loads((self.repo / ".goal-flow" / "test-goal" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(old_state["status"], "PAUSED")
        self.assertIn("Switched to new goal", old_state["wait_reason"])

    def test_standard_plan_check_uses_reduced_contract(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "light-standard", "--title", "Light Standard", "--goal", "Ship one small change",
            "--mode", "standard",
        )
        goal = self.repo / ".goal-flow" / "light-standard" / "goal.md"
        goal.write_text(
            """# Light Standard

## Outcome
feature.txt exists with expected content.

## Questions requiring user decision
- None after repository inspection.

## Acceptance dimensions
- functional: COVERED; The observable file outcome is checked; REQ-001

## Acceptance criteria
REQ-001 | MUST | feature.txt exists with expected content

Required check TEST: test -f feature.txt
""",
            encoding="utf-8",
        )
        self.record_check("--goal-id", "light-standard", "--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.ctl(
            "record", "requirement", "--goal-id", "light-standard", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "feature.txt exists with expected content", "--verified-by", "TEST", *REQUIREMENT_EVIDENCE_ARGS,
        )
        self.ctl(
            "record", "dimension", "--goal-id", "light-standard", "--id", "functional", "--status", "COVERED",
            "--rationale", "The observable file outcome is checked", "--requirement-id", "REQ-001",
        )
        ready = self.ctl("plan-check", "--goal-id", "light-standard")
        self.assertEqual(ready["gate"], "READY_FOR_APPROVAL")
        self.assertEqual(ready["dimensions_total"], 1)

    def test_standard_preserves_dirty_baseline_but_rejects_new_drift(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        (self.repo / "preexisting.txt").write_text("user work\n", encoding="utf-8")
        self.ctl(
            "init", "--goal-id", "baseline-standard", "--title", "Baseline", "--goal", "Ship a small change",
            "--mode", "standard",
        )
        self.write_complete_goal_for("baseline-standard")
        self.record_check("--goal-id", "baseline-standard", "--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("baseline-standard")
        self.ctl(
            "record", "dimension", "--goal-id", "baseline-standard", "--id", "functional", "--status", "COVERED",
            "--rationale", "functional is covered by the observable acceptance criterion", "--requirement-id", "REQ-001",
        )
        self.ctl("approve", "--goal-id", "baseline-standard", "--auto-approved", "--next-action", "Implement baseline task")
        self.commit_product()
        (self.repo / "new-drift.txt").write_text("unexpected\n", encoding="utf-8")
        denied = self.ctl("verify", "--goal-id", "baseline-standard", "--id", "TEST", expected=2)
        self.assertIn("beyond its initialization baseline", denied["error"])
        (self.repo / "new-drift.txt").unlink()
        self.assertEqual(self.ctl("verify", "--goal-id", "baseline-standard", "--id", "TEST")["status"], "PASS")

    def test_standard_behavior_change_keeps_final_acceptance(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "behavior-standard", "--title", "Behavior Standard", "--goal", "Change behavior",
            "--mode", "standard", "--behavior-change",
        )
        self.write_complete_goal_for("behavior-standard")
        behavior_dir = self.repo / ".goal-flow" / "behavior-standard"
        (behavior_dir / "delta.md").write_text(
            """# Behavior Delta

## ADDED

### REQ-001: Observable feature

#### SCN-001 (REQ-001): Feature succeeds

- GIVEN the repository is ready
- WHEN the feature is invoked
- THEN the expected result is returned

## MODIFIED
## REMOVED
""",
            encoding="utf-8",
        )
        (behavior_dir / "tasks.md").write_text(
            "- [ ] T-001 (REQ-001, SCN-001): Implement and verify the feature\n",
            encoding="utf-8",
        )
        self.record_check("--goal-id", "behavior-standard", "--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("behavior-standard")
        self.ctl(
            "record", "dimension", "--goal-id", "behavior-standard", "--id", "functional", "--status", "COVERED",
            "--rationale", "functional is covered by the observable acceptance criterion", "--requirement-id", "REQ-001",
        )
        self.ctl("approve", "--goal-id", "behavior-standard", "--auto-approved", "--next-action", "Implement behavior task")
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        ready = self.ctl("gate", "--goal-id", "behavior-standard", "--apply")
        self.assertEqual(ready["status"], "READY_FOR_ACCEPTANCE")
        accepted = self.ctl("accept", "--goal-id", "behavior-standard", "--user-accepted", "--accepted-by", "test-user")
        self.assertEqual(accepted["state"]["status"], "ACCEPTED")

    def test_standard_mode_supports_implicit_approval_and_current_worktree(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "standard-goal", "--title", "Standard", "--goal", "Ship a small change",
            "--mode", "standard",
        )
        self.write_complete_goal_for("standard-goal")
        self.record_check("--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("standard-goal")
        self.register_dimensions_for("standard-goal")
        approved = self.ctl("approve", "--goal-id", "standard-goal", "--auto-approved", "--next-action", "Implement standard task")
        self.assertEqual(approved["state"]["approval_mode"], "implicit-standard")
        binding = self.ctl("bind-worktree", "--goal-id", "standard-goal")
        self.assertTrue(binding["skipped"])
        self.assertIsNone(binding["state"]["worktree_binding"])

    def test_strict_profile_never_uses_lightweight_standard_shortcuts(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "strict-standard", "--title", "Strict Standard", "--goal", "Ship a risky change",
            "--mode", "standard", "--profile", "strict",
        )
        self.write_complete_goal_for("strict-standard")
        self.record_check("--goal-id", "strict-standard", "--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("strict-standard")
        self.register_dimensions_for("strict-standard")
        approved = self.ctl("approve", "--goal-id", "strict-standard", "--user-approved", "--next-action", "Implement strict task")
        self.assertEqual(approved["state"]["profile"], "strict")
        binding = self.ctl("bind-worktree", "--goal-id", "strict-standard")
        self.assertFalse(binding.get("skipped", False))
        self.assertIsNotNone(binding["state"]["worktree_binding"])

    def test_standard_gate_completes_without_final_acceptance_button(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "standard-goal", "--title", "Standard", "--goal", "Ship a small change",
            "--mode", "standard",
        )
        self.write_complete_goal_for("standard-goal")
        self.record_check("--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("standard-goal")
        self.register_dimensions_for("standard-goal")
        self.ctl("approve", "--goal-id", "standard-goal", "--auto-approved", "--next-action", "Implement standard task")
        self.commit_product()
        self.ctl("verify", "--goal-id", "standard-goal", "--id", "TEST")
        self.record_complete_evidence(self.git("rev-parse", "HEAD"))
        completed = self.ctl("gate", "--goal-id", "standard-goal", "--apply")
        self.assertEqual(completed["gate"], "ACCEPTED")
        self.assertFalse(self.ctl("status")["active"])

    def test_behavior_change_scaffolds_harness_delta_and_tasks(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        initialized = self.ctl(
            "init", "--goal-id", "behavior-goal", "--title", "Behavior Goal",
            "--goal", "Change observable behavior", "--behavior-change",
            "--mode", "standard", "--task-type", "feature", "--risk-level", "medium",
        )
        state = initialized["state"]
        self.assertEqual(state["harness"]["mode"], "standard")
        self.assertTrue(state["harness"]["behavior_change"])
        directory = self.repo / ".goal-flow" / "behavior-goal"
        self.assertTrue((directory / "delta.md").exists())
        self.assertTrue((directory / "tasks.md").exists())
        review = self.ctl("review", "--goal-id", "behavior-goal", expected=1)
        self.assertEqual(review["status"], "BLOCK")

    def test_behavior_change_review_traces_scenarios_and_tasks(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "behavior-goal", "--title", "Behavior Goal",
            "--goal", "Change observable behavior", "--behavior-change",
        )
        self.write_complete_goal_for("behavior-goal")
        directory = self.repo / ".goal-flow" / "behavior-goal"
        (directory / "delta.md").write_text(
            """# Behavior Delta

## ADDED

### REQ-001: Observable feature

#### SCN-001 (REQ-001): Feature succeeds

- GIVEN the repository is ready
- WHEN the feature is invoked
- THEN the expected result is returned

## MODIFIED

## REMOVED
""",
            encoding="utf-8",
        )
        (directory / "tasks.md").write_text(
            "- [ ] T-001 (REQ-001, SCN-001): Implement and verify the feature\n",
            encoding="utf-8",
        )
        self.record_check("--id", "TEST", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.register_requirement_for("behavior-goal")
        self.register_dimensions_for("behavior-goal")
        review = self.ctl("review", "--goal-id", "behavior-goal")
        self.assertEqual(review["status"], "WARN")
        self.assertEqual(review["scenario_count"], 1)
        self.assertEqual(review["task_count"], 1)
        strict = self.ctl("review", "--goal-id", "behavior-goal", "--strict", expected=1)
        self.assertEqual(strict["status"], "BLOCK")

    def test_standard_requires_core_dimensions_but_strict_requires_all(self) -> None:
        self.write_complete_goal()
        self.record_check(
            "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "test -f feature.txt",
        )
        self.register_requirement()
        for dimension in [
            "functional", "negative-boundary", "regression-compatibility",
            "documentation-deliverables",
        ]:
            if dimension in {"functional", "negative-boundary", "documentation-deliverables"}:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "COVERED",
                    "--rationale", f"{dimension} is covered by the observable acceptance criterion",
                    "--requirement-id", "REQ-001",
                )
            else:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "N_A",
                    "--rationale", f"{dimension} has no material impact for this isolated file fixture",
                )
        standard = self.ctl("plan-check")
        self.assertEqual(standard["gate"], "READY_FOR_APPROVAL")
        self.assertEqual(standard["dimensions_total"], 4)

        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["profile"] = "strict"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        strict = self.ctl("plan-check", expected=1)
        self.assertEqual(strict["gate"], "REVISE_PLAN")
        self.assertIn("security-privacy", " ".join(strict["reasons"]))

    def test_summary_has_human_and_json_views(self) -> None:
        payload = self.ctl("summary", "--json")
        self.assertEqual(payload["profile"], "standard")
        self.assertEqual(payload["must_total"], 0)
        self.assertIn("Next:", payload["text"])
        result = subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.repo), "summary"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Goal: Test Goal", result.stdout)
        self.assertNotIn('"active"', result.stdout)

    def test_bind_worktree_requires_approval_and_rejects_wrong_branch(self) -> None:
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["harness"]["mode"] = "goal-flow"
        state["harness"]["requested_mode"] = "goal-flow"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        denied = self.ctl("bind-worktree", expected=2)
        self.assertIn("Approve", denied["error"])
        self.register_and_approve()
        binding = self.ctl("status")["state"]["worktree_binding"]
        self.assertEqual(binding["branch"], self.git("branch", "--show-current"))
        self.git("switch", "-c", "wrong-branch")
        mismatch = self.ctl("update", "--next-action", "wrong branch", expected=2)
        self.assertIn("binding mismatch", mismatch["error"])

    def test_locked_concurrent_updates_increment_state_revision_without_loss(self) -> None:
        self.register_and_approve()
        before = self.ctl("status")["state"]
        processes = [
            subprocess.Popen(
                [sys.executable, str(CLI), "--root", str(self.repo), "update", "--no-progress"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            for _ in range(4)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr + stdout)
        after = self.ctl("status")["state"]
        self.assertEqual(after["no_progress_count"], 4)
        self.assertEqual(after["state_revision"], before["state_revision"] + 4)
        events_path = self.repo / ".goal-flow" / "test-goal" / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual(sum(item["event"] == "update" for item in events), 0)

    def test_events_are_minimal_and_report_tolerates_an_incomplete_tail(self) -> None:
        secret = "SECRET-user-supplied-next-action"
        self.ctl("update", "--next-action", secret)
        events_path = self.repo / ".goal-flow" / "test-goal" / "events.jsonl"
        raw_events = events_path.read_text(encoding="utf-8")
        events = [json.loads(line) for line in raw_events.splitlines()]
        allowed = {
            "time", "event", "status", "revision", "milestone", "check",
            "result", "duration_ms", "git_sha", "reason",
        }
        self.assertTrue(events)
        self.assertTrue(all(set(item) <= allowed for item in events))
        self.assertNotIn(secret, raw_events)

        report = self.ctl("report", "--json")
        self.assertEqual(report["goal_id"], "test-goal")
        self.assertIn("assurance", report)
        self.assertIn("Timeline", report["text"])

        with events_path.open("a", encoding="utf-8") as handle:
            handle.write('{"time":"unfinished"')
        recovered = self.ctl("report", "--json")
        self.assertTrue(recovered["warnings"])
        self.assertIn("incomplete final event", recovered["warnings"][0])

    def test_report_supports_legacy_goals_without_events(self) -> None:
        events_path = self.repo / ".goal-flow" / "test-goal" / "events.jsonl"
        events_path.unlink()
        report = self.ctl("report", "--json")
        self.assertEqual(report["events"], [])
        self.assertIn("No event history", report["text"])

    def test_state_compare_and_swap_rejects_a_stale_writer(self) -> None:
        spec = importlib.util.spec_from_file_location("goalctl_under_test", CLI)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _, directory, first = module.load_state(self.repo)
        _, _, stale = module.load_state(self.repo)
        first["next_action"] = "first writer"
        module.save_state(directory, first)
        stale["next_action"] = "stale writer"
        with self.assertRaises(module.GoalFlowError):
            module.save_state(directory, stale)

    def test_verifier_receipt_contains_allowlisted_environment_fingerprint(self) -> None:
        self.register_and_approve()
        (self.repo / "feature.txt").write_text("done\n", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("example==1\n", encoding="utf-8")
        self.git("add", "feature.txt", "requirements.txt")
        self.git("commit", "-qm", "implement with lockfile")
        payload = self.ctl("verify", "--id", "TEST")
        environment = payload["environment"]
        self.assertEqual(set(environment), {"os", "os_release", "architecture", "python", "lockfiles"})
        self.assertIn("requirements.txt", environment["lockfiles"])
        self.assertNotIn("PATH", json.dumps(environment))

    def test_verifier_timeout_kills_descendant_process_group(self) -> None:
        descriptor, pid_name = tempfile.mkstemp(prefix="goal-flow-child-")
        os.close(descriptor)
        pid_file = Path(pid_name)
        command = (
            "python3 -c 'import subprocess,time; "
            "p=subprocess.Popen([\"python3\",\"-c\",\"import signal,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)\"]); "
            f"open(\"{pid_file}\",\"w\").write(str(p.pid)); time.sleep(60)'"
        )
        try:
            self.write_complete_goal(command)
            self.record_check(
                "--id", "TEST", "--status", "PENDING", "--required",
                "--command", command, "--timeout", "1",
            )
            self.register_requirement()
            self.register_dimensions()
            self.ctl("approve", "--user-approved", "--next-action", "Run timeout fixture")
            self.ctl("bind-worktree")
            payload = self.ctl("verify", "--id", "TEST", expected=1)
            self.assertTrue(payload["timed_out"])
            self.assertEqual(payload["termination"], "SIGKILL")
            child_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.time() + 2
            while time.time() < deadline:
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail(f"descendant process {child_pid} survived verifier timeout")
        finally:
            pid_file.unlink(missing_ok=True)

    def write_complete_goal(self, check_command: str = "test -f feature.txt") -> None:
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        dimension_lines = []
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary", "documentation-deliverables"}:
                rationale = f"{dimension} is covered by the observable acceptance criterion"
                dimension_lines.append(f"- {dimension}: COVERED; {rationale}; REQ-001")
            else:
                rationale = f"{dimension} has no material impact for this isolated file fixture"
                dimension_lines.append(f"- {dimension}: N_A; {rationale}")
        goal.write_text(
            f"""# Test Goal

## Outcome
Ship an observable feature.

## Non-goals
- No unrelated refactoring.

## Context and sources
- Existing repository behavior and tests.

## Assumptions and decisions
- Preserve compatibility.

## Questions requiring user decision
- None after repository inspection.

## Approved design
Add feature.txt with deterministic behavior.

## Acceptance dimensions
{chr(10).join(dimension_lines)}

## Acceptance criteria
REQ-001 | MUST | feature.txt exists with expected content | The committed feature artifact exists and is readable | The file is missing or contains unexpected content | The requested repository outcome and existing test conventions | TEST

Required check TEST: {check_command}

## Milestones
1. Implement and verify.

## Risks, migration, and rollback
- Revert the implementation commit.

## Approval
- Revision: 1
- Status: PENDING
""",
            encoding="utf-8",
        )

    def write_complete_goal_for(self, goal_id: str, check_command: str = "test -f feature.txt") -> None:
        goal = self.repo / ".goal-flow" / goal_id / "goal.md"
        dimension_lines = []
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary", "documentation-deliverables"}:
                rationale = f"{dimension} is covered by the observable acceptance criterion"
                dimension_lines.append(f"- {dimension}: COVERED; {rationale}; REQ-001")
            else:
                rationale = f"{dimension} has no material impact for this isolated file fixture"
                dimension_lines.append(f"- {dimension}: N_A; {rationale}")
        goal.write_text(
            f"""# Behavior Goal

## Outcome
Ship an observable feature.

## Non-goals
- No unrelated refactoring.

## Context and sources
- Existing repository behavior and tests.

## Assumptions and decisions
- Preserve compatibility.

## Questions requiring user decision
- None after repository inspection.

## Approved design
Add feature.txt with deterministic behavior.

## Acceptance dimensions
{chr(10).join(dimension_lines)}

## Acceptance criteria
REQ-001 | MUST | feature.txt exists with expected content | The committed feature artifact exists and is readable | The file is missing or contains unexpected content | The requested repository outcome and existing test conventions | TEST

Required check TEST: {check_command}

## Milestones
1. Implement and verify.

## Risks, migration, and rollback
- Revert the implementation commit.

## Approval
- Revision: 1
- Status: PENDING
""",
            encoding="utf-8",
        )

    def register_requirement(self) -> None:
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "feature.txt exists with expected content",
            "--proves", "The committed feature artifact exists and is readable",
            "--failure-mode", "The file is missing or contains unexpected content",
            "--basis", "The requested repository outcome and existing test conventions",
            "--verified-by", "TEST",
            *REQUIREMENT_EVIDENCE_ARGS,
        )

    def register_requirement_for(self, goal_id: str) -> None:
        self.ctl(
            "record", "requirement", "--goal-id", goal_id, "--id", "REQ-001", "--kind", "must",
            "--status", "UNVERIFIED", "--statement", "feature.txt exists with expected content",
            "--proves", "The committed feature artifact exists and is readable",
            "--failure-mode", "The file is missing or contains unexpected content",
            "--basis", "The requested repository outcome and existing test conventions",
            "--verified-by", "TEST",
            *REQUIREMENT_EVIDENCE_ARGS,
        )

    def complete_visual_design_for(self, goal_id: str) -> Path:
        path = self.repo / ".goal-flow" / goal_id / "design" / "architecture.drawio"
        source = path.read_text(encoding="utf-8").replace("TODO: ", "")
        path.write_text(source, encoding="utf-8")
        return path

    def register_dimensions(self) -> None:
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary", "documentation-deliverables"}:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "COVERED",
                    "--rationale", f"{dimension} is covered by the observable acceptance criterion",
                    "--requirement-id", "REQ-001",
                )
            else:
                self.ctl(
                    "record", "dimension", "--id", dimension, "--status", "N_A",
                    "--rationale", f"{dimension} has no material impact for this isolated file fixture",
                )

    def register_dimensions_for(self, goal_id: str) -> None:
        for dimension in DIMENSIONS:
            if dimension in {"functional", "negative-boundary", "documentation-deliverables"}:
                self.ctl(
                    "record", "dimension", "--goal-id", goal_id, "--id", dimension, "--status", "COVERED",
                    "--rationale", f"{dimension} is covered by the observable acceptance criterion",
                    "--requirement-id", "REQ-001",
                )
            else:
                self.ctl(
                    "record", "dimension", "--goal-id", goal_id, "--id", dimension, "--status", "N_A",
                    "--rationale", f"{dimension} has no material impact for this isolated file fixture",
                )

    def prepare_plan(self, check_command: str = "test -f feature.txt") -> None:
        self.write_complete_goal(check_command)
        self.record_check(
            "--id", "TEST", "--status", "PENDING", "--required",
            "--command", check_command,
        )
        self.register_requirement()
        self.register_dimensions()

    def register_and_approve(self, check_command: str = "test -f feature.txt") -> None:
        self.prepare_plan(check_command)
        self.ctl("approve", "--user-approved", "--next-action", "Implement feature")
        self.ctl("bind-worktree")

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
            "--status", "VERIFIED", "--statement", "feature.txt exists with expected content",
            "--evidence", "Verified by the executed TEST receipt", "--git-sha", sha,
            *REQUIREMENT_EVIDENCE_ARGS,
        )

    def test_approval_requires_must_requirement(self) -> None:
        payload = self.ctl("approve", "--user-approved", "--next-action", "Implement", expected=2)
        self.assertIn("MUST", payload["error"])

    def test_approval_requires_explicit_user_flag(self) -> None:
        self.prepare_plan()
        payload = self.ctl("approve", "--next-action", "Implement", expected=2)
        self.assertIn("Explicit user approval", payload["error"])

    def test_approval_rejects_changed_design_snapshot(self) -> None:
        self.prepare_plan()
        snapshot = self.ctl("summary", "--json")["design_hash"]
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        goal.write_text(goal.read_text(encoding="utf-8") + "\nAdditional approved constraint.\n", encoding="utf-8")
        denied = self.ctl(
            "approve", "--user-approved", "--expected-design-hash", snapshot,
            "--next-action", "Implement", expected=2,
        )
        self.assertIn("方案内容已变化", denied["error"])

    def test_approved_design_drift_stops_gate(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl("gate", "--apply")
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        goal.write_text(goal.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
        payload = self.ctl("gate")
        self.assertEqual(payload["gate"], "WAIT")
        self.assertIn("changed", payload["reasons"][0])
        applied = self.ctl("gate", "--apply")
        self.assertEqual(applied["stored_status"], "BLOCKED")
        self.assertIn("replan", applied["next_action"])

    def test_gate_allows_audit_commits_but_invalidates_product_changes(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        # Controller receipts leave audit files dirty; they must not invalidate
        # evidence or prevent another verifier from starting.
        self.assertEqual(self.ctl("verify", "--id", "TEST")["status"], "PASS")
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

    def test_ds_store_reports_exact_invalidating_path_and_effective_status(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl("gate", "--apply")
        (self.repo / ".DS_Store").write_bytes(b"finder metadata")
        status = self.ctl("status")
        self.assertEqual(status["stored_status"], "READY_FOR_ACCEPTANCE")
        self.assertEqual(status["effective_status"], "VERIFYING")
        self.assertFalse(status["freshness"]["fresh"])
        self.assertEqual(status["invalidated_paths"], [".DS_Store"])
        summary = self.ctl("summary", "--json")
        report = self.ctl("report", "--json")
        self.assertIn(".DS_Store", summary["invalidated_paths"])
        self.assertIn(".DS_Store", report["invalidated_paths"])

    def test_real_requirement_rejects_weaker_planned_evidence(self) -> None:
        self.write_complete_goal()
        self.ctl(
            "record", "check", "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "test -f feature.txt", "--role", "goal",
            "--evidence-mode", "simulated", "--covers-requirement-id", "REQ-001",
            "--proves", "Exercises the planned user outcome through a simulation",
            "--limitations", "Does not execute the real user path or external boundary",
        )
        self.register_requirement()
        self.register_dimensions()
        denied = self.ctl("plan-check", expected=1)
        self.assertTrue(any("requires real evidence" in reason for reason in denied["reasons"]))

    def test_non_real_evidence_downgrade_can_deliver_with_medium_assurance(self) -> None:
        self.prepare_plan()
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-001"]["minimum_evidence_mode"] = "simulated"
        state["checks"]["TEST"]["evidence_mode"] = "mock"
        state["checks"]["TEST"]["role"] = "component"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        goal_path = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        goal_path.write_text(
            goal_path.read_text(encoding="utf-8") + "\nRequired check GOAL: test -f feature.txt\n",
            encoding="utf-8",
        )
        self.record_check("--id", "GOAL", "--status", "PENDING", "--required", "--command", "test -f feature.txt")
        self.ctl("approve", "--user-approved", "--next-action", "Implement feature")
        self.ctl("bind-worktree")
        sha = self.commit_product()
        self.ctl("verify", "--id", "TEST")
        self.ctl("verify", "--id", "GOAL")
        self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "VERIFIED", "--statement", "feature.txt exists with expected content",
            "--evidence", "Mock receipt is an explicit evidence downgrade", "--git-sha", sha,
            "--minimum-evidence-mode", "simulated",
        )
        gate = self.ctl("gate")
        self.assertEqual(gate["gate"], "READY_FOR_REVIEW")
        self.assertEqual(gate["assurance"], "MEDIUM")
        report = self.ctl("report", "--json")
        self.assertEqual(report["partially_proved"], ["REQ-001"])

    def test_full_flow_requires_goal_level_check(self) -> None:
        self.prepare_plan()
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["checks"]["TEST"]["role"] = "component"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        denied = self.ctl("plan-check", expected=1)
        self.assertTrue(any("goal check" in reason for reason in denied["reasons"]))

    def test_approval_requires_a_required_check(self) -> None:
        self.write_complete_goal()
        self.register_requirement()
        self.register_dimensions()
        payload = self.ctl("approve", "--user-approved", "--next-action", "Implement", expected=2)
        self.assertIn("required PENDING check", payload["error"])

    def test_controller_executes_checks_and_rejects_self_reported_pass(self) -> None:
        self.register_and_approve(check_command="python3 -c 'raise SystemExit(1)'")
        denied = self.ctl(
            "record", "check", "--id", "TEST", "--status", "PASS",
            "--command", "true", "--evidence", "claimed pass", expected=2,
        )
        self.assertIn("Use verify", denied["error"])
        executed = self.ctl("verify", "--id", "TEST", expected=1)
        self.assertEqual(executed["status"], "FAIL")
        self.assertIn("exit=1", executed["summary"])
        events = [
            json.loads(line)
            for line in (
                self.repo / ".goal-flow" / "test-goal" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        verify_event = [item for item in events if item["event"] == "verify"][-1]
        self.assertEqual(verify_event["check"], "TEST")
        self.assertEqual(verify_event["result"], "FAIL")
        self.assertIn("duration_ms", verify_event)
        self.assertNotIn("summary", verify_event)
        self.assertEqual(self.ctl("gate")["gate"], "CONTINUE")

    def test_failed_check_exposes_classification_and_next_strategy(self) -> None:
        self.register_and_approve(check_command="python3 -c 'raise AssertionError(\"bad behavior\")'")
        executed = self.ctl("verify", "--id", "TEST", expected=1)
        self.assertEqual(executed["failure_class"], "implementation_defect")
        self.assertIn("失败断言", executed["recommended_action"])

    def test_check_command_cannot_run_before_approval(self) -> None:
        self.record_check(
            "--id", "TEST", "--status", "PENDING", "--required",
            "--command", "python3 -c 'print(1)'",
        )
        denied = self.ctl("verify", "--id", "TEST", expected=2)
        self.assertIn("before explicit design approval", denied["error"])

    def test_approved_contract_cannot_be_weakened(self) -> None:
        self.register_and_approve()
        denied = self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "should",
            "--status", "UNVERIFIED", "--statement", "Weaker feature", *REQUIREMENT_EVIDENCE_ARGS, expected=2,
        )
        self.assertIn("frozen", denied["error"])
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-001"]["kind"] = "should"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertTrue(self.ctl("status")["design_drift"])

    def test_plan_check_requires_detailed_acceptance_contract(self) -> None:
        incomplete = self.ctl("plan-check", expected=1)
        self.assertEqual(incomplete["gate"], "REVISE_PLAN")
        self.assertTrue(any("placeholder" in reason for reason in incomplete["reasons"]))
        self.prepare_plan()
        ready = self.ctl("plan-check")
        self.assertEqual(ready["gate"], "READY_FOR_APPROVAL")
        self.assertEqual(ready["dimensions_assessed"], 4)

    def test_visual_design_scaffold_is_editable_previewable_and_required(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        created = self.ctl(
            "init", "--goal-id", "visual-goal", "--title", "Visual Goal",
            "--goal", "Design and ship an understandable change", "--mode", "standard",
            "--visual-design",
        )
        directory = self.repo / ".goal-flow" / "visual-goal" / "design"
        self.assertTrue((directory / "architecture.drawio").exists())
        self.assertTrue((directory / "architecture.html").exists())
        self.assertTrue(created["state"]["harness"]["visual_design"])
        self.assertEqual(self.ctl("status")["phase"], "analysis-design")
        incomplete = self.ctl("design-check", expected=1)
        self.assertTrue(any("placeholder" in reason for reason in incomplete["reasons"]))
        self.complete_visual_design_for("visual-goal")
        checked = self.ctl("design-check")
        self.assertEqual(checked["pages"], ["Architecture", "Critical data flow"])
        rendered = self.ctl("design-render")
        self.assertEqual(Path(rendered["viewer"]).resolve(), (directory / "architecture.html").resolve())

    def test_visual_design_requires_protocol_field_contracts(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "visual-fields", "--title", "Visual Fields",
            "--goal", "Design and ship an understandable change", "--mode", "standard",
            "--visual-design",
        )
        drawing = self.complete_visual_design_for("visual-fields")
        source = drawing.read_text(encoding="utf-8").replace(' data-fields="id|UUID|required|format|identity"', "", 1)
        drawing.write_text(source, encoding="utf-8")
        denied = self.ctl("design-check", expected=1)
        self.assertTrue(any("data-fields" in item for item in denied["reasons"]))

    def test_visual_design_semantics_are_frozen_but_layout_remains_editable(self) -> None:
        self.ctl("cancel", "--reason", "replace default goal")
        self.ctl(
            "init", "--goal-id", "visual-contract", "--title", "Visual Contract",
            "--goal", "Design and ship an understandable change", "--mode", "standard",
            "--visual-design",
        )
        self.write_complete_goal_for("visual-contract")
        drawing = self.complete_visual_design_for("visual-contract")
        self.record_check(
            "--goal-id", "visual-contract", "--id", "TEST", "--status", "PENDING",
            "--required", "--command", "test -f feature.txt",
        )
        self.register_requirement_for("visual-contract")
        self.ctl(
            "record", "dimension", "--goal-id", "visual-contract", "--id", "functional",
            "--status", "COVERED", "--rationale",
            "functional is covered by the observable acceptance criterion",
            "--requirement-id", "REQ-001",
        )
        self.ctl("design-render", "--goal-id", "visual-contract")
        self.assertEqual(self.ctl("plan-check", "--goal-id", "visual-contract")["gate"], "READY_FOR_APPROVAL")
        auto = self.ctl(
            "approve", "--goal-id", "visual-contract", "--auto-approved",
            "--next-action", "Implement", expected=2,
        )
        self.assertIn("explicit user approval", auto["error"])
        self.ctl(
            "approve", "--goal-id", "visual-contract", "--user-approved",
            "--next-action", "Implement",
        )
        self.assertEqual(self.ctl("summary", "--goal-id", "visual-contract", "--json")["phase"], "implementation")
        self.ctl("update", "--goal-id", "visual-contract", "--status", "VERIFYING")
        self.assertEqual(self.ctl("report", "--goal-id", "visual-contract", "--json")["phase"], "acceptance")
        source = drawing.read_text(encoding="utf-8")
        drawing.write_text(source.replace("fillColor=#E0F2FE", "fillColor=#DBEAFE", 1), encoding="utf-8")
        self.assertFalse(self.ctl("status", "--goal-id", "visual-contract")["design_drift"])
        drawing.write_text(
            drawing.read_text(encoding="utf-8").replace("current system / starting point", "current runtime", 1),
            encoding="utf-8",
        )
        self.assertTrue(self.ctl("status", "--goal-id", "visual-contract")["design_drift"])
        self.ctl("replan", "--goal-id", "visual-contract", "--reason", "Architecture semantics changed")
        self.assertEqual(self.ctl("summary", "--goal-id", "visual-contract", "--json")["phase"], "analysis-design")

    def test_plan_check_rejects_machine_only_acceptance_details(self) -> None:
        self.prepare_plan()
        goal = self.repo / ".goal-flow" / "test-goal" / "goal.md"
        goal.write_text(
            goal.read_text(encoding="utf-8").replace(
                "The file is missing or contains unexpected content", "Hidden from user-facing plan"
            ),
            encoding="utf-8",
        )
        payload = self.ctl("plan-check", expected=1)
        self.assertTrue(any("not visible" in reason for reason in payload["reasons"]))

    def test_approved_acceptance_dimensions_are_frozen(self) -> None:
        self.register_and_approve()
        denied = self.ctl(
            "record", "dimension", "--id", "functional", "--status", "N_A",
            "--rationale", "Attempt to weaken the approved functional quality gate", expected=2,
        )
        self.assertIn("frozen", denied["error"])

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
            "--severity", "medium", "--statement", "Known limitation", "--minimum-evidence-mode", "real", expected=2,
        )
        self.assertIn("--accepted-by", denied["error"])
        accepted = self.ctl(
            "record", "risk", "--id", "RISK-001", "--status", "ACCEPTED",
            "--severity", "medium", "--statement", "Known limitation",
            "--accepted-by", "test-user", "--minimum-evidence-mode", "real",
        )
        self.assertEqual(accepted["state"]["risks"]["RISK-001"]["accepted_by"], "test-user")

    def test_serious_risk_mitigation_requires_fresh_check_receipt(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "OPEN",
            "--severity", "critical", "--statement", "Critical failure mode", "--minimum-evidence-mode", "real",
        )
        self.assertEqual(self.ctl("gate")["gate"], "CONTINUE")
        denied = self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "MITIGATED",
            "--evidence", "Agent says fixed", "--minimum-evidence-mode", "real", expected=2,
        )
        self.assertIn("fresh PASS", denied["error"])
        mitigated = self.ctl(
            "record", "risk", "--id", "RISK-CRITICAL", "--status", "MITIGATED",
            "--evidence", "Covered by executed TEST", "--verified-by", "TEST", "--minimum-evidence-mode", "real",
        )
        self.assertEqual(mitigated["state"]["risks"]["RISK-CRITICAL"]["severity"], "critical")
        self.assertEqual(self.ctl("gate")["gate"], "READY_FOR_REVIEW")

    def test_partial_risk_blocks_when_serious_but_only_lowers_assurance_when_medium(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        partial = self.ctl(
            "record", "risk", "--id", "RISK-HIGH", "--status", "PARTIALLY_MITIGATED",
            "--severity", "high", "--statement", "Main path still has a serious residual failure mode",
            "--evidence", "TEST reduces but does not eliminate the risk", "--verified-by", "TEST",
            "--minimum-evidence-mode", "real", "--residual-risk", "Failure remains possible outside the checked boundary",
        )
        self.assertEqual(partial["state"]["risks"]["RISK-HIGH"]["status"], "PARTIALLY_MITIGATED")
        self.assertEqual(self.ctl("gate")["gate"], "CONTINUE")
        self.ctl(
            "record", "risk", "--id", "RISK-HIGH", "--status", "ACCEPTED",
            "--accepted-by", "test-user", "--minimum-evidence-mode", "real",
        )
        self.ctl(
            "record", "risk", "--id", "RISK-MEDIUM", "--status", "PARTIALLY_MITIGATED",
            "--severity", "medium", "--statement", "A bounded residual limitation remains",
            "--evidence", "TEST covers the primary path", "--verified-by", "TEST",
            "--minimum-evidence-mode", "real", "--residual-risk", "Rare unsupported inputs remain",
        )
        gate = self.ctl("gate")
        self.assertEqual(gate["gate"], "READY_FOR_REVIEW")
        self.assertEqual(gate["assurance"], "MEDIUM")

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

    def test_paused_goal_cannot_run_verification(self) -> None:
        self.register_and_approve()
        self.ctl("pause", "--reason", "等待用户输入")
        denied = self.ctl("verify", "--id", "TEST", expected=2)
        self.assertIn("paused", denied["error"])

    def test_resume_goal_id_requires_explicit_switch_and_updates_active_pointer(self) -> None:
        self.ctl(
            "init", "--goal-id", "second-goal", "--title", "Second", "--goal", "Another task", "--switch",
        )
        denied = self.ctl("resume", "--goal-id", "test-goal", expected=2)
        self.assertIn("--switch", denied["error"])
        self.assertEqual(self.ctl("status")["goal_id"], "second-goal")
        resumed = self.ctl("resume", "--goal-id", "test-goal", "--switch")
        self.assertEqual(resumed["state"]["goal_id"], "test-goal")
        self.assertEqual(self.ctl("status")["goal_id"], "test-goal")

    def test_delivery_rejection_invalidates_old_receipts_until_reverified(self) -> None:
        self.register_and_approve()
        sha = self.commit_product()
        self.record_complete_evidence(sha)
        ready = self.ctl("gate", "--apply")
        self.assertEqual(ready["status"], "READY_FOR_ACCEPTANCE")
        self.ctl("reject", "--reason", "补充边界处理")
        blocked = self.ctl("gate")
        self.assertEqual(blocked["gate"], "CONTINUE")
        self.assertTrue(any("current evidence" in item or "current PASS" in item for item in blocked["reasons"]))
        refreshed = self.ctl("verify", "--id", "TEST")
        self.assertEqual(refreshed["status"], "PASS")
        self.record_complete_evidence(self.git("rev-parse", "HEAD"))
        ready_again = self.ctl("gate", "--apply")
        self.assertEqual(ready_again["status"], "READY_FOR_ACCEPTANCE")

    def test_verified_requirement_sha_must_match_linked_check_receipt(self) -> None:
        self.register_and_approve()
        self.commit_product()
        self.ctl("verify", "--id", "TEST")
        wrong = self.git("rev-parse", "HEAD^")
        denied = self.ctl(
            "record", "requirement", "--id", "REQ-001", "--kind", "must",
            "--status", "VERIFIED", "--statement", "feature.txt exists with expected content",
            "--evidence", "Verified by TEST", "--git-sha", wrong, *REQUIREMENT_EVIDENCE_ARGS, expected=2,
        )
        self.assertIn("must match linked check receipts", denied["error"])

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
        events = [
            json.loads(line)
            for line in (self.repo / ".goal-flow" / "test-goal" / "events.jsonl").read_text().splitlines()
        ]
        self.assertEqual(sum(item["event"] == "gate" for item in events), 1)

    def test_read_only_views_do_not_need_repository_write_permission(self) -> None:
        self.prepare_plan()
        store = self.repo / ".goal-flow"
        goal = store / "test-goal"
        paths = [store / "controller.lock", goal / "state.json", goal / "goal.md", goal / "events.jsonl", goal, store]
        original_modes = {path: path.stat().st_mode for path in paths if path.exists()}
        try:
            for path in paths:
                if path.exists():
                    os.chmod(path, 0o444 if path.is_file() else 0o555)
            self.assertTrue(self.ctl("status")["active"])
            self.assertTrue(self.ctl("summary", "--json")["active"])
            self.assertEqual(self.ctl("report", "--json")["goal_id"], "test-goal")
        finally:
            for path, mode in reversed(list(original_modes.items())):
                os.chmod(path, mode)

    def test_old_schema_is_rejected_without_mutation(self) -> None:
        state_path = self.repo / ".goal-flow" / "test-goal" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["schema_version"] = 2
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before = state_path.read_bytes()
        denied = self.ctl("status", expected=2)
        self.assertIn("Incompatible Goal Flow schema v2", denied["error"])
        self.assertIn("Archive", denied["error"])
        self.assertEqual(state_path.read_bytes(), before)

    def test_recording_definitions_does_not_duplicate_evidence_or_events(self) -> None:
        self.prepare_plan()
        directory = self.repo / ".goal-flow" / "test-goal"
        evidence = (directory / "evidence.md").read_text(encoding="utf-8")
        self.assertNotIn("Requirement REQ-001", evidence)
        self.assertNotIn("Check TEST", evidence)
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        self.assertFalse(any(item["event"].startswith("record") for item in events))


if __name__ == "__main__":
    unittest.main()
