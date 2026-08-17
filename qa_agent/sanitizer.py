"""Prompt-injection guards — sanitise untrusted Figma text and DOM content.

All external text (Figma component names, DOM innerHTML, Jira descriptions)
passes through this module before reaching any agent prompt. It strips or
quarantines content that could hijack agent behaviour.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Patterns that indicate prompt-injection attempts
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Direct instruction hijacking
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"you\s+are\s+now\s+a", re.I),
    re.compile(r"new\s+instructions?:", re.I),
    re.compile(r"system\s*prompt:", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"\[/INST\]", re.I),

    # Role-play injection
    re.compile(r"pretend\s+you\s+are", re.I),
    re.compile(r"act\s+as\s+if\s+you", re.I),
    re.compile(r"simulate\s+(being|a)", re.I),

    # Output manipulation
    re.compile(r"output\s+only\s+the\s+following", re.I),
    re.compile(r"respond\s+with\s+exactly", re.I),
    re.compile(r"print\s+the\s+(secret|password|key|token)", re.I),

    # Tool/function hijacking
    re.compile(r"call\s+(the\s+)?function", re.I),
    re.compile(r"execute\s+(the\s+)?tool", re.I),
    re.compile(r"run\s+(the\s+)?(command|shell|bash)", re.I),
]

# Maximum lengths for untrusted fields
_MAX_LENGTHS = {
    "element_name": 200,
    "element_text": 500,
    "dom_snippet": 5000,
    "description": 3000,
    "figma_text": 1000,
}


class InjectionDetectedError(Exception):
    """Raised when a prompt-injection attempt is detected in untrusted input."""


def sanitize_text(
    text: str,
    field_type: str = "element_text",
    raise_on_injection: bool = False,
) -> str:
    """Sanitise a single text field from an untrusted source.

    1. Truncates to max length for the field type.
    2. Strips control characters.
    3. Checks for injection patterns.

    Args:
        text: The untrusted input text.
        field_type: Key into _MAX_LENGTHS for truncation.
        raise_on_injection: If True, raise instead of stripping.

    Returns:
        The sanitised text.
    """
    if not text:
        return text

    # 1. Truncate
    max_len = _MAX_LENGTHS.get(field_type, 1000)
    if len(text) > max_len:
        text = text[:max_len]
        logger.warning("Sanitizer: truncated %s to %d chars", field_type, max_len)

    # 2. Strip control characters (keep newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 3. Check for injection patterns
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            if raise_on_injection:
                raise InjectionDetectedError(
                    f"Injection detected in {field_type}: matched {pattern.pattern!r}"
                )
            # Strip the offending segment
            cleaned = pattern.sub("[REDACTED]", text)
            logger.warning(
                "Sanitizer: injection pattern detected and redacted in %s (pattern=%s)",
                field_type,
                pattern.pattern,
            )
            text = cleaned

    return text


def sanitize_dom(html: str) -> str:
    """Sanitise a DOM snapshot. Strips script content and injection patterns."""
    if not html:
        return html

    # Remove script tags and their content
    html = re.sub(r"<script[^>]*>.*?</script>", "[SCRIPT REMOVED]", html, flags=re.S | re.I)

    # Remove event handlers
    html = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', "", html, flags=re.I)
    html = re.sub(r"\s+on\w+\s*=\s*'[^']*'", "", html, flags=re.I)

    # General sanitize
    return sanitize_text(html, field_type="dom_snippet")


def sanitize_figma_elements(elements: list[dict]) -> list[dict]:
    """Sanitise a list of Figma UI element dicts."""
    sanitized = []
    for el in elements:
        clean = {}
        for key, val in el.items():
            if isinstance(val, str):
                field_type = "element_name" if key in ("name", "role") else "figma_text"
                clean[key] = sanitize_text(val, field_type=field_type)
            else:
                clean[key] = val
        sanitized.append(clean)
    return sanitized


def check_for_injection(text: str) -> bool:
    """Return True if the text contains any injection patterns. Does not modify."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False
