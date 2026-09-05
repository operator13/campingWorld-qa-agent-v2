"""Memory leak from unbounded list growth in a long-lived service."""


class PriceTracker:
    """Tracks price changes for products. Intended to run for the app lifetime."""

    def __init__(self) -> None:
        self._history: list[dict] = []

    def record_price(self, sku: str, price: float) -> None:
        """Record a price observation. Called on every page view."""
        self._history.append({
            "sku": sku,
            "price": price,
        })

    def get_average_price(self, sku: str) -> float:
        """Compute average price for a SKU from full history."""
        prices = [h["price"] for h in self._history if h["sku"] == sku]
        if not prices:
            return 0.0
        return sum(prices) / len(prices)

    def get_history_size(self) -> int:
        return len(self._history)


# Module-level singleton that lives forever
tracker = PriceTracker()
