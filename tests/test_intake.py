"""Tests for intake adapters."""

from qa_agent.intake.base import IntakeResult, parse_source
from qa_agent.intake.jira import JiraIntake
from qa_agent.intake.figma import FigmaIntake


def test_parse_source_jira():
    """Parses 'jira:QA-123' correctly."""
    stype, ref = parse_source("jira:QA-123")
    assert stype == "jira"
    assert ref == "QA-123"


def test_parse_source_figma():
    """Parses 'figma:abc123/1:24' correctly."""
    stype, ref = parse_source("figma:abc123/1:24")
    assert stype == "figma"
    assert ref == "abc123/1:24"


def test_parse_source_default():
    """Bare reference defaults to jira."""
    stype, ref = parse_source("QA-123")
    assert stype == "jira"
    assert ref == "QA-123"


def test_intake_result_model():
    """IntakeResult can be constructed with all fields."""
    result = IntakeResult(
        goal="Test checkout",
        acceptance_criteria=["User can submit order", "Email required"],
        figma_ref="abc123/1:24",
        app_url="http://localhost:3000",
    )
    assert result.goal == "Test checkout"
    assert len(result.acceptance_criteria) == 2


def test_intake_result_minimal():
    """IntakeResult works with just a goal."""
    result = IntakeResult(goal="Test login")
    assert result.figma_ref is None
    assert result.app_url is None


def test_jira_parse_issue():
    """JiraIntake._parse_issue extracts data from a Jira payload."""
    jira = JiraIntake()
    data = {
        "fields": {
            "summary": "Implement checkout flow",
            "description": "As a user I want to:\n- Submit my order\n- Receive confirmation\n- See order number",
        }
    }
    result = jira._parse_issue(data)
    assert result.goal == "Implement checkout flow"
    assert len(result.acceptance_criteria) >= 2


def test_jira_parse_issue_with_adf():
    """JiraIntake handles Atlassian Document Format descriptions."""
    jira = JiraIntake()
    data = {
        "fields": {
            "summary": "Login page",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "User can log in with email and password"}
                        ]
                    },
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Invalid credentials show an error message"}
                        ]
                    }
                ]
            },
        }
    }
    result = jira._parse_issue(data)
    assert result.goal == "Login page"
    assert len(result.acceptance_criteria) >= 1


def test_jira_find_figma_url():
    """JiraIntake finds Figma URLs in text."""
    url = JiraIntake._find_figma_url(
        "Check the design: https://figma.com/file/abc123/My-Design?node-id=1:24 for details"
    )
    assert url is not None
    assert "figma.com" in url


def test_figma_parse_ref_url():
    """FigmaIntake parses full Figma URLs."""
    file_key, node_id = FigmaIntake._parse_ref(
        "https://www.figma.com/file/abc123/My-Design?node-id=1%3A24"
    )
    assert file_key == "abc123"
    assert node_id == "1:24"


def test_figma_parse_ref_short():
    """FigmaIntake parses short FILE/NODE format."""
    file_key, node_id = FigmaIntake._parse_ref("abc123/1:24")
    assert file_key == "abc123"
    assert node_id == "1:24"
