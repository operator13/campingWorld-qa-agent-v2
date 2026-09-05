"""User profile processing - single function doing too much."""
import json
import re
from datetime import datetime


def process_user_profile(raw_data: str, country_code: str) -> dict:
    """Parse, validate, and format a user profile from raw JSON string."""
    # --- Parsing phase ---
    data = json.loads(raw_data)
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    email = data.get("email", "").strip().lower()
    phone = data.get("phone", "")
    date_of_birth = data.get("date_of_birth", "")
    address_line_1 = data.get("address", {}).get("line1", "")
    address_line_2 = data.get("address", {}).get("line2", "")
    city = data.get("address", {}).get("city", "")
    state = data.get("address", {}).get("state", "")
    zip_code = data.get("address", {}).get("zip", "")
    preferences = data.get("preferences", {})
    newsletter = preferences.get("newsletter", False)
    language = preferences.get("language", "en")
    timezone = preferences.get("timezone", "UTC")

    # --- Validation phase ---
    errors = []
    if not first_name:
        errors.append("First name is required")
    if len(first_name) > 50:
        errors.append("First name must be 50 characters or fewer")
    if not last_name:
        errors.append("Last name is required")
    if len(last_name) > 50:
        errors.append("Last name must be 50 characters or fewer")
    if not email:
        errors.append("Email is required")
    elif not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        errors.append("Email format is invalid")
    if phone:
        cleaned_phone = re.sub(r"[^\d+]", "", phone)
        if len(cleaned_phone) < 7 or len(cleaned_phone) > 15:
            errors.append("Phone number must be between 7 and 15 digits")
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
            age = (datetime.now() - dob).days // 365
            if age < 13:
                errors.append("User must be at least 13 years old")
            if age > 150:
                errors.append("Invalid date of birth")
        except ValueError:
            errors.append("Date of birth must be in YYYY-MM-DD format")
    if country_code == "US" and zip_code:
        if not re.match(r"^\d{5}(-\d{4})?$", zip_code):
            errors.append("Invalid US zip code format")
    elif country_code == "UK" and zip_code:
        if not re.match(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", zip_code.upper()):
            errors.append("Invalid UK postcode format")
    if language not in ("en", "es", "fr", "de", "pt", "ja", "zh"):
        errors.append("Unsupported language")
    if errors:
        return {"success": False, "errors": errors}

    # --- Formatting phase ---
    display_name = f"{first_name} {last_name}"
    formatted_phone = ""
    if phone:
        digits = re.sub(r"[^\d]", "", phone)
        if len(digits) == 10:
            formatted_phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        else:
            formatted_phone = phone
    full_address = address_line_1
    if address_line_2:
        full_address += f", {address_line_2}"
    full_address += f", {city}, {state} {zip_code}"
    return {
        "success": True,
        "profile": {
            "display_name": display_name,
            "email": email,
            "phone": formatted_phone,
            "date_of_birth": date_of_birth,
            "address": full_address.strip(", "),
            "preferences": {
                "newsletter": newsletter,
                "language": language,
                "timezone": timezone,
            },
            "created_at": datetime.now().isoformat(),
        },
    }
