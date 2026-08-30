"""Tests for the Triage Runner — failure parsing and self-healing integration."""

import json
import pytest
from pathlib import Path

from qa_agent.triage_runner import parse_failures, _SPEC_TO_POM


SAMPLE_RESULTS = {
    "suites": [
        {
            "title": "cart.spec.ts",
            "suites": [
                {
                    "title": "Shopping Cart",
                    "specs": [
                        {
                            "title": "cart page loads",
                            "ok": True,
                            "file": "cart.spec.ts",
                            "line": 12,
                            "tests": [{"status": "expected", "results": [{"status": "passed"}]}],
                        },
                        {
                            "title": "Top Picks Add To Cart buttons",
                            "ok": False,
                            "file": "cart.spec.ts",
                            "line": 28,
                            "tests": [
                                {
                                    "status": "unexpected",
                                    "results": [
                                        {
                                            "status": "failed",
                                            "errors": [
                                                {
                                                    "message": "Error: expect(received).toBeGreaterThan(expected)\n\nExpected: > 0\nReceived: 0",
                                                    "location": {"file": "cart.spec.ts", "line": 30},
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                    "suites": [],
                }
            ],
            "specs": [],
        },
        {
            "title": "search.spec.ts",
            "suites": [
                {
                    "title": "Search Results",
                    "specs": [
                        {
                            "title": "Add To Cart button is enabled",
                            "ok": False,
                            "file": "search.spec.ts",
                            "line": 25,
                            "tests": [
                                {
                                    "status": "unexpected",
                                    "results": [
                                        {
                                            "status": "failed",
                                            "errors": [
                                                {
                                                    "message": "TimeoutError: locator.click: Timeout 10000ms exceeded.\nCall log:\n  - waiting for getByRole('button', { name: /add to cart/i })",
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                    "suites": [],
                }
            ],
            "specs": [],
        },
    ],
}


class TestParseFailures:

    def test_extracts_failures(self, tmp_path):
        path = tmp_path / "results.json"
        path.write_text(json.dumps(SAMPLE_RESULTS))

        failures = parse_failures(path)
        assert len(failures) == 2

    def test_failure_has_error_message(self, tmp_path):
        path = tmp_path / "results.json"
        path.write_text(json.dumps(SAMPLE_RESULTS))

        failures = parse_failures(path)
        assert "toBeGreaterThan" in failures[0]["error"]

    def test_failure_has_spec_file(self, tmp_path):
        path = tmp_path / "results.json"
        path.write_text(json.dumps(SAMPLE_RESULTS))

        failures = parse_failures(path)
        assert failures[0]["spec_file"] == "cart.spec.ts"
        assert failures[1]["spec_file"] == "search.spec.ts"

    def test_failure_maps_to_pom(self, tmp_path):
        path = tmp_path / "results.json"
        path.write_text(json.dumps(SAMPLE_RESULTS))

        failures = parse_failures(path)
        assert failures[0]["pom_file"] == "CartPage.ts"
        assert failures[0]["route"] == "/cart"
        assert failures[1]["pom_file"] == "SearchPage.ts"

    def test_skips_passing_tests(self, tmp_path):
        results = {
            "suites": [{
                "title": "homepage.spec.ts",
                "suites": [{
                    "title": "Homepage",
                    "specs": [{
                        "title": "hero banner visible",
                        "ok": True,
                        "file": "homepage.spec.ts",
                        "line": 12,
                        "tests": [{"status": "expected", "results": [{"status": "passed"}]}],
                    }],
                    "suites": [],
                }],
                "specs": [],
            }],
        }
        path = tmp_path / "results.json"
        path.write_text(json.dumps(results))

        failures = parse_failures(path)
        assert len(failures) == 0

    def test_empty_results(self, tmp_path):
        path = tmp_path / "results.json"
        path.write_text('{"suites": []}')

        failures = parse_failures(path)
        assert len(failures) == 0

    def test_strips_ansi_codes(self, tmp_path):
        results = {
            "suites": [{
                "title": "test.spec.ts",
                "suites": [{
                    "title": "Test",
                    "specs": [{
                        "title": "fails",
                        "ok": False,
                        "file": "test.spec.ts",
                        "line": 1,
                        "tests": [{
                            "status": "unexpected",
                            "results": [{
                                "status": "failed",
                                "errors": [{"message": "\x1b[31mError: timeout\x1b[0m"}],
                            }],
                        }],
                    }],
                    "suites": [],
                }],
                "specs": [],
            }],
        }
        path = tmp_path / "results.json"
        path.write_text(json.dumps(results))

        failures = parse_failures(path)
        assert "\x1b" not in failures[0]["error"]


class TestSpecToPomMapping:

    def test_all_specs_have_mapping(self):
        expected_specs = [
            "homepage.spec.ts", "nav.spec.ts", "search.spec.ts",
            "product.spec.ts", "cart.spec.ts", "checkout.spec.ts",
            "sign-in.spec.ts", "register.spec.ts", "store-locator.spec.ts",
            "rvs-for-sale.spec.ts", "rvs-for-sale-detail.spec.ts",
            "good-sam.spec.ts", "footer.spec.ts", "rv-parts.spec.ts",
        ]
        for spec in expected_specs:
            assert spec in _SPEC_TO_POM, f"Missing mapping for {spec}"

    def test_all_pom_files_exist(self):
        pom_dir = Path(__file__).resolve().parent.parent / "page_objects"
        for spec, (pom_file, route) in _SPEC_TO_POM.items():
            pom_path = pom_dir / pom_file
            assert pom_path.exists(), f"POM file {pom_file} (for {spec}) not found"
