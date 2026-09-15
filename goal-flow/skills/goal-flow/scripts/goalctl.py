#!/usr/bin/env python3
"""Small deterministic controller for goal-flow repository state."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import html
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION}
REQUIREMENT_STATUSES = {"VERIFIED", "PARTIAL", "UNVERIFIED", "CONTRADICTED"}
CHECK_STATUSES = {"PASS", "FAIL", "PENDING"}
RISK_STATUSES = {"OPEN", "PARTIALLY_MITIGATED", "MITIGATED", "ACCEPTED"}
EVIDENCE_MODES = {"mock", "simulated", "real"}
EVIDENCE_MODE_ORDER = {"mock": 0, "simulated": 1, "real": 2}
CHECK_ROLES = {"component", "goal"}
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
HARNESS_MODES = {"auto", "micro", "standard", "goal-flow", "strict"}
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
LIGHTWEIGHT_STANDARD_DIMENSIONS = {"functional"}
PLACEHOLDER_MARKERS = {
    "to be defined during planning",
    "define during planning",
    "pending user discussion and approval",
    "repository and domain context to be investigated",
}
VISUAL_PLACEHOLDER_MARKERS = {
    "todo",
    "待补充",
    "replace with",
    "describe the",
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
STATUS_TRANSITIONS = {
    "PLANNING": {"WAITING_PLAN_APPROVAL", "WAITING_INPUT", "PAUSED", "BLOCKED", "CANCELLED"},
    "WAITING_PLAN_APPROVAL": {"PLANNING", "EXECUTING", "WAITING_INPUT", "PAUSED", "BLOCKED", "CANCELLED"},
    "EXECUTING": {"VERIFYING", "READY_FOR_ACCEPTANCE", "WAITING_INPUT", "WAITING_AUTHORIZATION", "PAUSED", "BLOCKED", "CANCELLED"},
    "VERIFYING": {"EXECUTING", "READY_FOR_ACCEPTANCE", "WAITING_INPUT", "WAITING_AUTHORIZATION", "PAUSED", "BLOCKED", "CANCELLED"},
    "READY_FOR_ACCEPTANCE": {"VERIFYING", "EXECUTING", "PAUSED", "BLOCKED", "CANCELLED", "ACCEPTED"},
    "WAITING_INPUT": {"PLANNING", "EXECUTING", "VERIFYING", "PAUSED", "BLOCKED", "CANCELLED"},
    "WAITING_AUTHORIZATION": {"EXECUTING", "VERIFYING", "PAUSED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"PLANNING", "EXECUTING", "VERIFYING", "PAUSED", "CANCELLED"},
    "PAUSED": {"PLANNING", "EXECUTING", "VERIFYING", "READY_FOR_ACCEPTANCE", "WAITING_INPUT", "WAITING_AUTHORIZATION", "BLOCKED", "CANCELLED"},
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


def ensure_status_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in STATUS_TRANSITIONS.get(current, set()):
        raise GoalFlowError(f"Invalid Goal Flow status transition: {current} -> {target}")


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
    if exclusive:
        store.mkdir(parents=True, exist_ok=True)
    lock_path = store / "controller.lock"
    if not exclusive and not lock_path.exists():
        yield
        return
    with lock_path.open("a+" if exclusive else "r", encoding="utf-8") as handle:
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
    default_mode: str = "auto",
) -> dict[str, Any]:
    """Choose the smallest harness that covers the task's observable risk."""
    if files < 1 or steps < 1:
        raise GoalFlowError("files and steps must be positive integers")
    if task_type not in TASK_TYPES:
        raise GoalFlowError(f"invalid task type: {task_type}")
    if risk_level not in RISK_LEVELS:
        raise GoalFlowError(f"invalid risk level: {risk_level}")
    reasons: list[str] = []
    # An explicitly requested harness is a user constraint, not a hint for
    # auto-classification.  Only ``auto`` may be reduced or upgraded from the
    # task characteristics below.
    explicit_mode = default_mode if default_mode in {"micro", "standard", "goal-flow", "strict"} else None
    if explicit_mode is not None:
        mode = "goal-flow" if explicit_mode == "strict" else explicit_mode
        profile = "strict" if explicit_mode == "strict" else "standard"
        reasons.append("using the explicitly requested harness")
        if (risk_level in {"high", "critical"} or task_type == "migration") and profile != "strict":
            mode = "goal-flow"
            profile = "strict"
            reasons.append("safety floor upgraded the requested harness for high-impact risk or migration")
        resolved = "strict" if profile == "strict" else "goal-flow" if mode == "goal-flow" else mode
        return {
            "mode": mode,
            "profile": profile,
            "resolved_harness": resolved,
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
                "plan": "lightweight" if mode in {"micro", "standard"} else "structured",
                "approval": "required" if mode == "goal-flow" else "conditional",
                "evidence": "strict" if profile == "strict" else "standard",
                "resume": mode == "goal-flow",
            },
        }
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
    elif default_mode in {"micro", "standard", "goal-flow", "strict"}:
        mode = "goal-flow" if default_mode == "strict" else default_mode
        profile = "strict" if default_mode == "strict" else "standard"
        reasons.append("small, bounded task fits the smallest requested harness")
    else:
        mode = "micro"
        profile = "standard"
        reasons.append("small, bounded task fits the smallest harness")
    resolved = "strict" if profile == "strict" else "goal-flow" if mode == "goal-flow" else mode
    return {
        "mode": mode,
        "profile": profile,
        "resolved_harness": resolved,
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
            "plan": "lightweight" if mode in {"micro", "standard"} else "structured",
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
    if explicit:
        goal_id = explicit
    elif not active_file(root).exists():
        return ""
    else:
        goal_id = str(load_json(active_file(root)).get("goal_id") or "")
    if goal_id and not SLUG_RE.fullmatch(goal_id):
        raise GoalFlowError("Invalid goal-id in request or active.json")
    return goal_id


def goal_dir(root: Path, goal_id: str) -> Path:
    return goal_store(root) / goal_id


def phase_for_state(state: dict[str, Any]) -> str:
    """Return the user-facing phase without duplicating it in persisted state."""
    status = state.get("status")
    if not state.get("approved") or status in {"PLANNING", "WAITING_PLAN_APPROVAL"}:
        return "analysis-design"
    if status in {"VERIFYING", "READY_FOR_ACCEPTANCE", "ACCEPTED"}:
        return "acceptance"
    resume_status = state.get("resume_status") if status == "PAUSED" else None
    if resume_status in {"VERIFYING", "READY_FOR_ACCEPTANCE"}:
        return "acceptance"
    return "implementation"


def visual_design_enabled(state: dict[str, Any]) -> bool:
    return bool((state.get("harness") or {}).get("visual_design"))


def visual_design_dir(directory: Path) -> Path:
    return directory / "design"


def visual_design_path(directory: Path) -> Path:
    return visual_design_dir(directory) / "architecture.drawio"


def visual_viewer_path(directory: Path) -> Path:
    return visual_design_dir(directory) / "architecture.html"


def visual_design_scaffold(title: str) -> str:
    safe_title = html.escape(title, quote=True)
    return f'''<mxfile host="Codex" modified="{now()}" agent="goal-flow" version="24.7.17" compressed="false">
  <diagram id="architecture" name="Architecture">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="arch-title" value="{safe_title} — Architecture" style="text;html=1;fontSize=24;fontStyle=1;" vertex="1" parent="1" data-kind="title" />
        <mxCell id="arch-current" value="TODO: current system / starting point" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;" vertex="1" parent="1" data-kind="component" data-description="TODO: current responsibility and repository location" data-requirements="REQ-001" data-status="existing"><mxGeometry x="70" y="150" width="250" height="110" as="geometry" /></mxCell>
        <mxCell id="arch-change" value="TODO: proposed change" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FEF3C7;strokeColor=#D97706;" vertex="1" parent="1" data-kind="component" data-description="TODO: new responsibility and implementation boundary" data-requirements="REQ-001" data-status="changed"><mxGeometry x="450" y="150" width="250" height="110" as="geometry" /></mxCell>
        <mxCell id="arch-target" value="TODO: target system / resulting capability" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#DCFCE7;strokeColor=#16A34A;" vertex="1" parent="1" data-kind="component" data-description="TODO: target capability and ownership" data-requirements="REQ-001" data-status="target"><mxGeometry x="830" y="150" width="250" height="110" as="geometry" /></mxCell>
        <mxCell id="arch-edge-1" value="change boundary" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;" edge="1" parent="1" source="arch-current" target="arch-change" data-kind="boundary" data-description="Existing to proposed boundary" data-requirements="REQ-001"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="arch-edge-2" value="produces" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;" edge="1" parent="1" source="arch-change" target="arch-target" data-kind="boundary" data-description="Proposed change to target capability" data-requirements="REQ-001"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="arch-note" value="TODO: key decisions, constraints, and out-of-scope boundaries" style="shape=note;whiteSpace=wrap;html=1;fillColor=#F8FAFC;strokeColor=#64748B;" vertex="1" parent="1" data-kind="decision" data-description="TODO: decisions, constraints, and deferred scope" data-requirements="REQ-001"><mxGeometry x="330" y="350" width="500" height="150" as="geometry" /></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
  <diagram id="critical-flow" name="Critical data flow">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
      <root>
        <mxCell id="f0" />
        <mxCell id="f1" parent="f0" />
        <mxCell id="flow-title" value="{safe_title} — Critical data flow" style="text;html=1;fontSize=24;fontStyle=1;" vertex="1" parent="f1" data-kind="title" />
        <mxCell id="flow-entry" value="TODO: trigger / input" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0284C7;" vertex="1" parent="f1" data-kind="entry" data-description="TODO: trigger, actor, and input source" data-requirements="REQ-001"><mxGeometry x="70" y="170" width="220" height="100" as="geometry" /></mxCell>
        <mxCell id="flow-process" value="TODO: processing and validation" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FEF3C7;strokeColor=#D97706;" vertex="1" parent="f1" data-kind="process" data-description="TODO: validation, authorization, transformation, and business rule" data-requirements="REQ-001"><mxGeometry x="430" y="170" width="260" height="100" as="geometry" /></mxCell>
        <mxCell id="flow-result" value="TODO: persistence / response / side effect" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#DCFCE7;strokeColor=#16A34A;" vertex="1" parent="f1" data-kind="output" data-description="TODO: persisted result, response, and side effect" data-requirements="REQ-001"><mxGeometry x="850" y="170" width="240" height="100" as="geometry" /></mxCell>
        <mxCell id="flow-edge-1" value="TODO: API-01 | request and validation contract" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;" edge="1" parent="f1" source="flow-entry" target="flow-process" data-kind="protocol" data-contract-id="API-01" data-description="TODO: input contract, auth, timeout, and validation" data-requirements="REQ-001"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="flow-edge-2" value="TODO: API-02 | response and persistence contract" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;" edge="1" parent="f1" source="flow-process" target="flow-result" data-kind="protocol" data-contract-id="API-02" data-description="TODO: output contract, consistency, and side effect" data-requirements="REQ-001"><mxGeometry relative="1" as="geometry" /></mxCell>
        <mxCell id="flow-failure" value="TODO: failure, retry, or rollback path" style="shape=note;whiteSpace=wrap;html=1;fillColor=#FEE2E2;strokeColor=#DC2626;" vertex="1" parent="f1" data-kind="failure" data-description="TODO: failure modes, retry, idempotency, and rollback" data-requirements="REQ-001"><mxGeometry x="430" y="380" width="360" height="130" as="geometry" /></mxCell>
        <mxCell id="flow-contract-1" value="TODO: API-01 | Request: input object with required fields | Fields: id type UUID required validation format meaning identity | Response: validation result | Errors: 400 / 401 | Auth: required | Timeout: 3s | Retry: none unless idempotent | Idempotency: request key" style="shape=note;whiteSpace=wrap;html=1;fillColor=#F8FAFC;strokeColor=#64748B;" vertex="1" parent="f1" data-kind="contract" data-contract-id="API-01" data-description="Request and validation protocol details" data-requirements="REQ-001" data-protocol="http" data-method="POST" data-path="/v1/resource" data-request="InputRequest" data-fields="id|UUID|required|format|identity" data-response="ValidationResult" data-errors="400,401" data-auth="required" data-timeout-ms="3000" data-retry="none" data-idempotency="request-key"><mxGeometry x="70" y="560" width="500" height="135" as="geometry" /></mxCell>
        <mxCell id="flow-contract-2" value="TODO: API-02 | Request: validated command | Fields: id type UUID required validation format meaning identity | Response: persisted result | Errors: 409 / 500 | Auth: service identity | Timeout: 5s | Retry: bounded | Idempotency: command key" style="shape=note;whiteSpace=wrap;html=1;fillColor=#F8FAFC;strokeColor=#64748B;" vertex="1" parent="f1" data-kind="contract" data-contract-id="API-02" data-description="Persistence and response protocol details" data-requirements="REQ-001" data-protocol="internal" data-method="COMMAND" data-path="service://resource" data-request="ValidatedCommand" data-fields="id|UUID|required|format|identity" data-response="ResourceResult" data-errors="409,500" data-auth="service-identity" data-timeout-ms="5000" data-retry="bounded" data-idempotency="command-key"><mxGeometry x="600" y="560" width="500" height="135" as="geometry" /></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
'''


def diagram_model(diagram: ET.Element) -> ET.Element:
    model = diagram.find("mxGraphModel")
    if model is not None:
        return model
    encoded = (diagram.text or "").strip()
    if not encoded:
        raise GoalFlowError(f"Draw.io page {diagram.get('name') or diagram.get('id')} has no model")
    try:
        raw = base64.b64decode(encoded)
        xml_text = urllib.parse.unquote(zlib.decompress(raw, -15).decode("utf-8"))
        return ET.fromstring(xml_text)
    except (ValueError, zlib.error, ET.ParseError) as exc:
        raise GoalFlowError(f"Cannot decode Draw.io page {diagram.get('name') or diagram.get('id')}: {exc}") from exc


def normalize_diagram_value(value: str | None) -> str:
    plain = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return " ".join(plain.split())


SEMANTIC_STYLE_KEYS = {
    "shape", "endArrow", "startArrow", "dashed", "dashPattern", "edgeStyle",
    "curved", "orthogonalLoop", "container", "swimlane", "direction",
}


def semantic_style(style: str | None) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in (style or "").split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key in SEMANTIC_STYLE_KEYS:
            values[key] = value
    return values


def visual_design_model(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise GoalFlowError(f"Missing visual design: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise GoalFlowError(f"Invalid Draw.io XML in {path}: {exc}") from exc
    if root.tag != "mxfile":
        raise GoalFlowError("architecture.drawio must contain an mxfile root")
    pages: list[dict[str, Any]] = []
    for page_index, diagram in enumerate(root.findall("diagram")):
        model = diagram_model(diagram)
        cells: list[dict[str, Any]] = []
        wrappers: dict[str, ET.Element] = {}
        for wrapper in [*model.findall(".//object"), *model.findall(".//UserObject")]:
            wrapped_cell = wrapper.find("mxCell")
            if wrapped_cell is not None:
                wrapper_id = wrapper.get("id")
                cell_id = wrapped_cell.get("id")
                if wrapper_id:
                    wrappers[str(wrapper_id)] = wrapper
                if cell_id:
                    wrappers[str(cell_id)] = wrapper
        for cell in model.findall(".//mxCell"):
            if not (cell.get("vertex") == "1" or cell.get("edge") == "1"):
                continue
            wrapper = wrappers.get(str(cell.get("id") or ""))
            cell_id = cell.get("id") or (wrapper.get("id") if wrapper is not None else None)
            display_value = cell.get("value")
            if wrapper is not None:
                display_value = wrapper.get("label") or wrapper.get("value") or display_value
            semantic = {
                "id": cell_id,
                "value": normalize_diagram_value(display_value),
                "vertex": cell.get("vertex") == "1",
                "edge": cell.get("edge") == "1",
                "source": cell.get("source"),
                "target": cell.get("target"),
                "parent": cell.get("parent"),
            }
            custom = {
                key: value for key, value in cell.attrib.items()
                if key.startswith("data-")
            }
            if wrapper is not None:
                custom.update({
                    key: value for key, value in wrapper.attrib.items()
                    if key.startswith("data-")
                })
            if custom:
                semantic["metadata"] = custom
            style = semantic_style(cell.get("style"))
            if style:
                semantic["style"] = style
            cells.append(semantic)
        pages.append({
            "index": page_index,
            "name": diagram.get("name") or f"Page {page_index + 1}",
            "cells": sorted(cells, key=lambda item: str(item.get("id") or "")),
        })
    if not pages:
        raise GoalFlowError("architecture.drawio must contain at least one page")
    return {"pages": pages}


def visual_design_semantic_hash(path: Path) -> str:
    raw = json.dumps(visual_design_model(path), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def visual_design_check(directory: Path, state: dict[str, Any] | None = None) -> dict[str, Any]:
    path = visual_design_path(directory)
    try:
        model = visual_design_model(path)
    except GoalFlowError as exc:
        return {"ok": False, "reasons": [str(exc)], "path": str(path), "pages": []}
    reasons: list[str] = []
    structural_reasons: list[str] = []
    page_names = {page["name"].strip().lower() for page in model["pages"]}
    for required in ("architecture", "critical data flow"):
        if required not in page_names:
            structural_reasons.append(f"architecture.drawio needs a '{required}' page")
    all_ids: dict[str, str] = {}
    protocol_edges: dict[str, str] = {}
    contract_cards: dict[str, str] = {}
    coverage = {
        "components": 0,
        "protocols": 0,
        "contracts": 0,
        "failure_paths": 0,
        "requirements": set(),
    }
    for page in model["pages"]:
        for cell in page["cells"]:
            cell_id = str(cell.get("id") or "")
            if not cell_id:
                continue
            if cell_id in all_ids:
                structural_reasons.append(f"Draw.io cell id is duplicated: {cell_id}")
            else:
                all_ids[cell_id] = page["name"]
    for page in model["pages"]:
        vertices = [cell for cell in page["cells"] if cell["vertex"]]
        edges = [cell for cell in page["cells"] if cell["edge"]]
        if len(vertices) < 3:
            structural_reasons.append(f"Draw.io page {page['name']} needs at least three semantic nodes")
        if page["name"].strip().lower() == "critical data flow" and len(edges) < 2:
            structural_reasons.append("Critical data flow needs at least two connected steps")
        for cell in page["cells"]:
            lowered = cell["value"].lower()
            if any(marker in lowered for marker in VISUAL_PLACEHOLDER_MARKERS):
                structural_reasons.append(f"Draw.io page {page['name']} still contains placeholder: {cell['value']}")
            cell_id = str(cell.get("id") or "")
            if not cell_id:
                structural_reasons.append(f"Draw.io page {page['name']} contains a semantic cell without an id")
            metadata = cell.get("metadata") or {}
            kind = str(metadata.get("data-kind") or "").strip().lower()
            if kind in {"title", "legend"}:
                continue
            if not kind:
                structural_reasons.append(
                    f"Draw.io page {page['name']} cell {cell_id} needs data-kind metadata"
                )
            if not cell.get("parent"):
                structural_reasons.append(f"Draw.io cell {cell_id} needs a parent reference")
            description = str(metadata.get("data-description") or "").strip()
            if not description or not substantive(description):
                structural_reasons.append(
                    f"Draw.io page {page['name']} cell {cell_id} needs a substantive data-description"
                )
            requirement_ids = {
                item.strip() for item in re.split(r"[,;\s]+", str(metadata.get("data-requirements") or ""))
                if item.strip()
            }
            if not requirement_ids:
                structural_reasons.append(
                    f"Draw.io page {page['name']} cell {cell_id} needs data-requirements metadata"
                )
            coverage["requirements"].update(requirement_ids)
            if cell["vertex"] and kind in {"component", "entry", "process", "output", "store", "actor", "service"}:
                coverage["components"] += 1
            if kind == "failure":
                coverage["failure_paths"] += 1
            if kind == "protocol" and cell["edge"]:
                contract_id = str(metadata.get("data-contract-id") or "").strip()
                if not contract_id:
                    structural_reasons.append(f"Protocol edge {cell_id} needs data-contract-id metadata")
                else:
                    protocol_edges[contract_id] = cell_id
                    coverage["protocols"] += 1
                if not cell.get("source") or not cell.get("target"):
                    structural_reasons.append(f"Protocol edge {cell_id} must reference source and target cells")
                elif cell.get("source") not in all_ids or cell.get("target") not in all_ids:
                    structural_reasons.append(f"Protocol edge {cell_id} references an unknown source or target")
            if kind == "contract" and cell["vertex"]:
                contract_id = str(metadata.get("data-contract-id") or "").strip()
                if not contract_id:
                    structural_reasons.append(f"Contract card {cell_id} needs data-contract-id metadata")
                else:
                    contract_cards[contract_id] = cell_id
                    coverage["contracts"] += 1
                required_contract_fields = {
                    "data-protocol", "data-request", "data-response", "data-errors",
                    "data-fields", "data-auth", "data-timeout-ms", "data-retry", "data-idempotency",
                }
                missing_contract = sorted(key for key in required_contract_fields if not metadata.get(key))
                if missing_contract:
                    structural_reasons.append(
                        f"Contract card {cell_id} is missing: {', '.join(missing_contract)}"
                    )
                field_specs = [item for item in str(metadata.get("data-fields") or "").split(";") if item.strip()]
                if field_specs and any(len(item.split("|")) < 5 for item in field_specs):
                    structural_reasons.append(
                        f"Contract card {cell_id} fields need name, type, requiredness, validation, and meaning"
                    )
                visible = lowered
                term_groups = {
                    "request": ("request", "请求"),
                    "response": ("response", "响应", "返回"),
                    "field": ("field", "字段"),
                    "type": ("type", "类型"),
                    "required": ("required", "必填"),
                    "validation": ("validation", "校验", "验证"),
                    "meaning": ("meaning", "含义"),
                    "error": ("error", "错误"),
                    "auth": ("auth", "鉴权", "认证"),
                    "retry": ("retry", "重试"),
                    "idempotency": ("idempot", "幂等"),
                }
                for label, terms in term_groups.items():
                    if not any(term in visible for term in terms):
                        structural_reasons.append(f"Contract card {cell_id} must visibly explain {label}")
        for cell in edges:
            if not cell.get("parent"):
                structural_reasons.append(f"Draw.io edge {cell.get('id')} needs a parent reference")
            if cell.get("source") and cell.get("source") not in all_ids:
                structural_reasons.append(f"Draw.io edge {cell.get('id')} references unknown source {cell.get('source')}")
            if cell.get("target") and cell.get("target") not in all_ids:
                structural_reasons.append(f"Draw.io edge {cell.get('id')} references unknown target {cell.get('target')}")
    for contract_id in sorted(set(protocol_edges) - set(contract_cards)):
        structural_reasons.append(f"Protocol {contract_id} has no visible contract card")
    if "critical data flow" in page_names:
        flow = next(page for page in model["pages"] if page["name"].strip().lower() == "critical data flow")
        flow_kinds = {str((cell.get("metadata") or {}).get("data-kind") or "").lower() for cell in flow["cells"]}
        for required_kind in ("entry", "process", "output", "failure"):
            if required_kind not in flow_kinds:
                structural_reasons.append(f"Critical data flow needs a {required_kind} node")
    if coverage["protocols"] and coverage["protocols"] != coverage["contracts"]:
        structural_reasons.append("Every protocol edge must have exactly one visible contract card")
    if state is not None:
        known_requirements = set(state.get("requirements", {}))
        unknown_requirements = sorted(coverage["requirements"] - known_requirements)
        if known_requirements and unknown_requirements:
            structural_reasons.append(
                "Visual design references unknown requirements: " + ", ".join(unknown_requirements)
            )
        must_requirements = {
            req_id for req_id, item in state.get("requirements", {}).items()
            if item.get("kind") == "must"
        }
        uncovered = sorted(must_requirements - coverage["requirements"])
        if uncovered:
            structural_reasons.append(
                "MUST requirements missing from visual design: " + ", ".join(uncovered)
            )
    reasons.extend(structural_reasons)
    viewer = visual_viewer_path(directory)
    viewer_fresh = False
    viewer_reason = "viewer is missing"
    if viewer.exists():
        try:
            marker = re.search(r'data-source-semantic-hash="([0-9a-f]{64})"', viewer.read_text(encoding="utf-8"))
        except OSError:
            marker = None
        expected_hash = visual_design_semantic_hash(path)
        if marker and marker.group(1) == expected_hash:
            viewer_fresh = True
            viewer_reason = "viewer matches the current Draw.io semantic hash"
        else:
            viewer_reason = "viewer is stale; run design-render"
    return {
        "ok": not reasons,
        "reasons": reasons,
        "path": str(path),
        "viewer": str(viewer),
        "viewer_fresh": viewer_fresh,
        "viewer_reason": viewer_reason,
        "pages": [page["name"] for page in model["pages"]],
        "semantic_hash": visual_design_semantic_hash(path),
        "coverage": {
            **{key: value for key, value in coverage.items() if key != "requirements"},
            "requirements": sorted(coverage["requirements"]),
        },
    }


def render_visual_viewer(directory: Path, title: str) -> Path:
    source = visual_design_path(directory)
    if not source.exists():
        raise GoalFlowError(f"Missing visual design: {source}")
    xml = source.read_text(encoding="utf-8")
    semantic_hash = visual_design_semantic_hash(source)
    pages = visual_design_model(source)["pages"]
    page_index = " · ".join(
        f"<span class=\"page-name\">{html.escape(str(page['name']))}</span>"
        for page in pages
    )
    config = json.dumps({
        "highlight": "#0000ff",
        "nav": True,
        "resize": True,
        "toolbar": "zoom layers lightbox",
        "xml": xml,
    }, ensure_ascii=False, separators=(",", ":"))
    document = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — Architecture</title>
  <style>
    html, body {{ height: 100%; margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; background: #f8fafc; color: #0f172a; }}
    header {{ min-height: 48px; display: flex; align-items: center; gap: 18px; padding: 6px 16px; background: #fff; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }}
    nav {{ color: #475569; font-size: 13px; flex: 1; }}
    .page-name {{ display: inline-block; margin-right: 8px; padding: 3px 8px; border: 1px solid #cbd5e1; border-radius: 999px; }}
    main {{ height: calc(100% - 49px); }}
    .mxgraph {{ width: 100%; height: 100%; border: 0; }}
    a {{ color: #4f46e5; text-decoration: none; }}
  </style>
</head>
<body>
  <header><strong>{html.escape(title)}</strong><nav aria-label="Diagram pages">页面：{page_index}</nav><a href="architecture.drawio">下载 / 用 Draw.io 编辑源文件</a></header>
  <main><div class="mxgraph" data-source-semantic-hash="{semantic_hash}" data-mxgraph="{html.escape(config, quote=True)}"></div></main>
  <script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
</body>
</html>
'''
    output = visual_viewer_path(directory)
    output.write_text(document, encoding="utf-8")
    return output


def initialize_visual_design(directory: Path, title: str) -> None:
    design_dir = visual_design_dir(directory)
    design_dir.mkdir(parents=True, exist_ok=True)
    visual_design_path(directory).write_text(visual_design_scaffold(title), encoding="utf-8")
    render_visual_viewer(directory, title)


def load_state(root: Path, explicit: str | None = None) -> tuple[str, Path, dict[str, Any]]:
    goal_id = active_goal_id(root, explicit)
    if not goal_id:
        raise GoalFlowError("No active goal")
    directory = goal_dir(root, goal_id)
    state = load_json(directory / "state.json")
    schema_version = state.get("schema_version", 1)
    if schema_version != SCHEMA_VERSION:
        raise GoalFlowError(
            f"Incompatible Goal Flow schema v{schema_version}; this release requires schema v{SCHEMA_VERSION}. "
            "Archive the existing .goal-flow directory and run init again. No files were changed."
        )
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
        "visual_design": False,
    })
    state["harness"].setdefault("visual_design", False)
    state.setdefault("state_revision", 0)
    state.setdefault("contract_version", 1)
    state.setdefault("resolved_harness", resolve_harness(state))
    state.setdefault("decision_check", {
        "auto_decided": [],
        "recommended_defaults": [],
        "user_decisions": [],
        "status": "none",
    })
    state.setdefault("delivery_attempt", 0)
    state.setdefault("delivery_feedback", None)
    state.setdefault("delivery_rejection_baseline", None)
    state.setdefault("epoch", None)
    return goal_id, directory, state


def resolve_harness(state: dict[str, Any]) -> str:
    """Normalize legacy mode/profile combinations into one public harness."""
    harness = state.get("harness") or {}
    if state.get("resolved_harness") and state.get("resolved_harness") not in {"micro", "standard", "goal-flow", "strict"}:
        errors.append(f"invalid resolved_harness: {state.get('resolved_harness')}")
    mode = harness.get("mode") or state.get("mode") or "goal-flow"
    profile = state.get("profile", "strict")
    if profile == "strict" or mode == "strict":
        return "strict"
    if mode == "goal-flow":
        return "goal-flow"
    if mode == "micro":
        return "micro"
    return "standard"


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


def activate_goal(root: Path, goal_id: str, state: dict[str, Any], *, switch: bool = False) -> None:
    """Make exactly one non-terminal goal active, without implicit takeover."""
    current_id = active_goal_id(root)
    if current_id and current_id != goal_id:
        current_dir = goal_dir(root, current_id)
        current_path = current_dir / "state.json"
        if current_path.exists():
            current = load_json(current_path)
            if current.get("status") not in {"ACCEPTED", "CANCELLED"}:
                if not switch:
                    raise GoalFlowError(
                        f"Active goal {current_id!r} is {current.get('status')}; pass --switch to activate {goal_id!r}"
                    )
                current["resume_status"] = current.get("status")
                current["status"] = "PAUSED"
                current["wait_reason"] = f"Switched to goal {goal_id}"
                save_state(current_dir, current)
    atomic_json_write(active_file(root), {"goal_id": goal_id, "updated_at": now()})


def list_goals(root: Path) -> list[dict[str, Any]]:
    store = goal_store(root)
    result: list[dict[str, Any]] = []
    if not store.exists():
        return result
    current = active_goal_id(root)
    for directory in sorted(store.iterdir()):
        path = directory / "state.json"
        if not directory.is_dir() or not path.exists():
            continue
        state = load_json(path)
        result.append({
            "goal_id": state.get("goal_id", directory.name),
            "title": state.get("title"),
            "status": state.get("status"),
            "active": state.get("goal_id", directory.name) == current,
            "updated_at": state.get("updated_at"),
            "resolved_harness": state.get("resolved_harness") or resolve_harness(state),
        })
    return result


def is_lightweight_standard(state: dict[str, Any]) -> bool:
    """Return whether the goal uses the day-to-day Standard path."""
    return (
        resolve_harness(state) == "standard"
    )


def standard_auto_completion_allowed(state: dict[str, Any]) -> bool:
    """Only silently complete low-risk, non-public-behavior Standard work."""
    return (
        is_lightweight_standard(state)
        and not state.get("harness", {}).get("behavior_change")
        and not visual_design_enabled(state)
        and state.get("harness", {}).get("risk_level") in {"unspecified", "low"}
    )


def compact_harness(state: dict[str, Any]) -> dict[str, Any]:
    """Expose only resolved harness facts in user-facing summaries."""
    harness = state.get("harness", {})
    result = {
        key: harness.get(key)
        for key in ("mode", "task_type", "risk_level", "behavior_change", "visual_design")
        if key in harness
    }
    result["resolved_harness"] = state.get("resolved_harness") or resolve_harness(state)
    return result


def product_worktree_fingerprint(root: Path) -> str:
    """Hash product changes, excluding Goal Flow's own audit files."""
    digest = hashlib.sha256()
    status = product_status(root) or ""
    digest.update(status.encode("utf-8"))
    digest.update(b"\0")
    pathspec = [".", ":(exclude).goal-flow", ":(exclude).goal-flow/**"]
    for prefix, command in (("unstaged", ["diff"]), ("staged", ["diff", "--cached"])):
        result = subprocess.run(
            ["git", *command, "--binary", "--", *pathspec],
            cwd=root,
            text=False,
            capture_output=True,
            check=False,
        )
        digest.update(prefix.encode("ascii"))
        digest.update(b"\0")
        digest.update(result.stdout)
        digest.update(b"\0")
    untracked = run_git(root, "ls-files", "--others", "--exclude-standard") or ""
    for relative in sorted(
        path for path in untracked.splitlines()
        if path != ".goal-flow" and not path.startswith(".goal-flow/")
    ):
        path = root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


def product_tree_is_acceptable(root: Path, state: dict[str, Any]) -> bool:
    """Allow Standard's pre-existing dirty baseline, but detect new drift."""
    if not is_lightweight_standard(state):
        return product_tree_is_clean(root)
    baseline = state.get("harness", {}).get("baseline_product_fingerprint")
    if not baseline:
        return product_tree_is_clean(root)
    return product_worktree_fingerprint(root) == baseline or product_tree_is_clean(root)


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
                "minimum_evidence_mode": value.get("minimum_evidence_mode"),
            }
            for key, value in sorted(state.get("requirements", {}).items())
        },
        "checks": {
            key: {
                "required": bool(value.get("required")),
                "command": value.get("command"),
                "timeout": value.get("timeout"),
                "role": value.get("role"),
                "evidence_mode": value.get("evidence_mode"),
                "covers": sorted(value.get("covers") or []),
                "proves": value.get("proves"),
                "limitations": value.get("limitations"),
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
        harness = dict(state.get("harness", {}) or {})
        # Contract v3 did not include the visual_design default.  Do not let
        # load-time normalization change the identity of an already-approved
        # v3 contract.  New goals use v4 and include the complete harness.
        if int(state.get("contract_version", 1)) < 4:
            harness.pop("visual_design", None)
        definitions["harness"] = harness
        definitions["resolved_harness"] = state.get("resolved_harness") or resolve_harness(state)
        definitions["decision_check"] = state.get("decision_check", {})
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


def current_worktree_identity(root: Path) -> dict[str, Any]:
    top = run_git(root, "rev-parse", "--show-toplevel")
    git_dir = run_git(root, "rev-parse", "--absolute-git-dir")
    branch = current_branch(root)
    if not top or not git_dir:
        raise GoalFlowError("Worktree binding requires a Git worktree")
    if not branch:
        raise GoalFlowError("Worktree binding requires a named branch; detached HEAD is not supported")
    worktrees = run_git(root, "worktree", "list", "--porcelain") or ""
    primary = None
    for line in worktrees.splitlines():
        if line.startswith("worktree "):
            primary = str(Path(line.split(" ", 1)[1]).resolve())
            break
    resolved_root = str(Path(top).resolve())
    return {
        "root": resolved_root,
        "git_dir": str(Path(git_dir).resolve()),
        "branch": branch,
        "is_primary_worktree": resolved_root == primary,
    }


def enforce_isolation_policy(
    root: Path, state: dict[str, Any], binding: dict[str, Any] | None = None
) -> None:
    """Full/strict Harnesses may not silently run on a normal primary branch."""
    if resolve_harness(state) not in {"goal-flow", "strict"}:
        return
    binding = binding or state.get("worktree_binding") or {}
    mode = binding.get("isolation_mode")
    if mode == "explicit_current_worktree":
        if not binding.get("override_reason"):
            raise GoalFlowError("Current-worktree exceptions require an audit reason")
        return
    branch = str(binding.get("branch") or "")
    if branch.startswith("codex/goal-flow-"):
        return
    if binding.get("is_primary_worktree") is False:
        return
    raise GoalFlowError(
        "Full/strict goals require a codex/goal-flow-* branch or an independent Git worktree; "
        "use --allow-current-worktree --reason only for an explicit exception"
    )


def require_bound_worktree(root: Path, state: dict[str, Any]) -> None:
    if not state.get("approved"):
        return
    if is_lightweight_standard(state):
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
    enforce_isolation_policy(root, state, binding)


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


def product_status_paths(root: Path) -> list[str]:
    status = product_status(root)
    if status is None:
        return []
    paths: list[str] = []
    for line in status.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            paths.append(path)
    return sorted(set(paths))


def evidence_freshness(
    root: Path,
    evidence_sha: str | None,
    state: dict[str, Any] | None = None,
    product_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Explain whether a receipt still describes the current product tree."""
    result = {
        "fresh": False,
        "reason": None,
        "invalidated_paths": [],
        "evidence_sha": evidence_sha,
    }
    if not evidence_sha or evidence_sha == "UNBORN":
        result["reason"] = "missing evidence commit"
        return result
    if state is None:
        clean = product_tree_is_clean(root)
    else:
        clean = product_tree_is_acceptable(root, state)
    if not clean:
        result["reason"] = "uncommitted product changes invalidate evidence"
        result["invalidated_paths"] = product_status_paths(root)
        return result
    if product_fingerprint:
        current_fingerprint = product_worktree_fingerprint(root)
        if current_fingerprint != product_fingerprint:
            result["reason"] = "product tree fingerprint changed after verification"
            result["invalidated_paths"] = product_status_paths(root)
            result["product_fingerprint"] = current_fingerprint
            return result
        result["product_fingerprint"] = current_fingerprint
    if run_git(root, "merge-base", "--is-ancestor", evidence_sha, "HEAD") is None:
        result["reason"] = "evidence commit is not an ancestor of HEAD"
        return result
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
    changed_paths = sorted(path for path in (changed or "").splitlines() if path)
    if changed_paths:
        result["reason"] = "committed product changes occurred after verification"
        result["invalidated_paths"] = changed_paths
        return result
    result["fresh"] = True
    result["reason"] = "evidence matches the current product tree"
    return result


def evidence_is_fresh(
    root: Path,
    evidence_sha: str | None,
    state: dict[str, Any] | None = None,
    product_fingerprint: str | None = None,
) -> bool:
    return bool(evidence_freshness(root, evidence_sha, state, product_fingerprint)["fresh"])


def evidence_mode_satisfies(actual: str | None, minimum: str | None) -> bool:
    return (
        actual in EVIDENCE_MODE_ORDER
        and minimum in EVIDENCE_MODE_ORDER
        and EVIDENCE_MODE_ORDER[actual] >= EVIDENCE_MODE_ORDER[minimum]
    )


def evidence_is_fresh_after_rejection(item: dict[str, Any], baseline: dict[str, Any] | None) -> bool:
    """Rejecting delivery creates a new evidence epoch; old receipts cannot reopen Gate."""
    if not baseline:
        return True
    try:
        rejected_ns = int(baseline.get("rejected_at_ns") or 0)
        updated_ns = int(item.get("updated_at_ns") or 0)
    except (TypeError, ValueError):
        rejected_ns = 0
        updated_ns = 0
    if rejected_ns and updated_ns:
        time_is_new = updated_ns > rejected_ns
    else:
        rejected_at = str(baseline.get("rejected_at") or "")
        updated_at = str(item.get("updated_at") or "")
        time_is_new = bool(updated_at and rejected_at and updated_at > rejected_at)
    receipt_id = item.get("receipt_id")
    old_receipts = set(baseline.get("receipt_ids") or [])
    return bool(time_is_new and receipt_id not in old_receipts)


def verifiers_are_fresh(root: Path, state: dict[str, Any], check_ids: list[str]) -> bool:
    return bool(check_ids) and all(
        check_id in state.get("checks", {})
        and state["checks"][check_id].get("status") == "PASS"
        and evidence_is_fresh(
            root,
            state["checks"][check_id].get("git_sha"),
            state,
            state["checks"][check_id].get("product_fingerprint"),
        )
        for check_id in check_ids
    )


def risk_is_unresolved(root: Path, state: dict[str, Any], risk: dict[str, Any]) -> bool:
    if risk.get("status") in {"OPEN", "PARTIALLY_MITIGATED"}:
        return True
    if risk.get("status") == "MITIGATED":
        return not verifiers_are_fresh(root, state, risk.get("verified_by") or [])
    return False


def delivery_freshness(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for req_id, item in state.get("requirements", {}).items():
        if item.get("kind") == "must" and item.get("status") == "VERIFIED":
            items.append({"id": req_id, **evidence_freshness(
                root, item.get("git_sha"), state, item.get("product_fingerprint")
            )})
    for check_id, item in state.get("checks", {}).items():
        if item.get("required") and item.get("status") == "PASS":
            items.append({"id": check_id, **evidence_freshness(
                root, item.get("git_sha"), state, item.get("product_fingerprint")
            )})
    stale = [item for item in items if not item["fresh"]]
    invalidated_paths = sorted({path for item in stale for path in item["invalidated_paths"]})
    if not items:
        reason = "no completed delivery evidence"
    elif stale:
        reason = "; ".join(sorted({str(item["reason"]) for item in stale}))
    else:
        reason = "all completed delivery evidence matches the current product tree"
    return {
        "fresh": bool(items) and not stale,
        "reason": reason,
        "invalidated_paths": invalidated_paths,
        "evidence_sha": state.get("last_verified_commit"),
    }


def effective_status(root: Path, state: dict[str, Any]) -> str:
    stored = str(state.get("status"))
    if stored == "READY_FOR_ACCEPTANCE" and not delivery_freshness(root, state)["fresh"]:
        return "VERIFYING"
    return stored


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
    if state.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
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
    decision_check = state.get("decision_check") or {}
    if decision_check.get("status") not in {"none", "resolved", "pending"}:
        errors.append("invalid decision_check status")
    if not isinstance(decision_check.get("user_decisions", []), list):
        errors.append("decision_check user_decisions must be a list")
    binding = state.get("worktree_binding")
    if binding:
        if binding.get("isolation_mode") not in {"isolated_branch", "isolated_worktree", "explicit_current_worktree"}:
            errors.append("invalid worktree isolation_mode")
        if binding.get("isolation_mode") == "explicit_current_worktree" and not binding.get("override_reason"):
            errors.append("current-worktree exception needs override_reason")
    for req_id, item in state.get("requirements", {}).items():
        if item.get("status") not in REQUIREMENT_STATUSES:
            errors.append(f"invalid requirement status for {req_id}")
        if item.get("kind") not in {"must", "should"}:
            errors.append(f"invalid requirement kind for {req_id}")
        if item.get("minimum_evidence_mode") not in EVIDENCE_MODES:
            errors.append(f"invalid minimum evidence mode for {req_id}")
    for check_id, item in state.get("checks", {}).items():
        if item.get("status") not in CHECK_STATUSES:
            errors.append(f"invalid check status for {check_id}")
        if item.get("role") not in CHECK_ROLES:
            errors.append(f"invalid check role for {check_id}")
        if item.get("evidence_mode") not in EVIDENCE_MODES:
            errors.append(f"invalid check evidence mode for {check_id}")
        if not isinstance(item.get("covers"), list):
            errors.append(f"invalid check requirement coverage for {check_id}")
    for risk_id, item in state.get("risks", {}).items():
        if item.get("status") not in RISK_STATUSES:
            errors.append(f"invalid risk status for {risk_id}")
        if item.get("severity") not in RISK_SEVERITIES:
            errors.append(f"invalid risk severity for {risk_id}")
        if item.get("minimum_evidence_mode") not in EVIDENCE_MODES:
            errors.append(f"invalid risk minimum evidence mode for {risk_id}")
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


def has_open_user_questions(text: str) -> bool:
    patterns = (
        r"^##\s+Questions requiring user decision\s*$([\s\S]*?)(?=^##\s+|\Z)",
        r"^##\s+仍需用户决定\s*$([\s\S]*?)(?=^##\s+|\Z)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        for line in match.group(1).splitlines():
            value = line.strip().lstrip("- *").strip()
            if not value or value.lower() in {"none", "none after repository inspection.", "no unresolved questions.", "无", "无待决定"}:
                continue
            if substantive(value):
                return True
    return False


def decision_check_from_goal(text: str, state: dict[str, Any]) -> dict[str, Any]:
    """Read the small, human-editable Decision Check block with legacy fallback."""
    current = state.get("decision_check") or {}
    result = {
        "auto_decided": list(current.get("auto_decided") or []),
        "recommended_defaults": list(current.get("recommended_defaults") or []),
        "user_decisions": list(current.get("user_decisions") or []),
        "status": current.get("status") or "none",
    }
    match = re.search(
        r"^##\s+(?:Decision Check|决策检查)\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if match:
        section = match.group(1)
        labels = {
            "auto-decided": "auto_decided",
            "recommended defaults": "recommended_defaults",
            "user decisions": "user_decisions",
            "已自动确定": "auto_decided",
            "建议默认": "recommended_defaults",
            "仍需用户决定": "user_decisions",
        }
        for label, key in labels.items():
            found = re.search(rf"^[-*]?\s*{re.escape(label)}\s*[:：]\s*(.+)$", section, re.IGNORECASE | re.MULTILINE)
            if found:
                value = found.group(1).strip()
                result[key] = [] if value.lower() in {"none", "无", "none after repository inspection."} else [value]
        status = re.search(r"^[-*]?\s*(?:status|状态)\s*[:：]\s*(.+)$", section, re.IGNORECASE | re.MULTILINE)
        if status:
            normalized = status.group(1).strip().lower()
            result["status"] = "resolved" if normalized in {"resolved", "ready", "已解决", "无待决定", "已解决"} else "pending"
    chinese_section = re.search(
        r"^##\s+仍需用户决定\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    if chinese_section and not result["user_decisions"]:
        questions = [
            line.strip().lstrip("- *").strip()
            for line in chinese_section.group(1).splitlines()
            if line.strip().lstrip("- *").strip()
        ]
        result["user_decisions"] = [item for item in questions if substantive(item)]
        if result["user_decisions"]:
            result["status"] = "pending"
    if not result["user_decisions"] and has_open_user_questions(text):
        result["user_decisions"] = ["Questions requiring user decision contains unresolved items"]
        result["status"] = "pending"
    elif result["status"] == "none":
        result["status"] = "resolved"
        if not result["auto_decided"]:
            result["auto_decided"] = ["No high-impact decision remains after repository inspection"]
    return result


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

    decision_check = decision_check_from_goal(goal_text, state)
    if decision_check.get("user_decisions") or decision_check.get("status") == "pending":
        reasons.append("Resolve every item in the Decision Check before approval")

    visual_check = None
    if visual_design_enabled(state):
        visual_check = visual_design_check(directory, state)
        reasons.extend(f"Visual design: {reason}" for reason in visual_check["reasons"])
        if visual_check.get("ok") and not visual_check.get("viewer_fresh"):
            reasons.append(f"Visual design: {visual_check.get('viewer_reason')}")

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
        if check.get("role") not in CHECK_ROLES:
            reasons.append(f"Required check {check_id} must declare --role")
        if check.get("evidence_mode") not in EVIDENCE_MODES:
            reasons.append(f"Required check {check_id} must declare --evidence-mode")
        if not substantive(check.get("proves")):
            reasons.append(f"Required check {check_id} must state what it proves")
        if not substantive(check.get("limitations")):
            reasons.append(f"Required check {check_id} must state its limitations")

    needs_goal_check = (
        resolve_harness(state) in {"goal-flow", "strict"}
        or bool(state.get("harness", {}).get("behavior_change"))
        or visual_design_enabled(state)
    )
    valid_goal_checks = [
        check for check in required_checks.values()
        if check.get("role") == "goal"
        and check.get("evidence_mode") == "real"
        and any(req_id in must for req_id in (check.get("covers") or []))
    ]
    if needs_goal_check and not valid_goal_checks:
        reasons.append("Register at least one required goal check covering the real user main path")
    for check_id, check in required_checks.items():
        unknown = [req_id for req_id in (check.get("covers") or []) if req_id not in requirements]
        if unknown:
            reasons.append(f"Required check {check_id} covers unknown requirements: {', '.join(unknown)}")

    lightweight_standard = is_lightweight_standard(state)
    for req_id, criterion in must.items():
        if not substantive(criterion.get("statement")):
            reasons.append(f"MUST criterion {req_id} lacks an observable outcome")
        covering = [
            check_id for check_id, check in required_checks.items()
            if req_id in (check.get("covers") or [])
        ]
        if not covering:
            reasons.append(f"MUST criterion {req_id} has no required check declaring coverage")
        minimum_mode = criterion.get("minimum_evidence_mode")
        if minimum_mode not in EVIDENCE_MODES:
            reasons.append(f"MUST criterion {req_id} must declare --minimum-evidence-mode")
        elif minimum_mode == "real" and covering and not any(
            evidence_mode_satisfies(required_checks[check_id].get("evidence_mode"), minimum_mode)
            for check_id in covering
        ):
            reasons.append(
                f"MUST criterion {req_id} requires {minimum_mode} evidence but linked checks are weaker"
            )
        if lightweight_standard:
            verifiers = criterion.get("verified_by") or []
            if not verifiers:
                reasons.append(f"MUST criterion {req_id} has no --verified-by check")
            invalid = [check_id for check_id in verifiers if check_id not in required_checks]
            if invalid:
                reasons.append(
                    f"MUST criterion {req_id} references non-required checks: {', '.join(invalid)}"
                )
            for value in (req_id, criterion.get("statement")):
                if value and str(value) not in goal_text:
                    reasons.append(f"MUST criterion {req_id} detail is not visible in goal.md: {value}")
            continue
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
    harness_mode = state.get("harness", {}).get("mode", "goal-flow")
    required_dimensions = (
        ACCEPTANCE_DIMENSIONS if profile == "strict" else STANDARD_DIMENSIONS
    )
    if profile != "strict" and harness_mode == "standard":
        required_dimensions = LIGHTWEIGHT_STANDARD_DIMENSIONS
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
        "harness": compact_harness(state),
        "decision_check": decision_check,
        "visual_design": visual_check,
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
    visual_digest = None
    if visual_design_enabled(state):
        drawing = visual_design_path(directory)
        try:
            visual_digest = visual_design_semantic_hash(drawing)
        except GoalFlowError:
            visual_digest = "INVALID:" + (file_hash(drawing) if drawing.exists() else "MISSING")
    if len(paths) == 1 and visual_digest is None:
        return file_hash(paths[0]) if paths[0].exists() else ""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.name).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash(path).encode("ascii") if path.exists() else b"MISSING")
        digest.update(b"\0")
    if visual_digest is not None:
        digest.update(b"architecture.drawio\0")
        digest.update(visual_digest.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def assurance_payload(root: Path, state: dict[str, Any], current_sha: str) -> dict[str, Any]:
    requirements = state.get("requirements", {})
    must = [item for item in requirements.values() if item.get("kind") == "must"]
    verified = [item for item in must if item.get("status") == "VERIFIED"]
    fresh = [item for item in verified if evidence_is_fresh(
        root, item.get("git_sha"), state, item.get("product_fingerprint")
    )]
    required_checks = [item for item in state.get("checks", {}).values() if item.get("required")]
    passing_checks = [
        item for item in required_checks
        if item.get("status") == "PASS" and evidence_is_fresh(
            root, item.get("git_sha"), state, item.get("product_fingerprint")
        )
    ]
    required_goal_checks = [item for item in required_checks if item.get("role") == "goal"]
    passing_goal_checks = [
        item for item in required_goal_checks
        if item.get("status") == "PASS" and evidence_is_fresh(
            root, item.get("git_sha"), state, item.get("product_fingerprint")
        )
    ]
    evidence_downgrades = [
        item for item in must
        if item.get("status") == "VERIFIED" and not any(
            check_id in state.get("checks", {})
            and state["checks"][check_id].get("status") == "PASS"
            and evidence_mode_satisfies(
                state["checks"][check_id].get("evidence_mode"), item.get("minimum_evidence_mode")
            )
            for check_id in (item.get("verified_by") or [])
        )
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
    residual_medium_or_low = [
        item for item in state.get("risks", {}).values()
        if risk_is_unresolved(root, state, item) and item.get("severity") in {"low", "medium"}
    ]
    goal_check_required = (
        resolve_harness(state) in {"goal-flow", "strict"}
        or bool(state.get("harness", {}).get("behavior_change"))
    )
    goal_check_ok = not goal_check_required or bool(required_goal_checks) and len(passing_goal_checks) == len(required_goal_checks)
    if (
        coverage == 100
        and check_coverage == 100
        and not unresolved_risks
        and not accepted_serious
        and not contradicted
        and not failed_optional
        and not evidence_downgrades
        and goal_check_ok
    ):
        band = "HIGH"
    elif coverage == 100 and check_coverage == 100 and not unresolved_serious and goal_check_ok:
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
        "goal_check_passed": goal_check_ok,
        "evidence_downgrades": len(evidence_downgrades),
        "residual_medium_or_low_risks": len(residual_medium_or_low),
    }


def evaluate_gate(root: Path, directory: Path, state: dict[str, Any]) -> dict[str, Any]:
    errors = validate_state(state)
    sha = current_git_sha(root)
    metrics = assurance_payload(root, state, sha)
    freshness = delivery_freshness(root, state)
    stored_status = state.get("status")
    shown_status = effective_status(root, state)
    result: dict[str, Any] = {
        "gate": "WAIT",
        "status": shown_status,
        "stored_status": stored_status,
        "effective_status": shown_status,
        "freshness": freshness,
        "invalidated_paths": freshness["invalidated_paths"],
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
        if value.get("status") != "VERIFIED"
        or not evidence_is_fresh(root, value.get("git_sha"), state, value.get("product_fingerprint"))
        or not evidence_is_fresh_after_rejection(value, state.get("delivery_rejection_baseline"))
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
        if value.get("status") != "PASS"
        or not evidence_is_fresh(root, value.get("git_sha"), state, value.get("product_fingerprint"))
        or not evidence_is_fresh_after_rejection(value, state.get("delivery_rejection_baseline"))
    ]
    serious_risks = [
        key for key, value in state.get("risks", {}).items()
        if risk_is_unresolved(root, state, value)
        and value.get("severity") in {"high", "critical"}
    ]
    weak_requirements = [
        key for key, value in must.items()
        if value.get("status") == "VERIFIED"
        and value.get("minimum_evidence_mode") == "real"
        and not any(
            check_id in checks
            and checks[check_id].get("status") == "PASS"
            and evidence_mode_satisfies(
                checks[check_id].get("evidence_mode"), value.get("minimum_evidence_mode")
            )
            for check_id in (value.get("verified_by") or [])
        )
    ]
    if weak_requirements:
        incomplete = sorted(set(incomplete + weak_requirements))
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
    if args.mode == "micro":
        raise GoalFlowError("Micro tasks do not initialize Goal Flow; use the lightweight plan and direct verification path")
    active_id = active_goal_id(root)
    if active_id and active_id != goal_id:
        active_directory = goal_dir(root, active_id)
        active_state_path = active_directory / "state.json"
        if not active_state_path.exists():
            raise GoalFlowError(
                f"Active goal {active_id!r} has no state.json; repair or clear active.json before starting another goal"
            )
        active_state = load_json(active_state_path)
        active_status = active_state.get("status")
        if active_status not in {"ACCEPTED", "CANCELLED"}:
            if not args.switch_active:
                raise GoalFlowError(
                    f"Active goal {active_id!r} is {active_status}; pause/cancel it or pass --switch to make {goal_id!r} active"
                )
            active_state["resume_status"] = active_status
            active_state["status"] = "PAUSED"
            active_state["wait_reason"] = f"Switched to new goal {goal_id}"
            save_state(active_directory, active_state)
    baseline_product_fingerprint = product_worktree_fingerprint(root)
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
        default_mode=args.mode,
    )
    # ``init`` creates a persistent Goal Flow record; keep it at least
    # Standard even when auto-classification says a one-line task could use
    # the direct micro path.
    if args.mode == "auto" and classification["mode"] == "micro":
        classification["mode"] = "standard"
        classification["resolved_harness"] = "standard"
        classification["harness"]["plan"] = "lightweight"
        classification["harness"]["approval"] = "conditional"
        classification["harness"]["resume"] = False
        classification["reasons"].append("persistent goals use at least the Standard harness")
    profile = "strict" if args.profile == "standard" and classification["profile"] == "strict" else args.profile
    mode = classification["mode"]
    required_dimensions = (
        dimension_order
        if profile == "strict"
        else [
            item for item in dimension_order
            if item in (STANDARD_DIMENSIONS if mode == "goal-flow" else LIGHTWEIGHT_STANDARD_DIMENSIONS)
        ]
    )
    dimension_table = "\n".join(f"| {item} | TBD | TBD | TBD |" for item in required_dimensions)
    goal_text = f"""# {args.title}\n\n## Outcome\n\n{args.goal}\n\n## Non-goals\n\n- To be defined during planning.\n\n## Context and sources\n\n- Repository and domain context to be investigated.\n\n## Assumptions and decisions\n\n- Profile: {args.profile}.\n- Infer from repository and domain evidence before asking the user.\n\n## Questions requiring user decision\n\n- Only unresolved, high-impact choices belong here.\n\n## Approved design\n\nPending user discussion and approval.\n\n## Acceptance dimensions\n\n| Dimension | COVERED or N_A | Rationale | Criterion IDs |\n| --- | --- | --- | --- |\n{dimension_table}\n\n## Acceptance criteria\n\n| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |\n| --- | --- | --- | --- | --- | --- | --- |\n| REQ-001 | MUST | Define during planning | Define during planning | Define during planning | Define during planning | Define during planning |\n\n## Milestones\n\n1. Complete the decision-ready design and acceptance contract.\n\n## Risks, migration, and rollback\n\n- To be defined during planning.\n\n## Approval\n\nApproval state is stored only in state.json.\n"""
    goal_text = goal_text.replace(
        "## Questions requiring user decision\\n\\n",
        "## Decision Check\\n\\n"
        "- Status: RESOLVED\\n"
        "- Auto-decided: No high-impact decision remains after repository inspection.\\n"
        "- Recommended defaults: Preserve repository conventions and existing compatibility.\\n"
        "- User decisions: None\\n\\n"
        "## Questions requiring user decision\\n\\n",
        1,
    )
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
    if args.visual_design:
        goal_text = goal_text.replace(
            "## Approved design\n\nPending user discussion and approval.",
            "## Approved design\n\n"
            "Pending user discussion and approval. The semantic content in "
            "`design/architecture.drawio` is part of this contract; "
            "`design/architecture.html` is its generated viewer.",
            1,
        )
    (directory / "goal.md").write_text(goal_text, encoding="utf-8")
    (directory / "evidence.md").write_text(f"# Evidence — {args.title}\n", encoding="utf-8")
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
        "resolved_harness": classification["resolved_harness"],
        "harness": {
            "mode": mode,
            "requested_mode": args.mode,
            "task_type": args.task_type,
            "risk_level": args.risk_level,
            "behavior_change": behavior_change,
            "visual_design": bool(args.visual_design),
            "baseline_product_fingerprint": baseline_product_fingerprint,
            "baseline_git_sha": current_git_sha(root),
            "classification_reasons": classification["reasons"],
        },
        "contract_version": 4,
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
        "delivery_attempt": 0,
        "delivery_feedback": None,
        "delivery_rejection_baseline": None,
        "epoch": None,
        "resume_status": None,
        "decision_check": {
            "auto_decided": [],
            "recommended_defaults": [],
            "user_decisions": [],
            "status": "none",
        },
        "created_at": now(),
        "updated_at": now(),
    }
    if args.visual_design:
        initialize_visual_design(directory, args.title)
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
    freshness = delivery_freshness(root, state)
    gate = evaluate_gate(root, directory, state)
    payload = {
        "ok": not validate_state(state),
        "active": True,
        "goal_id": goal_id,
        "goal_dir": str(directory),
        "git_sha": current_git_sha(root),
        "design_drift": design_drift(directory, state),
        "validation_errors": validate_state(state),
        "stored_status": state.get("status"),
        "effective_status": effective_status(root, state),
        "status": effective_status(root, state),
        "phase": phase_for_state(state),
        "design_hash": design_hash(goal_dir(root, goal_id), state),
        "definitions_hash": definitions_hash(state),
        "gate": gate.get("gate"),
        "freshness": freshness,
        "invalidated_paths": freshness["invalidated_paths"],
        "state": state,
    }
    if not state.get("approved"):
        payload["plan"] = plan_readiness(directory, state)
    return payload


def cmd_design_check(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if not visual_design_enabled(state):
        raise GoalFlowError("This goal was not initialized with --visual-design")
    result = visual_design_check(directory, state)
    return {
        **result,
        "phase": phase_for_state(state),
        "message": "Visual design is ready" if result["ok"] else "Visual design needs revision",
    }


def cmd_design_render(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if not visual_design_enabled(state):
        raise GoalFlowError("This goal was not initialized with --visual-design")
    output = render_visual_viewer(directory, state.get("title") or state["goal_id"])
    return {
        "ok": True,
        "message": "Visual design viewer regenerated",
        "source": str(visual_design_path(directory)),
        "viewer": str(output),
        "phase": phase_for_state(state),
    }


def cmd_goals(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goals = list_goals(root)
    return {
        "ok": True,
        "active_goal_id": active_goal_id(root) or None,
        "goals": goals,
        "count": len(goals),
    }


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
    lifecycle_commands = {
        "init", "approve", "verify", "replan", "pause", "resume",
        "block", "cancel", "gate", "accept", "reject",
    }
    if args.command not in lifecycle_commands:
        return
    if args.command == "gate" and not payload.get("state_changed"):
        return
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
        and evidence_is_fresh(root, item.get("git_sha"), state, item.get("product_fingerprint"))
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
    freshness = delivery_freshness(root, state)
    gate = evaluate_gate(root, goal_dir(root, goal_id), state)
    payload = {
        "ok": not validate_state(state),
        "active": True,
        "goal_id": goal_id,
        "title": state.get("title") or goal_id,
        "profile": state.get("profile", "strict"),
        "harness": compact_harness(state),
        "context_excerpt": context_excerpt(root),
        "status": effective_status(root, state),
        "stored_status": state.get("status"),
        "effective_status": effective_status(root, state),
        "phase": phase_for_state(state),
        "design_hash": design_hash(goal_dir(root, goal_id), state),
        "definitions_hash": definitions_hash(state),
        "gate": gate.get("gate"),
        "freshness": freshness,
        "invalidated_paths": freshness["invalidated_paths"],
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
        f"Status: {payload['status']} (stored: {payload['stored_status']})",
        f"Phase: {payload['phase']}",
        f"Gate: {payload['gate']}",
        f"Progress: {payload['must_verified']}/{payload['must_total']} MUST verified",
        f"Milestone: {payload['milestone'] or '-'}",
    ]
    if blocker:
        lines.append(f"Blocked by: {blocker}")
    elif recent_failure:
        lines.append(f"Recent failure: {recent_failure}")
    if payload["invalidated_paths"]:
        lines.append(f"Invalidated by: {', '.join(payload['invalidated_paths'])}")
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
            "freshness": evidence_freshness(
                root, item.get("git_sha"), state, item.get("product_fingerprint")
            ),
            "minimum_evidence_mode": item.get("minimum_evidence_mode"),
        }
        for requirement_id, item in sorted(state.get("requirements", {}).items())
    ]
    checks = [
        {
            "id": check_id,
            "required": bool(item.get("required")),
            "status": item.get("status"),
            "fresh": evidence_is_fresh(root, item.get("git_sha"), state, item.get("product_fingerprint")),
            "duration_ms": item.get("duration_ms"),
            "timed_out": bool(item.get("timed_out")),
            "termination": item.get("termination"),
            "git_sha": item.get("git_sha"),
            "role": item.get("role"),
            "evidence_mode": item.get("evidence_mode"),
            "covers": item.get("covers") or [],
            "proves": item.get("proves"),
            "limitations": item.get("limitations"),
        }
        for check_id, item in sorted(state.get("checks", {}).items())
    ]
    risks = [
        {
            "id": risk_id,
            "status": item.get("status"),
            "severity": item.get("severity"),
            "residual_risk": item.get("residual_risk"),
        }
        for risk_id, item in sorted(state.get("risks", {}).items())
    ]
    attempts = sum(item.get("event") == "verify" for item in events)
    failures = sum(
        item.get("event") == "verify" and item.get("result") == "FAIL"
        for item in events
    )
    rejections = sum(item.get("event") == "reject" for item in events)
    verification_runtime_ms = sum(
        int(item.get("duration_ms") or 0) for item in events if item.get("event") == "verify"
    )
    created_at = state.get("created_at")
    try:
        wall_time_seconds = max(
            0,
            round((datetime.now(timezone.utc) - datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))).total_seconds()),
        )
    except (TypeError, ValueError):
        wall_time_seconds = None
    freshness = delivery_freshness(root, state)
    requirement_map = state.get("requirements", {})
    check_map = state.get("checks", {})
    def declared_evidence_met(requirement_id: str) -> bool:
        item = requirement_map[requirement_id]
        return any(
            check_id in check_map
            and evidence_mode_satisfies(
                check_map[check_id].get("evidence_mode"), item.get("minimum_evidence_mode")
            )
            for check_id in (item.get("verified_by") or [])
        )
    proved = [
        item["id"] for item in requirements
        if item["status"] == "VERIFIED" and item["freshness"]["fresh"] and declared_evidence_met(item["id"])
    ]
    partially_proved = [
        item["id"] for item in requirements
        if item["status"] == "PARTIAL"
        or item["status"] == "VERIFIED" and item["freshness"]["fresh"] and not declared_evidence_met(item["id"])
    ]
    not_proved = [item["id"] for item in requirements if item["id"] not in proved + partially_proved]
    residual_risks = [item for item in risks if item["status"] != "MITIGATED"]
    payload = {
        "ok": not validate_state(state),
        "active": active_goal_id(root) == goal_id if active_file(root).exists() else False,
        "goal_id": goal_id,
        "title": state.get("title") or goal_id,
        "profile": state.get("profile", "strict"),
        "status": effective_status(root, state),
        "stored_status": state.get("status"),
        "effective_status": effective_status(root, state),
        "phase": phase_for_state(state),
        "gate": evaluate_gate(root, directory, state).get("gate"),
        "freshness": freshness,
        "invalidated_paths": freshness["invalidated_paths"],
        "git_sha": sha,
        "milestone": state.get("current_milestone"),
        "assurance": metrics,
        "attempts": attempts,
        "failures": failures,
        "rejections": rejections,
        "wall_time_seconds": wall_time_seconds,
        "verification_runtime_ms": verification_runtime_ms,
        "proved": proved,
        "partially_proved": partially_proved,
        "not_proved": not_proved,
        "residual_risks": residual_risks,
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
        f"- Status: {payload['status']} (stored: {payload['stored_status']})",
        f"- Phase: {payload['phase']}",
        f"- Gate: {payload['gate']}",
        f"- Git: {sha}",
        f"- Milestone: {payload['milestone'] or '-'}",
        "",
        "## Coverage",
        "",
        f"- MUST requirements: {metrics['must_verified_on_current_sha']}/{metrics['must_total']}",
        f"- Required checks: {metrics['required_check_coverage']}%",
        f"- Verification attempts/failures/rejections: {attempts}/{failures}/{rejections}",
        f"- Wall time / verification runtime: {wall_time_seconds if wall_time_seconds is not None else '-'}s / {verification_runtime_ms}ms",
        f"- Open risks: {metrics['open_risks']} ({metrics['open_high_or_critical_risks']} high/critical)",
        f"- Assurance: {metrics['assurance']} ({metrics['confidence']})",
        "",
        "## Delivery conclusion",
        "",
        f"- Proved: {', '.join(proved) or 'none'}",
        f"- Partially proved: {', '.join(partially_proved) or 'none'}",
        f"- Not proved: {', '.join(not_proved) or 'none'}",
        f"- Residual risks: {', '.join(item['id'] for item in residual_risks) or 'none'}",
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
    if is_lightweight_standard(state):
        return {"ok": True, "skipped": True, "message": "Standard Harness uses the current worktree", "state": state}
    if not state.get("approved"):
        raise GoalFlowError("Approve the design before binding its implementation worktree")
    if not product_tree_is_clean(root):
        raise GoalFlowError("Commit or clean product-tree changes before binding the worktree")
    binding = current_worktree_identity(root)
    if args.allow_current_worktree:
        if not args.reason or not args.reason.strip():
            raise GoalFlowError("--allow-current-worktree requires a non-empty --reason")
        binding["isolation_mode"] = "explicit_current_worktree"
        binding["override_reason"] = args.reason.strip()
    else:
        if (
            resolve_harness(state) in {"goal-flow", "strict"}
            and binding.get("is_primary_worktree") is not False
            and not str(binding.get("branch", "")).startswith("codex/goal-flow-")
        ):
            isolated_branch = f"codex/goal-flow-{state['goal_id']}"
            if run_git(root, "show-ref", "--verify", f"refs/heads/{isolated_branch}"):
                raise GoalFlowError(
                    f"普通分支不能直接绑定；隔离分支 {isolated_branch!r} 已存在，请切换到它或使用独立 worktree"
                )
            switched = subprocess.run(
                ["git", "switch", "-c", isolated_branch],
                cwd=root, text=True, capture_output=True, check=False,
            )
            if switched.returncode != 0:
                raise GoalFlowError(f"无法自动创建隔离分支 {isolated_branch}: {(switched.stderr or '').strip()}")
            binding = current_worktree_identity(root)
        binding["isolation_mode"] = (
            "isolated_worktree"
            if binding.get("is_primary_worktree") is False
            else "isolated_branch"
        )
        enforce_isolation_policy(root, state, binding)
    state["worktree_binding"] = binding
    state["branch"] = binding["branch"]
    save_state(directory, state)
    return {"ok": True, "message": "Worktree bound", "binding": binding, "state": state}


def cmd_approve(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    expected_revision = getattr(args, "expected_state_revision", None)
    if expected_revision is not None and int(state.get("state_revision", 0)) != expected_revision:
        raise GoalFlowError("状态已更新，请刷新方案后重新审批")
    if state.get("approved") and state.get("status") not in {"PLANNING", "WAITING_PLAN_APPROVAL"}:
        return {"ok": True, "message": "Design approval already applied", "state": state, "idempotent": True}
    if state["status"] not in {"PLANNING", "WAITING_PLAN_APPROVAL"}:
        raise GoalFlowError(f"Cannot approve from {state['status']}")
    current_design_hash = design_hash(directory, state)
    expected_design_hash = getattr(args, "expected_design_hash", None)
    if expected_design_hash and expected_design_hash != current_design_hash:
        raise GoalFlowError("方案内容已变化，请刷新方案并重新审批")
    readiness = plan_readiness(directory, state)
    if not readiness["ok"]:
        raise GoalFlowError("Plan is not approval-ready: " + "; ".join(readiness["reasons"]))
    auto_approved = bool(args.auto_approved)
    decision_check = readiness.get("decision_check") or decision_check_from_goal(
        (directory / "goal.md").read_text(encoding="utf-8"), state
    )
    if auto_approved:
        if visual_design_enabled(state):
            raise GoalFlowError("Visual design goals require explicit user approval")
        if resolve_harness(state) != "standard":
            raise GoalFlowError("Automatic approval is only available for the standard Harness")
        if state.get("profile") == "strict" or state.get("harness", {}).get("risk_level") in {"high", "critical"}:
            raise GoalFlowError("Strict or high-risk goals require explicit user approval")
        if decision_check.get("user_decisions"):
            raise GoalFlowError("Open high-impact user questions require explicit approval")
    if not args.user_approved and not auto_approved:
        raise GoalFlowError("Explicit user approval is required; pass --user-approved only after it is given")
    state["decision_check"] = decision_check
    state.update({
        "approved": True,
        "approved_design_hash": current_design_hash,
        "approved_definitions_hash": definitions_hash(state),
        "status": "EXECUTING",
        "current_milestone": args.milestone or "M1",
        "next_action": args.next_action,
        "wait_reason": None,
        "no_progress_count": 0,
        "stop_repeat_count": 0,
        "approved_by": args.approved_by if args.user_approved else "standard-auto",
        "approval_mode": "explicit" if args.user_approved else "implicit-standard",
    })
    save_state(directory, state)
    append_evidence(directory, "Design approved", {
        "goal revision": state["goal_revision"],
        "design hash": state["approved_design_hash"],
        "definitions hash": state["approved_definitions_hash"],
        "next action": state["next_action"],
        "approved by": state["approved_by"],
        "approval mode": state["approval_mode"],
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
        minimum_evidence_mode = args.minimum_evidence_mode or prior.get("minimum_evidence_mode")
        if minimum_evidence_mode not in EVIDENCE_MODES:
            raise GoalFlowError("Requirements need --minimum-evidence-mode: mock, simulated, or real")
        product_fingerprint: str | None = None
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
            if minimum_evidence_mode != prior.get("minimum_evidence_mode"):
                raise GoalFlowError("Approved requirement evidence level is frozen; run replan to change it")
        if args.status == "VERIFIED":
            invalid = [
                check_id for check_id in verified_by
                if check_id not in state.get("checks", {})
                or state["checks"][check_id].get("status") != "PASS"
                or not evidence_is_fresh(
                    root,
                    state["checks"][check_id].get("git_sha"),
                    state,
                    state["checks"][check_id].get("product_fingerprint"),
                )
            ]
            if not verified_by or invalid:
                suffix = f": {', '.join(invalid)}" if invalid else ""
                raise GoalFlowError(f"VERIFIED requirements need fresh passing --verified-by checks{suffix}")
            weak = [
                check_id for check_id in verified_by
                if not evidence_mode_satisfies(
                    state["checks"][check_id].get("evidence_mode"), minimum_evidence_mode
                )
            ]
            if weak and minimum_evidence_mode == "real":
                raise GoalFlowError(
                    f"VERIFIED requirement needs {minimum_evidence_mode} evidence; weaker checks: {', '.join(weak)}"
                )
            linked_shas = {
                state["checks"][check_id].get("git_sha")
                for check_id in verified_by
            }
            if len(linked_shas) != 1 or None in linked_shas:
                raise GoalFlowError("VERIFIED requirements need linked checks from one identical Git commit")
            derived_sha = next(iter(linked_shas))
            if args.git_sha and args.git_sha != derived_sha:
                raise GoalFlowError(
                    f"Requirement evidence SHA must match linked check receipts ({derived_sha})"
                )
            sha = derived_sha
            linked_fingerprints = {
                state["checks"][check_id].get("product_fingerprint")
                for check_id in verified_by
            }
            if len(linked_fingerprints) != 1 or None in linked_fingerprints:
                raise GoalFlowError("VERIFIED requirements need linked checks from one identical product tree")
            product_fingerprint = next(iter(linked_fingerprints))
        state["requirements"][args.id] = {
            "statement": statement,
            "kind": kind,
            "verified_by": verified_by,
            "proves": proves,
            "failure_modes": failure_modes,
            "basis": basis,
            "minimum_evidence_mode": minimum_evidence_mode,
            "status": args.status,
            "evidence": args.evidence,
            "git_sha": sha if args.status != "UNVERIFIED" else None,
            "product_fingerprint": (
                product_fingerprint or product_worktree_fingerprint(root)
                if args.status != "UNVERIFIED" else None
            ),
            "updated_at": now(),
            "updated_at_ns": time.time_ns(),
        }
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
            "role": args.role,
            "evidence_mode": args.evidence_mode,
            "covers": args.covers_requirement_id or [],
            "proves": args.proves,
            "limitations": args.limitations,
            "summary": None,
            "output_digest": None,
            "git_sha": None,
            "product_fingerprint": None,
            "updated_at": now(),
        }
    elif args.record_type == "risk":
        if args.status not in RISK_STATUSES:
            raise GoalFlowError("Invalid risk status")
        prior = state["risks"].get(args.id, {})
        severity = args.severity or prior.get("severity") or "low"
        if prior and RISK_SEVERITY_ORDER[severity] < RISK_SEVERITY_ORDER[prior["severity"]]:
            raise GoalFlowError("Risk severity cannot be lowered; mitigate or explicitly accept it")
        verified_by = args.verified_by or prior.get("verified_by") or []
        minimum_evidence_mode = args.minimum_evidence_mode or prior.get("minimum_evidence_mode")
        if minimum_evidence_mode not in EVIDENCE_MODES:
            raise GoalFlowError("Risks need --minimum-evidence-mode: mock, simulated, or real")
        if args.status == "ACCEPTED" and not args.accepted_by:
            raise GoalFlowError("Accepted risks require --accepted-by with the approving identity")
        if args.status in {"MITIGATED", "PARTIALLY_MITIGATED"}:
            if not args.evidence:
                raise GoalFlowError("Mitigated risks require non-empty evidence")
            if not verifiers_are_fresh(root, state, verified_by):
                raise GoalFlowError("Mitigated risks require fresh PASS checks via --verified-by")
        effective_risk_status = args.status
        if args.status == "MITIGATED" and not any(
            evidence_mode_satisfies(state["checks"][check_id].get("evidence_mode"), minimum_evidence_mode)
            for check_id in verified_by
        ):
            effective_risk_status = "PARTIALLY_MITIGATED"
        state["risks"][args.id] = {
            "status": effective_risk_status,
            "severity": severity,
            "description": args.statement or prior.get("description") or args.evidence or args.id,
            "evidence": args.evidence,
            "verified_by": verified_by,
            "git_sha": current_git_sha(root) if effective_risk_status in {"MITIGATED", "PARTIALLY_MITIGATED"} else None,
            "accepted_by": args.accepted_by if args.status == "ACCEPTED" else None,
            "minimum_evidence_mode": minimum_evidence_mode,
            "residual_risk": args.residual_risk or prior.get("residual_risk"),
            "updated_at": now(),
        }
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
    else:
        pass
    if args.record_type in {"requirement", "check"} and args.status not in {"UNVERIFIED", "PENDING"}:
        state["last_verified_commit"] = sha
    epoch = state.get("epoch") or {}
    if epoch.get("target_requirement_ids") and all(
        state.get("requirements", {}).get(req_id, {}).get("status") == "VERIFIED"
        for req_id in epoch["target_requirement_ids"]
    ):
        epoch["completed_at"] = now()
        state["epoch"] = epoch
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
    if state["status"] == "PAUSED":
        raise GoalFlowError("Cannot verify a paused goal; resume it before running checks")
    if not state.get("approved"):
        raise GoalFlowError("Check commands cannot run before explicit design approval")
    require_bound_worktree(root, state)
    check = state.get("checks", {}).get(args.id)
    if not check:
        raise GoalFlowError(f"Unknown check: {args.id}")
    epoch = state.get("epoch") or {}
    target_checks = epoch.get("target_check_ids") or []
    if target_checks and args.id not in target_checks:
        raise GoalFlowError(
            f"Current execution epoch targets checks {', '.join(target_checks)}; finish the declared epoch first"
        )
    command = check.get("command")
    if not command:
        raise GoalFlowError(f"Check {args.id} has no approved command")
    if state.get("approved") and design_drift(directory, state):
        raise GoalFlowError("Approved definitions changed; run replan before verification")
    if not product_tree_is_acceptable(root, state):
        if is_lightweight_standard(state):
            raise GoalFlowError(
                "Standard detected product changes beyond its initialization baseline; commit or restore them before verification"
            )
        raise GoalFlowError("Commit or clean product-tree changes before running a bound check")
    sha = current_git_sha(root)
    if sha == "UNBORN":
        raise GoalFlowError("Verification requires an existing Git commit")
    if (
        is_lightweight_standard(state)
        and product_tree_is_acceptable(root, state)
        and product_worktree_fingerprint(root) == state.get("harness", {}).get("baseline_product_fingerprint")
        and sha == state.get("harness", {}).get("baseline_git_sha")
    ):
        raise GoalFlowError(
            "Standard cannot verify a delivery without a product-tree change after goal initialization"
        )
    timeout = int(check.get("timeout") or 300)
    execution = execute_verifier(command, root, timeout)
    returncode = execution["returncode"]
    output = execution["output"]
    product_fingerprint = product_worktree_fingerprint(root)
    failure_class, recommended_action = classify_failure(execution)
    clean_after = product_tree_is_acceptable(root, state)
    status = "PASS" if returncode == 0 and clean_after else "FAIL"
    summary_parts = [f"exit={returncode}"]
    if execution["timed_out"]:
        summary_parts.append(f"timed out after {timeout}s")
        summary_parts.append(f"terminated with {execution['termination']}")
    if not clean_after:
        summary_parts.append("command changed the product tree or Standard baseline")
    if output:
        summary_parts.append(output[-4000:])
    summary = " | ".join(summary_parts)
    check.update({
        "status": status,
        "summary": summary,
        "output_digest": hashlib.sha256(output.encode()).hexdigest(),
        "receipt_id": hashlib.sha256(
            f"{time.time_ns()}:{args.id}:{sha}:{output}".encode()
        ).hexdigest()[:24],
        "git_sha": sha,
        "product_fingerprint": product_fingerprint,
        "duration_ms": execution["duration_ms"],
        "timed_out": execution["timed_out"],
        "termination": execution["termination"],
        "failure_class": failure_class,
        "recommended_action": recommended_action,
        "environment": environment_fingerprint(root),
        "updated_at": now(),
        "updated_at_ns": time.time_ns(),
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
        "product fingerprint": product_fingerprint,
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
        ensure_status_transition(state["status"], args.status)
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
    target_requirements = args.target_requirement_id or []
    target_checks = args.target_check_id or []
    if target_requirements or target_checks:
        if not target_requirements:
            raise GoalFlowError("An execution epoch must target at least one requirement")
        unknown_requirements = [item for item in target_requirements if item not in state.get("requirements", {})]
        unknown_checks = [item for item in target_checks if item not in state.get("checks", {})]
        if unknown_requirements or unknown_checks:
            raise GoalFlowError(
                "Unknown epoch targets: " + ", ".join(unknown_requirements + unknown_checks)
            )
        completed = [
            item for item in target_requirements
            if state["requirements"][item].get("status") == "VERIFIED"
        ]
        if completed == target_requirements:
            raise GoalFlowError("Execution epoch must target at least one unsatisfied requirement")
        state["epoch"] = {
            "target_requirement_ids": target_requirements,
            "target_check_ids": target_checks,
            "started_at": now(),
            "completed_at": None,
        }
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
        "delivery_attempt": 0,
        "delivery_feedback": None,
        "delivery_rejection_baseline": None,
        "epoch": None,
    })
    for item in state.get("requirements", {}).values():
        item.update({"status": "UNVERIFIED", "evidence": None, "git_sha": None, "product_fingerprint": None})
    for item in state.get("checks", {}).values():
        item.update({"status": "PENDING", "summary": None, "output_digest": None, "git_sha": None, "product_fingerprint": None})
    save_state(directory, state)
    return {"ok": True, "message": "Goal returned to planning", "state": state}


def cmd_pause(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot pause {state['status']}")
    if state["status"] == "PAUSED":
        raise GoalFlowError("Goal is already paused")
    state["resume_status"] = state["status"]
    state["status"] = "PAUSED"
    state["wait_reason"] = args.reason
    save_state(directory, state)
    return {"ok": True, "message": "Goal paused", "state": state}


def cmd_resume(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    if state["status"] not in {"PAUSED", "WAITING_INPUT", "WAITING_AUTHORIZATION", "BLOCKED"}:
        raise GoalFlowError(f"Cannot resume from {state['status']}")
    if state.get("approved"):
        require_bound_worktree(root, state)
    target = state.get("resume_status") or ("EXECUTING" if state.get("approved") else "PLANNING")
    state.update({"status": target, "wait_reason": None, "resume_status": None, "stop_repeat_count": 0})
    activate_goal(root, goal_id, state, switch=args.switch)
    save_state(directory, state)
    return {"ok": True, "message": "Goal resumed", "state": state}


def cmd_block(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    _, directory, state = load_state(root, args.goal_id)
    if state["status"] in {"ACCEPTED", "CANCELLED"}:
        raise GoalFlowError(f"Cannot block immutable goal {state['status']}")
    if state["status"] == "BLOCKED":
        raise GoalFlowError("Goal is already blocked")
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
    result["state_changed"] = False
    if args.apply and state["status"] == "READY_FOR_ACCEPTANCE" and design_drift(directory, state):
        state["resume_status"] = state["status"]
        state["status"] = "BLOCKED"
        state["wait_reason"] = "Approved design changed after verification"
        state["next_action"] = "Run replan and obtain approval for the changed design"
        save_state(directory, state)
        result.update({
            "status": "BLOCKED",
            "stored_status": "BLOCKED",
            "effective_status": "BLOCKED",
            "next_action": state["next_action"],
            "state_changed": True,
        })
        return result
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
            result["stored_status"] = state["status"]
            result["effective_status"] = state["status"]
            result["state_changed"] = True
        save_state(directory, state)
    if (
        args.apply
        and result["gate"] == "READY_FOR_REVIEW"
        and standard_auto_completion_allowed(state)
    ):
        state["status"] = "ACCEPTED"
        state["next_action"] = None
        state["last_verified_commit"] = result["git_sha"]
        state["approval_mode"] = state.get("approval_mode") or "implicit-standard"
        save_state(directory, state)
        append_evidence(directory, "Standard delivery completed", {
            "status": "ACCEPTED",
            "mode": "implicit-standard",
            "Git SHA": result["git_sha"],
        })
        deactivate_goal(root, state["goal_id"])
        result["gate"] = "ACCEPTED"
        result["status"] = "ACCEPTED"
        result["message"] = "Standard Harness delivery completed"
        result["stored_status"] = "ACCEPTED"
        result["effective_status"] = "ACCEPTED"
        result["state_changed"] = True
        return result
    if args.apply and result["gate"] == "READY_FOR_REVIEW" and state["status"] != "READY_FOR_ACCEPTANCE":
        state["status"] = "READY_FOR_ACCEPTANCE"
        state["next_action"] = result["next_action"]
        state["last_verified_commit"] = result["git_sha"]
        save_state(directory, state)
        result["status"] = state["status"]
        result["stored_status"] = state["status"]
        result["effective_status"] = state["status"]
        result["state_changed"] = True
    elif args.apply and result["gate"] == "CONTINUE" and state["status"] == "READY_FOR_ACCEPTANCE":
        state["status"] = "VERIFYING"
        invalidated = result.get("invalidated_paths") or []
        reason = str((result.get("freshness") or {}).get("reason") or "")
        if "uncommitted" in reason:
            state["next_action"] = "Clean or commit invalidating product files: " + ", ".join(invalidated)
        elif invalidated:
            state["next_action"] = "Rerun affected checks after product changes: " + ", ".join(invalidated)
        else:
            state["next_action"] = "Refresh stale evidence and rerun the delivery gate"
        save_state(directory, state)
        result["status"] = state["status"]
        result["stored_status"] = state["status"]
        result["effective_status"] = state["status"]
        result["next_action"] = state["next_action"]
        result["state_changed"] = True
    return result


def cmd_accept(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    goal_id, directory, state = load_state(root, args.goal_id)
    expected_revision = getattr(args, "expected_state_revision", None)
    if expected_revision is not None and int(state.get("state_revision", 0)) != expected_revision:
        raise GoalFlowError("状态已更新，请刷新交付后重新审批")
    if state.get("status") == "ACCEPTED":
        return {"ok": True, "message": "Goal already accepted", "state": state, "idempotent": True}
    require_bound_worktree(root, state)
    if state["status"] != "READY_FOR_ACCEPTANCE":
        raise GoalFlowError("Only a goal ready for acceptance can be accepted")
    expected_design_hash = getattr(args, "expected_design_hash", None)
    if expected_design_hash and expected_design_hash != design_hash(directory, state):
        raise GoalFlowError("交付设计已变化，请刷新交付后重新审批")
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
    expected_revision = getattr(args, "expected_state_revision", None)
    if expected_revision is not None and int(state.get("state_revision", 0)) != expected_revision:
        raise GoalFlowError("状态已更新，请刷新交付后重新处理")
    if state.get("delivery_feedback") and state.get("status") in {"EXECUTING", "VERIFYING"}:
        return {"ok": True, "message": "Delivery rejection already applied", "state": state, "idempotent": True}
    require_bound_worktree(root, state)
    if state["status"] != "READY_FOR_ACCEPTANCE":
        raise GoalFlowError("Only a goal ready for acceptance can be rejected")
    required_receipts = [
        item.get("receipt_id") for item in state.get("checks", {}).values()
        if item.get("required") and item.get("status") == "PASS" and item.get("receipt_id")
    ]
    state["delivery_attempt"] = int(state.get("delivery_attempt", 0)) + 1
    state["delivery_feedback"] = args.reason
    state["delivery_rejection_baseline"] = {
        "git_sha": current_git_sha(root),
        "receipt_ids": required_receipts,
        "rejected_at": now(),
        "rejected_at_ns": time.time_ns(),
    }
    # A rejected delivery starts a new acceptance epoch.  Keep the old
    # receipts in evidence.md for audit, but make their state explicitly stale
    # so a new epoch cannot be blocked by already-VERIFIED requirements.
    for requirement in state.get("requirements", {}).values():
        if requirement.get("kind") == "must":
            requirement.update({
                "status": "UNVERIFIED",
                "evidence": None,
                "git_sha": None,
                "product_fingerprint": None,
            })
    for check in state.get("checks", {}).values():
        if check.get("required"):
            check.update({
                "status": "PENDING",
                "summary": None,
                "output_digest": None,
                "git_sha": None,
                "product_fingerprint": None,
            })
    state["epoch"] = None
    state.update({"status": "EXECUTING", "next_action": args.reason, "wait_reason": None})
    save_state(directory, state)
    append_evidence(directory, "Delivery rejected", {
        "reason": args.reason,
        "attempt": state["delivery_attempt"],
        "Git SHA": state["delivery_rejection_baseline"]["git_sha"],
        "required receipts invalidated": ", ".join(required_receipts),
    })
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
    init.add_argument(
        "--visual-design",
        action="store_true",
        help="create an editable Draw.io architecture and critical-data-flow contract",
    )
    init.add_argument("--task-type", choices=sorted(TASK_TYPES), default="unspecified")
    init.add_argument("--risk-level", choices=sorted(RISK_LEVELS), default="unspecified")
    init.add_argument("--files", type=int, default=1)
    init.add_argument("--steps", type=int, default=1)
    init.add_argument("--cross-session", action="store_true")
    init.add_argument("--autonomous", action="store_true")
    init.add_argument(
        "--switch",
        dest="switch_active",
        action="store_true",
        help="pause the current active goal before making this goal active",
    )

    status = sub.add_parser("status")
    status.add_argument("--goal-id")

    design_check = sub.add_parser("design-check")
    design_check.add_argument("--goal-id")

    design_render = sub.add_parser("design-render")
    design_render.add_argument("--goal-id")

    summary = sub.add_parser("summary")
    summary.add_argument("--goal-id")
    summary.add_argument("--json", action="store_true")

    report = sub.add_parser("report")
    report.add_argument("--goal-id")
    report.add_argument("--json", action="store_true")

    bind_worktree = sub.add_parser("bind-worktree")
    bind_worktree.add_argument("--goal-id")
    bind_worktree.add_argument("--allow-current-worktree", action="store_true")
    bind_worktree.add_argument("--reason")

    approve = sub.add_parser("approve")
    approve.add_argument("--goal-id")
    approve.add_argument("--milestone")
    approve.add_argument("--next-action", required=True)
    approve.add_argument("--user-approved", action="store_true")
    approve.add_argument("--auto-approved", action="store_true")
    approve.add_argument("--approved-by", default="user")
    approve.add_argument("--expected-state-revision", type=int)
    approve.add_argument("--expected-design-hash")

    goals = sub.add_parser("goals")

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
    record.add_argument("--minimum-evidence-mode", choices=sorted(EVIDENCE_MODES))
    record.add_argument("--status")
    record.add_argument("--evidence")
    record.add_argument("--risk")
    record.add_argument("--git-sha")
    record.add_argument("--command", dest="check_command")
    record.add_argument("--role", choices=sorted(CHECK_ROLES))
    record.add_argument("--evidence-mode", choices=sorted(EVIDENCE_MODES))
    record.add_argument("--covers-requirement-id", action="append")
    record.add_argument("--limitations")
    record.add_argument("--required", action="store_true")
    record.add_argument("--severity", choices=sorted(RISK_SEVERITIES))
    record.add_argument("--accepted-by")
    record.add_argument("--residual-risk")
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
    classify.add_argument(
        "--default-mode", choices=["auto", "micro", "standard", "goal-flow", "strict"], default="auto"
    )

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
    update.add_argument("--target-requirement-id", action="append")
    update.add_argument("--target-check-id", action="append")

    replan = sub.add_parser("replan")
    replan.add_argument("--goal-id")
    replan.add_argument("--reason", required=True)

    pause = sub.add_parser("pause")
    pause.add_argument("--goal-id")
    pause.add_argument("--reason", required=True)

    resume = sub.add_parser("resume")
    resume.add_argument("--goal-id")
    resume.add_argument("--switch", action="store_true")

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
    accept.add_argument("--expected-state-revision", type=int)
    accept.add_argument("--expected-design-hash")

    reject = sub.add_parser("reject")
    reject.add_argument("--goal-id")
    reject.add_argument("--reason", required=True)
    reject.add_argument("--expected-state-revision", type=int)

    return parser


COMMANDS = {
    "init": cmd_init,
    "status": cmd_status,
    "design-check": cmd_design_check,
    "design-render": cmd_design_render,
    "goals": cmd_goals,
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
        read_only = args.command in {
            "status", "goals", "summary", "report", "plan-check", "review", "classify", "design-check"
        }
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
