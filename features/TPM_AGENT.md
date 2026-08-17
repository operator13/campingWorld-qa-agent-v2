# Feature: Technical Product Manager Agent

> An autonomous agent that discovers, scopes, and specs new features — reading the codebase, metrics, memory, and external sources to identify gaps and draft build specs. It proposes, humans decide.

**Status:** PLANNED
**Priority:** High
**Depends on:** Core framework (Phases 0-4), Memory feature (M1-M2 minimum)

---

## The Problem

As the project grows, feature discovery becomes manual and reactive — someone has to notice a gap, think through the spec, write it up, and pre-mortem it. Meanwhile, the system is generating data (metrics, memory, Triage patterns, human corrections) that contains signals about what's needed next. Nobody is reading that data systematically.

## The Solution

A TPM agent that reads everything the system knows — code, metrics, memory, Jira, Figma — and produces actionable feature specs in `features/`. It proposes with `Status: PROPOSED`; a human promotes to `PLANNED` before anything gets built.

---

## A. What the TPM Agent Reads

| Source | What it learns | Example insight |
|--------|---------------|-----------------|
| **`features/`** | Existing specs, their status, dependencies, gaps between them | "MEMORY M3 is TODO but AUTO_THRESHOLD_TUNING depends on it" |
| **`memory/`** | Locator history, failure patterns, human decisions, app structure | "80% of heals are on /checkout — dedicated checkout stability feature?" |
| **`metrics.db`** | Escape rate, Triage accuracy, run history, per-route stats | "Escape rate is 15% on /search — tests are missing coverage" |
| **`PROJECT_STATUS.md`** | Overall progress, what's done, what's pending | "Phase 4 is complete but observability alerts have never fired" |
| **`CHANGELOG.md`** | What was built, when, in which commit | "No changes to Planner in 30 days despite 5 human corrections on test quality" |
| **Codebase** | `qa_agent/`, `tests/`, current node implementations | "Generator doesn't use memory yet — M3 is needed" |
| **Jira (via MCP)** | Upcoming epics, recent bugs, team priorities | "3 new epics planned for /dashboard — no tests exist for that route" |
| **Figma (via MCP)** | New or changed designs not yet covered by tests | "New Figma frame for /settings added last week, no intake ticket" |
| **`memory/HUMAN_DECISIONS.md`** | Patterns in human corrections | "Humans override Triage on timeout errors 60% of the time — rubric needs updating" |
| **`memory/FAILURES.md`** | Recurring failure patterns | "FP-007 has 12 occurrences and no resolution — systemic issue" |

---

## B. What the TPM Agent Produces

### 1. Feature proposals (`features/FEATURE_NAME.md`)

Same format as existing specs:
- Problem statement derived from data
- Solution with architecture sketch
- Phased build plan with tasks, tests, exit gates
- Assumptions and not-in-scope
- Pre-mortem (self-applied before marking ready)
- `Status: PROPOSED` — never `PLANNED` without human approval

### 2. Gap reports

Periodic analysis surfaced via CLI or dashboard:

```
=== TPM Agent — Gap Report ===

COVERAGE GAPS:
  - /dashboard: 0 tests, 3 Jira epics planned (QA-201, QA-205, QA-210)
  - /settings: Figma frame exists (node 1:42), no intake ticket

MEMORY INSIGHTS:
  - Healer cache hit rate: 12% (below 30% target) — M3 (app structure) would help
  - 8 human corrections in last 7 days, all on timeout errors — Triage rubric may need updating
  - /checkout locators drifted 6 times this month — UI is unstable, flag to dev team?

FEATURE DEPENDENCY ISSUES:
  - AUTO_THRESHOLD_TUNING.md depends on MEMORY M2 (done) but references M3 data (not done)
  - PER_COMMIT_PR_GATING.md cost gates not yet measurable — needs 30 nightly runs first

STALE FEATURES:
  - WEBSOCKET_TESTING.md — status PLANNED but no app WebSocket usage detected

PROPOSED ACTIONS:
  1. [NEW SPEC] DASHBOARD_TESTING.md — cover the /dashboard route before epics land
  2. [UPDATE] MEMORY.md — prioritize M3, Healer cache hit rate is below target
  3. [UPDATE] Triage rubric — timeout error classification needs refinement
```

