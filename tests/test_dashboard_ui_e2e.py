"""Real browser E2E tests using Playwright.

These tests open a real browser, click real buttons, and assert real DOM state.
No mocks, no WebSocket API shortcuts — actual user interaction.
Every RUN button on the dashboard is tested.

Run with: pytest tests/test_dashboard_ui_e2e.py -v
Requires: docker compose up + pip install playwright && playwright install chromium
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright, expect

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

PIPELINE_AGENTS = ["triage", "planner", "generator", "healer"]
ECC_DETECTION_AGENTS = [
    "security-reviewer", "code-reviewer", "silent-failure-hunter",
    "python-reviewer", "typescript-reviewer", "fastapi-reviewer",
    "performance-optimizer",
]
ECC_GENERATIVE_AGENTS = [
    "planner-ecc", "tdd-guide", "build-error-resolver",
    "e2e-runner", "refactor-cleaner",
]
ECC_ALL_AGENTS = ECC_DETECTION_AGENTS + ECC_GENERATIVE_AGENTS


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
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


def _wait_for_idle(page, section="eval"):
    """Wait until no cards are in running state for the section."""
    import requests, time
    if section == "eval":
        for _ in range(60):
            r = requests.get(f"{WORKER_URL}/api/worker/status", timeout=3)
            if r.json()["eval"]["state"] == "idle":
                return
            time.sleep(2)
    elif section == "ecc":
        for _ in range(60):
            r = requests.get(f"{WORKER_URL}/api/worker/status", timeout=3)
            if r.json()["ecc_eval"]["state"] == "idle":
                return
            time.sleep(2)


# ---------------------------------------------------------------------------
# Pipeline Eval: Individual RUN button per agent
# ---------------------------------------------------------------------------


class TestPipelineEvalRunButtons:
    """Click RUN on each of the 4 pipeline eval agents and verify UI lifecycle."""

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_click_run_shows_running_state(self, page, agent):
        """Click RUN on {agent} → card shows 'Running...' and eval-running class."""
        _wait_for_idle(page, "eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        expect(btn).to_be_visible()
        btn.click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))
        expect(btn).to_be_hidden()

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_click_run_shows_progress_bar(self, page, agent):
        """Click RUN on {agent} → progress bar appears with scenario count."""
        _wait_for_idle(page, "eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        progress = card.locator('.eval-progress-container')
        expect(progress).to_be_visible(timeout=5000)

        progress_text = card.locator('.eval-progress-text')
        expect(progress_text).not_to_have_text('0%', timeout=60000)

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_click_run_completes_with_score(self, page, agent):
        """Click RUN on {agent} → eval completes → score, badge, tokens displayed."""
        _wait_for_idle(page, "eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        btn.click()
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        # Wait for completion (5 min max)
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

        expect(btn).to_be_visible()
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_eval_all_hidden_during_run(self, page, agent):
        """While {agent} is running, EVAL ALL is hidden and STOP is shown."""
        _wait_for_idle(page, "eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(page.locator('#btn-eval-all')).to_be_hidden()
        expect(page.locator('#btn-eval-stop')).to_be_visible()

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_tooltip_clickable_during_run(self, page, agent):
        """Info icon tooltip works while {agent} eval is running."""
        _wait_for_idle(page, "eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)

        card.locator('.eval-info-icon').click()
        expect(card.locator('.eval-tooltip')).to_have_class(re.compile('tooltip-open'))


# ---------------------------------------------------------------------------
# Pipeline Eval: EVAL ALL button
# ---------------------------------------------------------------------------


class TestEvalAllButton:
    """Click EVAL ALL and verify all 4 agents run simultaneously."""

    def test_eval_all_shows_all_cards_running(self, page):
        """Click EVAL ALL → all 4 pipeline cards show Running..."""
        _wait_for_idle(page, "eval")
        page.locator('#btn-eval-all').click()

        for agent in PIPELINE_AGENTS:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)
            expect(card).to_have_class(re.compile('eval-running'))

    def test_eval_all_completes_all_agents(self, page):
        """Click EVAL ALL → all 4 cards eventually show scores."""
        _wait_for_idle(page, "eval")
        page.locator('#btn-eval-all').click()

        for agent in PIPELINE_AGENTS:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        for agent in PIPELINE_AGENTS:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)


# ---------------------------------------------------------------------------
# ECC Eval: Individual RUN button per agent
# ---------------------------------------------------------------------------


class TestEccDetectionRunButtons:
    """Click RUN on each of the 7 detection agents and verify UI lifecycle."""

    @pytest.mark.parametrize("agent", ECC_DETECTION_AGENTS)
    def test_click_run_shows_running_state(self, page, agent):
        """Click RUN on {agent} → card shows 'Running...' with eval-running class."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        expect(btn).to_be_visible()
        btn.click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))
        expect(btn).to_be_hidden()

    @pytest.mark.parametrize("agent", ECC_DETECTION_AGENTS)
    def test_click_run_hides_detail_metrics(self, page, agent):
        """While {agent} is running, Recall/Precision/FP Rate are hidden."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    @pytest.mark.parametrize("agent", ECC_DETECTION_AGENTS)
    def test_click_run_completes_with_metrics(self, page, agent):
        """Click RUN on {agent} → eval completes → score, badge, metrics visible."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=180000)

        expect(card.locator('.ecc-detail-metrics')).to_be_visible()
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
        expect(card.locator('.eval-run-btn')).to_be_visible()


