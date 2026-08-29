"""Tests for the site map configuration."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.site_map import (
    BASE_URL,
    SITE_MAP,
    get_page,
    get_pages_by_priority,
)


def test_site_map_has_all_page_types():
    """Site map defines all 16 expected page types."""
    expected_keys = [
        "homepage", "global_nav", "search_results", "product_listing",
        "product_detail", "cart", "checkout", "sign_in", "registration",
        "account", "store_locator", "rv_listings", "rv_detail",
        "good_sam", "financing", "footer",
    ]
    for key in expected_keys:
        assert key in SITE_MAP, f"Missing page type: {key}"


def test_site_map_count():
    """Site map has exactly 16 page types."""
    assert len(SITE_MAP) == 16


def test_all_pages_have_required_fields():
    """Every page config has name, url, and route."""
    for key, config in SITE_MAP.items():
        assert config.name, f"{key} missing name"
        assert config.url, f"{key} missing url"
        assert config.route, f"{key} missing route"


def test_base_url_is_campingworld():
    """Base URL points to campingworld.com."""
    assert "campingworld.com" in BASE_URL


def test_get_page_returns_config():
    """get_page returns the correct PageConfig by name."""
    homepage = get_page("homepage")
    assert homepage.name == "Homepage"
    assert homepage.url == "/"


def test_get_page_raises_on_unknown():
    """get_page raises KeyError for unknown page names."""
    with pytest.raises(KeyError):
        get_page("nonexistent_page")


def test_get_pages_by_priority_sorted():
    """Pages are returned sorted by priority (1 first)."""
    pages = get_pages_by_priority()
    priorities = [p.priority for p in pages]
    assert priorities == sorted(priorities)


def test_get_pages_by_priority_excludes_auth_by_default():
    """Auth-gated pages are excluded by default."""
    pages = get_pages_by_priority(include_auth=False)
    for page in pages:
        assert not page.requires_auth, f"{page.name} requires auth but was included"


def test_get_pages_by_priority_includes_auth_when_requested():
    """Auth-gated pages are included when include_auth=True."""
    pages_without = get_pages_by_priority(include_auth=False)
    pages_with = get_pages_by_priority(include_auth=True)
    assert len(pages_with) > len(pages_without)


def test_account_requires_auth():
    """Account page is marked as requiring auth."""
    account = get_page("account")
    assert account.requires_auth is True


def test_homepage_does_not_require_auth():
    """Homepage does not require auth."""
    homepage = get_page("homepage")
    assert homepage.requires_auth is False


def test_dynamic_pages_have_flag():
    """Dynamic URL pages (PDP, RV detail) have dynamic_url=True."""
    pdp = get_page("product_detail")
    assert pdp.dynamic_url is True
    rv = get_page("rv_detail")
    assert rv.dynamic_url is True


def test_static_pages_not_dynamic():
    """Static pages have dynamic_url=False."""
    homepage = get_page("homepage")
    assert homepage.dynamic_url is False
