"""Tests for scenario templates — coverage and completeness."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.scenario_templates import (
    SCENARIO_TEMPLATES,
    get_all_page_keys,
    get_scenarios,
)
from qa_agent.orchestrator.site_map import SITE_MAP


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def test_every_site_map_page_has_scenarios():
    """Every page in SITE_MAP has a matching scenario template."""
    for key in SITE_MAP:
        assert key in SCENARIO_TEMPLATES, f"Missing scenario template for site map key: {key}"


def test_scenario_template_count():
    """We have templates for all 16 page types."""
    assert len(SCENARIO_TEMPLATES) == 16


# ---------------------------------------------------------------------------
# Minimum scenarios per page
# ---------------------------------------------------------------------------

def test_every_page_has_at_least_5_scenarios():
    """Each page type has at least 5 test scenarios."""
    for key, scenarios in SCENARIO_TEMPLATES.items():
        assert len(scenarios) >= 5, f"{key} has only {len(scenarios)} scenarios, need >= 5"


def test_total_scenarios_at_least_80():
    """Total test scenarios across all pages is >= 80."""
    total = sum(len(s) for s in SCENARIO_TEMPLATES.values())
    assert total >= 80, f"Only {total} total scenarios, need >= 80"


# ---------------------------------------------------------------------------
# Key scenarios present
# ---------------------------------------------------------------------------

def test_homepage_has_search_scenario():
    scenarios = get_scenarios("homepage")
    assert any("search" in s.lower() for s in scenarios)


def test_pdp_has_add_to_cart_scenario():
    scenarios = get_scenarios("product_detail")
    assert any("add to cart" in s.lower() for s in scenarios)


def test_checkout_no_real_submit():
    """Checkout scenarios should NOT include submitting real orders."""
    scenarios = get_scenarios("checkout")
    for s in scenarios:
        assert "place order" not in s.lower(), f"Checkout scenario should not submit real orders: {s}"
        assert "submit order" not in s.lower(), f"Checkout scenario should not submit real orders: {s}"


def test_cart_has_empty_state():
    scenarios = get_scenarios("cart")
    assert any("empty" in s.lower() for s in scenarios)


def test_sign_in_has_error_scenario():
    scenarios = get_scenarios("sign_in")
    assert any("invalid" in s.lower() or "error" in s.lower() for s in scenarios)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_get_scenarios_returns_list():
    result = get_scenarios("homepage")
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_scenarios_raises_on_unknown():
    with pytest.raises(KeyError):
        get_scenarios("nonexistent_page")


def test_get_all_page_keys():
    keys = get_all_page_keys()
    assert "homepage" in keys
    assert "product_detail" in keys
    assert len(keys) == 16
