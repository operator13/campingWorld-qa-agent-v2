"""Pricing engine with deeply nested business logic."""
from datetime import datetime
from decimal import Decimal


def calculate_discount(
    customer: dict, cart: dict, promotions: list[dict], season: str
) -> Decimal:
    """Calculate final discount with deeply nested conditional business rules."""
    total_discount = Decimal("0")
    subtotal = Decimal(str(cart.get("subtotal", 0)))

    for promo in promotions:
        if promo.get("active"):
            if promo.get("start_date") and promo.get("end_date"):
                start = datetime.fromisoformat(promo["start_date"])
                end = datetime.fromisoformat(promo["end_date"])
                if start <= datetime.now() <= end:
                    if promo["type"] == "percentage":
                        if customer.get("tier") == "gold":
                            if subtotal >= Decimal("100"):
                                discount = subtotal * Decimal(str(promo["value"])) / 100
                                if promo.get("max_discount"):
                                    if discount > Decimal(str(promo["max_discount"])):
                                        discount = Decimal(str(promo["max_discount"]))
                                total_discount += discount
                            elif subtotal >= Decimal("50"):
                                half_value = Decimal(str(promo["value"])) / 2
                                total_discount += subtotal * half_value / 100
                        elif customer.get("tier") == "silver":
                            if subtotal >= Decimal("75"):
                                reduced_value = Decimal(str(promo["value"])) * Decimal("0.75")
                                total_discount += subtotal * reduced_value / 100
                        else:
                            if customer.get("is_new") and season in ("holiday", "summer"):
                                if subtotal >= Decimal("150"):
                                    new_customer_rate = Decimal(str(promo["value"])) / 2
                                    total_discount += subtotal * new_customer_rate / 100
                    elif promo["type"] == "fixed":
                        if subtotal >= Decimal(str(promo.get("min_purchase", 0))):
                            if customer.get("tier") in ("gold", "silver"):
                                total_discount += Decimal(str(promo["value"]))
                            else:
                                if cart.get("item_count", 0) >= 3:
                                    total_discount += Decimal(str(promo["value"])) / 2

    if total_discount > subtotal * Decimal("0.5"):
        total_discount = subtotal * Decimal("0.5")

    return total_discount.quantize(Decimal("0.01"))
