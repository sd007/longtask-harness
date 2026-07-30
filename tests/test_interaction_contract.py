from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InteractionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (ROOT / "goal-flow/skills/goal-flow/SKILL.md").read_text(encoding="utf-8")
        self.planning = (ROOT / "goal-flow/skills/goal-flow/references/planning.md").read_text(encoding="utf-8")
        self.execution = (ROOT / "goal-flow/skills/goal-flow/references/execution.md").read_text(encoding="utf-8")
        self.usage = (ROOT / "docs/usage.md").read_text(encoding="utf-8")

    def test_commit_language_follows_conversation_and_repo_convention(self) -> None:
        self.assertIn("current conversation language", self.skill)
        self.assertIn("current conversation language", self.execution)
        self.assertIn("当前对话语言", self.usage)
        self.assertIn("仓库已有规范优先", self.usage)
        self.assertIn("feat:", self.execution)

    def test_decision_check_is_visible_and_asks_only_high_impact_questions(self) -> None:
        for label in ("已自动确定", "建议默认", "仍需用户决定"):
            self.assertIn(label, self.planning)
        self.assertIn("no high-impact user decision remains", self.skill)
        self.assertIn("高影响未决项", self.usage)

    def test_approval_has_button_labels_and_natural_language_fallback(self) -> None:
        for label in ("批准并执行", "修改方案", "接受交付", "需要修改", "自然语言"):
            self.assertIn(label, self.skill + self.usage)
        self.assertIn("fixed phrase", self.skill)


if __name__ == "__main__":
    unittest.main()
