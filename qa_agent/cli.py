"""CLI entrypoint for the QA agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from qa_agent.graph import compile_graph
from qa_agent.intake.base import parse_source
from qa_agent.mcp.atlassian_client import ATLASSIAN_MCP_SERVER_CONFIG
from qa_agent.mcp.figma_client import FIGMA_MCP_SERVER_CONFIG
from qa_agent.mcp.playwright_client import PLAYWRIGHT_MCP_SERVER_CONFIG

logger = logging.getLogger(__name__)


async def _dry_run() -> None:
    """Compile the graph and list MCP server tools — no LLM calls."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    print("=== QA Agent · Dry Run ===\n")

    # 1. Compile the graph
    compiled = compile_graph()
    print(f"[OK] Graph compiled: {len(compiled.nodes)} node(s)")

    # 2. Connect MCP servers independently and list tools
    servers = {
        "Playwright": PLAYWRIGHT_MCP_SERVER_CONFIG,
        "Figma": FIGMA_MCP_SERVER_CONFIG,
        "Atlassian (Jira)": ATLASSIAN_MCP_SERVER_CONFIG,
    }

    for name, config in servers.items():
        print(f"\n[..] Connecting to {name} MCP server...")
        try:
            client = MultiServerMCPClient(config)
            tools = await client.get_tools()
            print(f"[OK] {name} MCP — {len(tools)} tool(s):")
            for tool in tools:
                print(f"  - {tool.name}")
        except Exception as e:
            err_msg = str(e).split("\n")[0]
            print(f"[WARN] {name} MCP not available: {err_msg}")

    print("\n[OK] Dry run complete.")


async def _run(sources: list[str]) -> None:
    """Run the graph with the given source(s)."""
    from qa_agent.intake.figma import FigmaIntake
    from qa_agent.intake.jira import JiraIntake

    # Build initial state from sources
    initial_state: dict = {
        "goal": "",
        "acceptance_criteria": [],
    }

    for source in sources:
        source_type, ref = parse_source(source)
        print(f"[..] Loading source: {source_type}:{ref}")

        if source_type == "jira":
            intake = JiraIntake()
            result = await intake.load(ref)
        elif source_type == "figma":
            intake = FigmaIntake()  # type: ignore[assignment]
            result = await intake.load(ref)
        else:
            print(f"[ERROR] Unknown source type: {source_type}")
            sys.exit(1)

        # Merge: AC = union, Jira goal wins on conflict
        if result.goal and (not initial_state["goal"] or source_type == "jira"):
            initial_state["goal"] = result.goal
        initial_state["acceptance_criteria"] = list(
            dict.fromkeys(
                initial_state["acceptance_criteria"] + result.acceptance_criteria
            )
        )
        if result.figma_ref:
            initial_state["figma_ref"] = result.figma_ref
        if result.app_url:
            initial_state["app_url"] = result.app_url

    if not initial_state["goal"]:
        print("[ERROR] No goal derived from sources.")
        sys.exit(1)

    print(f"\n[OK] Goal: {initial_state['goal']}")
    print(f"[OK] {len(initial_state['acceptance_criteria'])} acceptance criteria")
    if initial_state.get("figma_ref"):
        print(f"[OK] Figma ref: {initial_state['figma_ref']}")

    # Compile and run the graph
    compiled = compile_graph()
    config = {"configurable": {"thread_id": "qa-agent-run-1"}}

    print("\n[..] Running graph...\n")
    result = await compiled.ainvoke(initial_state, config=config)

    # Report results
    run_results = result.get("run_results")
    if run_results:
        status = "PASSED" if run_results.passed else "FAILED"
        print(f"\n{'=' * 40}")
        print(f"[{'OK' if run_results.passed else 'FAIL'}] Tests {status}")
        if run_results.failed_cases:
            print(f"  Failed: {', '.join(run_results.failed_cases)}")
        print(f"{'=' * 40}")
    else:
        print("\n[WARN] No run results (executor may not have run)")

    plan = result.get("plan", [])
    print(f"\nSummary: {len(plan)} test case(s) planned")
    print(f"  Page objects: {len(result.get('page_objects', {}))}")
    print(f"  Test files: {len(result.get('test_code', {}))}")


