#!/usr/bin/env python3
"""Continue an active Goal Flow turn until a deterministic stop gate is met."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


CONTROLLER = Path(__file__).resolve().parents[1] / "skills" / "goal-flow" / "scripts" / "goalctl.py"


def read_event() -> dict[str, Any]:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        return {}


def main() -> int:
    event = read_event()
    cwd = str(event.get("cwd") or Path.cwd())
    result = subprocess.run(
        [
            sys.executable,
            str(CONTROLLER),
            "--root",
            cwd,
            "gate",
            "--apply",
            "--stop-event",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("{}")
        return 0
    try:
        gate = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("{}")
        return 0
    if gate.get("gate") != "CONTINUE":
        if gate.get("status") == "BLOCKED" and gate.get("reasons"):
            print(json.dumps({"systemMessage": f"Goal Flow blocked: {gate['reasons'][0]}"}))
            return 0
        print("{}")
        return 0
    reasons = "; ".join(gate.get("reasons") or ["delivery gate remains open"])
    next_action = gate.get("next_action") or "Resolve the largest verified delivery gap"
    print(json.dumps({
        "decision": "block",
        "reason": (
            "Goal Flow is not ready to stop. "
            f"Reasons: {reasons}. Next action: {next_action}. "
            "Continue one bounded implementation and verification epoch, record fresh evidence, then run the gate again."
        ),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
