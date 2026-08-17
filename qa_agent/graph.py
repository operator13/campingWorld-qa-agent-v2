"""StateGraph wiring — edges, checkpointer, routers, and the compilable graph.

Phase 3: Full flow with triage, healing loop, human review, defect reporting,
and metrics collection on every terminal path.

  design_reader → planner → generator → executor
                                            ↓
                                     [pass? → metrics → END]
                                     [fail? → triage]
                                            ↓
                              [sure drift → healer → executor (retry)]
                              [sure bug   → defect_report → metrics → END]
                              [unsure     → human_review → healer | defect_report]
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from qa_agent.config import CONF_SURE, MAX_ATTEMPTS, setup_langsmith
from qa_agent.nodes.defect_report import defect_report
from qa_agent.nodes.design_reader import design_reader
from qa_agent.nodes.executor import executor
from qa_agent.nodes.generator import generator
from qa_agent.nodes.healer import healer
from qa_agent.nodes.metrics import metrics
from qa_agent.nodes.planner import planner
from qa_agent.nodes.triage import triage
from qa_agent.state import QAState
from qa_agent.surfaces.human_review import human_review

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routers — the two conditional edges
# ---------------------------------------------------------------------------

def route_after_execute(state: QAState) -> str:
    """After running tests: pass → metrics, fail → triage."""
    if state.run_results and state.run_results.passed:
        return "metrics"
    return "triage"


def route_after_triage(state: QAState) -> str:
    """After triage: route based on confidence + failure class + attempts.

    Decision tree:
      1. Too many attempts → defect_report (stop the loop)
      2. Low confidence    → human_review (let a person decide)
      3. Sure it's drift   → healer (auto-fix)
      4. Sure it's a bug   → defect_report (file & stop)
    """
    if state.attempts >= MAX_ATTEMPTS:
        logger.info("Router: MAX_ATTEMPTS (%d) reached → defect_report", MAX_ATTEMPTS)
        return "defect_report"

    if state.confidence < CONF_SURE:
        logger.info("Router: low confidence (%.2f < %.2f) → human_review",
                     state.confidence, CONF_SURE)
        return "human_review"

    if state.failure_class == "locator_drift":
        logger.info("Router: sure drift (confidence=%.2f) → healer", state.confidence)
        return "healer"

    # app_defect or unknown with high confidence
    logger.info("Router: sure bug/unknown (class=%s, confidence=%.2f) → defect_report",
                state.failure_class, state.confidence)
    return "defect_report"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Build the QA agent StateGraph with the full Phase 3 flow."""
    graph = StateGraph(QAState)

    # --- Nodes ---
    graph.add_node("design_reader", design_reader)
    graph.add_node("planner", planner)
    graph.add_node("generator", generator)
    graph.add_node("executor", executor)
    graph.add_node("triage", triage)
    graph.add_node("healer", healer)
    graph.add_node("human_review", human_review)
    graph.add_node("defect_report", defect_report)
    graph.add_node("metrics", metrics)

    # --- Edges: happy path ---
    graph.set_entry_point("design_reader")
    graph.add_edge("design_reader", "planner")
    graph.add_edge("planner", "generator")
    graph.add_edge("generator", "executor")

    # --- After executor: pass → metrics, fail → triage ---
    graph.add_conditional_edges(
        "executor",
        route_after_execute,
        {"metrics": "metrics", "triage": "triage"},
    )

    # --- After triage: fan out by confidence + failure class ---
    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "healer": "healer",
            "human_review": "human_review",
            "defect_report": "defect_report",
        },
    )

    # --- Healer → executor (retry loop) ---
    graph.add_edge("healer", "executor")

    # --- human_review uses Command to route dynamically ---
    # (no static edge needed — Command(goto=...) handles routing)

    # --- Defect report → metrics → END ---
    graph.add_edge("defect_report", "metrics")

    # --- Metrics → END (terminal for both pass and defect paths) ---
    graph.add_edge("metrics", END)

    return graph


def compile_graph():  # type: ignore[no-untyped-def]
    """Compile the graph with a checkpointer, ready to invoke."""
    setup_langsmith()
    graph = build_graph()
    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("Graph compiled with %d node(s)", len(compiled.nodes))
    return compiled
