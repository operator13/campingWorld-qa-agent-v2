"""Declarative site map for campingworld.com — all page types to crawl."""

from __future__ import annotations

from qa_agent.orchestrator.models import PageConfig

BASE_URL = "https://www.campingworld.com"

SITE_MAP: dict[str, PageConfig] = {
    "homepage": PageConfig(
        name="Homepage",
        url="/",
        route="/",
        priority=1,
        regions=["hero", "navigation", "search", "featured_products", "promotions", "footer"],
    ),
    "global_nav": PageConfig(
        name="Global Navigation",
        url="/",
        route="/nav",
        priority=1,
        regions=["mega_menu", "category_dropdowns", "utility_nav"],
        prerequisites=[{"action": "hover", "target": "main navigation menu trigger"}],
    ),
    "search_results": PageConfig(
        name="Search Results",
        url="/search?q=tent",
        route="/search",
        priority=1,
        regions=["results_grid", "filters", "sort", "pagination"],
        prerequisites=[{"action": "fill", "target": "search input", "value": "tent"}],
    ),
    "product_listing": PageConfig(
        name="Product Listing Page",
        url="/rv-parts",
        route="/rv-parts",
        priority=2,
        regions=["breadcrumb", "product_grid", "filters", "sort", "pagination"],
    ),
    "product_detail": PageConfig(
        name="Product Detail Page",
        url="/wenzel-bristlecone-8-person-dome-tent-761437.html",
        route="/product",
        priority=2,
        dynamic_url=False,
        regions=["product_title", "images", "pricing", "add_to_cart", "reviews", "related"],
    ),
    "cart": PageConfig(
        name="Shopping Cart",
        url="/cart",
        route="/cart",
        priority=2,
        regions=["cart_items", "quantity", "subtotal", "checkout_button", "empty_state"],
        prerequisites=[{"action": "add_to_cart", "target": "any product"}],
    ),
    "checkout": PageConfig(
        name="Checkout",
        url="/checkout",
        route="/checkout",
        priority=3,
        regions=["shipping_form", "payment_form", "order_summary"],
        prerequisites=[{"action": "add_to_cart", "target": "any product"}],
    ),
    "sign_in": PageConfig(
        name="Sign In",
        url="/sign-in",
        route="/sign-in",
        priority=2,
        regions=["login_form", "register_link", "forgot_password"],
    ),
    "registration": PageConfig(
        name="Registration",
        url="/register",
        route="/register",
        priority=3,
        regions=["registration_form", "terms"],
    ),
    "account": PageConfig(
        name="Account Dashboard",
        url="/account",
        route="/account",
        requires_auth=True,
        priority=3,
        regions=["dashboard", "order_history", "settings", "saved_addresses"],
    ),
    "store_locator": PageConfig(
        name="Store Locator",
        url="/store-locator",
        route="/store-locator",
        priority=2,
        regions=["zip_search", "results_list", "map", "store_cards"],
    ),
    "rv_listings": PageConfig(
        name="RV Listings",
        url="/rvs-for-sale",
        route="/rvs-for-sale",
        priority=2,
        regions=["search_filters", "results_grid", "listing_cards", "pagination"],
    ),
    "rv_detail": PageConfig(
        name="RV Detail",
        url="https://rv.campingworld.com/rv/2027-keystone-coleman-17b-2667651-wauconda-il",
        route="/rvs-for-sale/detail",
        priority=3,
        dynamic_url=False,
        regions=["rv_specs", "images", "pricing", "dealer_info", "contact_form"],
    ),
    "good_sam": PageConfig(
        name="Good Sam Club",
        url="/good-sam",
        route="/good-sam",
        priority=3,
        regions=["membership_tiers", "benefits", "signup_cta"],
    ),
    "financing": PageConfig(
        name="Financing",
        url="/financing",
        route="/financing",
        priority=3,
        regions=["calculator", "application_form", "rates"],
    ),
    "footer": PageConfig(
        name="Footer & Legal Pages",
        url="/privacy-policy",
        route="/footer",
        priority=3,
        regions=["footer_links", "social_links", "legal_content"],
        sample_urls=["/privacy-policy", "/terms-of-use", "/accessibility"],
    ),
}


def get_pages_by_priority(include_auth: bool = False) -> list[PageConfig]:
    """Return page configs sorted by priority (1=first)."""
    pages = [
        config
        for config in SITE_MAP.values()
        if include_auth or not config.requires_auth
    ]
    return sorted(pages, key=lambda p: p.priority)


def get_page(name: str) -> PageConfig:
    """Look up a page config by name. Raises KeyError if not found."""
    return SITE_MAP[name]
