#!/usr/bin/env python3
"""Small stdio MCP server that turns Goal Flow decisions into native elicitation UI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = PLUGIN_ROOT / "skills" / "goal-flow" / "scripts" / "goalctl.py"
MAX_TEXT = 4000


def _text(value: Any, *, default: str = "", limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        return default
    return value.strip()[:limit]


def approval_schema(phase: str) -> dict[str, Any]:
    if phase == "plan":
        return {
            "message": "Goal Flow 方案已完成审查，请选择下一步。",
            "enum": ["approve", "modify"],
            "enumNames": ["批准并执行", "修改方案"],
        }
    return {
        "message": "Goal Flow 已通过交付 Gate，请选择交付处理方式。",
        "enum": ["accept", "revise"],
        "enumNames": ["接受交付", "需要修改"],
    }


def tool_definition() -> dict[str, Any]:
    return {
        "name": "goal_flow_approval",
        "title": "Goal Flow 审批",
        "description": (
            "在 Goal Flow 方案批准或最终交付验收节点显示宿主原生审批控件。"
            "只有用户明确选择后，才会执行对应的状态转换。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": ["plan", "delivery"],
                    "description": "审批阶段：方案 plan，或最终交付 delivery。",
                },
                "root": {
                    "type": "string",
                    "description": "目标 Git 仓库绝对路径。",
                },
                "goal_id": {
                    "type": "string",
                    "description": "可选的 Goal Flow 目标 ID。",
                },
                "revision": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "当前状态 state_revision，用于防止过期按钮提交。",
                },
                "summary": {
                    "type": "string",
                    "description": "展示给用户的方案或交付摘要。",
                    "maxLength": MAX_TEXT,
                },
                "next_action": {
                    "type": "string",
                    "description": "批准方案后要执行的第一个里程碑动作。",
                },
                "approved_by": {
                    "type": "string",
                    "description": "审批身份，默认 user。",
                },
            },
            "required": ["phase", "root", "summary"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    }


class ApprovalServer:
    def __init__(self) -> None:
        self._next_id = 1

    def read(self) -> dict[str, Any] | None:
        line = sys.stdin.readline()
        if not line:
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "id": None, "method": "__invalid__"}
        return payload if isinstance(payload, dict) else None

    def write(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def response(self, request_id: Any, result: dict[str, Any]) -> None:
        self.write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def error(self, request_id: Any, code: int, message: str) -> None:
        self.write({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        })

    def elicit(self, phase: str, message: str) -> dict[str, Any]:
        schema = approval_schema(phase)
        request_id = self._next_id
        self._next_id += 1
        self.write({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "elicitation/create",
            "params": {
                "message": message,
                "requestedSchema": {
                    "type": "object",
                    "properties": {
                        "decision": {
                            "type": "string",
                            "title": "审批决定",
                            "description": schema["message"],
                            "enum": schema["enum"],
                            "enumNames": schema["enumNames"],
                        },
                        "feedback": {
                            "type": "string",
                            "title": "补充说明（可选）",
                            "description": "选择修改时，可填写需要调整的内容。",
                            "maxLength": 1000,
                        },
                    },
                    "required": ["decision"],
                },
            },
        })
        while True:
            reply = self.read()
            if reply is None:
                return {"action": "cancel"}
            if reply.get("id") != request_id:
                continue
            result = reply.get("result")
            return result if isinstance(result, dict) else {"action": "cancel"}

    def run_transition(
        self,
        phase: str,
        root: Path,
        goal_id: str,
        next_action: str,
        approved_by: str,
        decision: str,
        feedback: str,
        state_revision: int | None = None,
    ) -> tuple[bool, str]:
        command = [sys.executable, str(CONTROLLER), "--root", str(root)]
        if phase == "plan" and decision == "approve":
            command += ["approve", "--user-approved", "--approved-by", approved_by, "--next-action", next_action]
        elif phase == "delivery" and decision == "accept":
            command += ["accept", "--user-accepted", "--accepted-by", approved_by]
        elif phase == "delivery" and decision == "revise":
            command += ["reject", "--reason", feedback or "用户选择需要修改交付"]
        else:
            return True, "未执行状态转换"
        if state_revision is not None:
            command += ["--expected-state-revision", str(state_revision)]
        if goal_id:
            command += ["--goal-id", goal_id]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            return True, "状态转换已完成"
        detail = (result.stderr or result.stdout or "Goal Flow 状态转换失败").strip()
        return False, detail[-2000:]

    def call_approval(self, arguments: dict[str, Any]) -> dict[str, Any]:
        phase = _text(arguments.get("phase"))
        if phase not in {"plan", "delivery"}:
            return {"isError": True, "content": [{"type": "text", "text": "phase 必须是 plan 或 delivery"}]}
        raw_root = _text(arguments.get("root"))
        root = Path(raw_root).expanduser().resolve() if raw_root else Path.cwd().resolve()
        if not root.is_dir() or not (root / ".goal-flow").is_dir():
            return {"isError": True, "content": [{"type": "text", "text": "root 必须是包含 .goal-flow 的 Git 仓库目录"}]}
        summary = _text(arguments.get("summary"), limit=MAX_TEXT)
        goal_id = _text(arguments.get("goal_id"), limit=200)
        revision = arguments.get("revision")
        approved_by = _text(arguments.get("approved_by"), default="user", limit=100) or "user"
        next_action = _text(arguments.get("next_action"), limit=1000)
        if goal_id:
            state_path = root / ".goal-flow" / goal_id / "state.json"
            if state_path.exists() and revision is not None:
                try:
                    current_revision = int(json.loads(state_path.read_text(encoding="utf-8")).get("state_revision", 0))
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    return {"isError": True, "content": [{"type": "text", "text": "无法读取当前 Goal Flow 状态，请刷新后重试"}]}
                if current_revision != int(revision):
                    return {"isError": True, "content": [{"type": "text", "text": "状态已更新，请刷新后重新审批"}]}
        message = f"{approval_schema(phase)['message']}\n\nRevision: {revision or '当前'}\n\n{summary}"
        result = self.elicit(phase, message)
        action = _text(result.get("action"))
        content = result.get("content") if isinstance(result.get("content"), dict) else {}
        decision = _text(content.get("decision"))
        feedback = _text(content.get("feedback"), limit=1000)
        if action != "accept":
            return {
                "structuredContent": {"ok": True, "phase": phase, "decision": action or "cancel", "transition": "none"},
                "content": [{"type": "text", "text": "用户未批准，未执行状态转换。"}],
            }
        expected = {"plan": {"approve", "modify"}, "delivery": {"accept", "revise"}}[phase]
        if decision not in expected:
            return {"isError": True, "content": [{"type": "text", "text": "审批控件返回了无效决定"}]}
        ok, transition = self.run_transition(
            phase, root, goal_id, next_action, approved_by, decision, feedback,
            int(revision) if revision is not None else None,
        )
        payload = {
            "ok": ok,
            "phase": phase,
            "decision": decision,
            "feedback": feedback,
            "transition": transition,
        }
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": transition}],
            **({} if ok else {"isError": True}),
        }

    def handle(self, request: dict[str, Any]) -> None:
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            self.response(request_id, {
                "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "goal-flow-approval", "version": "0.10.0"},
            })
        elif method == "notifications/initialized":
            return
        elif method == "ping":
            self.response(request_id, {})
        elif method == "tools/list":
            self.response(request_id, {"tools": [tool_definition()]})
        elif method == "tools/call":
            params = request.get("params") if isinstance(request.get("params"), dict) else {}
            if params.get("name") != "goal_flow_approval":
                self.error(request_id, -32602, "未知工具")
                return
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            self.response(request_id, self.call_approval(arguments))
        elif method == "__invalid__":
            self.error(request_id, -32700, "无效 JSON")
        elif request_id is not None:
            self.error(request_id, -32601, f"不支持的方法: {method}")

    def serve(self) -> None:
        while True:
            request = self.read()
            if request is None:
                return
            self.handle(request)


if __name__ == "__main__":
    ApprovalServer().serve()
