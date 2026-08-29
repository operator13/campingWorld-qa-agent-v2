"""Tests for FileWriter — file naming and writing."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.file_writer import (
    route_to_pom_filename,
    route_to_spec_filename,
    write_pair,
    write_pom,
    write_test,
)
from qa_agent.orchestrator.models import PageConfig


# ---------------------------------------------------------------------------
# POM filename
# ---------------------------------------------------------------------------

def test_pom_filename_homepage():
    assert route_to_pom_filename("/") == "HomepagePage.ts"


def test_pom_filename_cart():
    assert route_to_pom_filename("/cart") == "CartPage.ts"


def test_pom_filename_sign_in():
    assert route_to_pom_filename("/sign-in") == "SignInPage.ts"


def test_pom_filename_nested():
    assert route_to_pom_filename("/rvs-for-sale/detail") == "RvsForSaleDetailPage.ts"


# ---------------------------------------------------------------------------
# Spec filename
# ---------------------------------------------------------------------------

def test_spec_filename_homepage():
    assert route_to_spec_filename("/") == "homepage.spec.ts"


def test_spec_filename_cart():
    assert route_to_spec_filename("/cart") == "cart.spec.ts"


def test_spec_filename_sign_in():
    assert route_to_spec_filename("/sign-in") == "sign-in.spec.ts"


# ---------------------------------------------------------------------------
# Write POM
# ---------------------------------------------------------------------------

def test_write_pom_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Homepage", url="/", route="/")
    path = write_pom(config, "export class HomepagePage {}")
    assert path.exists()
    assert path.name == "HomepagePage.ts"
    assert "HomepagePage" in path.read_text()


def test_write_pom_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Homepage", url="/", route="/")

    write_pom(config, "original content")
    write_pom(config, "new content", overwrite=False)

    path = tmp_path / "page_objects" / "HomepagePage.ts"
    assert path.read_text() == "original content"


def test_write_pom_overwrites_when_forced(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Homepage", url="/", route="/")

    write_pom(config, "original content")
    write_pom(config, "new content", overwrite=True)

    path = tmp_path / "page_objects" / "HomepagePage.ts"
    assert path.read_text() == "new content"


# ---------------------------------------------------------------------------
# Write test
# ---------------------------------------------------------------------------

def test_write_test_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Homepage", url="/", route="/")
    path = write_test(config, "test.describe('Homepage', () => {})")
    assert path.exists()
    assert path.name == "homepage.spec.ts"


def test_write_test_skips_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Cart", url="/cart", route="/cart")

    write_test(config, "original")
    write_test(config, "new", overwrite=False)

    path = tmp_path / "tests_generated" / "cart.spec.ts"
    assert path.read_text() == "original"


# ---------------------------------------------------------------------------
# Write pair
# ---------------------------------------------------------------------------

def test_write_pair_creates_both(tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    config = PageConfig(name="Cart", url="/cart", route="/cart")

    pom_path, test_path = write_pair(config, "pom code", "test code")
    assert pom_path.exists()
    assert test_path.exists()
    assert pom_path.name == "CartPage.ts"
    assert test_path.name == "cart.spec.ts"
