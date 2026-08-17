"""Tests for graph compilation and wiring."""

from qa_agent.graph import build_graph, compile_graph


def test_graph_builds():
    """The graph builds without errors."""
    graph = build_graph()
    assert graph is not None


def test_graph_compiles():
    """The graph compiles with a checkpointer."""
    compiled = compile_graph()
    assert compiled is not None
    assert len(compiled.nodes) > 0


def test_graph_has_all_phase1_nodes():
    """The graph contains all Phase 1 nodes."""
    compiled = compile_graph()
    node_names = set(compiled.nodes.keys())
    expected = {"design_reader", "planner", "generator", "executor"}
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


def test_graph_has_all_phase2_nodes():
    """The graph contains all Phase 2 nodes."""
    compiled = compile_graph()
    node_names = set(compiled.nodes.keys())
    expected = {"triage", "healer", "human_review", "defect_report"}
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


def test_graph_has_metrics_node():
    """The graph contains the Phase 3 metrics node."""
    compiled = compile_graph()
    assert "metrics" in compiled.nodes


def test_graph_total_node_count():
    """Phase 3 graph has 10 nodes (start + 9 real nodes)."""
    compiled = compile_graph()
    assert len(compiled.nodes) == 10
