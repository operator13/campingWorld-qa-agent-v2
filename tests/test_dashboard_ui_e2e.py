"""Real browser E2E tests using Playwright.

11 tests covering every UI flow. Each code path tested once — no duplicate evals.

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


def _wait_for_idle(section="eval"):
    """Wait for worker to be idle AND reset dashboard state."""
    key = section if section != "ecc" else "ecc_eval"
    for _ in range(120):
        try:
            r = requests.get(f"{WORKER_URL}/api/worker/status", timeout=3)
            if r.json()[key]["state"] == "idle":
                if section == "ecc":
                    requests.post(f"{DASHBOARD_URL}/api/eval/ecc/broadcast",
                                  json={"event": "ecc_eval:complete", "completed": 0, "total": 0}, timeout=3)
                else:
                    requests.post(f"{DASHBOARD_URL}/api/worker/broadcast",
                                  json={"event": "eval:complete", "completed": 0, "failed": 0}, timeout=3)
                time.sleep(0.5)
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


# 1. Single pipeline agent full lifecycle (triage)
def test_pipeline_agent_lifecycle(page):
    """Click RUN on triage → Running... → progress → score → badge → buttons restored."""
    _wait_for_idle("eval")
    card = page.locator('.eval-card[data-agent="triage"]')
    btn = card.locator('.eval-run-btn')

    expect(btn).to_be_visible()
    btn.click()

    expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
    expect(card).to_have_class(re.compile('eval-running'))
    expect(btn).to_be_hidden()
    expect(page.locator('#btn-eval-all')).to_be_hidden()
    expect(page.locator('#btn-eval-stop')).to_be_visible()

    card.locator('.eval-info-icon').click()
    expect(card.locator('.eval-tooltip')).to_have_class(re.compile('tooltip-open'))
    page.click('body')

    progress = card.locator('.eval-progress-container')
    expect(progress).to_be_visible(timeout=10000)
    expect(card.locator('.eval-progress-text')).not_to_have_text('0%', timeout=60000)

    expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)
    expect(btn).to_be_visible()
    expect(page.locator('#btn-eval-all')).to_be_visible()
    expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))


# 2. EVAL ALL — all 4 pipeline agents in parallel
def test_eval_all(page):
    """EVAL ALL → 4 cards Running... → all complete with scores."""
    _wait_for_idle("eval")
    page.locator('#btn-eval-all').click()

    for agent in ['triage', 'planner', 'generator', 'healer']:
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

    expect(page.locator('#btn-eval-stop')).to_be_visible()

    for agent in ['triage', 'planner', 'generator', 'healer']:
        card = page.locator(f'.eval-card[data-agent="{agent}"]')
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

    expect(page.locator('#btn-eval-all')).to_be_visible()


# 3. Single ECC detection agent lifecycle (code-reviewer — fast, 15 scenarios)
def test_ecc_detection_lifecycle(page):
    """Click RUN on code-reviewer → Running... → metrics hidden → complete → metrics back."""
    _wait_for_idle("ecc")
    card = page.locator('.ecc-eval-card[data-agent="code-reviewer"]')
    btn = card.locator('.eval-run-btn')

    expect(btn).to_be_visible()
    btn.click()

    expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
    expect(card).to_have_class(re.compile('eval-running'))
    expect(btn).to_be_hidden()
    expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)
    expect(card.locator('.ecc-detail-metrics')).to_be_visible()
    expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
    expect(btn).to_be_visible()


# 4. Single ECC generative agent lifecycle (build-error-resolver — fast, 10 scenarios)
def test_ecc_generative_lifecycle(page):
    """Click RUN on build-error-resolver → Running... → metrics hidden → complete → metrics back."""
    _wait_for_idle("ecc")
    card = page.locator('.ecc-eval-card[data-agent="build-error-resolver"]')
    btn = card.locator('.eval-run-btn')

    expect(btn).to_be_visible()
    btn.click()

    expect(card.locator('.eval-score')).to_have_text('Running...', timeout=2000)
    expect(card).to_have_class(re.compile('eval-running'))
    expect(btn).to_be_hidden()
    expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)
    expect(card.locator('.ecc-detail-metrics')).to_be_visible()
    expect(card.locator('.eval-badge')).to_have_text(re.compile(r'PASS|FAIL'))
    expect(btn).to_be_visible()


# 5. EVAL ECC AGENTS — all 12 in parallel
def test_eval_ecc_all(page):
    """EVAL ECC AGENTS → 12 cards Running... → all complete."""
    _wait_for_idle("ecc")
    page.locator('#btn-ecc-eval-all').click()

    ecc_agents = [
        "security-reviewer", "code-reviewer", "silent-failure-hunter",
        "python-reviewer", "typescript-reviewer", "fastapi-reviewer",
        "performance-optimizer", "planner-ecc", "tdd-guide",
        "build-error-resolver", "e2e-runner", "refactor-cleaner",
    ]

    for agent in ecc_agents:
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)
        expect(card.locator('.ecc-detail-metrics')).to_be_hidden()

    expect(page.locator('#btn-ecc-eval-stop')).to_be_visible()

    for agent in ecc_agents:
        card = page.locator(f'.ecc-eval-card[data-agent="{agent}"]')
        expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=300000)

    expect(page.locator('#btn-ecc-eval-all')).to_be_visible()


# 6. STOP pipeline eval
def test_stop_pipeline_eval(page):
    """EVAL ALL → STOP → cards restore."""
    _wait_for_idle("eval")
    page.locator('#btn-eval-all').click()

    card = page.locator('.eval-card[data-agent="triage"]')
    expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

    page.locator('#btn-eval-stop').click()

    expect(card.locator('.eval-score')).to_have_text(re.compile(r'\d+\.\d+%'), timeout=10000)
    expect(page.locator('#btn-eval-all')).to_be_visible()


# 7. STOP ECC eval
def test_stop_ecc_eval(page):
    """EVAL ECC AGENTS → STOP → buttons restore."""
    _wait_for_idle("ecc")
    page.locator('#btn-ecc-eval-all').click()

    card = page.locator('.ecc-eval-card').first
    expect(card.locator('.eval-score')).to_have_text('Running...', timeout=5000)

    page.locator('#btn-ecc-eval-stop').click()

    expect(page.locator('#btn-ecc-eval-all')).to_be_visible(timeout=10000)


# 8. Pipeline eval does not block ECC
def test_pipeline_does_not_block_ecc(page):
    """Running triage leaves ECC buttons enabled."""
    _wait_for_idle("eval")
    page.locator('.eval-card[data-agent="triage"] .eval-run-btn').click()
    expect(page.locator('.eval-card[data-agent="triage"] .eval-score')).to_have_text('Running...', timeout=2000)

    ecc_btn = page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn')
    expect(ecc_btn).to_be_visible()
    expect(ecc_btn).to_be_enabled()


# 9. ECC eval does not block pipeline
def test_ecc_does_not_block_pipeline(page):
    """Running ECC agent leaves EVAL ALL enabled."""
    _wait_for_idle("ecc")
    page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-run-btn').click()
    expect(page.locator('.ecc-eval-card[data-agent="refactor-cleaner"] .eval-score')).to_have_text('Running...', timeout=2000)

    expect(page.locator('#btn-eval-all')).to_be_visible()
    expect(page.locator('#btn-eval-all')).to_be_enabled()


# 10. Worker online indicator
def test_worker_online(page):
    """Dashboard shows WORKER ONLINE."""
    page.wait_for_timeout(5000)
    expect(page.locator('#worker-status')).to_have_text('WORKER ONLINE', timeout=10000)


# 11. Cross-device sync
def test_two_tabs_sync(browser):
    """Click RUN in tab1 → tab2 also shows Running..."""
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
