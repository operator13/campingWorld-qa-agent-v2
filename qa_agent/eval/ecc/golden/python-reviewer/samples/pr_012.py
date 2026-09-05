"""Efficient string building with join patterns."""

from typing import Iterable


def build_csv_row(values: Iterable[str]) -> str:
    """Join values into a CSV row."""
    return ",".join(str(v) for v in values)


def build_log_entry(
    timestamp: str, level: str, message: str, context: dict[str, str]
) -> str:
    """Build a structured log line efficiently."""
    parts = [f"[{timestamp}]", f"[{level}]", message]
    if context:
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items())
        parts.append(f"({ctx_str})")
    return " ".join(parts)


def render_table(
    headers: list[str], rows: list[list[str]], separator: str = " | "
) -> str:
    """Render a text table using join for each row."""
    lines = [separator.join(headers)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(separator.join(row))
    return "\n".join(lines)
