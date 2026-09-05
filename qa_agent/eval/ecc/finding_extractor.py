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
    r"|Severity:\s*(CRITICAL|HIGH|MEDIUM|LOW)"
    r"|(?:^|\n)#+\s*(CRITICAL|HIGH|MEDIUM|LOW)"
    r")",
    re.IGNORECASE,
)

_FILE_LINE = re.compile(
    r"(?:"
    r"([^\s\"'`]+\.(?:py|ts|tsx|js|jsx)):(\d+)"
    r"|(?:line|Line)\s+(\d+)\s+(?:of|in)\s+[`\"']?([^\s`\"']+)"
    r"|(?:File|file):\s*[`\"']?([^\s`\"':]+)[`\"']?(?::(\d+))?"
    r")",
)

_NUMBERED_FINDING = re.compile(
    r"(?:^|\n)\s*(?:\d+\.\s*|\*\s*|-\s*)"
    r"\*\*(.*?)\*\*",
    re.MULTILINE,
)


def _extract_severity(text: str) -> str | None:
    """Extract severity from a text block."""
    m = _SEVERITY_BLOCK.search(text)
    if not m:
        return None
    return next((g.upper() for g in m.groups() if g), None)


def _extract_file_line(text: str) -> tuple[str | None, int | None]:
    """Extract file path and line number from a text block."""
    m = _FILE_LINE.search(text)
    if not m:
        return None, None

    groups = m.groups()
    if groups[0] and groups[1]:
        return groups[0], int(groups[1])
    if groups[2] and groups[3]:
        return groups[3], int(groups[2])
    if groups[4]:
        line = int(groups[5]) if groups[5] else None
        return groups[4], line

    return None, None


def extract_findings(agent_output: str) -> list[Finding]:
    """Parse unstructured agent output into a list of structured Findings.

    The extractor looks for severity markers and splits the output into
    finding blocks. Each block is then parsed for file/line references.
    """
    if not agent_output or not agent_output.strip():
        return []

    findings: list[Finding] = []

    markers = list(_SEVERITY_BLOCK.finditer(agent_output))

    if markers:
        for i, marker in enumerate(markers):
            severity = next(
                (g.upper() for g in marker.groups() if g), "MEDIUM"
            )
            start = marker.start()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(agent_output)
            block = agent_output[start:end].strip()

            file_path, line_num = _extract_file_line(block)

            lines = block.split("\n")
            desc_lines = []
            for line in lines:
                stripped = line.strip().strip("*#-").strip()
                if stripped and not _SEVERITY_BLOCK.match(stripped):
                    desc_lines.append(stripped)
                    if len(desc_lines) >= 3:
                        break
            description = " ".join(desc_lines) if desc_lines else block[:200]

            findings.append(Finding(
                severity=severity,
                file=file_path,
                line=line_num,
                description=description,
                raw_text=block[:500],
            ))
    else:
        for m in _NUMBERED_FINDING.finditer(agent_output):
            title = m.group(1)
            context_start = m.start()
            context_end = min(m.end() + 500, len(agent_output))
            context = agent_output[context_start:context_end]

            severity = _extract_severity(context) or "MEDIUM"
            file_path, line_num = _extract_file_line(context)

            findings.append(Finding(
                severity=severity,
                file=file_path,
                line=line_num,
                description=title,
                raw_text=context[:500],
            ))

    return findings
