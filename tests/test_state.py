"""Tests for QAState — round-trip serialization and the attempts reducer."""

from qa_agent.state import QAState
from qa_agent.schemas.models import ExpectedUI, RunResult, TestCase, UIElement, UIFlow


def test_state_defaults():
    """QAState can be constructed with all defaults."""
    state = QAState()
    assert state.goal == ""
    assert state.acceptance_criteria == []
    assert state.attempts == 0
    assert state.confidence == 0.0
    assert state.failure_class is None
    assert state.run_results is None


def test_state_round_trip():
    """QAState serializes to dict and back without data loss."""
    state = QAState(
        goal="Test checkout flow",
        acceptance_criteria=["User can submit order", "Email is required"],
        figma_ref="1:24",
        app_url="http://localhost:3000",
        expected_ui=ExpectedUI(
            route="/checkout",
            elements=[UIElement(role="button", name="Submit")],
            flows=[UIFlow(name="checkout", steps=["fill form", "click submit"])],
        ),
        plan=[
            TestCase(
                id="tc-1",
                title="Submit order",
                feature="checkout",
                route="/checkout",
                tags=["@smoke"],
                steps=["Navigate to /checkout", "Click Submit"],
                expected=["Order confirmed"],
                source="both",
            )
        ],
        page_objects={"/checkout": "class CheckoutPage: ..."},
        test_code={"tests/checkout.spec.ts": "test('submit', ...)"},
        run_results=RunResult(passed=True, failed_cases=[], logs="All passed"),
        attempts=2,
        confidence=0.85,
        failure_class="locator_drift",
        error=None,
    )

    # Round-trip via dict
    data = state.model_dump()
    restored = QAState(**data)

    assert restored.goal == state.goal
    assert restored.acceptance_criteria == state.acceptance_criteria
    assert restored.attempts == state.attempts
    assert restored.confidence == state.confidence
    assert restored.plan[0].id == "tc-1"
    assert restored.expected_ui is not None
    assert restored.expected_ui.route == "/checkout"
    assert restored.run_results is not None
    assert restored.run_results.passed is True


def test_state_round_trip_json():
    """QAState serializes to JSON and back."""
    state = QAState(goal="test", attempts=1)
    json_str = state.model_dump_json()
    restored = QAState.model_validate_json(json_str)
    assert restored.goal == "test"
    assert restored.attempts == 1


def test_attempts_reducer_annotation():
    """The attempts field uses operator.add as its reducer annotation."""
    import operator
    from typing import get_type_hints, get_args

    hints = get_type_hints(QAState, include_extras=True)
    attempts_hint = hints["attempts"]
    args = get_args(attempts_hint)
    # The Annotated type should contain operator.add
    assert operator.add in args, f"Expected operator.add in {args}"


def test_schemas_standalone():
    """Schema models can be constructed and validated independently."""
    tc = TestCase(
        id="tc-1",
        title="Login works",
        feature="login",
        route="/login",
        steps=["Navigate", "Enter creds", "Click login"],
        expected=["Dashboard visible"],
    )
    assert tc.source == "jira"  # default

    ui = ExpectedUI(route="/login", elements=[], flows=[])
    assert ui.route == "/login"

    rr = RunResult(passed=False, failed_cases=["tc-1"], logs="timeout")
    assert not rr.passed
