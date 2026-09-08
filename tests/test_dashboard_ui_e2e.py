"""Real browser E2E tests using Playwright.

Each agent runs exactly ONCE — all assertions happen during that single run.
No duplicate eval executions.

Run with: pytest tests/test_dashboard_ui_e2e.py -v
Requires: docker compose up + pip install playwright && playwright install chromium
"""
import re
import time
from pathlib import Path

import pytest
import requests

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright, expect

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"

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


def _wait_for_idle(section="eval"):
    for _ in range(120):
        try:
            r = requests.get(f"{WORKER_URL}/api/worker/status", timeout=3)
            s = r.json()[section if section != "ecc" else "ecc_eval"]["state"]
            if s == "idle":
                return
        except Exception:
            pass
        time.sleep(1)


@pytest.fixture(scope="module")
def browser():
    try:
        requests.get(f"{DASHBOARD_URL}/health", timeout=3)
        requests.get(f"{WORKER_URL}/health", timeout=3)
    except Exception:
        pytest.skip("Docker stack not running")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    pg = context.new_page()
    pg.goto(DASHBOARD_URL, wait_until="networkidle")
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# ---------------------------------------------------------------------------
# Pipeline Eval: One test per agent — full lifecycle in single run
# ---------------------------------------------------------------------------


class TestPipelineEvalFullLifecycle:
    """Click RUN on each pipeline agent ONCE and verify the full lifecycle."""

    @pytest.mark.parametrize("agent", PIPELINE_AGENTS)
    def test_full_lifecycle(self, page, agent):
        """Click RUN on {agent} → Running... → progress bar → 100% → score restored."""
        _wait_for_idle("eval")
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        # 1. Card starts in idle state
        expect(btn).to_be_visible()
        expect(card.locator('.eval-score')).not_to_have_text('Running...')

        # 2. Click RUN
        btn.click()

        # 3. Card shows Running... immediately
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))

        # 4. RUN button hidden, EVAL ALL hidden, STOP visible
        expect(btn).to_be_hidden()
        expect(page.locator('#btn-eval-all')).to_be_hidden()
        expect(page.locator('#btn-eval-stop')).to_be_visible()

        # 5. Tooltip still clickable during run
        card.locator('.eval-info-icon').click()
        expect(card.locator('.eval-tooltip')).to_have_class(re.compile('tooltip-open'))
        page.click('body')  # close tooltip

        # 6. Progress bar appears and updates
        progress = card.locator('.eval-progress-container')
        expect(progress).to_be_visible(timeout=10000)
        progress_text = card.locator('.eval-progress-text')
        expect(progress_text).not_to_have_text('0%', timeout=60000)

        # 7. Wait for completion — score becomes a percentage
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

        # 8. RUN button restored, EVAL ALL restored
        expect(btn).to_be_visible()
        expect(page.locator('#btn-eval-all')).to_be_visible()

        # 9. Badge shows PASS or FAIL
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))


# ---------------------------------------------------------------------------
# EVAL ALL: Runs all 4 in parallel — one test
# ---------------------------------------------------------------------------


class TestEvalAllFullLifecycle:
    """Click EVAL ALL once and verify all 4 agents complete."""

    def test_eval_all_full_lifecycle(self, page):
        """EVAL ALL → all 4 Running... → progress → all complete with scores."""
        _wait_for_idle("eval")
        page.locator('#btn-eval-all').click()

        # All 4 show Running...
        for agent in PIPELINE_AGENTS:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        # STOP visible
        expect(page.locator('#btn-eval-stop')).to_be_visible()

        # All 4 complete with scores
        for agent in PIPELINE_AGENTS:
            card = page.locator(f'.eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

        # EVAL ALL restored
        expect(page.locator('#btn-eval-all')).to_be_visible()


# ---------------------------------------------------------------------------
# ECC Detection: One test per agent — full lifecycle
# ---------------------------------------------------------------------------


class TestEccDetectionFullLifecycle:
    """Click RUN on each detection agent ONCE and verify lifecycle."""

    @pytest.mark.parametrize("agent", ECC_DETECTION_AGENTS)
    def test_full_lifecycle(self, page, agent):
        """Click RUN on {agent} → Running... → metrics hidden → complete → metrics restored."""
        _wait_for_idle("ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        # 1. Idle state
        expect(btn).to_be_visible()

        # 2. Click RUN
        btn.click()

        # 3. Running state
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))
        expect(btn).to_be_hidden()

        # 4. Detail metrics hidden during run
        expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

        # 5. Wait for completion
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=180000)

        # 6. Metrics restored
        expect(card.locator('.ecc-detail-metrics')).to_be_visible()
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
        expect(btn).to_be_visible()