def _review_weekly() -> None:
    """Generate and print a weekly review."""
    from qa_agent.weekly_review import (
        generate_weekly_review,
        get_previous_stats,
        write_weekly_review,
    )

    print("=== QA Agent · Weekly Review ===\n")

    previous = get_previous_stats()
    review = generate_weekly_review(previous_stats=previous)

    # Print to console
    print(review["markdown"])

    # Write to memory
    write_weekly_review(review)
    print(f"\n[OK] Review written to memory/WEEKLY_REVIEW.md (grade: {review['grade']})")


def _memory_learn() -> None:
    """Generate lessons from accumulated memory data."""
    from qa_agent.memory import MemoryStore

    store = MemoryStore()

    print("=== QA Agent · Memory Learn ===\n")

    # Clear old scoreboard rows before regenerating
    store.clear_pattern_scoreboard()

    # Generate pattern scoreboard
    scoreboard = store.generate_pattern_scoreboard()
    if scoreboard:
        print(f"Pattern scoreboard: {len(scoreboard)} patterns found")
        for p in scoreboard:
            store.record_lesson(
                "pattern",
                "/",
                f"{p['pattern']} | {p['occurrences']} | {p['success_rate']} | {p['best_strategy']}",
            )
        for p in scoreboard:
            print(f"  - {p['pattern']}: {p['occurrences']}x, success {p['success_rate']}, best: {p['best_strategy']}")
    else:
        print("No patterns found (need more run data)")

    # Clear old auto-generated route insights, then regenerate
    store.clear_auto_generated_insights()
    insights = store.generate_route_insights()
    if insights:
        print(f"\nRoute insights: {len(insights)} routes analyzed")
        for route, insight in insights.items():
            store.record_lesson("route_insight", route, insight, source="auto-generated")
            print(f"  {route}: {insight.split(chr(10))[0]}")
    else:
        print("No route insights (need more run data)")

    print("\n[OK] Lessons written to memory/LESSONS.md")


def _memory_stats() -> None:
    """Print memory statistics."""
    from qa_agent.memory import MemoryStore

    store = MemoryStore()
    s = store.stats()

    print("=== QA Agent · Memory Stats ===\n")
    print(f"Total entries: {s['total_entries']}")
    print(f"Total size: {s['total_size_kb']} KB\n")
    print("By file:")
    for name, count in s["files"].items():
        print(f"  {name}: {count} entries")


def _memory_prune(max_age: int) -> None:
    """Prune stale memory entries."""
    from qa_agent.memory import MemoryStore

    store = MemoryStore()

    print(f"=== QA Agent · Memory Prune (>{max_age} days) ===\n")

    before = store.stats()
    pruned = store.prune_stale(max_age_days=max_age)
    merged = store.dedup_failure_patterns()
    after = store.stats()

    print(f"Pruned: {pruned} stale entries")
    print(f"Merged: {merged} duplicate failure patterns")
    print(f"Entries: {before['total_entries']} → {after['total_entries']}")
    print(f"Size: {before['total_size_kb']} KB → {after['total_size_kb']} KB")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="qa-agent",
        description="QA Automation AI Agent — Playwright + LangGraph",
    )
    parser.add_argument(
        "command",
        choices=["run", "memory", "review"],
        help="Command to execute",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Dry run: compile graph and list MCP tools, no LLM calls",
    )
    parser.add_argument(
        "--source",
        type=str,
        action="append",
        default=[],
        help="Source reference: jira:QA-123 or figma:FILE/NODE (repeatable)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        default=None,
        help="Subcommand: stats, prune, learn (for memory command)",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=90,
        help="Max age in days for memory prune (default: 90)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.command == "run":
        if args.dry:
            asyncio.run(_dry_run())
        elif args.source:
            asyncio.run(_run(args.source))
        else:
            print("Usage: qa-agent run --source jira:QA-123 [--source figma:FILE/NODE]")
            sys.exit(1)
    elif args.command == "memory":
        if args.subcommand == "stats":
            _memory_stats()
        elif args.subcommand == "prune":
            _memory_prune(args.max_age)
        elif args.subcommand == "learn":
            _memory_learn()
        else:
            print("Usage: qa-agent memory stats | prune [--max-age 90] | learn")
            sys.exit(1)
    elif args.command == "review":
        if args.subcommand == "weekly":
            _review_weekly()
        else:
            print("Usage: qa-agent review weekly")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)
