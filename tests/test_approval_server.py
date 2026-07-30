from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "goal-flow" / "mcp"))
import approval_server  # noqa: E402


class ApprovalServerTests(unittest.TestCase):
    def test_native_labels_are_exposed_as_mcp_enum_names(self) -> None:
        plan = approval_server.approval_schema("plan")
        delivery = approval_server.approval_schema("delivery")
        self.assertEqual(plan["enumNames"], ["批准并执行", "修改方案"])
        self.assertEqual(delivery["enumNames"], ["接受交付", "需要修改"])
        tool = approval_server.tool_definition()
        self.assertEqual(tool["name"], "goal_flow_approval")
        self.assertFalse(tool["annotations"]["readOnlyHint"])

    def test_acceptance_choice_runs_only_after_explicit_elicitation_accept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".goal-flow").mkdir()
            server = approval_server.ApprovalServer()
            server.elicit = lambda phase, message: {
                "action": "accept",
                "content": {"decision": "approve"},
            }
            with patch.object(server, "run_transition", return_value=(True, "状态转换已完成")) as transition:
                result = server.call_approval({
                    "phase": "plan",
                    "root": str(root),
                    "revision": 1,
                    "summary": "方案摘要",
                    "next_action": "开始 M1",
                })
            transition.assert_called_once()
            self.assertEqual(result["structuredContent"]["decision"], "approve")
            self.assertTrue(result["structuredContent"]["ok"])

    def test_decline_or_cancel_never_runs_controller_transition(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".goal-flow").mkdir()
            for response in ({"action": "decline"}, {"action": "cancel"}):
                server = approval_server.ApprovalServer()
                server.elicit = lambda phase, message, response=response: response
                with patch.object(server, "run_transition") as transition:
                    result = server.call_approval({
                        "phase": "delivery",
                        "root": str(root),
                        "summary": "交付摘要",
                    })
                transition.assert_not_called()
                self.assertEqual(result["structuredContent"]["transition"], "none")

    def test_stdio_protocol_lists_approval_tool(self) -> None:
        server = approval_server.ApprovalServer()
        writes: list[dict] = []
        server.write = writes.append
        server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(writes[0]["result"]["serverInfo"]["name"], "goal-flow-approval")
        self.assertEqual(writes[1]["result"]["tools"][0]["name"], "goal_flow_approval")


if __name__ == "__main__":
    unittest.main()
