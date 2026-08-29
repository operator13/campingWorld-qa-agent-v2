"""Cart handler — adds an item to cart before snapshotting cart/checkout pages."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CartHandler:
    """Ensures the cart has at least one item for cart/checkout page testing."""

    def __init__(self, call_tool_fn: Any, base_url: str = "https://www.campingworld.com") -> None:
        self._call_tool = call_tool_fn
        self._base_url = base_url
        self._item_added = False

    @property
    def has_item(self) -> bool:
        return self._item_added

    async def ensure_cart_has_item(self) -> None:
        """Navigate to a product and add it to cart if cart is empty."""
        if self._item_added:
            logger.debug("CartHandler: cart already has item, skipping")
            return

        logger.info("CartHandler: adding item to cart")

        # 1. Navigate to a known category page to find a product
        await self._call_tool(
            "browser_navigate", {"url": f"{self._base_url}/rv-parts"}
        )

        # 2. Wait for products to load
        try:
            await self._call_tool("browser_wait_for", {"text": "Add to Cart", "timeout": 10000})
        except Exception:
            # Try clicking into a product first
            logger.debug("CartHandler: no Add to Cart on listing, clicking first product")
            try:
                await self._call_tool("browser_click", {"element": "product"})
                await self._call_tool(
                    "browser_wait_for", {"text": "Add to Cart", "timeout": 10000}
                )
            except Exception:
                logger.warning("CartHandler: could not find a product to add")
                return

        # 3. Click Add to Cart
        try:
            await self._call_tool("browser_click", {"element": "Add to Cart"})
            self._item_added = True
            logger.info("CartHandler: item added to cart")
        except Exception:
            logger.warning("CartHandler: failed to click Add to Cart")

        # 4. Brief wait for cart update
        try:
            await self._call_tool("browser_wait_for", {"time": 2000})
        except Exception:
            pass

    async def verify_cart_not_empty(self) -> bool:
        """Navigate to cart and check it has items."""
        await self._call_tool("browser_navigate", {"url": f"{self._base_url}/cart"})
        snapshot = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot).lower() if snapshot else ""

        is_empty = any(
            phrase in snapshot_text
            for phrase in ["your cart is empty", "no items", "cart is empty", "0 items"]
        )
        return not is_empty

    def reset(self) -> None:
        """Reset cart state."""
        self._item_added = False