class TestEccGenerativeRunButtons:
    """Click RUN on each of the 5 generative agents and verify UI lifecycle."""

    @pytest.mark.parametrize("agent", ECC_GENERATIVE_AGENTS)
    def test_click_run_shows_running_state(self, page, agent):
        """Click RUN on {agent} → card shows 'Running...' with eval-running class."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        expect(btn).to_be_visible()
        btn.click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))
        expect(btn).to_be_hidden()

    @pytest.mark.parametrize("agent", ECC_GENERATIVE_AGENTS)
    def test_click_run_hides_detail_metrics(self, page, agent):
        """While {agent} is running, Quality/Complete/Actionable etc. are hidden."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    @pytest.mark.parametrize("agent", ECC_GENERATIVE_AGENTS)
    def test_click_run_completes_with_metrics(self, page, agent):
        """Click RUN on {agent} → eval completes → score, badge, metrics visible."""
        _wait_for_idle(page, "ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        card.locator('.eval-run-btn').click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=180000)

        expect(card.locator('.ecc-detail-metrics')).to_be_visible()
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
        expect(card.locator('.eval-run-btn')).to_be_visible()


# ---------------------------------------------------------------------------
# EVAL ECC AGENTS button
# ---------------------------------------------------------------------------


class TestEvalEccAgentsButton:
    """Click EVAL ECC AGENTS and verify all 12 cards show running."""

    def test_eval_ecc_all_shows_all_12_cards_running(self, page):
        """Click EVAL ECC AGENTS → all 12 ECC cards show Running..."""
        _wait_for_idle(page, "ecc")
        page.locator('#btn-ecc-eval-all').click()

        for agent in ECC_ALL_AGENTS:
            card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

    def test_eval_ecc_all_hides_all_detail_metrics(self, page):
        """While EVAL ECC AGENTS running, all detail metrics hidden."""
        _wait_for_idle(page, "ecc")
        page.locator('#btn-ecc-eval-all').click()

        for agent in ECC_ALL_AGENTS:
            card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)
            expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    def test_eval_ecc_all_shows_stop_button(self, page):
        """While running, EVAL ECC AGENTS hidden and STOP visible."""
        _wait_for_idle(page, "ecc")
        page.locator('#btn-ecc-eval-all').click()

        page.locator('.ecc-eval-card').first.locator('.eval-score')
        page.wait_for_timeout(1000)

        expect(page.locator('#btn-ecc-eval-all')).to_be_hidden()
        expect(page.locator('#btn-ecc-eval-stop')).to_be_visible()


# ---------------------------------------------------------------------------
# STOP buttons
# ---------------------------------------------------------------------------


class TestStopButtons:
    """Verify STOP buttons cancel running evals and restore UI."""

    def test_stop_pipeline_eval_restores_cards(self, page):
        """Click EVAL ALL → STOP → cards restore with scores."""
        _wait_for_idle(page, "eval")
        page.locator('#btn-eval-all').click()

        card = page.locator('.eval-card[data-agent="triage"]')
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        page.locator('#btn-eval-stop').click()

        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=10000)
        expect(page.locator('#btn-eval-all')).to_be_visible()

    def test_stop_ecc_eval_restores_cards(self, page):
        """Click EVAL ECC AGENTS → STOP → cards restore."""
        _wait_for_idle(page, "ecc")
        page.locator('#btn-ecc-eval-all').click()

        card = page.locator('.ecc-eval-card').first
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        page.locator('#btn-ecc-eval-stop').click()

        expect(page.locator('#btn-ecc-eval-all')).to_be_visible(timeout=10000)


# ---------------------------------------------------------------------------
# Independent section disable
# ---------------------------------------------------------------------------


class TestIndependentSectionDisable:
    """Pipeline evals, ECC evals, and test runner are independent."""

    def test_pipeline_eval_does_not_disable_ecc_buttons(self, page):
        """Running a pipeline eval leaves ECC RUN buttons enabled."""
        _wait_for_idle(page, "eval")
        page.locator('.eval-card[data-agent="triage"] .eval-run-btn').click()

        expect(page.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=2000)

        ecc_btn = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn')
        expect(ecc_btn).to_be_visible()
        expect(ecc_btn).to_be_enabled()

    def test_ecc_eval_does_not_disable_pipeline_buttons(self, page):
        """Running an ECC eval leaves pipeline EVAL ALL button enabled."""
        _wait_for_idle(page, "ecc")
        page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn').click()

        expect(page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-score')).to_have_text('Running...', timeout=2000)

        eval_all = page.locator('#btn-eval-all')
        expect(eval_all).to_be_visible()
        expect(eval_all).to_be_enabled()


# ---------------------------------------------------------------------------
# Worker indicator
# ---------------------------------------------------------------------------


class TestWorkerIndicator:
    """Verify worker online/offline indicator."""

    def test_worker_online_shows(self, page):
        """Dashboard shows WORKER ONLINE."""
        page.wait_for_timeout(5000)
        expect(page.locator('#worker-status')).to_have_text('WORKER ONLINE', timeout=10000)


# ---------------------------------------------------------------------------
# Cross-device sync
# ---------------------------------------------------------------------------


class TestCrossDeviceSync:
    """Two browser tabs both see running state."""

    def test_two_tabs_see_same_running_state(self, browser):
        """Click RUN in tab1 → tab2 also shows Running... via WebSocket."""
        _wait_for_idle(None, "eval")
        ctx = browser.new_context()
        tab1 = ctx.new_page()
        tab2 = ctx.new_page()

        tab1.goto(DASHBOARD_URL, wait_until="networkidle")
        tab2.goto(DASHBOARD_URL, wait_until="networkidle")
        tab1.wait_for_timeout(3000)
        tab2.wait_for_timeout(1000)

        tab1.locator('.eval-card[data-agent="triage"] .eval-run-btn').click()

        expect(tab1.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=2000)
        expect(tab2.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=5000)

        ctx.close()
