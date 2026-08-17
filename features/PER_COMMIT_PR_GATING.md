# Feature: Per-Commit / PR-Gating Mode

> Run the QA agent on every pull request — blocking merge when tests fail — once cost and latency are proven acceptable.

**Status:** PLANNED
**Priority:** Low (gated on cost/latency proof)
**Depends on:** Core framework (Phases 0-4), proven nightly run stability

---

## The Problem

The framework currently runs nightly. Bugs found at 2 AM are reported the next morning — hours or days after the code was merged. Per-commit gating catches regressions *before* merge, when the context is fresh and the fix is cheap.

## The Solution

A GitHub Actions workflow that triggers on PR events, runs the QA agent against the PR's changes, and reports pass/fail as a required status check.

---

## A. How It Differs from Nightly

| Concern | Nightly | Per-commit |
|---------|---------|------------|
| Trigger | Cron schedule | PR open/push |
| Scope | Full test suite | Changed routes only (targeted) |
| Time budget | Minutes are fine | Must complete in < 5 min |
| Cost | ~$5/run acceptable | Must be < $1/run |
| Failure mode | Report → Jira | Block merge → PR comment |
| Healing | Full heal loop | No healing — just report (speed) |

### Targeted scope

Instead of running the full suite, the per-commit mode:
1. Detects which files changed in the PR (`git diff --name-only`)
2. Maps changed files to affected routes (via `figma_route_map` or convention)
3. Runs only the tests for those routes

---

## B. Build Phases

### Phase PC1 — Change detection + targeted test selection
| # | Task | Status |
|---|------|--------|
| 1 | `git diff` parser: extract changed files from PR | TODO |
| 2 | File → route mapping: which routes are affected by which source files | TODO |
| 3 | Test selector: filter `plan` to only affected routes | TODO |
| 4 | CLI flag: `qa-agent run --mode pr --changed-files <list>` | TODO |

**Tests:**
- Unit: file-to-route mapping works for common patterns
- Unit: test selector filters correctly
- Integration: a PR changing checkout code only runs checkout tests

**Done when:** The agent can run a targeted subset of tests based on changed files.

### Phase PC2 — GitHub Actions PR workflow
| # | Task | Status |
|---|------|--------|
| 1 | `.github/workflows/qa-agent-pr.yml` triggered on PR open/push | TODO |
| 2 | Cost guard: abort if estimated token usage exceeds budget | TODO |
| 3 | Time guard: abort if wall-clock exceeds 5 minutes | TODO |
| 4 | PR comment with results (pass/fail + details) via `gh pr comment` | TODO |
| 5 | Required status check configuration guide | TODO |

**Tests:**
- Unit: cost estimation based on route count
- Unit: time guard triggers abort
- Integration: PR workflow runs and posts comment

**Done when:** PRs get a QA agent status check; merge is blocked on failure.

### Phase PC3 — Incremental caching
| # | Task | Status |
|---|------|--------|
| 1 | Cache test results per route + commit hash | TODO |
| 2 | Skip re-running unchanged routes (cache hit) | TODO |
| 3 | Invalidate cache on Figma design changes | TODO |

**Done when:** Repeated pushes to the same PR only re-run tests for newly changed routes.

---

## C. Cost/Latency Gates (must be met before enabling)

| Gate | Threshold | How to measure |
|------|-----------|---------------|
| Cost per run | < $1 (targeted) | Token usage from nightly runs, scaled to subset |
| Wall-clock time | < 5 minutes | Time the targeted mode on a sample PR |
| False positive rate | < 5% | Track flaky failures over 30 nightly runs |
| Nightly stability | 30 consecutive green runs | Metrics DB |

**Do not enable per-commit mode until all gates are met.**

---

## D. Assumptions

- No healing in per-commit mode (too slow) — just classify and report.
- Targeted mode requires a file → route mapping (maintained in config or inferred).
- PR comments use `gh pr comment` (GitHub CLI).
- Cost estimation uses token counts from recent nightly runs as a baseline.

## E. Not in Scope

- Running on every commit to `main` (only PRs)
- Parallel PR runs (one run per PR, queued)
- Auto-fix PRs (the agent reports but doesn't push fixes in PR mode)
