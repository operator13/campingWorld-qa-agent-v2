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
    from qa_agent.audit import AuditStore
    import time as _time

    run_id = f"run-{int(_time.time())}"
    AuditStore.start_run(run_id)

    compiled = compile_graph()
    config = {"configurable": {"thread_id": run_id}}

    print(f"\n[..] Running graph (run_id={run_id})...\n")
    result = await compiled.ainvoke(initial_state, config=config)

    AuditStore.end_run()

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


async def _crawl(
    pages: list[str] | None,
    include_auth: bool,
    resume: bool,
    dry: bool,
    overwrite: bool,
) -> None:
    """Crawl campingworld.com and generate POM + test files."""
    from qa_agent.mcp.playwright_client import create_playwright_client
    from qa_agent.orchestrator.orchestrator import Orchestrator

    print("=== QA Agent · DOM Orchestrator ===\n")

    if pages:
        print(f"Pages: {', '.join(pages)}")
    else:
        print("Pages: all" + (" (including auth)" if include_auth else " (excluding auth)"))
    if dry:
        print("Mode: DRY RUN (snapshot only, no generation)")
    if resume:
        print("Mode: RESUME (skipping completed pages)")
    print()

    mcp_client = await create_playwright_client()
    tools = await mcp_client.get_tools()
    print(f"[OK] Playwright MCP connected ({len(tools)} tools)\n")

    async def call_tool(tool_name: str, args: dict) -> object:
        """Invoke a Playwright MCP tool by name."""
        for tool in tools:
            if tool.name == tool_name:
                return await tool.ainvoke(args)
        raise ValueError(f"MCP tool not found: {tool_name}")

    orchestrator = Orchestrator(call_tool, overwrite=overwrite)
    result = await orchestrator.crawl_site(
        pages=pages,
        include_auth=include_auth,
        resume=resume,
        dry_run=dry,
    )

    if result.pages_failed > 0:
        sys.exit(1)


def _print_generator_results(scorecard: dict) -> None:
    """Print generator eval results (multi-metric format)."""
    if scorecard["passed"] is None:
        status = "BASELINE (no judgment)"
    elif scorecard["passed"]:
        status = "PASS"
    else:
        status = "FAIL"

    print(f"Scenarios: {scorecard['scenarios_total']} loaded, "
          f"{scorecard['scenarios_skipped_expired']} skipped (expired)")
    print()

    for key, label in [("locator_quality", "Locator Quality"), ("pom_validity", "POM Validity"), ("test_validity", "Test Validity")]:
        data = scorecard.get(key, {})
        threshold_val = scorecard.get("thresholds", {}).get(key, 0.70)
        score = data.get("score", 0)
        print(f"  {label}:  {score * 100:.1f}%  (threshold: {threshold_val * 100:.1f}%)")

    print(f"\nOverall: {status}")

    recs = scorecard.get("recommendations", [])
    if recs:
        print(f"\nRecommendations ({len(recs)}):")
        for r in recs:
            priority = r["priority"].upper()
            print(f"\n  [{priority}] {r.get('category', 'general')}")
            print(f"    Finding: {r['finding']}")
            print(f"    Action:  {r['action']}")

    print(f"\nScorecard: {scorecard.get('eval_run_id', 'unknown')}")
    print(f"Report:    qa_agent/eval/reports/ (JSON + Markdown)")

    if scorecard["passed"] is False:
        sys.exit(1)


