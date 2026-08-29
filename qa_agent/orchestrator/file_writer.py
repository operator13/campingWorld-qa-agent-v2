"""File writer — writes generated POM and test files to disk."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from qa_agent.orchestrator.models import PageConfig

logger = logging.getLogger(__name__)

# Project root for writing output files
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def route_to_pom_filename(route: str) -> str:
    """Convert a route like '/sign-in' to 'SignInPage.ts'."""
    clean = route.strip("/") or "Homepage"
    parts = re.split(r"[-_/]", clean)
    name = "".join(p.capitalize() for p in parts if p)
    return f"{name}Page.ts"


def route_to_spec_filename(route: str) -> str:
    """Convert a route like '/sign-in' to 'sign-in.spec.ts'."""
    clean = route.strip("/") or "homepage"
    clean = clean.replace("/", "-")
    return f"{clean}.spec.ts"


def write_pom(config: PageConfig, source: str, overwrite: bool = False) -> Path:
    """Write a POM TypeScript file to page_objects/.

    Args:
        config: Page configuration.
        source: TypeScript source code.
        overwrite: If False, skip existing files.

    Returns:
        Path to the written file.
    """
    po_dir = _PROJECT_ROOT / "page_objects"
    po_dir.mkdir(exist_ok=True)

    filename = route_to_pom_filename(config.route)
    filepath = po_dir / filename

    if filepath.exists() and not overwrite:
        logger.info("FileWriter: skipping existing POM %s (use overwrite=True to replace)", filename)
        return filepath

    filepath.write_text(source)
    logger.info("FileWriter: wrote POM %s (%d bytes)", filepath, len(source))
    return filepath


def write_test(config: PageConfig, source: str, overwrite: bool = False) -> Path:
    """Write a test spec TypeScript file to tests_generated/.

    Args:
        config: Page configuration.
        source: TypeScript source code.
        overwrite: If False, skip existing files.

    Returns:
        Path to the written file.
    """
    test_dir = _PROJECT_ROOT / "tests_generated"
    test_dir.mkdir(exist_ok=True)

    filename = route_to_spec_filename(config.route)
    filepath = test_dir / filename

    if filepath.exists() and not overwrite:
        logger.info("FileWriter: skipping existing test %s (use overwrite=True to replace)", filename)
        return filepath

    filepath.write_text(source)
    logger.info("FileWriter: wrote test %s (%d bytes)", filepath, len(source))
    return filepath


def write_pair(
    config: PageConfig,
    pom_source: str,
    test_source: str,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write both POM and test files for a page.

    Returns:
        Tuple of (pom_path, test_path).
    """
    pom_path = write_pom(config, pom_source, overwrite=overwrite)
    test_path = write_test(config, test_source, overwrite=overwrite)
    return pom_path, test_path
