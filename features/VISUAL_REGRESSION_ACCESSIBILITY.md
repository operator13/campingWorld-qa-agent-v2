# Feature: Visual Regression & Accessibility Checks

> Catch visual layout drift and accessibility violations by comparing screenshots against Figma baselines and running automated a11y audits.

**Status:** PLANNED
**Priority:** Medium
**Depends on:** Core framework (Phases 0-4), Figma MCP integration

---

## The Problem

The current framework tests *behavior* (clicks, navigation, assertions on text) but not *appearance*. A button could work perfectly but be 2px off, overlapping another element, or the wrong color. Similarly, missing alt text, broken tab order, or insufficient contrast are invisible to behavioral tests.

## The Solution

Two complementary checks that run alongside the existing test suite:

1. **Visual regression** — screenshot comparison against Figma design baselines
2. **Accessibility audit** — automated axe-core scan against WCAG standards

---

## A. Visual Regression

### How it works

1. **Baseline capture:** The Design Reader extracts expected screenshots from Figma (via `get_screenshot` MCP tool) per route/viewport.
2. **Runtime capture:** The Executor takes screenshots after each test via Playwright's `page.screenshot()`.
3. **Comparison:** A pixel-diff algorithm (e.g. `pixelmatch` or Playwright's built-in `toHaveScreenshot()`) compares runtime vs baseline.
4. **Threshold:** Differences below a configurable percentage (e.g. 0.5%) are ignored; above triggers a visual regression failure.

### Storage

```
baselines/
  checkout/
    desktop.png
    mobile.png
  login/
    desktop.png
```

Baselines are git-tracked and updated explicitly (not auto-updated on drift).

---

## B. Accessibility Checks

### How it works

1. **Inject axe-core** into the page via Playwright's `page.evaluate()`.
2. **Run audit** against WCAG 2.1 AA (configurable level).
3. **Collect violations** — each violation includes the element, rule, impact level, and fix suggestion.
4. **Report** — violations are included in the `RunResult` and optionally filed as Jira tickets.

### What it checks

| Rule category | Examples |
|--------------|---------|
| Color contrast | Text below 4.5:1 ratio |
| Keyboard navigation | Elements not reachable via Tab |
| ARIA | Missing labels, invalid roles |
| Images | Missing alt text |
| Forms | Inputs without associated labels |
| Headings | Skipped heading levels |

---

## C. Build Phases

### Phase VA1 — Visual regression with Playwright snapshots
| # | Task | Status |
|---|------|--------|
| 1 | Baseline capture from Figma via MCP `get_screenshot` tool | TODO |
| 2 | Runtime screenshot capture in Executor after each test | TODO |
| 3 | Pixel-diff comparison using Playwright's `toHaveScreenshot()` | TODO |
| 4 | Configurable threshold (`VISUAL_DIFF_THRESHOLD=0.5`) | TODO |
| 5 | Visual diff report: side-by-side baseline vs actual with highlighted differences | TODO |
| 6 | Baseline management: CLI command to update baselines (`qa-agent baselines update`) | TODO |

**Tests:**
- Unit: baseline capture produces PNG files per route/viewport
- Unit: identical screenshots pass; modified screenshots fail above threshold
- Unit: threshold is configurable
- Integration: a CSS change triggers a visual regression failure

**Done when:** Layout changes that don't affect behavior are caught and reported.

### Phase VA2 — Accessibility audits
| # | Task | Status |
|---|------|--------|
| 1 | axe-core injection via Playwright `page.evaluate()` | TODO |
| 2 | WCAG level configuration (A, AA, AAA) | TODO |
| 3 | Violation collection and structured reporting | TODO |
| 4 | Integration with Defect Report — a11y violations filed as Jira tickets | TODO |
| 5 | Per-route a11y score tracking in Metrics DB | TODO |

**Tests:**
- Unit: axe-core runs and returns violations on a page with known issues
- Unit: clean page returns zero violations
- Unit: violations are structured with element, rule, impact
- Integration: a11y violation triggers a defect report

**Done when:** Every test run includes an a11y audit; violations are reported and tracked.

### Phase VA3 — Figma-to-DOM design token comparison
| # | Task | Status |
|---|------|--------|
| 1 | Extract design tokens from Figma (colors, spacing, typography) via MCP | TODO |
| 2 | Extract computed styles from the live DOM via Playwright | TODO |
| 3 | Token comparison: flag mismatches (wrong font size, wrong color, wrong spacing) | TODO |

**Done when:** Design token drift (e.g. wrong brand color in production) is detected automatically.

---

## D. Assumptions

- Visual regression uses Playwright's built-in snapshot testing (`toHaveScreenshot`) — no external services.
- Baselines are stored in git, not in a database.
- Accessibility uses axe-core (MIT licensed, industry standard).
- Both checks run as part of the existing Executor — no new graph nodes.
- Viewport matrix: desktop + mobile (from playwright.config projects).

## E. Not in Scope

- Cross-browser visual comparison (Chrome vs Safari rendering differences)
- PDF/print layout testing
- Manual accessibility testing workflows
- WCAG AAA compliance (AA is the default target)
