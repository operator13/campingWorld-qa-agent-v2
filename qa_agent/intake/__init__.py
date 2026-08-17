"""Flexible intake adapters — Jira, Figma, or both."""

from qa_agent.intake.base import Intake, IntakeResult, parse_source
from qa_agent.intake.figma import FigmaIntake
from qa_agent.intake.jira import JiraIntake

__all__ = ["Intake", "IntakeResult", "FigmaIntake", "JiraIntake", "parse_source"]
