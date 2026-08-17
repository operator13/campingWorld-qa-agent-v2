"""Tests for the PR gate surface."""

from qa_agent.surfaces.pr_gate import build_pr_body


class TestBuildPRBody:
    def test_includes_goal_and_outcome(self):
        body = build_pr_body(
            goal="Test checkout flow",
            changes=[
                {"file": "page_objects/CheckoutPage.ts", "reason": "locator healed"},
            ],
            outcome="healed",
        )
        assert "Test checkout flow" in body
        assert "healed" in body
        assert "CheckoutPage.ts" in body

    def test_includes_multiple_changes(self):
        body = build_pr_body(
            goal="test",
            changes=[
                {"file": "a.ts", "reason": "new"},
                {"file": "b.ts", "reason": "updated"},
            ],
            outcome="generated",
        )
        assert "a.ts" in body
        assert "b.ts" in body

    def test_includes_review_notice(self):
        body = build_pr_body(goal="test", changes=[], outcome="test")
        assert "review" in body.lower()
