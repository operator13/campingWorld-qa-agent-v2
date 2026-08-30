"""Evaluation harness — golden examples, scoring, and regression detection."""

from qa_agent.eval.eval_runner import run_triage_eval
from qa_agent.eval.scorecard import build_scorecard, save_scorecard, load_latest_scorecard
from qa_agent.eval.regression import detect_regression

__all__ = [
    "run_triage_eval",
    "build_scorecard",
    "save_scorecard",
    "load_latest_scorecard",
    "detect_regression",
]
