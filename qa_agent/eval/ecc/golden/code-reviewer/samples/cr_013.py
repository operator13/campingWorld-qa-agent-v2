"""Immutable domain models using frozen dataclasses."""
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    email: str
    address: Address
    tier: str = "standard"
    created_at: Optional[datetime] = None


def upgrade_tier(customer: Customer, new_tier: str) -> Customer:
    """Return a new Customer with the upgraded tier."""
    return replace(customer, tier=new_tier)


def update_address(customer: Customer, new_address: Address) -> Customer:
    """Return a new Customer with a changed address."""
    return replace(customer, address=new_address)


def create_customer(
    customer_id: str, name: str, email: str, address: Address
) -> Customer:
    """Factory function for creating a new customer."""
    return Customer(
        id=customer_id,
        name=name,
        email=email,
        address=address,
        tier="standard",
        created_at=datetime.now(),
    )
