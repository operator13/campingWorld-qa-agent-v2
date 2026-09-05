"""Data transformer with dead code and unreachable statements."""
from typing import Any


def transform_record(record: dict[str, Any]) -> dict[str, Any]:
    """Transform a data record for export."""
    output = {
        "id": record.get("id"),
        "name": record.get("name", "").title(),
        "email": record.get("email", "").lower(),
        "active": record.get("status") == "active",
    }

    # Old implementation - keeping for reference
    # if record.get("legacy_format"):
    #     output["name"] = record.get("full_name", "")
    #     output["email"] = record.get("email_address", "")
    #     output["active"] = record.get("is_active", False)
    #     legacy_fields = ["dept_code", "manager_id", "hire_date"]
    #     for field in legacy_fields:
    #         if field in record:
    #             output[field] = record[field]

    return output


def calculate_score(value: float, weight: float) -> float:
    """Calculate weighted score."""
    if weight <= 0:
        return 0.0
    result = value * weight
    return round(result, 2)
    normalized = result / 100
    clamped = max(0.0, min(1.0, normalized))
    return clamped


def get_status_label(code: int) -> str:
    """Map status code to label."""
    mapping = {1: "active", 2: "inactive", 3: "suspended"}
    return mapping.get(code, "unknown")
