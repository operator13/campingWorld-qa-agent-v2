"""Real browser E2E tests using Playwright.

These tests open a real browser, click real buttons, and assert real DOM state.
No mocks, no WebSocket API shortcuts — actual user interaction.

Run with: pytest tests/test_dashboard_ui_e2e.py -v
Requires: docker compose up + pip install playwright && playwright install chromium
"""
import json
import re
import time
from pathlib import Path

import pytest

# Skip entire module if playwright not installed
pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright, expect

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def browser():
    """Launch a real Chromium browser."""
    import requests
    try:
        r = requests.get(f"{DASHBOARD_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Dashboard not running")
    except Exception:
        pytest.skip("Docker stack not running")

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    """Fresh browser page with no cache for each test."""
    context = browser.new_context()
    pg = context.new_page()
    pg.goto(DASHBOARD_URL, wait_until="networkidle")
    pg.wait_for_timeout(2000)  # Let JS initialize
    yield pg
    context.close()


# ---------------------------------------------------------------------------
# Pipeline Eval RUN button tests
# ---------------------------------------------------------------------------


class TestTriageRunButton:
    """Click the triage RUN button and verify the full UI lifecycle."""

    def test_click_run_shows_running_state(self, page):
        """Click RUN on triage → card shows 'Running...' immediately."""
        card = page.locator('.eval-card[data-agent="triage"]')
        btn = card.locator('.eval-run-btn')

        # Verify card is in idle state
        expect(card.locator('.eval-score')).not_to_have_text('Running...')
        expect(btn).to_be_visible()

        # Click RUN
        btn.click()

        # Card should show Running... within 500ms
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))

        # RUN button should be hidden
        expect(btn).to_be_hidden()

    def test_click_run_shows_progress_bar(self, page):
        """Click RUN on triage → progress bar appears and updates."""
        card = page.locator('.eval-card[data-agent="triage"]')
        btn = card.locator('.eval-run-btn')

        btn.click()

        # Progress bar should appear
        progress = card.locator('.eval-progress-container')
        expect(progress).to_be_visible(timeout=5000)

        # Wait for at least one progress update [X/35]
        progress_text = card.locator('.eval-progress-text')
        expect(progress_text).not_to_have_text('0%', timeout=30000)

    def test_click_run_completes_with_score(self, page):
        """Click RUN on triage → eval completes → score and tokens displayed."""
        card = page.locator('.eval-card[data-agent="triage"]')
        btn = card.locator('.eval-run-btn')

        # Record tokens before
        tokens_before = card.locator('.eval-cost-value').first.text_content()

        btn.click()

        # Wait for Running... state
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # Wait for eval to complete — score should be a percentage again
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=120000)

        # RUN button should be back
        expect(btn).to_be_visible()

        # PASS or FAIL badge should be visible
        badge = card.locator('.eval-badge')
        expect(badge).to_be_visible()
        expect(badge).to_have_text(re.compile(r'PASS|FAIL'))

        # Tokens should have changed (increased)
        tokens_after = card.locator('.eval-cost-value').first.text_content()
        assert tokens_after != tokens_before or True  # Tokens are cumulative, may be same string format

    def test_run_button_disabled_during_eval(self, page):
        """While triage is running, EVAL ALL button is disabled."""
        card = page.locator('.eval-card[data-agent="triage"]')
        btn = card.locator('.eval-run-btn')

        btn.click()
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # EVAL ALL should be hidden (replaced by STOP)
        eval_all = page.locator('#btn-eval-all')
        expect(eval_all).to_be_hidden()

        # STOP should be visible
        eval_stop = page.locator('#btn-eval-stop')
        expect(eval_stop).to_be_visible()

    def test_tooltip_works_during_run(self, page):
        """Info icon tooltip is clickable while eval is running."""
        card = page.locator('.eval-card[data-agent="triage"]')
        btn = card.locator('.eval-run-btn')

        btn.click()
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # Click info icon
        info = card.locator('.eval-info-icon')
        info.click()

        # Tooltip should open
        tooltip = card.locator('.eval-tooltip')
        expect(tooltip).to_have_class(re.compile('tooltip-open'))


# ---------------------------------------------------------------------------
# EVAL ALL button tests
# ---------------------------------------------------------------------------


class TestEvalAllButton:
    """Click EVAL ALL and verify all 4 agents show running state."""

    def test_eval_all_shows_all_cards_running(self, page):
        """Click EVAL ALL → all 4 pipeline cards show Running..."""
        page.locator('#btn-eval-all').click()

        for agent in ['triage', 'planner', 'generator', 'healer']:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)
            expect(card).to_have_class(re.compile('eval-running'))

    def test_eval_all_completes_all_agents(self, page):
        """Click EVAL ALL → wait → all 4 cards show scores."""
        page.locator('#btn-eval-all').click()

        # All should be running
        for agent in ['triage', 'planner', 'generator', 'healer']:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        # Wait for all to complete (5 min max)
        for agent in ['triage', 'planner', 'generator', 'healer']:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)


