#!/usr/bin/env python3
"""Small deterministic controller for goal-flow repository state."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIREMENT_STATUSES = {"VERIFIED", "PARTIAL", "UNVERIFIED", "CONTRADICTED"}
CHECK_STATUSES = {"PASS", "FAIL", "PENDING"}
RISK_STATUSES = {"OPEN", "MITIGATED", "ACCEPTED"}
RISK_SEVERITIES = {"low", "medium", "high", "critical"}
RISK_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
DIMENSION_STATUSES = {"COVERED", "N_A"}
ACCEPTANCE_DIMENSIONS = {
    "functional",
    "negative-boundary",
    "regression-compatibility",
    "security-privacy",
    "performance-reliability",
    "operations-observability",
    "migration-rollback",
    "documentation-deliverables",
}
PROFILES = {"standard", "strict"}
HARNESS_MODES = {"auto", "micro", "standard", "goal-flow"}
TASK_TYPES = {"unspecified", "fix", "feature", "refactor", "docs", "test", "config", "migration"}
RISK_LEVELS = {"unspecified", "low", "medium", "high", "critical"}
FAILURE_CLASSES = {
    "implementation_defect",
    "environment_or_dependency",
    "authorization_or_external_input",
    "flaky_verifier",
    "unknown",
}
STANDARD_DIMENSIONS = {
    "functional",
    "negative-boundary",
    "regression-compatibility",
    "documentation-deliverables",
}
PLACEHOLDER_MARKERS = {
    "to be defined during planning",
    "define during planning",
    "pending user discussion and approval",
    "repository and domain context to be investigated",
}
WAIT_STATUSES = {
    "PLANNING",
    "WAITING_PLAN_APPROVAL",
    "WAITING_INPUT",
    "WAITING_AUTHORIZATION",
    "BLOCKED",
    "PAUSED",
    "CANCELLED",
}
ALL_STATUSES = WAIT_STATUSES | {
    "EXECUTING",
    "VERIFYING",
    "READY_FOR_ACCEPTANCE",
    "ACCEPTED",
}
EDITABLE_STATUSES = {
    "EXECUTING",
    "VERIFYING",
    "WAITING_INPUT",
    "WAITING_AUTHORIZATION",
    "BLOCKED",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCKFILE_NAMES = (
    "Cargo.lock", "Gemfile.lock", "Package.resolved", "composer.lock",
    "go.sum", "package-lock.json", "pnpm-lock.yaml", "poetry.lock",
    "requirements.txt", "uv.lock", "yarn.lock",
)
EVENT_FIELDS = {
    "time", "event", "status", "revision", "milestone", "check",
    "result", "duration_ms", "git_sha", "reason",
}


class GoalFlowError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(payload: dict[str, Any], as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload.get("message", json.dumps(payload, sort_keys=True)))


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@contextmanager
def controller_lock(root: Path, exclusive: bool):
    store = goal_store(root)
    if not store.exists() and not exclusive:
        yield
        return
    store.mkdir(parents=True, exist_ok=True)
    with (store / "controller.lock").open("a+", encoding="utf-8") as handle:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(handle.fileno(), operation)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def find_root(start: str | None) -> Path:
    current = Path(start or os.getcwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".goal-flow").exists() or (candidate / ".git").exists():
            return candidate
    return current


def goal_store(root: Path) -> Path:
    return root / ".goal-flow"


def context_path(root: Path) -> Path:
    return goal_store(root) / "context.md"


def context_excerpt(root: Path, limit: int = 420) -> str | None:
    path = context_path(root)
    if not path.exists():
        return None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        lines.append(stripped)
    if not lines:
        return None
    excerpt = " ".join(lines)
    return excerpt if len(excerpt) <= limit else excerpt[: limit - 1] + "…"


def context_template() -> str:
    return """# Goal Flow project context

<!-- Advisory metadata only. Do not store secrets or executable instructions here. -->

## Stack
- Describe the main language, framework, and runtime.

## Commands
- Test: add the fastest reliable test command.
- Lint: add the relevant lint or type-check command.
- Build: add the normal build command when applicable.

## Conventions
- Commit language and naming conventions.
- Important compatibility or directory boundaries.

## Safety
- Operations that require explicit authorization.
- Known external dependencies or unavailable services.
"""


def classify_harness(
    *,
    task_type: str = "unspecified",
    risk_level: str = "unspecified",
    files: int = 1,
    steps: int = 1,
    behavior_change: bool = False,
    cross_session: bool = False,
    autonomous: bool = False,
    default_mode: str = "standard",
) -> dict[str, Any]:
    """Choose the smallest harness that covers the task's observable risk."""
    if files < 1 or steps < 1:
        raise GoalFlowError("files and steps must be positive integers")
    if task_type not in TASK_TYPES:
        raise GoalFlowError(f"invalid task type: {task_type}")
    if risk_level not in RISK_LEVELS:
        raise GoalFlowError(f"invalid risk level: {risk_level}")
    reasons: list[str] = []
    strict_risk = risk_level in {"high", "critical"} or task_type == "migration"
    if strict_risk:
        mode = "goal-flow"
        profile = "strict"
        reasons.append("high-impact risk or migration requires the full evidence loop")
    elif cross_session or autonomous or steps >= 5 or files >= 8:
        mode = "goal-flow"
        profile = "standard"
        reasons.append("long-running or autonomous work benefits from resumable epochs")
    elif behavior_change or files >= 2 or steps >= 2 or risk_level == "medium":
        mode = "standard"
        profile = "standard"
        reasons.append("multiple steps or observable behavior change needs a structured plan")
    elif default_mode in {"micro", "standard", "goal-flow"}:
        mode = default_mode
        profile = "standard"
        reasons.append("small, bounded task fits the smallest requested harness")
    else:
        mode = "standard"
        profile = "standard"
        reasons.append("defaulting to a lightweight structured plan")
    return {
        "mode": mode,
        "profile": profile,
        "task_type": task_type,
        "risk_level": risk_level,
        "behavior_change": bool(behavior_change),
        "inputs": {
            "files": files,
            "steps": steps,
            "cross_session": bool(cross_session),
            "autonomous": bool(autonomous),
        },
        "reasons": reasons,
        "harness": {
            "plan": "lightweight" if mode == "micro" else "structured",
            "approval": "required" if mode == "goal-flow" else "conditional",
            "evidence": "strict" if profile == "strict" else "standard",
            "resume": mode == "goal-flow",
        },
    }


def active_file(root: Path) -> Path:
    return goal_store(root) / "active.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GoalFlowError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GoalFlowError(f"Invalid JSON in {path}: {exc}") from exc


def active_goal_id(root: Path, explicit: str | None = None) -> str:
    goal_id = explicit or str(load_json(active_file(root)).get("goal_id") or "")
    if goal_id and not SLUG_RE.fullmatch(goal_id):
        raise GoalFlowError("Invalid goal-id in request or active.json")
    return goal_id


def goal_dir(root: Path, goal_id: str) -> Path:
    return goal_store(root) / goal_id


def load_state(root: Path, explicit: str | None = None) -> tuple[str, Path, dict[str, Any]]:
    goal_id = active_goal_id(root, explicit)
    if not goal_id:
        raise GoalFlowError("No active goal")
    directory = goal_dir(root, goal_id)
    state = load_json(directory / "state.json")
    state.setdefault("dimensions", {})
    # Goals created before v0.3 keep the original strict contract.
    state.setdefault("profile", "strict")
    state.setdefault("harness", {
        "mode": "goal-flow",
        "requested_mode": "goal-flow",
        "task_type": "unspecified",
        "risk_level": "unspecified",
        "behavior_change": False,
        "evidence_level": "strict",
    })
    state.setdefault("state_revision", 0)
    state.setdefault("contract_version", 1)
    return goal_id, directory, state


def save_state(directory: Path, state: dict[str, Any]) -> None:
    state_path = directory / "state.json"
    expected_revision = int(state.get("state_revision", 0))
    if state_path.exists():
        current = load_json(state_path)
        current_revision = int(current.get("state_revision", 0))
        if current_revision != expected_revision:
            raise GoalFlowError(
                f"State revision conflict: expected {expected_revision}, found {current_revision}"
            )
    state["state_revision"] = expected_revision + 1
    state["updated_at"] = now()
    atomic_json_write(state_path, state)


