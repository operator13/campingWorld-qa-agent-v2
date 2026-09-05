"""Data pipeline that logs errors then continues with corrupt state."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_pipeline(records: list[dict[str, Any]]) -> list[dict]:
    """Run ETL pipeline, logging errors but continuing with bad data."""
    results = []
    for record in records:
        data = record.copy()

        try:
            data = transform(data)
        except Exception as e:
            logger.error("Transform failed for record %s: %s", data.get("id"), e)

        try:
            data = enrich(data)
        except Exception as e:
            logger.error("Enrich failed for record %s: %s", data.get("id"), e)

        results.append(data)

    return results


def transform(record: dict) -> dict:
    """Transform a record - may raise on invalid data."""
    record["amount"] = float(record["amount"]) * 100
    record["currency"] = record["currency"].upper()
    return record


def enrich(record: dict) -> dict:
    """Enrich record with computed fields."""
    record["tax"] = record["amount"] * 0.08
    record["total"] = record["amount"] + record["tax"]
    return record