# ---------------------------------------------------------------------------
# ECC Generative: One test per agent — full lifecycle
# ---------------------------------------------------------------------------


class TestEccGenerativeFullLifecycle:
    """Click RUN on each generative agent ONCE and verify lifecycle."""

    @pytest.mark.parametrize("agent", ECC_GENERATIVE_AGENTS)
    def test_full_lifecycle(self, page, agent):
        """Click RUN on {agent} → Running... → metrics hidden → complete → metrics restored."""
        _wait_for_idle("ecc")
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        btn = card.locator('.eval-run-btn')

        expect(btn).to_be_visible()
        btn.click()

        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
        expect(card).to_have_class(re.compile('eval-running'))
        expect(btn).to_be_hidden()
        expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=180000)

        expect(card.locator('.ecc-detail-metrics')).to_be_visible()
        expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
        expect(btn).to_be_visible()


# ---------------------------------------------------------------------------
# EVAL ECC AGENTS: All 12 in parallel — one test
# ---------------------------------------------------------------------------


class TestEvalEccAgentsFullLifecycle:
    """Click EVAL ECC AGENTS once and verify all 12 cards."""

    def test_eval_ecc_all_full_lifecycle(self, page):
        """EVAL ECC AGENTS → all 12 Running... → all complete with scores."""
        _wait_for_idle("ecc")
        page.locator('#btn-ecc-eval-all').click()

        # All 12 running
        for agent in ECC_ALL_AGENTS:
            card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)
            expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

        # STOP visible
        expect(page.locator('#btn-ecc-eval-stop')).to_be_visible()

        # All 12 complete
        for agent in ECC_ALL_AGENTS:
            card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
            expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

        expect(page.locator('#btn-ecc-eval-all')).to_be_visible()


# ---------------------------------------------------------------------------
# STOP buttons
# ---------------------------------------------------------------------------


class TestStopButtons:
    """STOP cancels running evals and restores UI."""

    def test_stop_pipeline_eval(self, page):
        _wait_for_idle("eval")
        page.locator('#btn-eval-all').click()
        card = page.locator('.eval-card[data-agent="triage"]')
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        page.locator('#btn-eval-stop').click()
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=10000)
        expect(page.locator('#btn-eval-all')).to_be_visible()

    def test_stop_ecc_eval(self, page):
        _wait_for_idle("ecc")
        page.locator('#btn-ecc-eval-all').click()
        card = page.locator('.ecc-eval-card').first
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

        page.locator('#btn-ecc-eval-stop').click()
        expect(page.locator('#btn-ecc-eval-all')).to_be_visible(timeout=10000)


# ---------------------------------------------------------------------------
# Independent section disable
# ---------------------------------------------------------------------------


class TestIndependentSections:
    """Pipeline, ECC, and test runner are independent."""

    def test_pipeline_does_not_block_ecc(self, page):
        _wait_for_idle("eval")
        page.locator('.eval-card[data-agent="triage"] .eval-run-btn').click()
        expect(page.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=2000)

        ecc_btn = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn')
        expect(ecc_btn).to_be_visible()
        expect(ecc_btn).to_be_enabled()

    def test_ecc_does_not_block_pipeline(self, page):
        _wait_for_idle("ecc")
        page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn').click()
        expect(page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-score')).to_have_text('Running...', timeout=2000)

        expect(page.locator('#btn-eval-all')).to_be_visible()
        expect(page.locator('#btn-eval-all')).to_be_enabled()


# ---------------------------------------------------------------------------
# Worker indicator + cross-device sync
# ---------------------------------------------------------------------------


class TestWorkerAndSync:
    def test_worker_online(self, page):
        page.wait_for_timeout(5000)
        expect(page.locator('#worker-status')).to_have_text('WORKER ONLINE', timeout=10000)

    def test_two_tabs_sync(self, browser):
        _wait_for_idle("eval")
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