### 3. Status updates

Automatically updates `PROJECT_STATUS.md` and `CHANGELOG.md` after implementation phases complete (when asked).

---

## C. How It Works

### Trigger modes

| Mode | Trigger | Scope |
|------|---------|-------|
| **On demand** | `qa-agent tpm review` | Full analysis of all sources |
| **Post-run** | After every nightly run completes | Lightweight — metrics + memory only |
| **Scheduled** | Weekly cron | Full analysis + gap report |

### Architecture

The TPM agent is a standalone function (not a graph node — it doesn't participate in the test pipeline). It reads state but never writes to the graph.

```python
async def tpm_review(
    mode: str = "full",  # "full" | "post-run" | "gap-report"
) -> TPMReport:
    """Run the TPM agent and produce a report + proposals."""

    # 1. Gather context from all sources
    context = await _gather_context(mode)

    # 2. Ask the LLM to analyze and identify gaps
    analysis = await _analyze(context)

    # 3. For each identified gap, draft a feature spec
    proposals = []
    for gap in analysis.gaps:
        spec = await _draft_spec(gap, context)
        spec = await _pre_mortem(spec)  # self-review before proposing
        proposals.append(spec)

    # 4. Write proposals to features/
    for proposal in proposals:
        _write_proposal(proposal)

    # 5. Generate gap report
    report = _build_report(analysis, proposals)

    return report
```

### Context gathering

```python
async def _gather_context(mode: str) -> TPMContext:
    """Read all available sources into a structured context object."""
    ctx = TPMContext()

    # Always read
    ctx.features = _read_features_dir()
    ctx.project_status = _read_file("PROJECT_STATUS.md")
    ctx.changelog = _read_file("CHANGELOG.md")

    # Read memory
    memory = MemoryStore()
    ctx.locator_history = memory.get_locator_history_all()
    ctx.failure_patterns = memory.get_all_failure_patterns()
    ctx.human_decisions = memory.get_triage_calibration(n=50)
    ctx.app_structure = memory.get_all_routes()
    ctx.test_stability = memory.get_all_test_stability()

    # Read metrics
    db = MetricsDB()
    ctx.dashboard = db.get_dashboard()
    ctx.recent_runs = db.get_recent_runs(n=30)

    if mode == "full":
        # Read codebase structure
        ctx.codebase = _scan_codebase()

        # Read Jira (upcoming work)
        try:
            ctx.jira_epics = await _fetch_jira_upcoming()
        except Exception:
            ctx.jira_epics = []

        # Read Figma (uncovered designs)
        try:
            ctx.figma_frames = await _fetch_figma_frames()
        except Exception:
            ctx.figma_frames = []

    return ctx
```

### Spec drafting prompt

The LLM receives the full context and a system prompt:

```
You are a Technical Product Manager for a QA automation framework.

Given the current state of the project (features, metrics, memory, codebase),
identify gaps and propose new features or updates to existing ones.

For each proposal:
1. State the problem (backed by data from metrics/memory)
2. Propose a solution with clear scope
3. Draft a phased build plan
4. List assumptions and not-in-scope
5. Pre-mortem: what could go wrong?

Output as a structured JSON array of feature proposals.
```

---

## D. Safety Boundaries

| Rule | Why |
|------|-----|
| **Proposals are `PROPOSED`, never `PLANNED`** | A human must review and promote before any work starts |
| **Never modifies existing feature specs** | It can suggest updates in the gap report, but doesn't edit files |
| **Never triggers implementation** | It writes specs, not code |
| **Never changes priorities** | It proposes priority in the spec; the human decides |
| **Reads memory, never writes** | It's an observer, not a participant in the learning loop |
| **Proposals require data backing** | Every problem statement must cite metrics, memory, or external data — no speculation |

---

## E. Build Phases

### Phase TPM1 — Core review engine + gap report
**Goal:** `qa-agent tpm review` reads all sources and produces a gap report.

| # | Task | Status |
|---|------|--------|
| 1 | `qa_agent/tpm.py` — context gathering from features/, memory/, metrics, codebase | TODO |
| 2 | `TPMContext` + `TPMReport` Pydantic models | TODO |
| 3 | LLM analysis: identify coverage gaps, stale features, dependency issues | TODO |
| 4 | Gap report output: formatted console report | TODO |
| 5 | CLI command: `qa-agent tpm review` | TODO |
| 6 | System prompt: TPM analysis rubric | TODO |

**Tests:**
- Unit: context gathering reads features/, memory/, metrics correctly
- Unit: gap report includes coverage gaps, memory insights, stale features
- Unit: report is structured and parseable
- Integration: full review on the current project produces a meaningful report

**Done when:** `qa-agent tpm review` produces a data-backed gap report from all sources.

---

### Phase TPM2 — Feature spec drafting
**Goal:** TPM agent drafts new feature specs and writes them to features/.

| # | Task | Status |
|---|------|--------|
| 1 | Spec drafting: LLM generates feature spec from identified gap | TODO |
| 2 | Self-pre-mortem: LLM reviews its own spec for holes before writing | TODO |
| 3 | Write to `features/FEATURE_NAME.md` with `Status: PROPOSED` | TODO |
| 4 | Naming convention: auto-generate uppercase filename from feature title | TODO |
| 5 | Dedup check: don't propose a feature that already exists | TODO |

**Tests:**
- Unit: generated spec follows the standard format (problem, solution, phases, tests)
- Unit: spec has `Status: PROPOSED` header
- Unit: pre-mortem identifies at least one risk
- Unit: duplicate features are not proposed
- Integration: a coverage gap → a complete feature spec in features/

**Done when:** TPM agent writes well-structured, pre-mortemed feature specs for identified gaps.

---

### Phase TPM3 — External source integration (Jira + Figma)
**Goal:** TPM reads upcoming Jira epics and uncovered Figma designs.

| # | Task | Status |
|---|------|--------|
| 1 | Jira MCP: fetch upcoming epics/stories not yet covered by tests | TODO |
| 2 | Figma MCP: detect new/changed frames not yet in intake | TODO |
| 3 | Cross-reference: Jira epic → existing test coverage → gap | TODO |
| 4 | Cross-reference: Figma frame → existing route map → gap | TODO |

**Tests:**
- Unit: Jira upcoming epics parsed correctly
- Unit: Figma frame change detection works
- Integration: new Jira epic with no tests → gap report entry

**Done when:** TPM identifies untested upcoming work from Jira and uncovered designs from Figma.

---

### Phase TPM4 — Post-run + scheduled modes
**Goal:** TPM runs automatically after nightly runs and on a weekly schedule.

| # | Task | Status |
|---|------|--------|
| 1 | Post-run mode: lightweight analysis (metrics + memory only) after each nightly run | TODO |
| 2 | Weekly scheduled mode via cron | TODO |
| 3 | Notification: post gap report to Slack or email when new gaps are found | TODO |
| 4 | Auto-update PROJECT_STATUS.md when asked | TODO |

**Tests:**
- Unit: post-run mode skips codebase/Jira/Figma scanning (fast)
- Unit: scheduled mode triggers full review
- Integration: simulated nightly run → post-run TPM report

**Done when:** TPM runs automatically and notifies when it finds something worth proposing.

---

## F. Assumptions

- The TPM agent uses Opus (strongest reasoning) for analysis and spec drafting.
- It reads everything but writes only to `features/` (new files with `PROPOSED` status).
- It never modifies existing specs, code, or configuration.
- A human must promote `PROPOSED` → `PLANNED` before any implementation begins.
- Memory reads use the existing `MemoryStore` interface — no new memory methods needed (except `get_all_*` variants for bulk reads).
- Cost per review: ~$2-5 (one Opus call with large context). Acceptable for weekly/nightly cadence.

## G. Not in Scope

- Implementation of proposed features (TPM writes specs, not code)
- Automatic prioritization (it suggests, human decides)
- Modifying existing feature specs (suggests updates in gap report only)
- Sprint planning or timeline estimation
- Team assignment or workload balancing