async def _eval_run(agent: str, baseline: bool, threshold: float | None) -> None:
    """Run eval for the specified agent."""
    from qa_agent.eval.eval_runner import (
        run_generator_eval, run_healer_eval, run_planner_eval, run_triage_eval,
    )

    supported = ["triage", "planner", "generator", "healer", "all"]

    if agent == "all":
        mode = "BASELINE" if baseline else "EVAL"
        print(f"=== QA Agent · {mode} (all agents) ===\n")
        for a in ["triage", "planner", "generator", "healer"]:
            print(f"\n{'='*50}")
            await _eval_run(a, baseline, threshold)
        return

    mode = "BASELINE" if baseline else "EVAL"
    print(f"=== QA Agent · {mode} ({agent}) ===\n")

    agent_config = {
        "triage": (run_triage_eval, "triage_accuracy", "Triage Accuracy"),
        "planner": (run_planner_eval, "planner_accuracy", "AC Coverage"),
        "generator": (run_generator_eval, "generator_accuracy", "Locator Quality"),
        "healer": (run_healer_eval, "healer_accuracy", "Healer Accuracy"),
    }

    if agent not in agent_config:
        print(f"[ERROR] Agent '{agent}' not supported. Choose from: {', '.join(supported)}")
        sys.exit(1)

    run_fn, accuracy_key, label_name = agent_config[agent]
    if agent == "generator":
        scorecard = await run_fn(baseline_mode=baseline)
    else:
        scorecard = await run_fn(baseline_mode=baseline, threshold=threshold)

    # Generator has a custom multi-metric format
    if agent == "generator":
        _print_generator_results(scorecard)
        return

    # Print results for standard single-metric agents
    accuracy = scorecard[accuracy_key]
    thresholds = scorecard["thresholds"]
    threshold_val = thresholds.get(accuracy_key, 0.75)

    print(f"Scenarios: {scorecard['scenarios_total']} loaded, "
          f"{scorecard['scenarios_skipped_expired']} skipped (expired)")
    print()

    # Pass/fail display
    if scorecard["passed"] is None:
        status = "BASELINE (no judgment)"
    elif scorecard["passed"]:
        status = "PASS"
    else:
        status = "FAIL"

    print(f"{label_name}:  {accuracy['score'] * 100:.1f}%  "
          f"(threshold: {threshold_val * 100:.1f}%)  {status}")

    # Category breakdown
    for cat, data in scorecard.get("by_category", {}).items():
        print(f"  {cat}:  {data['score'] * 100:.1f}%  ({data['correct']}/{data['total']})")

    # Regression
    reg = scorecard.get("regression_vs_previous")
    if reg:
        delta_str = f"{reg['delta']:+.1%}" if reg["delta"] else "+0.0%"
        print(f"\nRegression: {reg['status'].upper()} (Δ {delta_str})")
        if reg.get("new_failures"):
            print(f"  New failures: {', '.join(reg['new_failures'])}")
        if reg.get("recovered"):
            print(f"  Recovered: {', '.join(reg['recovered'])}")

    # Misses (summary only — details in report)
    if accuracy.get("misses"):
        print(f"\nMisses: {len(accuracy['misses'])} scenario(s)")

    # Recommendations
    recs = scorecard.get("recommendations", [])
    if recs:
        print(f"\nRecommendations ({len(recs)}):")
        for r in recs:
            priority = r["priority"].upper()
            print(f"\n  [{priority}] {r.get('category', 'general')}")
            print(f"    Finding: {r['finding']}")
            print(f"    Action:  {r['action']}")

    print(f"\nScorecard: {scorecard.get('eval_run_id', 'unknown')}")
    print(f"Report:    qa_agent/eval/reports/ (JSON + Markdown)")
    print(f"Overall:   {status}")

    # Exit code
    if scorecard["passed"] is False:
        sys.exit(1)
    if reg and reg.get("severity") == "major":
        sys.exit(1)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="qa-agent",
        description="QA Automation AI Agent — Playwright + LangGraph",
    )
    parser.add_argument(
        "command",
        choices=["run", "memory", "review", "crawl", "eval"],
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
    # Crawl-specific arguments
    parser.add_argument(
        "--page",
        type=str,
        default=None,
        help="Comma-separated page keys to crawl (e.g. homepage,cart,pdp). Default: all.",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Include auth-gated pages in crawl",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last progress checkpoint",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing POM/test files",
    )
    # Eval-specific arguments
    parser.add_argument(
        "--agent",
        type=str,
        default="triage",
        help="Agent to evaluate: triage, planner, generator, healer, or all (default: triage)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override accuracy threshold for eval",
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
    elif args.command == "crawl":
        pages = args.page.split(",") if args.page else None
        asyncio.run(_crawl(
            pages=pages,
            include_auth=args.auth,
            resume=args.resume,
            dry=args.dry,
            overwrite=args.overwrite,
        ))
    elif args.command == "eval":
        if args.subcommand in ("run", "baseline"):
            baseline = args.subcommand == "baseline"
            asyncio.run(_eval_run(
                agent=args.agent,
                baseline=baseline,
                threshold=args.threshold,
            ))
        else:
            print("Usage: qa-agent eval run [--agent triage] [--threshold 0.80] | baseline")
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
