"""Extract structured findings from unstructured agent text output."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A single finding extracted from agent output."""

    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    file: str | None  # file path if identified
    line: int | None  # line number if identified
    description: str  # the finding text
    raw_text: str  # original matched block


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SEVERITY_BLOCK = re.compile(
    r"(?:"
    r"\*\*(CRITICAL|HIGH|MEDIUM|LOW)\*\*"
    r"|\[(CRITICAL|HIGH|MEDIUM|LOW)\]"
    r"|`\[(CRITICAL|HIGH|MEDIUM|LOW)\]`"
    r"|Severity:\s*`?\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?`?"
    r"|(?:^|\n)#+\s*(CRITICAL|HIGH|MEDIUM|LOW)"
    r")",
    re.IGNORECASE,
)

# Inline patterns: file.py:12, `file.py`, line 12, etc.
_FILE_LINE_INLINE = re.compile(
    r"(?:"
    r"([^\s\"'`*]+\.(?:py|ts|tsx|js|jsx)):(\d+)"
    r"|`([^`]+\.(?:py|ts|tsx|js|jsx))`(?:,\s*|\s+)(?:line\s+|:)(\d+)"
    r"|`([^`]+\.(?:py|ts|tsx|js|jsx))`:(\d+)"
    r")",
)

# Labeled patterns on separate lines:
# **File:** `api/users.py`
# **Line:** 16
_FILE_LABELED = re.compile(
    r"\*\*File:?\*\*\s*`?([^\s`\n]+\.(?:py|ts|tsx|js|jsx))`?",
    re.IGNORECASE,
)
_LINE_LABELED = re.compile(
    r"\*\*Lines?:?\*\*\s*`?(\d+)",
    re.IGNORECASE,
)

# Fallback: File: path or file mentioned with line
_FILE_COLON = re.compile(
    r"(?:File|file|Location|location):\s*`?([^\s`\"'\n]+\.(?:py|ts|tsx|js|jsx))`?",
)
_LINE_COLON = re.compile(
    r"(?:Line|line|Lines|lines):\s*`?(\d+)",
)


def _extract_severity(text: str) -> str | None:
    """Extract severity from a text block."""
    m = _SEVERITY_BLOCK.search(text)
    if not m:
        return None
    return next((g.upper() for g in m.groups() if g), None)


def _extract_file_line(text: str) -> tuple[str | None, int | None]:
    """Extract file path and line number from a text block.

    Tries multiple strategies:
    1. Inline patterns (file.py:12, `file.py`, line 12)
    2. Labeled patterns (**File:** `file.py` / **Line:** 12)
    3. Fallback colon patterns (File: file.py, Line: 12)
    """
    # Strategy 1: Inline patterns
    m = _FILE_LINE_INLINE.search(text)
    if m:
        groups = m.groups()
        if groups[0] and groups[1]:
            return groups[0], int(groups[1])
        if groups[2] and groups[3]:
            return groups[2], int(groups[3])
        if groups[4] and groups[5]:
            return groups[4], int(groups[5])

    # Strategy 2: Labeled patterns on separate lines
    file_match = _FILE_LABELED.search(text)
    line_match = _LINE_LABELED.search(text)
    if file_match:
        file_path = file_match.group(1)
        line_num = int(line_match.group(1)) if line_match else None
        return file_path, line_num

    # Strategy 3: Fallback colon patterns (File:, Location:)
    file_match = _FILE_COLON.search(text)
    line_match = _LINE_COLON.search(text)
    if file_match:
        file_path = file_match.group(1)
        line_num = int(line_match.group(1)) if line_match else None
        return file_path, line_num

    # Strategy 4: Location:** `file.py`, line N (common agent format)
    loc_match = re.search(
        r"Location:\*\*\s*`([^`]+\.(?:py|ts|tsx|js|jsx))`(?:,\s*|\s+)(?:line\s+|:)(\d+)",
        text, re.IGNORECASE,
    )
    if loc_match:
        return loc_match.group(1), int(loc_match.group(2))

    # Strategy 5: Any backtick-wrapped filename in the text
    any_file = re.search(r"`([^`]+\.(?:py|ts|tsx|js|jsx))`", text)
    any_line = re.search(r"(?:line|Line|lines?)\s+(\d+)", text)
    if any_file:
        line_num = int(any_line.group(1)) if any_line else None
        return any_file.group(1), line_num

    # Strategy 6: No file found, but extract line from "— Line N" pattern
    dash_line = re.search(r"—\s*Lines?\s+(\d+)", text)
    if dash_line:
        return None, int(dash_line.group(1))

    # Strategy 7: Extract line from any "Line N" or "Lines N" reference
    if any_line:
        return None, int(any_line.group(1))

    return None, None


def _extract_description(block: str) -> str:
    """Extract a meaningful description from a finding block."""
    lines = block.split("\n")
    desc_lines = []
    skip_patterns = re.compile(
        r"^\s*(\*\*File|\*\*Line|\*\*Severity|\*\*Fix|\*\*Example|```|---|\|)",
        re.IGNORECASE,
    )
    for line in lines:
        stripped = line.strip().strip("*#-").strip()
        if not stripped:
            continue
        if _SEVERITY_BLOCK.match(stripped):
            continue
        if skip_patterns.match(line.strip()):
            continue
        desc_lines.append(stripped)
        if len(desc_lines) >= 2:
            break
    return " ".join(desc_lines) if desc_lines else block[:200]


def extract_findings(agent_output: str) -> list[Finding]:
    """Parse unstructured agent output into a list of structured Findings.

    Splits output into blocks by severity markers, then extracts file/line
    from each block using multiple strategies (inline, labeled, fallback).
    Deduplicates findings by (file, line) to avoid counting the same issue twice.
    """
    if not agent_output or not agent_output.strip():
        return []

    findings: list[Finding] = []
    seen: set[tuple[str | None, int | None]] = set()

    # Split by section headers (### Finding N, ### N., --- separators)
    sections = re.split(r"(?:^|\n)(?:###\s+|---\s*$)", agent_output, flags=re.MULTILINE)

    for section in sections:
        if not section.strip():
            continue

        severity = _extract_severity(section)
        if not severity:
            continue

        file_path, line_num = _extract_file_line(section)

        # Deduplicate by file+line
        key = (file_path, line_num)
        if key in seen and file_path is not None:
            continue
        if file_path is not None:
            seen.add(key)

        description = _extract_description(section)

        findings.append(Finding(
            severity=severity,
            file=file_path,
            line=line_num,
            description=description,
            raw_text=section[:500],
        ))

    # Fallback: if section splitting found nothing, try severity markers
    if not findings:
        markers = list(_SEVERITY_BLOCK.finditer(agent_output))
        for i, marker in enumerate(markers):
            severity = next(
                (g.upper() for g in marker.groups() if g), "MEDIUM"
            )
            start = marker.start()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(agent_output)
            block = agent_output[start:end].strip()

            file_path, line_num = _extract_file_line(block)
            description = _extract_description(block)

            key = (file_path, line_num)
            if key in seen and file_path is not None:
                continue
            if file_path is not None:
                seen.add(key)

            findings.append(Finding(
                severity=severity,
                file=file_path,
                line=line_num,
                description=description,
                raw_text=block[:500],
            ))

    return findings
