"""Tests for memory integration — updates APP_STRUCTURE.md."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qa_agent.orchestrator.memory_integration import (
    extract_components,
    extract_testids,
    update_memory_from_crawl,
)
from qa_agent.orchestrator.models import GeneratedOutput, PageConfig

POM_WITH_TESTIDS = """
import { type Page, type Locator } from '@playwright/test';

export class CartPage {
  readonly page: Page;

  // Cart Items
  readonly cartList: Locator;
  readonly removeButton: Locator;

  // Summary
  readonly subtotal: Locator;
  readonly checkoutButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.cartList = page.getByTestId('cart-items-list');
    this.removeButton = page.getByTestId('remove-item');
    this.subtotal = page.getByTestId('cart-subtotal');
    this.checkoutButton = page.getByRole('button', { name: 'Checkout' });
  }

  async navigate() {
    await this.page.goto('/cart');
  }
}
""".strip()

POM_NO_TESTIDS = """
import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;
  readonly searchInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.getByRole('searchbox');
  }

  async navigate() {
    await this.page.goto('/');
  }
}
""".strip()


# ---------------------------------------------------------------------------
# extract_testids
# ---------------------------------------------------------------------------

def test_extract_testids_finds_all():
    testids = extract_testids(POM_WITH_TESTIDS)
    assert "cart-items-list" in testids
    assert "remove-item" in testids
    assert "cart-subtotal" in testids


def test_extract_testids_count():
    testids = extract_testids(POM_WITH_TESTIDS)
    assert len(testids) == 3


def test_extract_testids_empty_when_none():
    testids = extract_testids(POM_NO_TESTIDS)
    assert testids == []


def test_extract_testids_deduplicates():
    source = POM_WITH_TESTIDS + "\n    this.x = page.getByTestId('cart-items-list');"
    testids = extract_testids(source)
    assert testids.count("cart-items-list") == 1


# ---------------------------------------------------------------------------
# extract_components
# ---------------------------------------------------------------------------

def test_extract_components_finds_regions():
    components = extract_components(POM_WITH_TESTIDS)
    assert "Cart Items" in components
    assert "Summary" in components


def test_extract_components_count():
    components = extract_components(POM_WITH_TESTIDS)
    assert len(components) == 2


def test_extract_components_empty_when_none():
    source = "export class X { constructor() {} }"
    components = extract_components(source)
    assert components == []


# ---------------------------------------------------------------------------
# update_memory_from_crawl
# ---------------------------------------------------------------------------

def test_update_memory_calls_store():
    """update_memory_from_crawl calls MemoryStore.update_route for each output."""
    config = PageConfig(name="Cart", url="/cart", route="/cart")
    output = GeneratedOutput(
        page_config=config,
        pom_filename="CartPage.ts",
        pom_source=POM_WITH_TESTIDS,
        test_filename="cart.spec.ts",
        test_source="test code",
    )

    with patch("qa_agent.orchestrator.memory_integration.MemoryStore") as MockStore:
        mock_instance = MockStore.return_value
        updated = update_memory_from_crawl([output])

    assert updated == 1
    mock_instance.update_route.assert_called_once()
    call_kwargs = mock_instance.update_route.call_args
    assert call_kwargs[1]["route"] == "/cart"
    assert "cart-items-list" in call_kwargs[1]["testids"]


def test_update_memory_multiple_outputs():
    configs = [
        PageConfig(name="Cart", url="/cart", route="/cart"),
        PageConfig(name="Homepage", url="/", route="/"),
    ]
    outputs = [
        GeneratedOutput(
            page_config=configs[0],
            pom_filename="CartPage.ts",
            pom_source=POM_WITH_TESTIDS,
            test_filename="cart.spec.ts",
            test_source="test",
        ),
        GeneratedOutput(
            page_config=configs[1],
            pom_filename="HomepagePage.ts",
            pom_source=POM_NO_TESTIDS,
            test_filename="homepage.spec.ts",
            test_source="test",
        ),
    ]

    with patch("qa_agent.orchestrator.memory_integration.MemoryStore") as MockStore:
        mock_instance = MockStore.return_value
        updated = update_memory_from_crawl(outputs)

    assert updated == 2
    assert mock_instance.update_route.call_count == 2


def test_update_memory_empty_list():
    with patch("qa_agent.orchestrator.memory_integration.MemoryStore"):
        updated = update_memory_from_crawl([])
    assert updated == 0