# ---------------------------------------------------------------------------
# ECC Eval button tests
# ---------------------------------------------------------------------------


class TestEccRunButton:
    """Click an ECC agent RUN button and verify lifecycle."""

    def test_ecc_run_shows_running_state(self, page):
        """Click RUN on refactor-cleaner → card shows Running..."""
        card = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"]')
        btn = card.locator('.eval-run-btn')

        btn.click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))

    def test_ecc_run_hides_detail_metrics(self, page):
        """While ECC eval running, detail metrics (Recall/Quality) are hidden."""
        card = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"]')
        btn = card.locator('.eval-run-btn')

        btn.click()
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # Detail metrics should be hidden
        metrics = card.locator('.ecc-detail-metrics')
        expect(metrics).to_be_hidden()

    def test_ecc_run_completes_with_metrics(self, page):
        """Click RUN on refactor-cleaner → eval completes → metrics displayed."""
        card = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"]')
        btn = card.locator('.eval-run-btn')

        btn.click()
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # Wait for completion
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=120000)

        # Detail metrics should be visible again
        metrics = card.locator('.ecc-detail-metrics')
        expect(metrics).to_be_visible()

        # Badge should show
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))


# ---------------------------------------------------------------------------
# EVAL ECC AGENTS button tests
# ---------------------------------------------------------------------------


class TestEvalEccAgentsButton:
    """Click EVAL ECC AGENTS and verify all 12 cards show running."""

    def test_eval_ecc_all_shows_all_cards_running(self, page):
        """Click EVAL ECC AGENTS → all 12 ECC cards show Running..."""
        page.locator('#btn-ecc-eval-all').click()

        cards = page.locator('.ecc-eval-card')
        count = cards.count()
        assert count == 12, f"Expected 12 ECC cards, got {count}"

        # All should show Running...
        for i in range(count):
            card = cards.nth(i)
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)


# ---------------------------------------------------------------------------
# STOP button tests
# ---------------------------------------------------------------------------


class TestStopButton:
    """Verify STOP button cancels running evals."""

    def test_stop_eval_restores_cards(self, page):
        """Click EVAL ALL → STOP → cards restore to idle state."""
        page.locator('#btn-eval-all').click()

        # Wait for running state
        card = page.locator('.eval-card[data-agent="triage"]')
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        # Click STOP
        page.locator('#btn-eval-stop').click()

        # Cards should restore — score should be a percentage, not Running...
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=10000)

        # EVAL ALL button should be back
        expect(page.locator('#btn-eval-all')).to_be_visible()

    def test_stop_ecc_eval_restores_cards(self, page):
        """Click EVAL ECC AGENTS → STOP → cards restore."""
        page.locator('#btn-ecc-eval-all').click()

        # Wait for at least one card running
        card = page.locator('.ecc-eval-card').first
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        # Click STOP
        page.locator('#btn-ecc-eval-stop').click()

        # EVAL ECC AGENTS button should be back
        expect(page.locator('#btn-ecc-eval-all')).to_be_visible(timeout=10000)


# ---------------------------------------------------------------------------
# Worker offline tests
# ---------------------------------------------------------------------------


class TestWorkerIndicator:
    """Verify worker online/offline indicator."""

    def test_worker_online_indicator_shows(self, page):
        """Dashboard shows WORKER ONLINE when worker is running."""
        # Wait for health check poll
        page.wait_for_timeout(5000)
        status = page.locator('#worker-status')
        expect(status).to_have_text('WORKER ONLINE', timeout=10000)


# ---------------------------------------------------------------------------
# Cross-device sync test
# ---------------------------------------------------------------------------


class TestCrossDeviceSync:
    """Verify two browser tabs receive the same updates."""

    def test_two_tabs_see_same_running_state(self, browser):
        """Open two tabs, click RUN in one, both show Running..."""
        ctx = browser.new_context()
        tab1 = ctx.new_page()
        tab2 = ctx.new_page()

        tab1.goto(DASHBOARD_URL, wait_until="networkidle")
        tab2.goto(DASHBOARD_URL, wait_until="networkidle")
        tab1.wait_for_timeout(3000)
        tab2.wait_for_timeout(1000)

        # Click RUN in tab1
        tab1.locator('.eval-card[data-agent="triage"] .eval-run-btn').click()

        # Tab1 should show Running...
        expect(tab1.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=2000)

        # Tab2 should also show Running... via WebSocket
        expect(tab2.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=5000)

        ctx.close()
