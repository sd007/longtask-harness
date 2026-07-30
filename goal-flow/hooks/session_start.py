#!/usr/bin/env python3
"""Restore concise Goal Flow context when Codex starts or resumes a session."""

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
        [sys.executable, str(CONTROLLER), "--root", cwd, "status"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("{}")
        return 0
    try:
        payload = json.loads(result.stdout)
        state = payload["state"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("{}")
        return 0
    if state.get("status") in {"ACCEPTED", "CANCELLED"}:
        print("{}")
        return 0
    context = (
        "Goal Flow is active. Resume it before starting unrelated work. "
        f"Goal={state['goal_id']}; revision={state['goal_revision']}; "
        f"status={state['status']}; milestone={state.get('current_milestone')}; "
        f"next_action={state.get('next_action')}; design_drift={payload.get('design_drift')}. "
        "Read goal.md, state.json, evidence.md, and Git state. Use goalctl.py for transitions."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
