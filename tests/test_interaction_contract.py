from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InteractionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (ROOT / "goal-flow/skills/goal-flow/SKILL.md").read_text(encoding="utf-8")
        self.planning = (ROOT / "goal-flow/skills/goal-flow/references/planning.md").read_text(encoding="utf-8")
        self.execution = (ROOT / "goal-flow/skills/goal-flow/references/execution.md").read_text(encoding="utf-8")
        self.verification = (ROOT / "goal-flow/skills/goal-flow/references/verification.md").read_text(encoding="utf-8")
        self.usage = (ROOT / "docs/usage.md").read_text(encoding="utf-8")

    def test_commit_language_follows_conversation_and_repo_convention(self) -> None:
        self.assertIn("current conversation language", self.skill)
        self.assertIn("current conversation language", self.execution)
        self.assertIn("当前对话语言", self.usage)
        self.assertIn("仓库已有规范优先", self.usage)
        self.assertIn("feat:", self.execution)

    def test_commit_messages_explain_change_and_boundary(self) -> None:
        contract = self.skill + self.execution + self.usage
        self.assertIn("changed object", contract)
        self.assertIn("core behavior change", contract)
        self.assertIn("purpose or boundary", contract)
        self.assertIn("不要求为了润色而改写已有历史", contract)

    def test_decision_check_is_visible_and_asks_only_high_impact_questions(self) -> None:
        for label in ("已自动确定", "建议默认", "仍需用户决定"):
            self.assertIn(label, self.planning)
        self.assertIn("no high-impact user decision remains", self.skill)
        self.assertIn("高影响未决项", self.usage)

    def test_approval_has_button_labels_and_natural_language_fallback(self) -> None:
        for label in ("批准并执行", "修改方案", "接受交付", "需要修改", "自然语言"):
            self.assertIn(label, self.skill + self.usage)
        self.assertIn("fixed phrase", self.skill)
        self.assertIn("goal_flow_approval", self.skill + self.usage)
        self.assertIn("elicitation/create", self.skill + self.planning)

    def test_quality_loop_stays_compact_and_product_shaped(self) -> None:
        contract = self.skill + self.planning + self.execution + self.verification + self.usage
        self.assertIn("evolvability probe", contract.lower())
        self.assertIn("Implementation fidelity review", contract)
        self.assertIn("Classic product scenario set", contract)
        self.assertIn("3–5 scenarios", contract)
        self.assertIn("delta.md` and `tasks.md` are optional", contract)
        for dimension in (
            "functional",
            "performance-reliability",
            "evolvability-maintainability",
        ):
            self.assertIn(dimension, self.planning)

    def test_branch_isolation_defaults_to_shared_worktree(self) -> None:
        self.assertIn("ordinary tasks on the current branch", self.skill)
        self.assertIn("普通任务（包括普通 Goal Flow）留在当前分支", self.usage)
        self.assertIn("new projects, major features, migrations", self.skill)

    def test_simple_tasks_can_skip_result_confirmation_only_with_a_hard_gate(self) -> None:
        contract = self.skill + self.planning + self.usage
        self.assertIn("A simple task may complete directly after the same hard gate", contract)
        self.assertIn("不再弹出结果确认", contract)
        self.assertIn("不超过两个文件和两个步骤", contract)
        self.assertIn("All other Goal Flow, strict", contract)


if __name__ == "__main__":
    unittest.main()
