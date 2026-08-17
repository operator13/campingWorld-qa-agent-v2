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


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="qa-agent",
        description="QA Automation AI Agent — Playwright + LangGraph",
    )
    parser.add_argument(
        "command",
        choices=["run"],
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
    else:
        parser.print_help()
        sys.exit(1)
