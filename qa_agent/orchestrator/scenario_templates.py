"""Per-page-type test scenario templates — what to test on each page type."""

from __future__ import annotations

SCENARIO_TEMPLATES: dict[str, list[str]] = {
    "homepage": [
        "hero banner is visible and has a CTA link",
        "main navigation links are visible and clickable",
        "search bar accepts input and submits",
        "featured products section displays product cards",
        "promotional banners are visible",
        "footer links are present and navigate correctly",
    ],
    "global_nav": [
        "top-level navigation links are visible",
        "hovering a category reveals a dropdown or mega menu",
        "mega menu contains subcategory links",
        "utility navigation (cart, sign in) is visible",
        "clicking a category navigates to the correct listing page",
    ],
    "search_results": [
        "search results display for a valid query",
        "no results message appears for nonsense query",
        "filter sidebar is visible with category options",
        "sort dropdown changes result order",
        "pagination controls work for multi-page results",
        "clicking a result navigates to PDP",
    ],
    "product_listing": [
        "category breadcrumb is accurate",
        "product grid displays product cards with image, name, price",
        "filter by price range works",
        "filter by brand works",
        "sort by price low-to-high reorders results",
        "pagination loads next page of results",
        "product count label is visible",
    ],
    "product_detail": [
        "product title and price are visible",
        "product image gallery loads and is navigable",
        "add to cart button is clickable",
        "quantity selector increments and decrements",
        "product reviews section is visible",
        "related products section displays items",
        "breadcrumb reflects category path",
    ],
    "cart": [
        "cart displays added item with correct name and price",
        "quantity increment updates subtotal",
        "remove item empties the cart",
        "continue shopping navigates back to browse",
        "proceed to checkout navigates to checkout",
        "empty cart shows empty state message",
    ],
    "checkout": [
        "guest checkout form renders all required fields",
        "shipping form validates required fields on submit",
        "payment section is visible after shipping",
        "order summary shows correct items and total",
        "form validation error messages display correctly",
    ],
    "sign_in": [
        "login form renders with email and password fields",
        "login with invalid credentials shows error message",
        "register link navigates to registration page",
        "forgot password link is visible",
        "sign in button is present and enabled",
    ],
    "registration": [
        "registration form has all required fields",
        "submit with empty fields shows validation errors",
        "password requirements are displayed",
        "terms and conditions link is present",
        "already have an account link navigates to sign in",
    ],
    "account": [
        "account dashboard renders after login",
        "order history section is visible",
        "account settings link is present",
        "saved addresses section is visible",
        "sign out option is available",
    ],
    "store_locator": [
        "zip code search input is visible",
        "search by zip code returns nearby stores",
        "store results show address and phone number",
        "map container is visible",
        "clicking a store shows detail view",
    ],
    "rv_listings": [
        "RV listing page displays search results",
        "filter by RV type narrows results",
        "filter by price range works",
        "listing card shows key details (price, year, make)",
        "clicking a listing navigates to RV detail page",
        "pagination controls are functional",
    ],
    "rv_detail": [
        "RV title and price are visible",
        "image gallery loads",
        "specifications table is present",
        "dealer info section is visible",
        "contact form or CTA is present",
    ],
    "good_sam": [
        "Good Sam page displays membership tiers",
        "membership benefits list is visible",
        "sign-up CTA is visible and clickable",
        "pricing information is displayed",
        "learn more links navigate correctly",
    ],
    "financing": [
        "financing page renders content",
        "calculator or application form is present",
        "apply now CTA is visible",
        "rates and terms information is displayed",
        "FAQ or details section is visible",
    ],
    "footer": [
        "all footer links are present and visible",
        "privacy policy link navigates to correct page",
        "terms of service page renders content",
        "social media links point to correct external URLs",
        "accessibility statement page renders",
    ],
}


def get_scenarios(page_key: str) -> list[str]:
    """Return test scenarios for a given page type. Raises KeyError if not found."""
    return SCENARIO_TEMPLATES[page_key]


def get_all_page_keys() -> list[str]:
    """Return all page keys that have scenario templates."""
    return list(SCENARIO_TEMPLATES.keys())
