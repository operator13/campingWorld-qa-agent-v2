"""Main orchestrator — iterates site map, crawls pages, generates POMs and tests."""

from __future__ import annotations

import logging
from typing import Any

from qa_agent.orchestrator.auth_handler import AuthHandler
from qa_agent.orchestrator.cart_handler import CartHandler
from qa_agent.orchestrator.crawler import PageCrawler
from qa_agent.orchestrator.dynamic_page_resolver import DynamicPageResolver
from qa_agent.orchestrator.file_writer import write_pair
from qa_agent.orchestrator.models import CrawlResult, GeneratedOutput, PageConfig
from qa_agent.orchestrator.pom_generator import generate_pom
from qa_agent.orchestrator.pom_validator import validate_pom
from qa_agent.orchestrator.progress import ProgressTracker
from qa_agent.orchestrator.site_map import SITE_MAP, get_pages_by_priority
from qa_agent.orchestrator.test_generator import generate_tests
from qa_agent.orchestrator.test_validator import validate_test
from qa_agent.orchestrator.pom_generator import _route_to_class_name
from qa_agent.orchestrator.file_writer import route_to_pom_filename, route_to_spec_filename

logger = logging.getLogger(__name__)


class Orchestrator:
    """Crawls campingworld.com pages and generates POM + test files."""

    def __init__(self, call_tool_fn: Any, overwrite: bool = False) -> None:
        """
        Args:
            call_tool_fn: async callable to invoke MCP tools.
            overwrite: If True, overwrite existing POM/test files.
        """
        self.crawler = PageCrawler(call_tool_fn)
        self.auth_handler = AuthHandler(call_tool_fn)
        self.cart_handler = CartHandler(call_tool_fn)
        self.resolver = DynamicPageResolver(call_tool_fn)
        self.progress = ProgressTracker()
        self._overwrite = overwrite

    async def crawl_site(
        self,
        pages: list[str] | None = None,
        include_auth: bool = False,
        resume: bool = False,
        dry_run: bool = False,
    ) -> CrawlResult:
        """Crawl pages and generate POM + test files.

        Args:
            pages: Specific page keys to crawl (None = all).
            include_auth: Include auth-gated pages.
            resume: Skip pages already marked done in progress tracker.
            dry_run: Navigate and snapshot only, no LLM generation.

        Returns:
            CrawlResult with counts and outputs.
        """
        if not resume:
            self.progress.reset()

        targets = self._resolve_targets(pages, include_auth)
        result = CrawlResult()

        total = len(targets)
        for i, config in enumerate(targets, 1):
            page_key = self._find_key(config)

            # Skip if already done (resume mode)
            if resume and self.progress.is_done(config.name):
                logger.info("[%d/%d] Skipping %s (already done)", i, total, config.name)
                continue

            logger.info("[%d/%d] Processing: %s", i, total, config.name)
            print(f"\n[{i}/{total}] {config.name}...")

            try:
                # Handle prerequisites
                await self._handle_prerequisites(config, page_key)

                # Resolve dynamic URLs
                if config.dynamic_url:
                    resolved = await self.resolver.resolve(page_key)
                    if resolved:
                        config = config.model_copy(update={"url": resolved.replace("https://www.campingworld.com", "")})
                    else:
                        raise RuntimeError(f"Could not resolve dynamic URL for {config.name}")

                # 1. Crawl
                snapshot = await self.crawler.crawl_page(config)
                print(f"  [OK] Snapshot captured ({len(snapshot.snapshot_text)} chars)")

                if dry_run:
                    print(f"  [DRY] DOM snapshot for {config.name}:")
                    print(snapshot.snapshot_text[:500])
                    result.pages_crawled += 1
                    self.progress.mark_done(config.name)
                    continue

                # 2. Generate POM
                pom_source = await generate_pom(snapshot)
                pom_result = validate_pom(pom_source)
                if not pom_result.valid:
                    logger.warning("POM validation warnings for %s: %s", config.name, pom_result.errors)
                    print(f"  [WARN] POM validation: {pom_result.errors}")
                print(f"  [OK] POM generated ({len(pom_source)} bytes)")

                # 3. Generate tests
                test_source = await generate_tests(pom_source, config, snapshot)
                class_name = _route_to_class_name(config.route)
                test_result = validate_test(test_source, pom_class_name=class_name)
                if not test_result.valid:
                    logger.warning("Test validation warnings for %s: %s", config.name, test_result.errors)
                    print(f"  [WARN] Test validation: {test_result.errors}")
                print(f"  [OK] Tests generated ({len(test_source)} bytes)")

                # 4. Write files
                pom_path, test_path = write_pair(config, pom_source, test_source, overwrite=self._overwrite)
                print(f"  [OK] Written: {pom_path.name}, {test_path.name}")

                # 5. Track output
                output = GeneratedOutput(
                    page_config=config,
                    pom_filename=route_to_pom_filename(config.route),
                    pom_source=pom_source,
                    test_filename=route_to_spec_filename(config.route),
                    test_source=test_source,
                )
                result.outputs.append(output)
                result.pages_crawled += 1
                self.progress.mark_done(config.name)

            except Exception as e:
                error_msg = f"{config.name}: {e}"
                logger.error("Failed to process %s: %s", config.name, e)
                print(f"  [FAIL] {e}")
                result.errors.append(error_msg)
                result.pages_failed += 1
                self.progress.mark_failed(config.name, str(e))

        # Print summary
        self._print_summary(result)
        return result

    def _resolve_targets(
        self, pages: list[str] | None, include_auth: bool
    ) -> list[PageConfig]:
        """Resolve which pages to crawl."""
        if pages:
            targets = []
            for key in pages:
                if key in SITE_MAP:
                    targets.append(SITE_MAP[key])
                else:
                    logger.warning("Unknown page key: %s (skipping)", key)
            return targets
        return get_pages_by_priority(include_auth=include_auth)

    def _find_key(self, config: PageConfig) -> str:
        """Find the SITE_MAP key for a PageConfig."""
        for key, val in SITE_MAP.items():
            if val.name == config.name:
                return key
        return config.name.lower().replace(" ", "_")

    async def _handle_prerequisites(self, config: PageConfig, page_key: str) -> None:
        """Handle auth and cart prerequisites before crawling."""
        if config.requires_auth:
            await self.auth_handler.ensure_authenticated()

        if page_key in ("cart", "checkout"):
            await self.cart_handler.ensure_cart_has_item()

    def _print_summary(self, result: CrawlResult) -> None:
        """Print a final crawl summary."""
        print(f"\n{'=' * 50}")
        print(f"  Crawl Complete")
        print(f"{'=' * 50}")
        print(f"  Pages crawled: {result.pages_crawled}")
        print(f"  Pages failed:  {result.pages_failed}")
        print(f"  POM files:     {len(result.outputs)}")
        print(f"  Test files:    {len(result.outputs)}")
        if result.errors:
            print(f"\n  Errors:")
            for err in result.errors:
                print(f"    - {err}")
        print(f"{'=' * 50}")

        progress = self.progress.summary()
        if progress["done"]:
            print(f"\n  Done: {', '.join(progress['done'])}")
        if progress["failed"]:
            print(f"  Failed: {', '.join(progress['failed'])}")
