"""Input validators with small, focused functions."""
import re
from typing import Optional


def validate_email(email: str) -> Optional[str]:
    """Return error message if email is invalid, else None."""
    if not email or not email.strip():
        return "Email is required"
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(pattern, email.strip()):
        return "Invalid email format"
    return None


def validate_phone(phone: str) -> Optional[str]:
    """Return error message if phone is invalid, else None."""
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) < 7:
        return "Phone number too short"
    if len(digits) > 15:
        return "Phone number too long"
    return None


def validate_zip_code(zip_code: str, country: str = "US") -> Optional[str]:
    """Return error message if zip code is invalid for the country."""
    patterns = {
        "US": r"^\d{5}(-\d{4})?$",
        "UK": r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$",
        "CA": r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$",
    }
    pattern = patterns.get(country)
    if pattern is None:
        return f"Unsupported country: {country}"
    if not re.match(pattern, zip_code.upper()):
        return f"Invalid {country} postal code"
    return None


def validate_required_fields(data: dict, fields: list[str]) -> list[str]:
    """Return list of missing required field names."""
    return [f for f in fields if not data.get(f)]