def deactivate_goal(root: Path, goal_id: str) -> None:
    active = load_json(active_file(root))
    if active.get("goal_id") == goal_id:
        atomic_json_write(active_file(root), {
            "goal_id": None,
            "last_goal_id": goal_id,
            "updated_at": now(),
        })


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definitions_hash(state: dict[str, Any]) -> str:
    definitions = {
        "requirements": {
            key: {
                "statement": value.get("statement"),
                "kind": value.get("kind"),
                "verified_by": sorted(value.get("verified_by") or []),
                "proves": value.get("proves"),
                "failure_modes": sorted(value.get("failure_modes") or []),
                "basis": sorted(value.get("basis") or []),
            }
            for key, value in sorted(state.get("requirements", {}).items())
        },
        "checks": {
            key: {
                "required": bool(value.get("required")),
                "command": value.get("command"),
                "timeout": value.get("timeout"),
            }
            for key, value in sorted(state.get("checks", {}).items())
        },
        "dimensions": {
            key: {
                "status": value.get("status"),
                "rationale": value.get("rationale"),
                "requirement_ids": sorted(value.get("requirement_ids") or []),
            }
            for key, value in sorted(state.get("dimensions", {}).items())
        },
    }
    if int(state.get("contract_version", 1)) >= 2:
        definitions["profile"] = state.get("profile", "strict")
        definitions["harness"] = state.get("harness", {})
    raw = json.dumps(definitions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def run_git(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def current_git_sha(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD") or "UNBORN"


def current_branch(root: Path) -> str | None:
    return run_git(root, "branch", "--show-current")


def current_worktree_identity(root: Path) -> dict[str, str]:
    top = run_git(root, "rev-parse", "--show-toplevel")
    git_dir = run_git(root, "rev-parse", "--absolute-git-dir")
    branch = current_branch(root)
    if not top or not git_dir:
        raise GoalFlowError("Worktree binding requires a Git worktree")
    if not branch:
        raise GoalFlowError("Worktree binding requires a named branch; detached HEAD is not supported")
    return {
        "root": str(Path(top).resolve()),
        "git_dir": str(Path(git_dir).resolve()),
        "branch": branch,
    }


def require_bound_worktree(root: Path, state: dict[str, Any]) -> None:
    if not state.get("approved"):
        return
    binding = state.get("worktree_binding")
    if not binding:
        raise GoalFlowError("Approved goal is not bound; run bind-worktree on its implementation branch")
    current = current_worktree_identity(root)
    mismatches = [
        key for key in ("root", "git_dir", "branch")
        if binding.get(key) != current.get(key)
    ]
    if mismatches:
        rendered = ", ".join(
            f"{key}={current.get(key)!r} (expected {binding.get(key)!r})"
            for key in mismatches
        )
        raise GoalFlowError(f"Worktree binding mismatch: {rendered}")


def product_status(root: Path) -> str | None:
    """Return porcelain status excluding Goal Flow audit files."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    # Keep the leading XY status columns; generic run_git() strips them from
    # the first line and can turn an audit-only path into a false product edit.
    output = result.stdout.rstrip("\n")
    product_lines: list[str] = []
    for line in output.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path != ".goal-flow" and not path.startswith(".goal-flow/"):
            product_lines.append(line)
    return "\n".join(product_lines)


def product_tree_is_clean(root: Path) -> bool:
    """Return true when only Goal Flow audit files may be dirty."""
    return product_status(root) == ""


def evidence_is_fresh(root: Path, evidence_sha: str | None) -> bool:
    """Evidence stays fresh across audit-only commits, but not product changes."""
    if not evidence_sha or evidence_sha == "UNBORN" or not product_tree_is_clean(root):
        return False
    if run_git(root, "merge-base", "--is-ancestor", evidence_sha, "HEAD") is None:
        return False
    changed = run_git(
        root,
        "diff",
        "--name-only",
        f"{evidence_sha}..HEAD",
        "--",
        ".",
        ":(exclude).goal-flow",
        ":(exclude).goal-flow/**",
    )
    return changed == ""


def verifiers_are_fresh(root: Path, state: dict[str, Any], check_ids: list[str]) -> bool:
    return bool(check_ids) and all(
        check_id in state.get("checks", {})
        and state["checks"][check_id].get("status") == "PASS"
        and evidence_is_fresh(root, state["checks"][check_id].get("git_sha"))
        for check_id in check_ids
    )


def risk_is_unresolved(root: Path, state: dict[str, Any], risk: dict[str, Any]) -> bool:
    if risk.get("status") == "OPEN":
        return True
    if risk.get("status") == "MITIGATED":
        return not verifiers_are_fresh(root, state, risk.get("verified_by") or [])
    return False


def append_evidence(directory: Path, heading: str, fields: dict[str, Any]) -> None:
    lines = [f"\n## {now()} — {heading}\n"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        safe = str(value).replace("\n", " ").strip()
        lines.append(f"- **{key}:** {safe}\n")
    with (directory / "evidence.md").open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def validate_state(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "goal_id",
        "goal_revision",
        "status",
        "approved",
        "requirements",
        "checks",
        "risks",
        "dimensions",
    }
    missing = sorted(required - state.keys())
    if missing:
        errors.append(f"missing state fields: {', '.join(missing)}")
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {state.get('schema_version')}")
    if state.get("status") not in ALL_STATUSES:
        errors.append(f"invalid status: {state.get('status')}")
    if state.get("profile", "strict") not in PROFILES:
        errors.append(f"invalid profile: {state.get('profile')}")
    harness = state.get("harness") or {}
    if harness.get("mode") and harness.get("mode") not in HARNESS_MODES - {"auto"}:
        errors.append(f"invalid harness mode: {harness.get('mode')}")
    if harness.get("task_type") and harness.get("task_type") not in TASK_TYPES:
        errors.append(f"invalid task type: {harness.get('task_type')}")
    if harness.get("risk_level") and harness.get("risk_level") not in RISK_LEVELS:
        errors.append(f"invalid risk level: {harness.get('risk_level')}")
    if not isinstance(state.get("state_revision", 0), int) or state.get("state_revision", 0) < 0:
        errors.append("invalid state_revision")
    for req_id, item in state.get("requirements", {}).items():
        if item.get("status") not in REQUIREMENT_STATUSES:
            errors.append(f"invalid requirement status for {req_id}")
        if item.get("kind") not in {"must", "should"}:
            errors.append(f"invalid requirement kind for {req_id}")
    for check_id, item in state.get("checks", {}).items():
        if item.get("status") not in CHECK_STATUSES:
            errors.append(f"invalid check status for {check_id}")
    for risk_id, item in state.get("risks", {}).items():
        if item.get("status") not in RISK_STATUSES:
            errors.append(f"invalid risk status for {risk_id}")
        if item.get("severity") not in RISK_SEVERITIES:
            errors.append(f"invalid risk severity for {risk_id}")
    for dimension_id, item in state.get("dimensions", {}).items():
        if dimension_id not in ACCEPTANCE_DIMENSIONS:
            errors.append(f"invalid acceptance dimension: {dimension_id}")
        if item.get("status") not in DIMENSION_STATUSES:
            errors.append(f"invalid dimension status for {dimension_id}")
    return errors


def substantive(value: str | None) -> bool:
    if not value or len(value.strip()) < 8:
        return False
    lowered = value.strip().lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def valid_check_command(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return value.strip().lower() not in {"true", ":", "exit 0"}


SCENARIO_HEADING_RE = re.compile(
    r"^####\s+(SCN-[A-Z0-9][A-Z0-9_-]*)(?:\s*\((REQ-[A-Z0-9][A-Z0-9_-]*)\))?\s*:\s*(.+)$",
    re.IGNORECASE,
)
DELTA_HEADING_RE = re.compile(r"^###\s+(REQ-[A-Z0-9][A-Z0-9_-]*)\b", re.IGNORECASE)
TASK_RE = re.compile(
    r"^-\s*\[[ xX]\]\s+(T-[A-Z0-9][A-Z0-9_-]*)\s*\(([^)]*)\)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def parse_scenarios(text: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    scenarios: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = SCENARIO_HEADING_RE.match(line.strip())
        if match:
            scenario_id, requirement_id, title = match.groups()
            scenario_id = scenario_id.upper()
            if scenario_id in scenarios:
                errors.append(f"Duplicate scenario ID: {scenario_id}")
            current = {
                "id": scenario_id,
                "requirement_id": requirement_id.upper() if requirement_id else None,
                "title": title.strip(),
                "given": [],
                "when": [],
                "then": [],
            }
            scenarios[scenario_id] = current
            continue
        if current is None:
            continue
        condition = re.match(r"^-\s*(GIVEN|WHEN|THEN)\s+(.+)$", line.strip(), re.IGNORECASE)
        if condition:
            key = condition.group(1).lower()
            current[key].append(condition.group(2).strip())
    for scenario_id, scenario in scenarios.items():
        missing = [key.upper() for key in ("given", "when", "then") if not scenario[key]]
        if missing:
            errors.append(f"Scenario {scenario_id} is missing: {', '.join(missing)}")
    return scenarios, errors


def parse_delta(text: str) -> tuple[dict[str, set[str]], list[str]]:
    sections = {"ADDED": set(), "MODIFIED": set(), "REMOVED": set()}
    errors: list[str] = []
    current: str | None = None
    seen: dict[str, str] = {}
    for line in text.splitlines():
        heading = line.strip().upper()
        if heading.startswith("## "):
            name = heading[3:].strip()
            current = name if name in sections else None
            continue
        match = DELTA_HEADING_RE.match(line.strip())
        if not match or current is None:
            continue
        req_id = match.group(1).upper()
        if req_id in seen:
            errors.append(f"Requirement {req_id} appears in both {seen[req_id]} and {current}")
        seen[req_id] = current
        sections[current].add(req_id)
    if not any(sections.values()):
        errors.append("delta.md must contain at least one ADDED, MODIFIED, or REMOVED requirement")
    return sections, errors


def parse_tasks(text: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    tasks: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for line in text.splitlines():
        match = TASK_RE.match(line.strip())
        if not match:
            continue
        task_id, refs_text, description = match.groups()
        task_id = task_id.upper()
        if task_id in tasks:
            errors.append(f"Duplicate task ID: {task_id}")
            continue
        refs = {item.strip().upper() for item in refs_text.split(",") if item.strip()}
        tasks[task_id] = {"id": task_id, "refs": refs, "description": description.strip()}
    if not tasks:
        errors.append("tasks.md must contain at least one checked or unchecked task")
    return tasks, errors


def semantic_review(directory: Path, state: dict[str, Any], strict: bool = False) -> dict[str, Any]:
    """Review the traceability of a behavior change without making claims about code."""
    harness = state.get("harness", {})
    behavior_change = bool(harness.get("behavior_change"))
    if not behavior_change and not any((directory / name).exists() for name in ("delta.md", "tasks.md")):
        return {
            "ok": True,
            "status": "PASS",
            "skipped": True,
            "dimensions": {"completeness": "N_A", "correctness": "N_A", "coherence": "N_A"},
            "findings": [],
        }

    findings: list[dict[str, str]] = []

    def finding(severity: str, dimension: str, message: str) -> None:
        findings.append({"severity": severity, "dimension": dimension, "message": message})

    goal_text = (directory / "goal.md").read_text(encoding="utf-8") if (directory / "goal.md").exists() else ""
    delta_path = directory / "delta.md"
    tasks_path = directory / "tasks.md"
    delta_text = delta_path.read_text(encoding="utf-8") if delta_path.exists() else ""
    tasks_text = tasks_path.read_text(encoding="utf-8") if tasks_path.exists() else ""
    scenarios, scenario_errors = parse_scenarios("\n".join(part for part in (goal_text, delta_text) if part))
    for error in scenario_errors:
        finding("CRITICAL", "completeness", error)

    if not delta_path.exists():
        finding("CRITICAL", "completeness", "Behavior change requires delta.md")
    else:
        _, delta_errors = parse_delta(delta_text)
        for error in delta_errors:
            finding("CRITICAL", "coherence", error)
    if not tasks_path.exists():
        finding("CRITICAL", "completeness", "Behavior change requires tasks.md")
        tasks = {}
    else:
        tasks, task_errors = parse_tasks(tasks_text)
        for error in task_errors:
            finding("CRITICAL", "completeness", error)

    requirements = state.get("requirements", {})
    must_ids = {req_id.upper() for req_id, item in requirements.items() if item.get("kind") == "must"}
    scenario_req_ids = {scenario.get("requirement_id") for scenario in scenarios.values()}
    for req_id in sorted(must_ids):
        matching = [item for item in scenarios.values() if item.get("requirement_id") == req_id]
        if not matching:
            finding("CRITICAL", "completeness", f"MUST requirement {req_id} has no linked scenario")
    for scenario_id, scenario in scenarios.items():
        req_id = scenario.get("requirement_id")
        if req_id and req_id not in requirements:
            finding("CRITICAL", "coherence", f"Scenario {scenario_id} references unknown requirement {req_id}")
    for task_id, task in tasks.items():
        unknown = sorted(
            ref for ref in task["refs"]
            if ref.startswith("REQ-") and ref not in requirements
            or ref.startswith("SCN-") and ref not in scenarios
        )
        if unknown:
            finding("CRITICAL", "coherence", f"Task {task_id} references unknown IDs: {', '.join(unknown)}")
    for req_id in sorted(must_ids):
        if tasks and not any(req_id in task["refs"] for task in tasks.values()):
            finding("CRITICAL", "completeness", f"MUST requirement {req_id} has no linked task")

    if strict:
        for req_id in sorted(must_ids):
            item = requirements[req_id]
            if item.get("status") != "VERIFIED" or not item.get("git_sha"):
                finding("CRITICAL", "correctness", f"MUST requirement {req_id} lacks verified implementation evidence")
    elif must_ids and any(requirements[req_id].get("status") != "VERIFIED" for req_id in must_ids):
        finding("WARNING", "correctness", "Some MUST requirements are not verified yet")

    dimensions = {dimension: "PASS" for dimension in ("completeness", "correctness", "coherence")}
    for item in findings:
        if item["severity"] == "CRITICAL":
            dimensions[item["dimension"]] = "BLOCK"
        elif dimensions[item["dimension"]] == "PASS":
            dimensions[item["dimension"]] = "WARN"
    has_critical = any(item["severity"] == "CRITICAL" for item in findings)
    has_warning = any(item["severity"] == "WARNING" for item in findings)
    return {
        "ok": not has_critical,
        "status": "BLOCK" if has_critical else "WARN" if has_warning else "PASS",
        "skipped": False,
        "dimensions": dimensions,
        "findings": findings,
        "scenario_count": len(scenarios),
        "task_count": len(tasks),
    }


def plan_readiness(directory: Path, state: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    goal_path = directory / "goal.md"
    goal_text = ""
    if not goal_path.exists():
        reasons.append("goal.md is missing")
    else:
        goal_text = goal_path.read_text(encoding="utf-8")
        lowered = goal_text.lower()
        for marker in sorted(PLACEHOLDER_MARKERS):
            if marker in lowered:
                reasons.append(f"goal.md still contains placeholder: {marker}")
        if "## acceptance criteria" not in lowered:
            reasons.append("goal.md needs an Acceptance criteria section")

    requirements = state.get("requirements", {})
    must = {key: value for key, value in requirements.items() if value.get("kind") == "must"}
    if not must:
        reasons.append("Register at least one MUST acceptance criterion")

    required_checks = {
        key: value for key, value in state.get("checks", {}).items() if value.get("required")
    }
    if not required_checks:
        reasons.append("Register at least one required PENDING check")
    for check_id, check in required_checks.items():
        if not valid_check_command(check.get("command")):
            reasons.append(f"Required check {check_id} has no substantive executable command")
        if check.get("status") != "PENDING":
            reasons.append(f"Required check {check_id} must be PENDING at approval")
        if check_id not in goal_text or str(check.get("command")) not in goal_text:
            reasons.append(f"Required check {check_id} and its exact command must appear in goal.md")

    for req_id, criterion in must.items():
        if not substantive(criterion.get("statement")):
            reasons.append(f"MUST criterion {req_id} lacks an observable outcome")
        if not substantive(criterion.get("proves")):
            reasons.append(f"MUST criterion {req_id} must state what its evidence proves")
        if not criterion.get("failure_modes") or not all(
            substantive(item) for item in criterion.get("failure_modes", [])
        ):
            reasons.append(f"MUST criterion {req_id} needs negative or boundary failure modes")
        if not criterion.get("basis") or not all(
            substantive(item) for item in criterion.get("basis", [])
        ):
            reasons.append(f"MUST criterion {req_id} needs repository, domain, or user basis")
        verifiers = criterion.get("verified_by") or []
        if not verifiers:
            reasons.append(f"MUST criterion {req_id} has no --verified-by check")
        invalid = [check_id for check_id in verifiers if check_id not in required_checks]
        if invalid:
            reasons.append(
                f"MUST criterion {req_id} references non-required checks: {', '.join(invalid)}"
            )
        visible_values = [
            req_id,
            criterion.get("statement"),
            criterion.get("proves"),
            *(criterion.get("failure_modes") or []),
            *(criterion.get("basis") or []),
        ]
        for value in visible_values:
            if value and str(value) not in goal_text:
                reasons.append(f"MUST criterion {req_id} detail is not visible in goal.md: {value}")

    if state.get("harness", {}).get("behavior_change"):
        review = semantic_review(directory, state)
        for finding_item in review.get("findings", []):
            if finding_item.get("severity") == "CRITICAL":
                reasons.append(f"Semantic review: {finding_item['message']}")

    dimensions = state.get("dimensions", {})
    profile = state.get("profile", "strict")
    required_dimensions = (
        ACCEPTANCE_DIMENSIONS if profile == "strict" else STANDARD_DIMENSIONS
    )
    missing_dimensions = sorted(required_dimensions - dimensions.keys())
    if missing_dimensions:
        reasons.append(f"Unassessed acceptance dimensions: {', '.join(missing_dimensions)}")
    for dimension_id in sorted(required_dimensions & dimensions.keys()):
        dimension = dimensions[dimension_id]
        status = dimension.get("status")
        rationale = dimension.get("rationale")
        linked = dimension.get("requirement_ids") or []
        if not substantive(rationale):
            reasons.append(f"Acceptance dimension {dimension_id} needs a substantive rationale")
        if status == "COVERED":
            if not linked:
                reasons.append(f"Covered dimension {dimension_id} needs linked requirement IDs")
            unknown = [req_id for req_id in linked if req_id not in requirements]
            if unknown:
                reasons.append(
                    f"Acceptance dimension {dimension_id} links unknown requirements: {', '.join(unknown)}"
                )
            if linked and not any(req_id in must for req_id in linked):
                reasons.append(f"Covered dimension {dimension_id} must link at least one MUST criterion")
        if dimension_id not in goal_text or (rationale and rationale not in goal_text):
            reasons.append(f"Acceptance dimension {dimension_id} and its rationale must appear in goal.md")

    return {
        "ok": not reasons,
        "gate": "READY_FOR_APPROVAL" if not reasons else "REVISE_PLAN",
        "reasons": reasons,
        "must_acceptance_criteria": len(must),
        "required_checks": len(required_checks),
        "profile": profile,
        "dimensions_assessed": len(required_dimensions & dimensions.keys()),
        "dimensions_total": len(required_dimensions),
        "harness": state.get("harness", {}),
    }


def state_fingerprint(root: Path, state: dict[str, Any]) -> str:
    selected = {
        "goal_revision": state.get("goal_revision"),
        "status": state.get("status"),
        "current_milestone": state.get("current_milestone"),
        "next_action": state.get("next_action"),
        "last_verified_commit": state.get("last_verified_commit"),
        "requirements": state.get("requirements", {}),
        "checks": state.get("checks", {}),
        "risks": state.get("risks", {}),
        "dimensions": state.get("dimensions", {}),
        "git_sha": current_git_sha(root),
        "product_status": product_status(root),
    }
    raw = json.dumps(selected, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def design_drift(directory: Path, state: dict[str, Any]) -> bool:
    expected = state.get("approved_design_hash")
    expected_definitions = state.get("approved_definitions_hash")
    goal_path = directory / "goal.md"
    return bool(
        state.get("approved")
        and (
            not expected
            or not expected_definitions
            or design_hash(directory, state) != expected
            or definitions_hash(state) != expected_definitions
        )
    )


def design_hash(directory: Path, state: dict[str, Any]) -> str:
    """Hash the approved human-authored contract and optional change artifacts."""
    paths = [directory / "goal.md"]
    if state.get("harness", {}).get("behavior_change") or (directory / "delta.md").exists():
        # tasks.md is intentionally a living checklist; changing it alone must
        # not invalidate the approved outcome. Delta and goal remain frozen.
        paths.append(directory / "delta.md")
    if len(paths) == 1:
        return file_hash(paths[0]) if paths[0].exists() else ""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.name).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash(path).encode("ascii") if path.exists() else b"MISSING")
        digest.update(b"\0")
    return digest.hexdigest()


def assurance_payload(root: Path, state: dict[str, Any], current_sha: str) -> dict[str, Any]:
    requirements = state.get("requirements", {})
    must = [item for item in requirements.values() if item.get("kind") == "must"]
    verified = [item for item in must if item.get("status") == "VERIFIED"]
    fresh = [item for item in verified if evidence_is_fresh(root, item.get("git_sha"))]
    required_checks = [item for item in state.get("checks", {}).values() if item.get("required")]
    passing_checks = [
        item for item in required_checks
        if item.get("status") == "PASS" and evidence_is_fresh(root, item.get("git_sha"))
    ]
    coverage = round(100 * len(fresh) / len(must)) if must else 0
    check_coverage = round(100 * len(passing_checks) / len(required_checks)) if required_checks else 0
    unresolved_serious = [
        item for item in state.get("risks", {}).values()
        if risk_is_unresolved(root, state, item)
        and item.get("severity") in {"high", "critical"}
    ]
    unresolved_risks = [
        item for item in state.get("risks", {}).values() if risk_is_unresolved(root, state, item)
    ]
    accepted_serious = [
        item for item in state.get("risks", {}).values()
        if item.get("status") == "ACCEPTED" and item.get("severity") in {"high", "critical"}
    ]
    contradicted = [
        item for item in requirements.values() if item.get("status") == "CONTRADICTED"
    ]
    failed_optional = [
        item for item in state.get("checks", {}).values()
        if not item.get("required") and item.get("status") == "FAIL"
    ]
    if (
        coverage == 100
        and check_coverage == 100
        and not unresolved_risks
        and not accepted_serious
        and not contradicted
        and not failed_optional
    ):
        band = "HIGH"
    elif coverage >= 50 and not unresolved_serious:
        band = "MEDIUM"
    else:
        band = "LOW"
    return {
        "assurance": band,
        "confidence": "UNCALIBRATED",
        "must_requirement_coverage": coverage,
        "acceptance_criteria_coverage": coverage,
        "required_check_coverage": check_coverage,
        "open_high_or_critical_risks": len(unresolved_serious),
        "open_risks": len(unresolved_risks),
        "accepted_high_or_critical_risks": len(accepted_serious),
        "contradicted_requirements": len(contradicted),
        "failed_optional_checks": len(failed_optional),
        "must_total": len(must),
        "acceptance_criteria_total": len(must),
        "must_verified_on_current_sha": len(fresh),
    }


def evaluate_gate(root: Path, directory: Path, state: dict[str, Any]) -> dict[str, Any]:
    errors = validate_state(state)
    sha = current_git_sha(root)
    metrics = assurance_payload(root, state, sha)
    result: dict[str, Any] = {
        "gate": "WAIT",
        "status": state.get("status"),
        "goal_id": state.get("goal_id"),
        "goal_revision": state.get("goal_revision"),
        "git_sha": sha,
        "next_action": state.get("next_action"),
        "reasons": [],
        **metrics,
    }
    if errors:
        result["reasons"] = errors
        return result
    status = state["status"]
    if status == "ACCEPTED":
        result["gate"] = "ACCEPTED"
        return result
    if status in WAIT_STATUSES:
        result["reasons"] = [state.get("wait_reason") or f"Goal is {status}"]
        return result
    if not state.get("approved"):
        result["reasons"] = ["Design is not approved"]
        return result
    if design_drift(directory, state):
        result["reasons"] = ["Approved plan or acceptance contract changed; run replan and obtain approval"]
        return result
    if state.get("harness", {}).get("behavior_change"):
        review = semantic_review(directory, state, strict=state.get("profile") == "strict")
        result["semantic_review"] = review
        if review.get("status") == "BLOCK":
            result["gate"] = "CONTINUE"
            result["reasons"] = [
                f"Semantic review blocked delivery: {item['message']}"
                for item in review.get("findings", [])
                if item.get("severity") == "CRITICAL"
            ]
            return result
    requirements = state.get("requirements", {})
    must = {key: value for key, value in requirements.items() if value.get("kind") == "must"}
    if not must:
        result["reasons"] = ["No MUST requirements are registered"]
        return result
    incomplete = [
        key for key, value in must.items()
        if value.get("status") != "VERIFIED" or not evidence_is_fresh(root, value.get("git_sha"))
    ]
    checks = state.get("checks", {})
    required_checks = {
        key: value for key, value in checks.items() if value.get("required")
    }
    if not required_checks:
        result["gate"] = "CONTINUE"
        result["reasons"] = ["No required verification checks are registered"]
        return result
    failing_checks = [
        key for key, value in required_checks.items()
        if value.get("status") != "PASS" or not evidence_is_fresh(root, value.get("git_sha"))
    ]
    serious_risks = [
        key for key, value in state.get("risks", {}).items()
        if risk_is_unresolved(root, state, value)
        and value.get("severity") in {"high", "critical"}
    ]
    if incomplete or failing_checks or serious_risks:
        result["gate"] = "CONTINUE"
        if incomplete:
            result["reasons"].append(f"MUST acceptance criteria need current evidence: {', '.join(incomplete)}")
        if failing_checks:
            result["reasons"].append(f"Required checks need current PASS evidence: {', '.join(failing_checks)}")
        if serious_risks:
            result["reasons"].append(f"Unresolved high/critical risks: {', '.join(serious_risks)}")
        return result
    result["gate"] = "READY_FOR_REVIEW"
    result["next_action"] = "Present the evidence-backed delivery for user acceptance"
    return result


def cmd_init(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if run_git(root, "rev-parse", "--show-toplevel") is None:
        raise GoalFlowError("Goal Flow requires a Git repository")
    goal_id = args.goal_id
    if not SLUG_RE.fullmatch(goal_id):
        raise GoalFlowError("goal-id must be lowercase kebab-case")
    directory = goal_dir(root, goal_id)
    if directory.exists():
        raise GoalFlowError(f"Goal already exists: {goal_id}")
    directory.mkdir(parents=True)
    dimension_order = [
        "functional", "negative-boundary", "regression-compatibility",
        "security-privacy", "performance-reliability", "operations-observability",
        "migration-rollback", "documentation-deliverables",
    ]
    behavior_change = bool(args.behavior_change)
    classification = classify_harness(
        task_type=args.task_type,
        risk_level=args.risk_level,
        files=args.files,
        steps=args.steps,
        behavior_change=behavior_change,
        cross_session=args.cross_session,
        autonomous=args.autonomous,
        default_mode="standard" if args.mode == "auto" else args.mode,
    )
    profile = "strict" if args.profile == "standard" and classification["profile"] == "strict" else args.profile
    mode = classification["mode"]
    required_dimensions = (
        dimension_order
        if profile == "strict"
        else [item for item in dimension_order if item in STANDARD_DIMENSIONS]
    )
    dimension_table = "\n".join(f"| {item} | TBD | TBD | TBD |" for item in required_dimensions)
    goal_text = f"""# {args.title}\n\n## Outcome\n\n{args.goal}\n\n## Non-goals\n\n- To be defined during planning.\n\n## Context and sources\n\n- Repository and domain context to be investigated.\n\n## Assumptions and decisions\n\n- Profile: {args.profile}.\n- Infer from repository and domain evidence before asking the user.\n\n## Questions requiring user decision\n\n- Only unresolved, high-impact choices belong here.\n\n## Approved design\n\nPending user discussion and approval.\n\n## Acceptance dimensions\n\n| Dimension | COVERED or N_A | Rationale | Criterion IDs |\n| --- | --- | --- | --- |\n{dimension_table}\n\n## Acceptance criteria\n\n| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |\n| --- | --- | --- | --- | --- | --- | --- |\n| REQ-001 | MUST | Define during planning | Define during planning | Define during planning | Define during planning | Define during planning |\n\n## Milestones\n\n1. Complete the decision-ready design and acceptance contract.\n\n## Risks, migration, and rollback\n\n- To be defined during planning.\n\n## Approval\n\n- Revision: 1\n- Status: PENDING\n- Approved by: pending\n"""
    goal_text = goal_text.replace(
        "- Infer from repository and domain evidence before asking the user.",
        "- Harness mode: " + mode + ".\n"
        + "- Task type: " + args.task_type + ".\n"
        + "- Risk level: " + args.risk_level + ".\n"
        + "- Behavior change: " + ("yes" if behavior_change else "no") + ".\n"
        + "- Infer from repository and domain evidence before asking the user.",
        1,
    )
    goal_text = goal_text.replace(f"- Profile: {args.profile}.", f"- Profile: {profile}.", 1)
    (directory / "goal.md").write_text(goal_text, encoding="utf-8")
    (directory / "evidence.md").write_text(
        f"# Evidence — {args.title}\n\n- Goal revision: 1\n- Confidence: UNCALIBRATED\n",
        encoding="utf-8",
    )
    if not context_path(root).exists():
        context_path(root).write_text(context_template(), encoding="utf-8")
    if behavior_change:
        (directory / "delta.md").write_text(
            """# Behavior Delta

Describe only externally observable behavior changes. Use one of the sections below.

## ADDED

### REQ-001: Describe the added behavior

#### SCN-001 (REQ-001): Describe the concrete scenario

- GIVEN the starting state
- WHEN the user or system performs an action
- THEN the observable result is produced

## MODIFIED

## REMOVED

""",
            encoding="utf-8",
        )
        (directory / "tasks.md").write_text(
            """# Tasks

Keep this checklist traceable to REQ-* or SCN-* IDs. Additive task edits do not require replan unless the approved contract changes.

- [ ] T-001 (REQ-001, SCN-001): Implement and verify the behavior
""",
            encoding="utf-8",
        )
    state = {
        "schema_version": SCHEMA_VERSION,
        "goal_id": goal_id,
        "title": args.title,
        "goal_revision": 1,
        "profile": profile,
        "harness": {
            "mode": mode,
            "requested_mode": args.mode,
            "task_type": args.task_type,
            "risk_level": args.risk_level,
            "behavior_change": behavior_change,
            "evidence_level": "strict" if profile == "strict" else "standard",
            "classification": classification,
        },
        "contract_version": 2,
        "state_revision": 0,
        "worktree_binding": None,
        "status": "PLANNING",
        "approved": False,
        "approved_design_hash": None,
        "approved_definitions_hash": None,
        "branch": current_branch(root),
        "current_milestone": "PLAN",
        "next_action": "Complete the evidence-backed plan and acceptance contract, then obtain approval",
        "wait_reason": "Design approval is required before implementation",
        "requirements": {},
        "checks": {},
        "risks": {},
        "dimensions": {},
        "last_verified_commit": None,
        "no_progress_count": 0,
        "last_stop_fingerprint": None,
        "stop_repeat_count": 0,
        "resume_status": None,
        "created_at": now(),
        "updated_at": now(),
    }
    save_state(directory, state)
    atomic_json_write(active_file(root), {"goal_id": goal_id, "updated_at": now()})
    return {"ok": True, "message": f"Initialized goal {goal_id}", "goal_dir": str(directory), "state": state}


def cmd_status(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not args.goal_id:
        path = active_file(root)
        if not path.exists() or not load_json(path).get("goal_id"):
            return {
                "ok": True,
                "active": False,
                "message": "No active goal; run init to start one",
                "git_sha": current_git_sha(root),
            }
    goal_id, directory, state = load_state(root, args.goal_id)
    payload = {
        "ok": not validate_state(state),
        "active": True,
        "goal_id": goal_id,
        "goal_dir": str(directory),
        "git_sha": current_git_sha(root),
        "design_drift": design_drift(directory, state),
        "validation_errors": validate_state(state),
        "state": state,
    }
    if not state.get("approved"):
        payload["plan"] = plan_readiness(directory, state)
    return payload


def concise(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    rendered = " ".join(str(value).split())
    if not rendered:
        return None
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def append_event(directory: Path, event: dict[str, Any]) -> None:
    """Append one deliberately small, non-sensitive event under the controller lock."""
    unknown = set(event) - EVENT_FIELDS
    if unknown:
        raise GoalFlowError(f"Event contains unsupported fields: {', '.join(sorted(unknown))}")
    payload = {key: value for key, value in event.items() if value is not None}
    path = directory / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_events(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    path = directory / "events.jsonl"
    if not path.exists():
        return [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines):
                warnings.append(f"Ignored incomplete final event line {index}")
                continue
            raise GoalFlowError(f"Invalid event JSON at line {index}: {exc}") from exc
        if not isinstance(item, dict):
            raise GoalFlowError(f"Event line {index} is not a JSON object")
        unknown = set(item) - EVENT_FIELDS
        if unknown:
            warnings.append(
                f"Ignored unsupported fields on event line {index}: {', '.join(sorted(unknown))}"
            )
        events.append({key: item[key] for key in EVENT_FIELDS if key in item})
    return events, warnings


def append_command_event(
    root: Path, args: argparse.Namespace, payload: dict[str, Any]
) -> None:
    state = payload.get("state")
    if not isinstance(state, dict):
        explicit = payload.get("goal_id") or getattr(args, "goal_id", None)
        try:
            _, _, state = load_state(root, explicit)
        except GoalFlowError:
            return
    goal_id = state.get("goal_id")
    if not goal_id:
        return
    event_name = args.command.replace("-", "_")
    if args.command == "record":
        event_name = f"record_{args.record_type}"
    result = None
    reason = None
    if args.command == "verify":
        result = payload.get("status")
        if payload.get("timed_out"):
            reason = "verifier timed out"
        elif result == "FAIL":
            reason = "verifier failed"
    elif args.command == "gate":
        result = payload.get("gate")
    event = {
        "time": now(),
        "event": event_name,
        "status": state.get("status"),
        "revision": state.get("state_revision"),
        "milestone": state.get("current_milestone"),
        "check": payload.get("check_id"),
        "result": result,
        "duration_ms": payload.get("duration_ms"),
        "git_sha": payload.get("git_sha") or current_git_sha(root),
        "reason": reason,
    }
    append_event(goal_dir(root, str(goal_id)), event)


def build_summary(root: Path, goal_id: str, state: dict[str, Any]) -> dict[str, Any]:
    must = [
        item for item in state.get("requirements", {}).values()
        if item.get("kind") == "must"
    ]
    verified = [
        item for item in must
        if item.get("status") == "VERIFIED"
        and evidence_is_fresh(root, item.get("git_sha"))
    ]
    failed_checks = sorted(
        (
            (check_id, item)
            for check_id, item in state.get("checks", {}).items()
            if item.get("status") == "FAIL"
        ),
        key=lambda pair: str(pair[1].get("updated_at") or ""),
        reverse=True,
    )
    recent_failure = None
    if failed_checks:
        check_id, item = failed_checks[0]
        failure_class = item.get("failure_class") or "unknown"
        recent_failure = concise(f"{check_id} [{failure_class}]: {item.get('summary') or 'check failed'}")
    blocker = concise(state.get("wait_reason")) if state.get("status") in WAIT_STATUSES else None
    payload = {
        "ok": not validate_state(state),
        "active": True,
        "goal_id": goal_id,
        "title": state.get("title") or goal_id,
        "profile": state.get("profile", "strict"),
        "harness": state.get("harness", {}),
        "context_excerpt": context_excerpt(root),
        "status": state.get("status"),
        "must_verified": len(verified),
        "must_total": len(must),
        "milestone": state.get("current_milestone"),
        "blocker": blocker,
        "recent_failure": recent_failure,
        "git_sha": current_git_sha(root),
        "next_action": concise(state.get("next_action")),
    }
    lines = [
        f"Goal: {payload['title']} ({goal_id})",
        f"Profile: {payload['profile']}",
        f"Harness: {payload['harness'].get('mode', 'goal-flow')}"
        + (" (behavior change)" if payload['harness'].get("behavior_change") else ""),
        f"Status: {payload['status']}",
        f"Progress: {payload['must_verified']}/{payload['must_total']} MUST verified",
        f"Milestone: {payload['milestone'] or '-'}",
    ]
    if blocker:
        lines.append(f"Blocked by: {blocker}")
    elif recent_failure:
        lines.append(f"Recent failure: {recent_failure}")
    lines.extend([
        f"Git: {payload['git_sha']}",
        f"Next: {payload['next_action'] or '-'}",
    ])
    payload["text"] = "\n".join(lines)
    return payload


def cmd_summary(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not args.goal_id:
        path = active_file(root)
        if not path.exists() or not load_json(path).get("goal_id"):
            return {
                "ok": True,
                "active": False,
                "message": "No active Goal Flow goal",
                "text": "No active Goal Flow goal.",
            }
    goal_id, _, state = load_state(root, args.goal_id)
    return build_summary(root, goal_id, state)


def build_report(
    root: Path, goal_id: str, directory: Path, state: dict[str, Any]
) -> dict[str, Any]:
    sha = current_git_sha(root)
    events, warnings = read_events(directory)
    metrics = assurance_payload(root, state, sha)
    requirements = [
        {
            "id": requirement_id,
            "kind": item.get("kind"),
            "status": item.get("status"),
            "fresh": evidence_is_fresh(root, item.get("git_sha")),
        }
        for requirement_id, item in sorted(state.get("requirements", {}).items())
    ]
    checks = [
        {
            "id": check_id,
            "required": bool(item.get("required")),
            "status": item.get("status"),
            "fresh": evidence_is_fresh(root, item.get("git_sha")),
            "duration_ms": item.get("duration_ms"),
            "timed_out": bool(item.get("timed_out")),
            "termination": item.get("termination"),
            "git_sha": item.get("git_sha"),
        }
        for check_id, item in sorted(state.get("checks", {}).items())
    ]
    risks = [
        {
            "id": risk_id,
            "status": item.get("status"),
            "severity": item.get("severity"),
        }
        for risk_id, item in sorted(state.get("risks", {}).items())
    ]
    attempts = sum(item.get("event") == "verify" for item in events)
    failures = sum(
        item.get("event") == "verify" and item.get("result") == "FAIL"
        for item in events
    )
    payload = {
        "ok": not validate_state(state),
        "active": active_goal_id(root) == goal_id if active_file(root).exists() else False,
        "goal_id": goal_id,
        "title": state.get("title") or goal_id,
        "profile": state.get("profile", "strict"),
        "status": state.get("status"),
        "git_sha": sha,
        "milestone": state.get("current_milestone"),
        "assurance": metrics,
        "attempts": attempts,
        "failures": failures,
        "requirements": requirements,
        "checks": checks,
        "risks": risks,
        "events": events,
        "warnings": warnings,
    }
    lines = [
        f"# Goal Flow report — {payload['title']}",
        "",
        f"- Goal: {goal_id}",
        f"- Profile: {payload['profile']}",
        f"- Status: {payload['status']}",
        f"- Git: {sha}",
        f"- Milestone: {payload['milestone'] or '-'}",
        "",
        "## Coverage",
        "",
        f"- MUST requirements: {metrics['must_verified_on_current_sha']}/{metrics['must_total']}",
        f"- Required checks: {metrics['required_check_coverage']}%",
        f"- Verification attempts/failures: {attempts}/{failures}",
        f"- Open risks: {metrics['open_risks']} ({metrics['open_high_or_critical_risks']} high/critical)",
        f"- Assurance: {metrics['assurance']} ({metrics['confidence']})",
        "",
        "## Timeline",
        "",
    ]
    if events:
        for item in events:
            detail = ""
            if item.get("check"):
                detail += f" {item['check']}"
            if item.get("result"):
                detail += f" → {item['result']}"
            lines.append(f"- {item.get('time', '-')} · {item.get('event', 'unknown')}{detail}")
    else:
        lines.append("- No event history is available for this goal.")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    payload["text"] = "\n".join(lines)
    return payload


def cmd_report(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if not args.goal_id:
        path = active_file(root)
        if not path.exists() or not load_json(path).get("goal_id"):
            return {
                "ok": True,
                "active": False,
                "message": "No active Goal Flow goal",
                "text": "No active Goal Flow goal.",
            }
    goal_id, directory, state = load_state(root, args.goal_id)
    return build_report(root, goal_id, directory, state)


def cmd_plan_check(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    result = plan_readiness(directory, state)
    return {"goal_id": goal_id, **result}


def cmd_review(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    result = semantic_review(directory, state, strict=args.strict)
    result["goal_id"] = goal_id
    result["mode"] = state.get("harness", {}).get("mode", "goal-flow")
    result["message"] = f"Semantic review {result['status']}"
    return result


def cmd_classify(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    result = classify_harness(
        task_type=args.task_type,
        risk_level=args.risk_level,
        files=args.files,
        steps=args.steps,
        behavior_change=args.behavior_change,
        cross_session=args.cross_session,
        autonomous=args.autonomous,
        default_mode=args.default_mode,
    )
    result["goal"] = args.goal
    result["message"] = f"Recommended Harness: {result['mode']} ({result['profile']})"
    return result


def cmd_context(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    path = context_path(root)
    if args.init:
        if path.exists():
            return {"ok": True, "created": False, "path": str(path), "message": "Project context already exists"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(context_template(), encoding="utf-8")
        return {"ok": True, "created": True, "path": str(path), "message": "Project context initialized"}
    return {
        "ok": True,
        "exists": path.exists(),
        "path": str(path),
        "excerpt": context_excerpt(root, limit=1200),
        "message": "Project context loaded" if path.exists() else "No project context; run context --init",
    }


def cmd_bind_worktree(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot bind immutable goal {state['status']}")
    if not state.get("approved"):
        raise GoalFlowError("Approve the design before binding its implementation worktree")
    if not product_tree_is_clean(root):
        raise GoalFlowError("Commit or clean product-tree changes before binding the worktree")
    binding = current_worktree_identity(root)
    state["worktree_binding"] = binding
    state["branch"] = binding["branch"]
    save_state(directory, state)
    append_evidence(directory, "Worktree bound", binding)
    return {"ok": True, "message": "Worktree bound", "binding": binding, "state": state}


def cmd_approve(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] not in {"PLANNING", "WAITING_PLAN_APPROVAL"}:
        raise GoalFlowError(f"Cannot approve from {state['status']}")
    readiness = plan_readiness(directory, state)
    if not readiness["ok"]:
        raise GoalFlowError("Plan is not approval-ready: " + "; ".join(readiness["reasons"]))
    if not args.user_approved:
        raise GoalFlowError("Explicit user approval is required; pass --user-approved only after it is given")
    state.update({
        "approved": True,
        "approved_design_hash": design_hash(directory, state),
        "approved_definitions_hash": definitions_hash(state),
        "status": "EXECUTING",
        "current_milestone": args.milestone or "M1",
        "next_action": args.next_action,
        "wait_reason": None,
        "no_progress_count": 0,
        "stop_repeat_count": 0,
        "approved_by": args.approved_by,
    })
    save_state(directory, state)
    append_evidence(directory, "Design approved", {
        "goal revision": state["goal_revision"],
        "design hash": state["approved_design_hash"],
        "definitions hash": state["approved_definitions_hash"],
        "next action": state["next_action"],
        "approved by": state["approved_by"],
    })
    return {"ok": True, "message": "Design approved", "state": state}


def cmd_record(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot record evidence for immutable goal {state['status']}")
    if state.get("approved"):
        require_bound_worktree(root, state)
    sha = args.git_sha or current_git_sha(root)
    if args.record_type == "requirement":
        if args.status not in REQUIREMENT_STATUSES:
            raise GoalFlowError("Invalid requirement status")
        if args.status != "UNVERIFIED" and not args.evidence:
            raise GoalFlowError("Requirement findings need non-empty evidence")
        if args.status != "UNVERIFIED" and (
            sha == "UNBORN" or run_git(root, "cat-file", "-e", f"{sha}^{{commit}}") is None
        ):
            raise GoalFlowError("Requirement evidence must reference an existing Git commit")
        prior = state["requirements"].get(args.id, {})
        verified_by = args.verified_by or prior.get("verified_by") or []
        statement = args.statement or prior.get("statement") or args.id
        kind = args.kind or prior.get("kind") or "must"
        proves = args.proves or prior.get("proves")
        failure_modes = args.failure_mode or prior.get("failure_modes") or []
        basis = args.basis or prior.get("basis") or []
        if state.get("approved"):
            if not prior:
                raise GoalFlowError("Approved requirement set is frozen; run replan before adding one")
            if statement != prior.get("statement") or kind != prior.get("kind"):
                raise GoalFlowError("Approved requirement definitions are frozen; run replan to change them")
            if sorted(verified_by) != sorted(prior.get("verified_by") or []):
                raise GoalFlowError("Approved requirement verifiers are frozen; run replan to change them")
            if proves != prior.get("proves"):
                raise GoalFlowError("Approved evidence scope is frozen; run replan to change it")
            if sorted(failure_modes) != sorted(prior.get("failure_modes") or []):
                raise GoalFlowError("Approved failure modes are frozen; run replan to change them")
            if sorted(basis) != sorted(prior.get("basis") or []):
                raise GoalFlowError("Approved acceptance basis is frozen; run replan to change it")
        if args.status == "VERIFIED":
            invalid = [
                check_id for check_id in verified_by
                if check_id not in state.get("checks", {})
                or state["checks"][check_id].get("status") != "PASS"
                or not evidence_is_fresh(root, state["checks"][check_id].get("git_sha"))
            ]
            if not verified_by or invalid:
                suffix = f": {', '.join(invalid)}" if invalid else ""
                raise GoalFlowError(f"VERIFIED requirements need fresh passing --verified-by checks{suffix}")
        state["requirements"][args.id] = {
            "statement": statement,
            "kind": kind,
            "verified_by": verified_by,
            "proves": proves,
            "failure_modes": failure_modes,
            "basis": basis,
            "status": args.status,
            "evidence": args.evidence,
            "git_sha": sha if args.status != "UNVERIFIED" else None,
            "updated_at": now(),
        }
        append_evidence(directory, f"Requirement {args.id}", {
            "status": args.status,
            "statement": state["requirements"][args.id]["statement"],
            "evidence": args.evidence,
            "Git SHA": state["requirements"][args.id]["git_sha"],
            "verified by": ", ".join(verified_by),
            "what evidence proves": proves,
            "failure modes": "; ".join(failure_modes),
            "basis": "; ".join(basis),
            "residual risk": args.risk,
        })
    elif args.record_type == "check":
        if args.status not in CHECK_STATUSES:
            raise GoalFlowError("Invalid check status")
        if args.status != "PENDING":
            raise GoalFlowError("Use verify to execute checks; record check only registers PENDING definitions")
        if state.get("approved"):
            raise GoalFlowError("Approved check definitions are frozen; run replan to change them")
        if not args.check_command or not args.check_command.strip():
            raise GoalFlowError("Check definitions need an executable --command")
        if args.timeout <= 0:
            raise GoalFlowError("Check timeout must be a positive number of seconds")
        state["checks"][args.id] = {
            "status": "PENDING",
            "required": args.required,
            "command": args.check_command,
            "timeout": args.timeout,
            "summary": None,
            "output_digest": None,
            "git_sha": None,
            "updated_at": now(),
        }
        append_evidence(directory, f"Check {args.id}", {
            "status": "PENDING",
            "required": args.required,
            "command": args.check_command,
            "timeout": args.timeout,
        })
    elif args.record_type == "risk":
        if args.status not in RISK_STATUSES:
            raise GoalFlowError("Invalid risk status")
        prior = state["risks"].get(args.id, {})
        severity = args.severity or prior.get("severity") or "low"
        if prior and RISK_SEVERITY_ORDER[severity] < RISK_SEVERITY_ORDER[prior["severity"]]:
            raise GoalFlowError("Risk severity cannot be lowered; mitigate or explicitly accept it")
        verified_by = args.verified_by or prior.get("verified_by") or []
        if args.status == "ACCEPTED" and not args.accepted_by:
            raise GoalFlowError("Accepted risks require --accepted-by with the approving identity")
        if args.status == "MITIGATED":
            if not args.evidence:
                raise GoalFlowError("MITIGATED risks require non-empty evidence")
            if not verifiers_are_fresh(root, state, verified_by):
                raise GoalFlowError("MITIGATED risks require fresh PASS checks via --verified-by")
        state["risks"][args.id] = {
            "status": args.status,
            "severity": severity,
            "description": args.statement or prior.get("description") or args.evidence or args.id,
            "evidence": args.evidence,
            "verified_by": verified_by,
            "git_sha": current_git_sha(root) if args.status == "MITIGATED" else None,
            "accepted_by": args.accepted_by if args.status == "ACCEPTED" else None,
            "updated_at": now(),
        }
        append_evidence(directory, f"Risk {args.id}", {
            "status": args.status,
            "severity": severity,
            "description": state["risks"][args.id]["description"],
            "evidence": args.evidence,
            "verified by": ", ".join(verified_by),
            "accepted by": state["risks"][args.id]["accepted_by"],
        })
    elif args.record_type == "dimension":
        if state.get("approved"):
            raise GoalFlowError("Approved acceptance dimensions are frozen; run replan to change them")
        if args.id not in ACCEPTANCE_DIMENSIONS:
            raise GoalFlowError(
                "Unknown acceptance dimension; use one of: " + ", ".join(sorted(ACCEPTANCE_DIMENSIONS))
            )
        if args.status not in DIMENSION_STATUSES:
            raise GoalFlowError("Dimension status must be COVERED or N_A")
        if not substantive(args.rationale):
            raise GoalFlowError("Acceptance dimensions need a substantive --rationale")
        requirement_ids = args.requirement_id or []
        if args.status == "COVERED" and not requirement_ids:
            raise GoalFlowError("COVERED dimensions need at least one --requirement-id")
        unknown = [req_id for req_id in requirement_ids if req_id not in state["requirements"]]
        if unknown:
            raise GoalFlowError(f"Unknown requirement IDs: {', '.join(unknown)}")
        state["dimensions"][args.id] = {
            "status": args.status,
            "rationale": args.rationale,
            "requirement_ids": requirement_ids,
            "updated_at": now(),
        }
        append_evidence(directory, f"Acceptance dimension {args.id}", {
            "status": args.status,
            "rationale": args.rationale,
            "criteria": ", ".join(requirement_ids),
        })
    else:
        append_evidence(directory, "Note", {"message": args.evidence or args.statement})
    if args.record_type in {"requirement", "check"} and args.status not in {"UNVERIFIED", "PENDING"}:
        state["last_verified_commit"] = sha
    state["no_progress_count"] = 0
    state["stop_repeat_count"] = 0
    save_state(directory, state)
    return {"ok": True, "message": f"Recorded {args.record_type}", "state": state}


def environment_fingerprint(root: Path) -> dict[str, Any]:
    lockfiles: dict[str, str] = {}
    for name in LOCKFILE_NAMES:
        path = root / name
        if path.is_file():
            lockfiles[name] = file_hash(path)
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "lockfiles": lockfiles,
    }


def execute_verifier(command: str, root: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        executable="/bin/sh",
        start_new_session=True,
    )
    timed_out = False
    termination = None
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        returncode = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = 124
        termination = "SIGTERM"
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            termination = "SIGKILL"
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
    output = "\n".join(part for part in (stdout, stderr) if part).strip()
    return {
        "returncode": returncode,
        "output": output,
        "timed_out": timed_out,
        "termination": termination,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def classify_failure(execution: dict[str, Any]) -> tuple[str | None, str | None]:
    if execution.get("returncode") == 0 and not execution.get("timed_out"):
        return None, None
    output = str(execution.get("output") or "").lower()
    if execution.get("timed_out"):
        return "environment_or_dependency", "检查运行超时；先确认服务、依赖和资源状态，再决定是否重试。"
    if any(token in output for token in ("permission denied", "not authorized", "unauthorized", "forbidden")):
        return "authorization_or_external_input", "检查需要权限或外部输入；不要反复重试，缺少授权时暂停并请求用户处理。"
    if any(token in output for token in ("command not found", "no module named", "modulenotfounderror", "cannot import")):
        return "environment_or_dependency", "检查运行时、依赖安装和项目上下文；环境未恢复前不要修改业务代码。"
    if any(token in output for token in ("assertionerror", "assert ", "traceback", "failed", "error:")):
        return "implementation_defect", "定位失败断言和最近改动，修复一个可验证原因后重新执行检查。"
    return "unknown", "保存失败输出并增加诊断信息；没有新证据时不要重复同一策略。"


def cmd_verify(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot verify immutable goal {state['status']}")
    if not state.get("approved"):
        raise GoalFlowError("Check commands cannot run before explicit design approval")
    require_bound_worktree(root, state)
    check = state.get("checks", {}).get(args.id)
    if not check:
        raise GoalFlowError(f"Unknown check: {args.id}")
    command = check.get("command")
    if not command:
        raise GoalFlowError(f"Check {args.id} has no approved command")
    if state.get("approved") and design_drift(directory, state):
        raise GoalFlowError("Approved definitions changed; run replan before verification")
    if not product_tree_is_clean(root):
        raise GoalFlowError("Commit or clean product-tree changes before running a bound check")
    sha = current_git_sha(root)
    if sha == "UNBORN":
        raise GoalFlowError("Verification requires an existing Git commit")
    timeout = int(check.get("timeout") or 300)
    execution = execute_verifier(command, root, timeout)
    returncode = execution["returncode"]
    output = execution["output"]
    failure_class, recommended_action = classify_failure(execution)
    clean_after = product_tree_is_clean(root)
    status = "PASS" if returncode == 0 and clean_after else "FAIL"
    summary_parts = [f"exit={returncode}"]
    if execution["timed_out"]:
        summary_parts.append(f"timed out after {timeout}s")
        summary_parts.append(f"terminated with {execution['termination']}")
    if not clean_after:
        summary_parts.append("command changed the product tree")
    if output:
        summary_parts.append(output[-4000:])
    summary = " | ".join(summary_parts)
    check.update({
        "status": status,
        "summary": summary,
        "output_digest": hashlib.sha256(output.encode()).hexdigest(),
        "git_sha": sha,
        "duration_ms": execution["duration_ms"],
        "timed_out": execution["timed_out"],
        "termination": execution["termination"],
        "failure_class": failure_class,
        "recommended_action": recommended_action,
        "environment": environment_fingerprint(root),
        "updated_at": now(),
    })
    state["last_verified_commit"] = sha
    state["no_progress_count"] = 0
    state["stop_repeat_count"] = 0
    save_state(directory, state)
    append_evidence(directory, f"Executed check {args.id}", {
        "status": status,
        "command": command,
        "exit code": returncode,
        "summary": summary,
        "output digest": check["output_digest"],
        "duration ms": check["duration_ms"],
        "termination": check["termination"],
        "failure class": failure_class,
        "recommended action": recommended_action,
        "environment": json.dumps(check["environment"], sort_keys=True),
        "Git SHA": sha,
    })
    return {
        "ok": status == "PASS",
        "message": f"Check {args.id} {status}",
        "check_id": args.id,
        "status": status,
        "git_sha": sha,
        "summary": summary,
        "duration_ms": check["duration_ms"],
        "timed_out": check["timed_out"],
        "termination": check["termination"],
        "failure_class": failure_class,
        "recommended_action": recommended_action,
        "environment": check["environment"],
        "state": state,
    }


def cmd_update(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot update immutable goal {state['status']}")
    if state.get("approved"):
        require_bound_worktree(root, state)
    if args.status and args.status not in EDITABLE_STATUSES:
        raise GoalFlowError(f"Use a dedicated command for status {args.status}")
    if args.status:
        state["status"] = args.status
    if args.milestone:
        state["current_milestone"] = args.milestone
    if args.next_action:
        state["next_action"] = args.next_action
    if args.progress:
        state["no_progress_count"] = 0
        state["stop_repeat_count"] = 0
    if args.no_progress:
        state["no_progress_count"] = int(state.get("no_progress_count", 0)) + 1
    save_state(directory, state)
    return {"ok": True, "message": "State updated", "state": state}


def cmd_replan(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot replan immutable goal {state['status']}")
    state["goal_revision"] += 1
    state.update({
        "status": "PLANNING",
        "approved": False,
        "approved_design_hash": None,
        "approved_definitions_hash": None,
        "current_milestone": "PLAN",
        "next_action": "Revise the plan and acceptance contract, then obtain explicit approval",
        "wait_reason": args.reason,
        "no_progress_count": 0,
        "stop_repeat_count": 0,
    })
    for item in state.get("requirements", {}).values():
        item.update({"status": "UNVERIFIED", "evidence": None, "git_sha": None})
    for item in state.get("checks", {}).values():
        item.update({"status": "PENDING", "summary": None, "output_digest": None, "git_sha": None})
    save_state(directory, state)
    append_evidence(directory, "Replan required", {"new revision": state["goal_revision"], "reason": args.reason})
    return {"ok": True, "message": "Goal returned to planning", "state": state}


def cmd_pause(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot pause {state['status']}")
    state["resume_status"] = state["status"]
    state["status"] = "PAUSED"
    state["wait_reason"] = args.reason
    save_state(directory, state)
    return {"ok": True, "message": "Goal paused", "state": state}


def cmd_resume(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] not in {"PAUSED", "WAITING_INPUT", "WAITING_AUTHORIZATION", "BLOCKED"}:
        raise GoalFlowError(f"Cannot resume from {state['status']}")
    if state.get("approved"):
        require_bound_worktree(root, state)
    target = state.get("resume_status") or ("EXECUTING" if state.get("approved") else "PLANNING")
    state.update({"status": target, "wait_reason": None, "resume_status": None, "stop_repeat_count": 0})
    save_state(directory, state)
    return {"ok": True, "message": "Goal resumed", "state": state}


def cmd_block(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot block immutable goal {state['status']}")
    state["resume_status"] = state["status"]
    state["status"] = "BLOCKED"
    state["wait_reason"] = args.reason
    save_state(directory, state)
    return {"ok": True, "message": "Goal blocked", "state": state}


def cmd_cancel(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot cancel immutable goal {state['status']}")
    state["status"] = "CANCELLED"
    state["wait_reason"] = args.reason
    save_state(directory, state)
    deactivate_goal(root, goal_id)
    return {"ok": True, "message": "Goal cancelled", "state": state}


def cmd_gate(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state.get("approved") and (args.apply or args.stop_event):
        require_bound_worktree(root, state)
    result = evaluate_gate(root, directory, state)
    if args.stop_event and result["gate"] == "CONTINUE":
        fingerprint = state_fingerprint(root, state)
        if fingerprint == state.get("last_stop_fingerprint"):
            state["stop_repeat_count"] = int(state.get("stop_repeat_count", 0)) + 1
        else:
            state["last_stop_fingerprint"] = fingerprint
            state["stop_repeat_count"] = 1
        if state["stop_repeat_count"] >= 3:
            result["gate"] = "WAIT"
            result["reasons"] = ["No observable state progress across three continuation attempts"]
            result["next_action"] = "Diagnose the blocker or request user input"
            state["resume_status"] = state["status"]
            state["status"] = "BLOCKED"
            state["wait_reason"] = result["reasons"][0]
            result["status"] = state["status"]
        save_state(directory, state)
    if args.apply and result["gate"] == "READY_FOR_REVIEW" and state["status"] != "READY_FOR_ACCEPTANCE":
        state["status"] = "READY_FOR_ACCEPTANCE"
        state["next_action"] = result["next_action"]
        state["last_verified_commit"] = result["git_sha"]
        save_state(directory, state)
        result["status"] = state["status"]
    elif args.apply and result["gate"] == "CONTINUE" and state["status"] == "READY_FOR_ACCEPTANCE":
        state["status"] = "VERIFYING"
        state["next_action"] = "Refresh stale evidence and rerun the delivery gate"
        save_state(directory, state)
        result["status"] = state["status"]
        result["next_action"] = state["next_action"]
    return result


def cmd_accept(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    require_bound_worktree(root, state)
    if state["status"] != "READY_FOR_ACCEPTANCE":
        raise GoalFlowError("Only a goal ready for acceptance can be accepted")
    gate = evaluate_gate(root, directory, state)
    if gate["gate"] != "READY_FOR_REVIEW":
        reasons = "; ".join(gate.get("reasons") or ["delivery evidence is stale"])
        raise GoalFlowError(f"Acceptance gate is no longer satisfied: {reasons}")
    if not args.user_accepted:
        raise GoalFlowError("Explicit user acceptance is required; pass --user-accepted only after it is given")
    state["status"] = "ACCEPTED"
    state["next_action"] = None
    save_state(directory, state)
    append_evidence(directory, "User acceptance", {
        "status": "ACCEPTED",
        "accepted by": args.accepted_by,
        "Git SHA": current_git_sha(root),
    })
    deactivate_goal(root, goal_id)
    return {"ok": True, "message": "Goal accepted", "state": state}


def cmd_reject(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    require_bound_worktree(root, state)
    if state["status"] != "READY_FOR_ACCEPTANCE":
        raise GoalFlowError("Only a goal ready for acceptance can be rejected")
    state.update({"status": "EXECUTING", "next_action": args.reason, "wait_reason": None})
    save_state(directory, state)
    append_evidence(directory, "Delivery rejected", {"reason": args.reason})
    return {"ok": True, "message": "Goal returned to execution", "state": state}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Repository root; defaults to discovery from cwd")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--goal-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--profile", choices=sorted(PROFILES), default="standard")
    init.add_argument("--mode", choices=sorted(HARNESS_MODES), default="auto")
    init.add_argument("--behavior-change", action="store_true")
    init.add_argument("--task-type", choices=sorted(TASK_TYPES), default="unspecified")
    init.add_argument("--risk-level", choices=sorted(RISK_LEVELS), default="unspecified")
    init.add_argument("--files", type=int, default=1)
    init.add_argument("--steps", type=int, default=1)
    init.add_argument("--cross-session", action="store_true")
    init.add_argument("--autonomous", action="store_true")

    status = sub.add_parser("status")
    status.add_argument("--goal-id")

    summary = sub.add_parser("summary")
    summary.add_argument("--goal-id")
    summary.add_argument("--json", action="store_true")

    report = sub.add_parser("report")
    report.add_argument("--goal-id")
    report.add_argument("--json", action="store_true")

    bind_worktree = sub.add_parser("bind-worktree")
    bind_worktree.add_argument("--goal-id")

    approve = sub.add_parser("approve")
    approve.add_argument("--goal-id")
    approve.add_argument("--milestone")
    approve.add_argument("--next-action", required=True)
    approve.add_argument("--user-approved", action="store_true")
    approve.add_argument("--approved-by", default="user")

    record = sub.add_parser("record")
    record.add_argument("record_type", choices=["requirement", "check", "risk", "dimension", "note"])
    record.add_argument("--goal-id")
    record.add_argument("--id", default="NOTE")
    record.add_argument("--statement")
    record.add_argument("--kind", choices=["must", "should"])
    record.add_argument("--verified-by", action="append")
    record.add_argument("--proves")
    record.add_argument("--failure-mode", action="append")
    record.add_argument("--basis", action="append")
    record.add_argument("--status")
    record.add_argument("--evidence")
    record.add_argument("--risk")
    record.add_argument("--git-sha")
    record.add_argument("--command", dest="check_command")
    record.add_argument("--required", action="store_true")
    record.add_argument("--severity", choices=sorted(RISK_SEVERITIES))
    record.add_argument("--accepted-by")
    record.add_argument("--timeout", type=int, default=300)
    record.add_argument("--rationale")
    record.add_argument("--requirement-id", action="append")

    plan_check = sub.add_parser("plan-check")
    plan_check.add_argument("--goal-id")

    review = sub.add_parser("review")
    review.add_argument("--goal-id")
    review.add_argument("--strict", action="store_true")
    review.add_argument("--json", action="store_true")

    classify = sub.add_parser("classify")
    classify.add_argument("--goal", required=True)
    classify.add_argument("--task-type", choices=sorted(TASK_TYPES), default="unspecified")
    classify.add_argument("--risk-level", choices=sorted(RISK_LEVELS), default="unspecified")
    classify.add_argument("--files", type=int, default=1)
    classify.add_argument("--steps", type=int, default=1)
    classify.add_argument("--cross-session", action="store_true")
    classify.add_argument("--autonomous", action="store_true")
    classify.add_argument("--behavior-change", action="store_true")
    classify.add_argument("--default-mode", choices=["micro", "standard", "goal-flow"], default="micro")

    context = sub.add_parser("context")
    context.add_argument("--init", action="store_true")
    context.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify")
    verify.add_argument("--goal-id")
    verify.add_argument("--id", required=True)

    update = sub.add_parser("update")
    update.add_argument("--goal-id")
    update.add_argument("--status")
    update.add_argument("--milestone")
    update.add_argument("--next-action")
    update.add_argument("--progress", action="store_true")
    update.add_argument("--no-progress", action="store_true")

    replan = sub.add_parser("replan")
    replan.add_argument("--goal-id")
    replan.add_argument("--reason", required=True)

    pause = sub.add_parser("pause")
    pause.add_argument("--goal-id")
    pause.add_argument("--reason", required=True)

    resume = sub.add_parser("resume")
    resume.add_argument("--goal-id")

    block = sub.add_parser("block")
    block.add_argument("--goal-id")
    block.add_argument("--reason", required=True)

    cancel = sub.add_parser("cancel")
    cancel.add_argument("--goal-id")
    cancel.add_argument("--reason", required=True)

    gate = sub.add_parser("gate")
    gate.add_argument("--goal-id")
    gate.add_argument("--apply", action="store_true")
    gate.add_argument("--stop-event", action="store_true")

    accept = sub.add_parser("accept")
    accept.add_argument("--goal-id")
    accept.add_argument("--user-accepted", action="store_true")
    accept.add_argument("--accepted-by", default="user")

    reject = sub.add_parser("reject")
    reject.add_argument("--goal-id")
    reject.add_argument("--reason", required=True)

    return parser


COMMANDS = {
    "init": cmd_init,
    "status": cmd_status,
    "summary": cmd_summary,
    "report": cmd_report,
    "bind-worktree": cmd_bind_worktree,
    "plan-check": cmd_plan_check,
    "review": cmd_review,
    "classify": cmd_classify,
    "context": cmd_context,
    "approve": cmd_approve,
    "record": cmd_record,
    "verify": cmd_verify,
    "update": cmd_update,
    "replan": cmd_replan,
    "pause": cmd_pause,
    "resume": cmd_resume,
    "block": cmd_block,
    "cancel": cmd_cancel,
    "gate": cmd_gate,
    "accept": cmd_accept,
    "reject": cmd_reject,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = find_root(args.root)
    try:
        read_only = args.command in {"status", "summary", "report", "plan-check", "review", "classify"}
        if args.command == "context":
            read_only = not args.init
        if args.command == "gate":
            read_only = not args.apply and not args.stop_event
        with controller_lock(root, exclusive=not read_only):
            payload = COMMANDS[args.command](args, root)
            if not read_only:
                append_command_event(root, args, payload)
        if args.command in {"summary", "report"} and not args.json:
            print(payload["text"])
        else:
            emit(payload, True)
        return 0 if payload.get("ok", True) else 1
    except GoalFlowError as exc:
        emit({"ok": False, "error": str(exc)}, True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
