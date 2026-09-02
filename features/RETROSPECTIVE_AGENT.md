# Feature: Retrospective Agent

> An agent that periodically analyzes triage reports, unhealed failures, and agent performance to recommend improvements to the Triage rubric, Healer strategies, and test configurations — closing the feedback loop so the system learns from its own failures.

**Status:** PLANNED
**Priority:** High
**Depends on:** Triage Agent, Healer Agent, Eval Agent, Audit Trail

---

## Architecture Overview — Retrospective Agent + Claude Dreaming

### The Complete System (How Everything Connects)

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                          QA AUTOMATION FRAMEWORK                                    ║
║                                                                                      ║
║   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               ║
║   │   TRIAGE    │  │   PLANNER   │  │  GENERATOR  │  │   HEALER    │               ║
║   │   Agent     │  │   Agent     │  │   Agent     │  │   Agent     │               ║
║   │             │  │             │  │             │  │             │               ║
║   │ Classifies  │  │ Plans test  │  │ Generates   │  │ Fixes drift │               ║
║   │ failures    │  │ cases from  │  │ Playwright  │  │ + timing    │               ║
║   │ drift/flake │  │ UI specs    │  │ specs+POMs  │  │ flakes      │               ║
║   │ /defect     │  │             │  │             │  │             │               ║
║   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               ║
║          │                │                │                │                        ║
║          │  Each agent run produces data that feeds into memory                      ║
║          │                │                │                │                        ║
║          ▼                ▼                ▼                ▼                        ║
║   ┌─────────────────────────────────────────────────────────────────────────┐       ║
║   │                         LOCAL MEMORY STORE                              │       ║
║   │                         memory/ (14 markdown files)                     │       ║
║   │                                                                         │       ║
║   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │       ║
║   │  │ FAILURES.md  │ │TIMING_FIXES  │ │TEST_STABILITY│ │ LESSONS.md   │  │       ║
║   │  │              │ │.md           │ │.md           │ │              │  │       ║
║   │  │ Error        │ │ Known waits  │ │ Pass/fail    │ │ Patterns +   │  │       ║
║   │  │ patterns +   │ │ per element  │ │ per test,    │ │ route        │  │       ║
║   │  │ resolutions  │ │ + strategy   │ │ flakiness %  │ │ insights     │  │       ║
║   │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │       ║
║   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │       ║
║   │  │ locators/    │ │HEALER_STATS  │ │HUMAN_        │ │CONFIDENCE_   │  │       ║
║   │  │ *.md         │ │.md           │ │DECISIONS.md  │ │RUBRIC.md     │  │       ║
║   │  │              │ │              │ │              │ │              │  │       ║
║   │  │ Per-route    │ │ Cache hits   │ │ Human        │ │ C1-C5        │  │       ║
║   │  │ locator      │ │ vs LLM      │ │ overrides +  │ │ scoring      │  │       ║
║   │  │ change log   │ │ call counts  │ │ verdicts     │ │ criteria     │  │       ║
║   │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │       ║
║   └─────────────────────────────────┬───────────────────────────────────────┘       ║
║                                     │                                                ║
║          Each test run also produces│reports                                         ║
║                                     │                                                ║
║   ┌─────────────────────────────────┼───────────────────────────────────────┐       ║
║   │                         REPORT HISTORY                                  │       ║
║   │                                 │                                       │       ║
║   │  ┌──────────────┐ ┌────────────┴─┐ ┌──────────────┐                   │       ║
║   │  │ health-      │ │ health-      │ │ eval/        │                   │       ║
║   │  │ reports/     │ │ reports/     │ │ reports/     │                   │       ║
║   │  │ *.json       │ │ *-triage.json│ │ */           │                   │       ║
║   │  │              │ │              │ │              │                   │       ║
║   │  │ Domain       │ │ Unhealed     │ │ Agent        │                   │       ║
║   │  │ scores,      │ │ failures,    │ │ accuracy,    │                   │       ║
║   │  │ pass/fail    │ │ reasoning,   │ │ tokens,      │                   │       ║
║   │  │ per run      │ │ C1-C5        │ │ cost         │                   │       ║
║   │  │              │ │ breakdown    │ │ per run      │                   │       ║
║   │  └──────────────┘ └──────────────┘ └──────────────┘                   │       ║
║   └─────────────────────────────────────────────────────────────────────────┘       ║
║                                                                                      ║
╚════════════════════════════════════════════════════╤═════════════════════════════════╝
                                                     │
                    All this data flows DOWN          │
                    into the Retrospective Agent      │
                                                     │
╔════════════════════════════════════════════════════╧═════════════════════════════════╗
║                                                                                      ║
║                          RETROSPECTIVE AGENT                                         ║
║                                                                                      ║
║   TRIGGER: Every 10 test runs / on-demand from dashboard / weekly cron               ║
║                                                                                      ║
║   ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║   │                                                                              │   ║
║   │   STEP 1: COLLECT                                                            │   ║
║   │   ─────────────────                                                          │   ║
║   │   Load recent data (last 7 days):                                            │   ║
║   │   • Triage reports → unhealed failures, confidence breakdowns                │   ║
║   │   • Health reports → domain pass/fail trends                                 │   ║
║   │   • Eval reports  → agent accuracy, token usage                              │   ║
║   │   • Memory files  → stability data, healer stats, timing fixes              │   ║
║   │                                                                              │   ║
║   │   STEP 2: ANALYZE (Rule-Based — Phase RA1)                                   │   ║
║   │   ────────────────────────────────────────                                   │   ║
║   │   Our code — fast, cheap, deterministic:                                     │   ║
║   │                                                                              │   ║
║   │   ┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐  │   ║
║   │   │ Unhealed Patterns  │  │ Rubric Gaps        │  │ Healer Effectiveness │  │   ║
║   │   │                    │  │                    │  │                      │  │   ║
║   │   │ "beforeEach timeout│  │ "C2 is 0.00 in    │  │ "Strategy D has 0%  │  │   ║
║   │   │  occurred 5 times  │  │  78% of runs —     │  │  success rate —     │  │   ║
║   │   │  in 7 days, all    │  │  DOM snapshots     │  │  networkidle waits  │  │   ║
║   │   │  unhealed"         │  │  never captured"   │  │  don't work here"   │  │   ║
║   │   └────────────────────┘  └────────────────────┘  └──────────────────────┘  │   ║
║   │                                                                              │   ║
║   │   ┌────────────────────┐  ┌────────────────────┐                            │   ║
║   │   │ Stability Trends   │  │ Cost Analysis      │                            │   ║
║   │   │                    │  │                    │                            │   ║
║   │   │ "rv-parts.spec.ts  │  │ "Triage uses 55%  │                            │   ║
║   │   │  failing 3 straight│  │  of total spend —  │                            │   ║
║   │   │  days — page may   │  │  fast-path could   │                            │   ║
║   │   │  be removed"       │  │  save $0.20/run"   │                            │   ║
║   │   └────────────────────┘  └────────────────────┘                            │   ║
║   │                                                                              │   ║
║   └──────────────────────────────────────┬───────────────────────────────────────┘   ║
║                                          │                                           ║
║                                          │ findings (structured JSON)                ║
║                                          │                                           ║
║   ┌──────────────────────────────────────▼───────────────────────────────────────┐   ║
║   │                                                                              │   ║
║   │   STEP 3: DREAM (Claude Dreaming API — Phase RA7)                            │   ║
║   │   ───────────────────────────────────────────                                │   ║
║   │                                                                              │   ║
║   │   ┌─────────────────────────────────────────────────────────────────────┐    │   ║
║   │   │                     CLAUDE DREAMING API                             │    │   ║
║   │   │                                                                     │    │   ║
║   │   │   INPUTS:                                                           │    │   ║
║   │   │   ┌───────────────────┐  ┌───────────────────────────────────┐     │    │   ║
║   │   │   │ Memory Store      │  │ Session Transcripts (50-100)     │     │    │   ║
║   │   │   │                   │  │                                   │     │    │   ║
║   │   │   │ memstore_019Yoq.. │  │ Each triage+health report pair   │     │    │   ║
║   │   │   │ (qa-automation-   │  │ converted to a conversation:     │     │    │   ║
║   │   │   │  memory)          │  │                                   │     │    │   ║
║   │   │   │                   │  │ "Run 08_31 completed. 126/127    │     │    │   ║
║   │   │   │ Synced from our   │  │  passed. Nav failed: beforeEach  │     │    │   ║
║   │   │   │ memory/ folder    │  │  timeout. Classified test_flake  │     │    │   ║
║   │   │   │                   │  │  confidence 0.20. Not healed:    │     │    │   ║
║   │   │   │                   │  │  below threshold."               │     │    │   ║
║   │   │   └───────────────────┘  └───────────────────────────────────┘     │    │   ║
║   │   │                                                                     │    │   ║
║   │   │   + Custom Instructions:                                            │    │   ║
║   │   │   "Rule-based analysis found these findings: {RA1 output}.          │    │   ║
║   │   │    Validate with evidence from transcripts. Surface patterns        │    │   ║
║   │   │    the rules missed. Recommend specific code changes."              │    │   ║
║   │   │                                                                     │    │   ║
║   │   │   DREAMING PROCESS (async, minutes to hours):                       │    │   ║
║   │   │   ┌─────────┐    ┌─────────┐    ┌─────────┐                       │    │   ║
║   │   │   │ VERIFY  │ →  │ORGANIZE │ →  │ ENRICH  │                       │    │   ║
║   │   │   │         │    │         │    │         │                       │    │   ║
║   │   │   │ Check   │    │ Merge   │    │ Surface │                       │    │   ║
║   │   │   │ memory  │    │ dupes,  │    │ novel   │                       │    │   ║
║   │   │   │ entries │    │ prune   │    │ cross-  │                       │    │   ║
║   │   │   │ against │    │ stale,  │    │ session │                       │    │   ║
║   │   │   │ recent  │    │ resolve │    │ patterns│                       │    │   ║
║   │   │   │ sessions│    │ conflicts│   │ & recs  │                       │    │   ║
║   │   │   └─────────┘    └─────────┘    └─────────┘                       │    │   ║
║   │   │                                                                     │    │   ║
║   │   │   OUTPUTS:                                                          │    │   ║
║   │   │   ┌───────────────────────────┐  ┌───────────────────────────┐     │    │   ║
║   │   │   │ Optimized Memory Store    │  │ Cross-Session Insights    │     │    │   ║
║   │   │   │                           │  │                           │     │    │   ║
║   │   │   │ • Deduped FAILURES.md     │  │ • "Nav tests flake on    │     │    │   ║
║   │   │   │ • Pruned stale locators   │  │    Tuesdays — correlates │     │    │   ║
║   │   │   │ • Merged timing fixes     │  │    with CW deploy cycle" │     │    │   ║
║   │   │   │ • Updated LESSONS.md      │  │ • "All scrollIntoView    │     │    │   ║
║   │   │   │                           │  │    fixes use Strategy A  │     │    │   ║
║   │   │   │ → Written back to         │  │    — stop suggesting D"  │     │    │   ║
║   │   │   │   memory/ files           │  │ • "C2 always 0.0 because │     │    │   ║
║   │   │   │                           │  │    no DOM on timeouts"   │     │    │   ║
║   │   │   └───────────────────────────┘  └───────────────────────────┘     │    │   ║
║   │   │                                                                     │    │   ║
║   │   └─────────────────────────────────────────────────────────────────────┘    │   ║
║   │                                                                              │   ║
║   │   FALLBACK: If Dreaming API unavailable → Phase RA2 local LLM synthesis     │   ║
║   │                                                                              │   ║
║   └──────────────────────────────────────┬───────────────────────────────────────┘   ║
║                                          │                                           ║
║                                          │ recommendations + optimized memory        ║
║                                          │                                           ║
║   ┌──────────────────────────────────────▼───────────────────────────────────────┐   ║
║   │                                                                              │   ║
║   │   STEP 4: RECOMMEND & CLASSIFY                                               │   ║
║   │   ────────────────────────────                                               │   ║
║   │                                                                              │   ║
║   │   Each recommendation gets classified:                                       │   ║
║   │                                                                              │   ║
║   │   ┌────────────────────────────┐    ┌────────────────────────────────────┐   │   ║
║   │   │  SURGICAL FIX (1-5 lines)  │    │  STRUCTURAL CHANGE (complex)       │   │   ║
║   │   │                            │    │                                    │   │   ║
║   │   │  Specific file + line      │    │  Multi-file, architectural,        │   │   ║
║   │   │  Exact code diff           │    │  needs investigation               │   │   ║
║   │   │  Can be auto-applied       │    │  Generates build spec in           │   │   ║
║   │   │                            │    │  /features/ for later              │   │   ║
║   │   │  Example:                  │    │                                    │   │   ║
║   │   │  "Add regex to             │    │  Example:                          │   │   ║
║   │   │   confidence.py:92"        │    │  "Redesign Healer Strategy D"      │   │   ║
║   │   └────────────────────────────┘    └────────────────────────────────────┘   │   ║
║   │                                                                              │   ║
║   └──────────────────────────────────────┬───────────────────────────────────────┘   ║
║                                          │                                           ║
╚══════════════════════════════════════════╧═══════════════════════════════════════════╝
                                           │
                                           │ presented on
                                           ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                      ║
║   STEP 5: DASHBOARD APPROVAL (Human-in-the-Loop)                                    ║
║   ──────────────────────────────────────────────                                    ║
║                                                                                      ║
║   ┌──────────────────────────────────────────────────────────────────────────────┐   ║
║   │  RETROSPECTIVE                                    Last dream: 3h ago [▶ RUN]│   ║
║   │                                                                              │   ║
║   │  ⚡ HIGH — Add beforeEach timeout to flake patterns                         │   ║
║   │     confidence.py:92 — surgical fix (1 line)                                │   ║
║   │     ┌─────────────────────────────────────────────┐                         │   ║
║   │     │ + re.compile(r"beforeEach.*Timeout", re.I), │                         │   ║
║   │     └─────────────────────────────────────────────┘                         │   ║
║   │                                                                              │   ║
║   │     [✓ APPROVE]         [✕ REJECT]         [✎ MODIFY]                       │   ║
║   │         │                    │                  │                             │   ║
║   │         ▼                    ▼                  ▼                             │   ║
║   │     ┌─────────┐        ┌─────────┐        ┌─────────┐                       │   ║
║   │     │ Apply   │        │ Record  │        │ Edit    │                       │   ║
║   │     │ code    │        │ reject  │        │ diff    │                       │   ║
║   │     │ change  │        │ + add   │        │ before  │                       │   ║
║   │     │    │    │        │ to sup- │        │ approve │                       │   ║
║   │     │    ▼    │        │ pression│        │ or      │                       │   ║
║   │     │ Git     │        │ list    │        │ reject  │                       │   ║
║   │     │ commit  │        └─────────┘        └─────────┘                       │   ║
║   │     │    │    │                                                              │   ║
║   │     │    ▼    │                                                              │   ║
║   │     │ Run     │                                                              │   ║
║   │     │ eval    │                                                              │   ║
║   │     │    │    │                                                              │   ║
║   │     │    ▼    │                                                              │   ║
║   │     │ Pass?───┼──Yes──▶ ✅ CONFIRMED — pushed to remote                     │   ║
║   │     │    │    │                                                              │   ║
║   │     │    No   │                                                              │   ║
║   │     │    │    │                                                              │   ║
║   │     │    ▼    │                                                              │   ║
║   │     │ REVERT  │──────▶ ⚠ Rolled back — eval score dropped                  │   ║
║   │     └─────────┘                                                              │   ║
║   │                                                                              │   ║
║   │  ⚡ HIGH — rv-parts.spec.ts may need removal                                │   ║
║   │     Structural change — needs investigation                                  │   ║
║   │                                                                              │   ║
║   │     [📝 GENERATE SPEC]     [✕ REJECT]         [✎ MODIFY]                    │   ║
║   │         │                                                                    │   ║
║   │         ▼                                                                    │   ║
║   │     LLM generates build spec → saved to /features/retro-*.md                │   ║
║   │                                                                              │   ║
║   └──────────────────────────────────────────────────────────────────────────────┘   ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
                                           │
                                           │ approved changes flow BACK UP
                                           ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                      ║
║   STEP 6: FEEDBACK LOOP (Improvements Applied)                                       ║
║   ─────────────────────────────────────────────                                      ║
║                                                                                      ║
║   Approved changes improve the agents for the NEXT test run:                         ║
║                                                                                      ║
║   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐  ║
║   │ Triage Rubric  │  │ Healer Prompts │  │ Test Configs   │  │ Memory Store    │  ║
║   │                │  │                │  │                │  │                 │  ║
║   │ • New flake    │  │ • Strategy     │  │ • Timeout      │  │ • Deduped       │  ║
║   │   patterns     │  │   priorities   │  │   adjustments  │  │ • Pruned stale  │  ║
║   │ • Adjusted     │  │ • New fix      │  │ • Spec file    │  │ • New lessons   │  ║
║   │   C1-C5 scores │  │   templates    │  │   additions/   │  │ • Optimized     │  ║
║   │ • Better error │  │ • Locator      │  │   removals     │  │   patterns      │  ║
║   │   matching     │  │   preferences  │  │                │  │                 │  ║
║   └───────┬────────┘  └───────┬────────┘  └───────┬────────┘  └────────┬────────┘  ║
║           │                   │                   │                    │             ║
║           └───────────────────┴───────────────────┴────────────────────┘             ║
║                                       │                                              ║
║                                       ▼                                              ║
║                          ┌─────────────────────────┐                                ║
║                          │    NEXT TEST RUN         │                                ║
║                          │    performs better        │                                ║
║                          │                          │                                ║
║                          │    → fewer unhealed      │                                ║
║                          │    → higher confidence    │                                ║
║                          │    → better fix success   │                                ║
║                          │    → lower token cost     │                                ║
║                          └──────────┬───────────────┘                                ║
║                                     │                                                ║
║                                     │ produces new data                              ║
║                                     │ for the NEXT retrospective                     ║
║                                     │                                                ║
║                                     └──────────▶ CYCLE REPEATS                       ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```

### The Key Insight

```
Traditional QA:    Test → Fail → Fix → Test → Fail → Fix → ...  (reactive, manual)

Our System:        Test → Fail → Triage → Heal → Test           (self-healing)

With Retrospective: Test → Fail → Triage → Heal → Test          (self-improving)
                                     ↑                │
                                     │   Retrospective │
                                     │   + Dreaming    │
                                     │   analyzes WHY  │
                                     │   and improves  │
                                     │   the agents    │
                                     └────────────────┘
```

The system doesn't just fix tests — it fixes **the agents that fix tests**.

---

## The Problem

The system detects failures, classifies them, attempts healing, and documents everything — but no agent reads the documented findings to improve future performance. Triage reports with full reasoning, confidence breakdowns, and not_healed_reasons accumulate in `health-reports/` without anyone analyzing them.

**Current feedback loops that exist:**
- Triage reads `FAILURES.md` for similar past failures → helps with repeat patterns
- Triage reads `HUMAN_DECISIONS.md` for calibration → helps with human-corrected patterns
- Healer reads `locators/` for known fixes → avoids repeated LLM calls
- Healer reads `TIMING_FIXES.md` for known timing fixes → same

**Feedback loops that are missing:**
- Nobody analyzes **why failures go unhealed** → rubric doesn't improve
- Nobody detects **recurring unhealed patterns** → same failures keep surfacing
- Nobody evaluates **whether Healer strategies are effective** → bad strategies persist
- Nobody identifies **systemic issues** → like "C2 is always 0.0 because we never capture DOM"
- Nobody recommends **config changes** → like "increase beforeEach timeout from 30s to 60s"

---

## The Solution

A **Retrospective Agent** that runs after every N test runs (or on-demand) and produces actionable recommendations by analyzing the accumulated data across triage reports, health reports, eval results, and memory files.

---

## What the Retrospective Agent Analyzes

### 1. Unhealed Failure Patterns

Scans all triage reports for failures that were not healed and identifies recurring patterns:

```
FINDING: "beforeEach timeout" failures occurred 5 times in the last 7 days
  - All classified as test_flake with confidence < 0.30
  - All on nav.spec.ts, product.spec.ts, cart.spec.ts
  - None healed — confidence too low due to missing DOM snapshot
  
RECOMMENDATION: Add beforeEach navigation timeout as a recognized
  flake pattern in confidence.py with C1 score 0.25 (currently 0.10).
  This would raise confidence above CONF_SURE for known slow-loading pages.
  
ALTERNATIVE: Increase Playwright navigation timeout from 30s to 60s
  in playwright.config.ts to reduce false timeouts on slow networks.
```

### 2. Confidence Rubric Gaps

Analyzes the confidence breakdown across all triage reports to find systematic scoring weaknesses:

```
FINDING: C2 (DOM evidence) is 0.00 in 78% of triage runs
  - DOM snapshots are rarely captured during test failures
  - This caps confidence at 0.50 via Guard G3 for many legitimate failures
  
RECOMMENDATION: Investigate why DOM snapshots aren't being captured.
  If Playwright doesn't provide them on navigation timeout, consider
  capturing a partial DOM before the timeout fires.

FINDING: C3 (historical match) gives 0.20 to failures seen 3+ times,
  but "beforeEach timeout" has been seen 5 times and still gets 0.00
  
ROOT CAUSE: The error normalization in find_similar_failure() doesn't
  match "beforeEach" timeouts because the URL in the error differs each run.
  
RECOMMENDATION: Normalize URLs in error signatures before matching.
```

### 3. Healer Effectiveness

Reviews healed vs unhealed outcomes to evaluate strategy performance:

```
FINDING: Healer timing fix Strategy A (waitFor before interaction) 
  succeeded 85% of the time, but Strategy D (networkidle) succeeded 0%
  
RECOMMENDATION: Deprioritize Strategy D in HEALER.md prompt.
  Network idle waits are unreliable on campingworld.com due to
  analytics scripts that never finish loading.

FINDING: 3 locator drift fixes were marked as failed after re-run
  - All used getByText() which broke again within 2 days
  
RECOMMENDATION: Add to HEALER.md: "Avoid getByText() for elements
  with dynamic text. Prefer getByTestId() or getByRole()."
```

### 4. Test Stability Trends

Analyzes `TEST_STABILITY.md` and health report history for deteriorating tests:

```
FINDING: cart.spec.ts "Top Picks section shows Add To Cart buttons"
  has failed 4 of the last 10 runs (40% flakiness)
  
RECOMMENDATION: This test depends on a recommendation API that
  returns empty results intermittently. Either:
  - Add a conditional skip when the carousel is empty
  - Increase waitFor timeout for the carousel section
  - Mark as known flaky and reduce its weight in health scoring

FINDING: rv-parts.spec.ts has failed every run for the last 3 days
  - Always "page renders a heading" — TimeoutError on navigation
  
RECOMMENDATION: The /rv-parts page may have been removed or redirected.
  Investigate whether the page still exists. If removed, delete the spec.
```

### 5. Cost Optimization

Reviews token usage across eval and triage runs:

```
FINDING: Triage agent uses 67K tokens per eval run — 55% of total cost
  - 35 scenarios × ~1,900 tokens average per scenario
  - C1 pattern matching could short-circuit 60% of scenarios without LLM
  
RECOMMENDATION: Add a fast-path in triage: if C1 score is 0.30 and
  error pattern is well-known (selector-not-found + "no element matching"),
  skip the LLM call and classify directly. Estimated savings: $0.20/run.
```

---

## Architecture

### Input Sources

| Source | What It Provides |
|--------|-----------------|
| `health-reports/*-triage.json` | Unhealed failures with reasoning, confidence breakdown, error |
| `health-reports/*.json` | Domain pass/fail history, health scores over time |
| `memory/FAILURES.md` | Known failure patterns and resolutions |
| `memory/TEST_STABILITY.md` | Per-test flakiness scores |
| `memory/TIMING_FIXES.md` | Timing fix attempts and success rates |
| `memory/HEALER_STATS.md` | Cache hit rate, LLM call count |
| `memory/locators/*.md` | Locator change history, fix success/failure |
| `qa_agent/eval/reports/*/` | Eval scores, token usage, regressions |
| `memory/HUMAN_DECISIONS.md` | Human overrides and calibration data |

### Output

The Retrospective Agent produces a **Retrospective Report** saved to `memory/RETROSPECTIVE.md` and `memory/retrospectives/{timestamp}.json`:

```markdown
# Retrospective Report — 2026-08-31

## Summary
- Analyzed: 14 triage reports, 52 health reports, 4 eval runs
- Findings: 7 (3 high, 2 medium, 2 low)
- Recommendations: 9

## High Priority Findings
...

## Medium Priority Findings
...

## Recommendations
1. [HIGH] Add beforeEach timeout to flake patterns (confidence.py)
2. [HIGH] Increase navigation timeout to 60s (playwright.config.ts)
3. [MEDIUM] Deprioritize Strategy D in Healer prompt
4. [MEDIUM] Normalize URLs in error signature matching
...
```

### Agent Design

```python
async def retrospective(
    lookback_days: int = 7,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Analyze recent triage, health, and eval data to produce improvement recommendations."""
    
    # 1. Load all data sources
    triage_reports = load_recent_triage_reports(lookback_days)
    health_reports = load_recent_health_reports(lookback_days)
    eval_reports = load_recent_eval_reports()
    stability = load_test_stability()
    healer_stats = load_healer_stats()
    timing_fixes = load_timing_fixes()
    
    # 2. Analyze each dimension
    unhealed_patterns = analyze_unhealed_failures(triage_reports)
    rubric_gaps = analyze_confidence_gaps(triage_reports)
    healer_effectiveness = analyze_healer_outcomes(triage_reports, timing_fixes, healer_stats)
    stability_trends = analyze_test_stability(stability, health_reports)
    cost_analysis = analyze_cost_trends(eval_reports)
    
    # 3. Generate recommendations (LLM-assisted)
    findings = unhealed_patterns + rubric_gaps + healer_effectiveness + stability_trends + cost_analysis
    recommendations = await generate_recommendations(findings)
    
    # 4. Save report
    report = build_retrospective_report(findings, recommendations)
    save_retrospective(report)
    
    return report
```

### LLM vs Rule-Based

| Analysis | Approach | Why |
|----------|----------|-----|
| Unhealed pattern detection | Rule-based | Count occurrences, group by error pattern — no LLM needed |
| Confidence gap analysis | Rule-based | Statistical analysis of C1-C5 distributions |
| Healer effectiveness | Rule-based | Success/failure rates from TIMING_FIXES.md |
| Test stability trends | Rule-based | Flakiness scores and pass/fail ratios |
| Cost analysis | Rule-based | Sum tokens from eval reports |
| Recommendation generation | LLM-assisted | Synthesize findings into actionable, context-aware advice |
| Root cause analysis | LLM-assisted | Connect patterns across data sources to identify systemic issues |

Most analysis is rule-based (cheap, fast). The LLM is only used for the final synthesis step — turning raw findings into human-readable recommendations with context.

---

## How Recommendations Get Applied

### Automatic (Future — with human approval)

The Retrospective Agent could propose code changes:
```
RECOMMENDATION: Add beforeEach timeout to flake patterns
PROPOSED CHANGE: confidence.py line 92 — add to _FLAKE_ERROR_PATTERNS:
  re.compile(r"beforeEach.*Timeout", re.I)
  
[APPROVE] [REJECT] [MODIFY]
```

User clicks APPROVE → the change is applied, committed, and the next triage run benefits.

### Manual (Phase 1)

The report surfaces recommendations that a human reads and decides whether to act on. The dashboard could show a "RETROSPECTIVE" section with the latest findings.

### Memory Integration

Recommendations feed back into the agent memory system:
- Approved recommendations → recorded in `memory/LESSONS.md`
- Rejected recommendations → recorded so the agent doesn't suggest them again
- Applied changes → tracked in `memory/RETROSPECTIVE.md` for future reference

---

## Dashboard Integration

### Retrospective Card

A new section on the dashboard between Agent Evaluation and Test Runner:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  RETROSPECTIVE                               Last run: 2 hours ago  [▶ RUN]│
│                                                                              │
│  7 findings  •  3 high priority  •  9 recommendations                       │
│                                                                              │
│  ⚡ [HIGH] Add beforeEach timeout to flake patterns                         │
│     confidence.py:92 — add regex to _FLAKE_ERROR_PATTERNS                   │
│     Type: Surgical fix (1 line)                                              │
│                                          [✓ APPROVE] [✕ REJECT] [✎ MODIFY] │
│  ─────────────────────────────────────────────────────────────────────────── │
│  ⚡ [HIGH] Increase navigation timeout to 60s                               │
│     playwright.config.ts — change timeout: 30000 → 60000                    │
│     Type: Surgical fix (1 line)                                              │
│                                          [✓ APPROVE] [✕ REJECT] [✎ MODIFY] │
│  ─────────────────────────────────────────────────────────────────────────── │
│  ⚡ [HIGH] rv-parts.spec.ts may need removal (failing 3 days)               │
│     Type: Structural change — needs investigation                            │
│                                  [📝 GENERATE SPEC] [✕ REJECT] [✎ MODIFY] │
│  ─────────────────────────────────────────────────────────────────────────── │
│  ◉ [MED]  Deprioritize Healer Strategy D                                   │
│     HEALER.md — update strategy guidance                                     │
│     Type: Structural change — needs build spec                               │
│                                  [📝 GENERATE SPEC] [✕ REJECT] [✎ MODIFY] │
│  ─────────────────────────────────────────────────────────────────────────── │
│  ◉ [MED]  Normalize URLs in error matching                                  │
│     memory.py:normalize_error() — strip URL paths before comparison          │
│     Type: Surgical fix (3 lines)                                             │
│                                          [✓ APPROVE] [✕ REJECT] [✎ MODIFY] │
│                                                                              │
│  [VIEW FULL REPORT]                                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Recommendation Types & Actions

Each recommendation is classified into one of two types, which determines the available actions:

| Type | Criteria | APPROVE Does | Example |
|------|----------|-------------|---------|
| **Surgical fix** | 1-5 line code change, specific file/line, low risk | Auto-applies the code change, commits to git, re-runs affected eval | Add regex to `_FLAKE_ERROR_PATTERNS` |
| **Structural change** | Multi-file, architectural, or needs investigation | Generates a build spec in `/features/retro-{id}.md` for later implementation | Redesign Healer Strategy D |

### Action Button Behavior

**[✓ APPROVE] — for surgical fixes:**
1. Server applies the exact code change (file, line, old → new)
2. Commits to git with message: `Retro fix: {recommendation title}`
3. Re-runs the affected agent's eval to verify no regression
4. Broadcasts result via WebSocket: "Applied: {title} — eval passed/failed"
5. If eval fails → auto-reverts the change, notifies user
6. Records in `memory/RETROSPECTIVE.md` as applied

**[📝 GENERATE SPEC] — for structural changes:**
1. Retrospective Agent generates a detailed build spec using LLM
2. Saves to `/features/retro-{timestamp}-{slug}.md`
3. Commits to git with message: `Build spec: {recommendation title} (from retrospective)`
4. Dashboard shows: "Build spec created: features/retro-..."
5. Records in `memory/RETROSPECTIVE.md` as spec_generated

**[✕ REJECT]:**
1. Records the rejection with optional reason in `memory/RETROSPECTIVE.md`
2. Agent won't suggest the same recommendation again (suppression)
3. Useful for: "this is intentional behavior, not a bug"

**[✎ MODIFY]:**
1. Opens the recommendation detail in an editable text area
2. User can adjust the proposed change before approving
3. For surgical fixes: edit the code diff
4. For structural changes: edit the spec outline before generation

### Approval Flow Diagram

```
Retrospective Agent produces recommendation
        │
        ├── Surgical fix (1-5 lines)?
        │         │
        │    [✓ APPROVE]              [✕ REJECT]           [✎ MODIFY]
        │         │                       │                      │
        │    Apply code change       Record rejection       Edit proposed change
        │    Git commit              Add to suppression     Then APPROVE or REJECT
        │    Re-run eval             list
        │         │
        │    Eval passed?
        │    ├── Yes → Done, recorded as applied
        │    └── No → Auto-revert, notify user
        │
        └── Structural change (complex)?
                  │
             [📝 GENERATE SPEC]       [✕ REJECT]           [✎ MODIFY]
                  │                       │                      │
             LLM generates            Record rejection       Edit spec outline
             build spec               Add to suppression     Then GENERATE or REJECT
             Save to /features/
             Git commit
             Notify user
```

### Safety Rails & Rollback Plan

Every approved change goes through a **verify → commit → test → confirm OR rollback** cycle. No change is permanent until tests prove it's safe.

#### Surgical Fix Approval Flow (Detailed)

```
User clicks [✓ APPROVE]
        │
        ▼
   1. Save rollback point
      └─ git stash current state (if dirty)
      └─ record current HEAD commit hash as ROLLBACK_SHA
        │
        ▼
   2. Apply the code change
      └─ write the diff to the target file
      └─ git add + commit: "Retro fix: {title}"
      └─ NEW_SHA = current HEAD
        │
        ▼
   3. Run affected tests
      └─ if change is in confidence.py → run triage eval
      └─ if change is in healer.py → run healer eval
      └─ if change is in tests_generated/ → run that spec file
      └─ if change is in playwright.config.ts → run full test suite
        │
        ▼
   4. Evaluate results
      ├── Tests pass + eval score stable or improved?
      │     └─ ✅ CONFIRMED — push to remote
      │     └─ Dashboard: "Applied: {title} — tests passed ✓"
      │     └─ Record in RETROSPECTIVE.md as: applied, verified
      │
      ├── Eval score dropped?
      │     └─ ⚠ REGRESSION DETECTED
      │     └─ git revert NEW_SHA (creates revert commit, preserves history)
      │     └─ Dashboard: "Reverted: {title} — eval score dropped from X to Y"
      │     └─ Record in RETROSPECTIVE.md as: reverted, reason
      │
      └── Tests fail / crash?
            └─ 🚨 CATASTROPHIC FAILURE
            └─ git reset --hard ROLLBACK_SHA (hard reset to safe state)
            └─ git push --force-with-lease (safe force push)
            └─ Dashboard: "Emergency rollback: {title} — tests crashed"
            └─ Record in RETROSPECTIVE.md as: emergency_rollback, error
            └─ Recommendation auto-rejected (added to suppression list)
```

#### Rollback Levels

| Level | Trigger | Action | Reversible? |
|-------|---------|--------|-------------|
| **Level 1: Revert** | Eval score drops but tests still run | `git revert` (clean revert commit) | Yes — revert of revert |
| **Level 2: Hard Reset** | Tests crash, process hangs, or server error | `git reset --hard ROLLBACK_SHA` | Yes — reflog has history |
| **Level 3: Restore Backup** | Multiple files corrupted, git state broken | Restore from pre-approval stash | Yes — stash preserved |

#### Safety Guards

| Guard | What It Prevents |
|-------|-----------------|
| **Pre-flight snapshot** | `ROLLBACK_SHA` saved before any change — always have a safe point |
| **Eval gate** | Changes reverted if eval score drops by any amount |
| **Test gate** | Changes hard-reset if tests crash or timeout |
| **Scope limit** | Surgical fixes limited to 5 lines max — anything larger requires a build spec |
| **File allowlist** | Only files in `qa_agent/`, `memory/`, `tests_generated/`, `playwright.config.ts` can be modified |
| **Human checkpoint** | Nothing is applied without explicit APPROVE click |
| **Suppression on crash** | If a fix causes catastrophic failure, it's auto-rejected and never suggested again |
| **Force push guard** | Only uses `--force-with-lease` (fails if remote has new commits from others) |

### Full Dashboard Visual — Approval Screen

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  QA COMMAND CENTER                                              ● LIVE  UTC     │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐   DOMAIN STATUS                                                │
│  │ SYSTEM      │   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │
│  │ HEALTH      │   │★Cart ││★Chkt ││★Sign ││ Nav  ││ Home ││Search│      │
│  │   92.9%     │   │ 100% ││ 100% ││ 100% ││92.9% ││ 100% ││ 100% │      │
│  │ DEGRADED    │   └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │
│  └─────────────┘                                                                │
│                                                                                  │
├────────────── AGENT EVALUATION ──────────────────────────── [▶ EVAL ALL] ────────┤
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌────────────────┐ │
│  │ TRIAGE   [▶ RUN]│ │ PLANNER  [▶ RUN]│ │ GENERATOR[▶ RUN]│ │ HEALER [▶ RUN]│ │
│  │    85.7%  PASS  │ │   100.0%  PASS  │ │   100.0%  PASS  │ │  96.0%  PASS  │ │
│  │ 271K   $1.31   │ │  79K   $0.90   │ │  24K   $0.18   │ │ 122K   $0.66  │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ └────────────────┘ │
│                                                                                  │
├────────────── RETROSPECTIVE ─────────────────── Last run: 2h ago ── [▶ RUN] ────┤
│                                                                                  │
│  7 findings  •  3 high  •  2 medium  •  2 low  •  9 recommendations            │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  ⚡ HIGH — Add beforeEach timeout to flake patterns                       │  │
│  │                                                                            │  │
│  │  File: qa_agent/confidence.py:92                                          │  │
│  │  Change: Add re.compile(r"beforeEach.*Timeout", re.I) to                 │  │
│  │          _FLAKE_ERROR_PATTERNS list                                        │  │
│  │  Type: Surgical fix (1 line)                                              │  │
│  │  Evidence: 5 beforeEach timeouts in last 7 days, all unhealed            │  │
│  │                                                                            │  │
│  │  ┌─── Proposed Diff ──────────────────────────────────────────────────┐   │  │
│  │  │  _FLAKE_ERROR_PATTERNS = [                                        │   │  │
│  │  │      re.compile(r"scrollIntoViewIfNeeded.*Timeout", re.I),        │   │  │
│  │  │      re.compile(r"locator\.(click|fill|type).*Timeout", re.I),    │   │  │
│  │  │      re.compile(r"element is not visible", re.I),                 │   │  │
│  │  │      re.compile(r"element is not stable", re.I),                  │   │  │
│  │  │      re.compile(r"element is outside of the viewport", re.I),     │   │  │
│  │  │  +   re.compile(r"beforeEach.*Timeout", re.I),                    │   │  │
│  │  │  ]                                                                 │   │  │
│  │  └────────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                            │  │
│  │  After approval: runs triage eval → must pass ≥ 75% → else auto-revert  │  │
│  │                                                                            │  │
│  │              [✓ APPROVE]    [✕ REJECT]    [✎ MODIFY]                      │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  ⚡ HIGH — rv-parts.spec.ts may need removal (failing 3 days)             │  │
│  │                                                                            │  │
│  │  Type: Structural change — needs investigation                            │  │
│  │  Evidence: /rv-parts page returns 404 since 2026-08-29                    │  │
│  │  Impact: Persistent false failure dragging health score to 96.4%          │  │
│  │                                                                            │  │
│  │  This change is too complex for auto-apply. GENERATE SPEC will create    │  │
│  │  a build spec in /features/ with investigation steps and options.         │  │
│  │                                                                            │  │
│  │           [📝 GENERATE SPEC]    [✕ REJECT]    [✎ MODIFY]                  │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  ◉ MED — Normalize URLs in error signature matching                       │  │
│  │                                                                            │  │
│  │  File: qa_agent/memory.py:normalize_error()                               │  │
│  │  Type: Surgical fix (3 lines)                                             │  │
│  │  Evidence: C3 scoring misses because URLs differ between runs             │  │
│  │                                                                            │  │
│  │              [✓ APPROVE]    [✕ REJECT]    [✎ MODIFY]                      │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  [VIEW FULL REPORT]                                                              │
│                                                                                  │
├────────────── Approval Status Banners (appear during/after approval) ────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  ✅ Applied: "Add beforeEach timeout to flake patterns"                   │  │
│  │     confidence.py updated → triage eval: 87.1% PASS (was 85.7%)  ✓      │  │
│  │     Committed: abc1234                                          [DISMISS]│  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  ⚠ Reverted: "Normalize URLs in error matching"                          │  │
│  │     memory.py updated → triage eval: 71.2% FAIL (was 85.7%)  ✕          │  │
│  │     Auto-reverted to: def4567                                 [DISMISS]  │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  📝 Spec Generated: "rv-parts.spec.ts investigation"                      │  │
│  │     Saved to: features/retro-20260831-rv-parts-removal.md     [DISMISS]  │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  🚨 Emergency Rollback: "Modify triage prompt structure"                  │  │
│  │     Tests crashed after applying change                                    │  │
│  │     Hard reset to: 789abcd — all changes reverted              [DISMISS] │  │
│  │     This recommendation has been auto-rejected                            │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
├────────────── TEST RUNNER + RUN HISTORY (existing, unchanged) ───────────────────┤
│  ...                                                                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Approval In Progress State

While a surgical fix is being verified, the recommendation card shows live progress:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ⚡ HIGH — Add beforeEach timeout to flake patterns                       │
│                                                                            │
│  ● APPLYING...                                                            │
│                                                                            │
│  Step 1: Apply code change ✓                                             │
│  Step 2: Git commit ✓                                                    │
│  Step 3: Running triage eval...  ◌  12/35 (34%)                         │
│          ████████████░░░░░░░░░░░░░░░░░░░░░                               │
│  Step 4: Evaluate results — waiting                                      │
│                                                                            │
│                                                          [■ CANCEL]      │
└────────────────────────────────────────────────────────────────────────────┘
```

### Mobile View (iPhone)

On iPhone, recommendations stack vertically with compact action buttons:

```
┌─────────────────────────────────┐
│ RETROSPECTIVE        [▶ RUN]   │
│ 7 findings • 3 high            │
│                                 │
│ ⚡ Add beforeEach timeout      │
│   confidence.py:92 (1 line)    │
│   [✓] [✕] [✎]                 │
│                                 │
│ ⚡ rv-parts.spec.ts removal    │
│   Structural change             │
│   [📝] [✕] [✎]                │
│                                 │
│ ◉ Normalize URL matching       │
│   memory.py (3 lines)          │
│   [✓] [✕] [✎]                 │
│                                 │
│ [VIEW FULL REPORT]              │
└─────────────────────────────────┘
```

### Trigger Options

- **Manual**: Click RUN on the dashboard or `qa-agent retrospective`
- **Automatic**: After every N test runs (configurable, default: every 10 runs)
- **Scheduled**: Weekly cron job alongside the weekly self-review

---

## Files to Modify

| File | Change |
|------|--------|
| `qa_agent/retrospective.py` | New — core analysis engine |
| `qa_agent/cli.py` | Add `qa-agent retrospective` command |
| `qa_agent/dashboard/server.py` | Add retrospective API endpoints |
| `qa_agent/dashboard/static/app.js` | Retrospective card rendering |
| `qa_agent/dashboard/static/styles.css` | Retrospective card styling |
| `qa_agent/dashboard/static/index.html` | Retrospective section |

### Files to Create

| File | Purpose |
|------|---------|
| `qa_agent/retrospective.py` | Retrospective Agent — analysis + recommendation engine |
| `memory/RETROSPECTIVE.md` | Latest retrospective findings + applied changes |
| `memory/retrospectives/` | Timestamped retrospective report history (JSON) |

---

## Build Phases

### Phase RA1 — Data Collection + Rule-Based Analysis (~1 day)

| # | Task |
|---|------|
| 1 | Load and parse recent triage reports (unhealed failures, confidence breakdowns) |
| 2 | Analyze unhealed failure patterns — group by error type, spec file, frequency |
| 3 | Analyze confidence rubric gaps — C1-C5 distribution, guards fired frequency |
| 4 | Analyze healer effectiveness — success rates by strategy, fix durability |
| 5 | Analyze test stability trends — deteriorating tests, persistent failures |
| 6 | Analyze cost trends — token usage per agent over time |

### Phase RA2 — LLM-Assisted Recommendations (~0.5 day)

| # | Task |
|---|------|
| 1 | Feed findings to Claude for synthesis into actionable recommendations |
| 2 | Prioritize: HIGH (immediate action needed), MEDIUM (should address), LOW (nice to have) |
| 3 | Include specific file/line references for code changes |
| 4 | Generate human-readable retrospective report (markdown + JSON) |

### Phase RA3 — CLI + Storage (~0.5 day)

| # | Task |
|---|------|
| 1 | `qa-agent retrospective` CLI command |
| 2 | Save reports to `memory/RETROSPECTIVE.md` and `memory/retrospectives/{timestamp}.json` |
| 3 | Auto-trigger after configurable N test runs |
| 4 | Notify dashboard via WebSocket when retrospective completes |

### Phase RA4 — Dashboard Integration (~0.5 day)

| # | Task |
|---|------|
| 1 | Retrospective card on dashboard with findings summary |
| 2 | RUN button to trigger retrospective from browser |
| 3 | VIEW FULL REPORT opens detailed findings panel |
| 4 | Real-time update via `retrospective:complete` WebSocket event |

### Phase RA5 — Approval Mechanism + Auto-Apply (~1 day)

| # | Task |
|---|------|
| 1 | Server: `POST /api/retro/{id}/approve` — apply surgical fix, commit, re-run eval |
| 2 | Server: `POST /api/retro/{id}/generate-spec` — LLM generates build spec, saves to `/features/` |
| 3 | Server: `POST /api/retro/{id}/reject` — record rejection + suppression |
| 4 | Server: `POST /api/retro/{id}/modify` — accept modified diff/outline, then apply or generate |
| 5 | Server: Auto-revert surgical fix if eval score drops after applying |
| 6 | Frontend: APPROVE / GENERATE SPEC / REJECT / MODIFY buttons per recommendation |
| 7 | Frontend: Editable text area for MODIFY action |
| 8 | Frontend: Status feedback — "Applying...", "Eval passed", "Reverted — eval failed" |
| 9 | WebSocket: `retro:applied`, `retro:reverted`, `retro:spec_generated`, `retro:rejected` events |
| 10 | Memory: Track all decisions in `memory/RETROSPECTIVE.md` for future suppression + learning |

### Phase RA6 — Build Spec Generation (~0.5 day)

| # | Task |
|---|------|
| 1 | LLM prompt for generating build specs from retrospective findings |
| 2 | Template: Context, Problem, Solution, Files to Modify, Build Phases, Success Criteria |
| 3 | Save to `/features/retro-{timestamp}-{slug}.md` |
| 4 | Include evidence from the retrospective analysis (data, charts, examples) |
| 5 | Git commit + push the generated spec |

---

## Claude Dreaming Integration (Phase RA7)

### What is Dreaming?

[Claude Dreaming](https://platform.claude.com/docs/en/managed-agents/dreams) is an async process in Claude's Managed Agents API that consolidates agent memory by reading past session transcripts, merging duplicates, pruning stale entries, and surfacing patterns that individual sessions can't see. It's the LLM-native equivalent of what our Retrospective Agent does with rule-based analysis.

### Why Integrate?

Our Retrospective Agent has two layers:

1. **Rule-based analysis** (Phase RA1) — structured data crunching: count unhealed failures, compute C1-C5 distributions, measure strategy success rates
2. **LLM synthesis** (Phase RA2) — turn findings into actionable recommendations with context

Dreaming can **replace Phase RA2** with a more powerful, context-rich synthesis — and add a third capability we don't have: **cross-session memory optimization**.

### How It Maps

```
┌────────────────────────────────────────────────────────────────┐
│                    RETROSPECTIVE AGENT                          │
│                                                                │
│  Phase RA1: Rule-Based Analysis          ← KEEP (our code)    │
│  ┌──────────────────────────────────┐                          │
│  │ Count unhealed patterns          │                          │
│  │ Compute C1-C5 distributions      │                          │
│  │ Measure strategy success rates   │                          │
│  │ Detect stability trends          │                          │
│  │ Analyze cost trajectories        │                          │
│  └──────────────────┬───────────────┘                          │
│                     │ findings                                  │
│                     ▼                                           │
│  Phase RA2: LLM Synthesis            ← REPLACE with Dreaming  │
│  ┌──────────────────────────────────┐                          │
│  │ Synthesize findings into recs    │  →  Dream processes      │
│  │ Prioritize by impact             │      session transcripts │
│  │ Generate file/line references    │      + memory store      │
│  │ Produce human-readable report    │      and produces        │
│  └──────────────────────────────────┘      optimized output    │
│                                                                │
│  Phase RA7: Dreaming Memory Optimization  ← NEW               │
│  ┌──────────────────────────────────┐                          │
│  │ Consolidate FAILURES.md          │                          │
│  │ Prune stale locator history      │                          │
│  │ Merge duplicate timing fixes     │                          │
│  │ Surface cross-run patterns       │                          │
│  │ Optimize LESSONS.md              │                          │
│  └──────────────────────────────────┘                          │
└────────────────────────────────────────────────────────────────┘
```

### Implementation

#### Session Transcript Format

Dreaming expects session transcripts. We convert our structured data into conversation-like transcripts:

```python
def build_dream_transcript(triage_report: dict, health_report: dict) -> str:
    """Convert a triage + health report pair into a Dreaming session transcript."""
    lines = []
    lines.append(f"Test run {health_report['run_id']} completed.")
    lines.append(f"Results: {health_report['total_passed']}/{health_report['total_tests']} passed.")
    
    for detail in triage_report.get("details", []):
        lines.append(f"Failure: {detail['spec_file']} — {detail['test_title']}")
        lines.append(f"Classification: {detail['failure_class']} (confidence: {detail['confidence']})")
        if detail.get("reasoning"):
            lines.append(f"Reasoning: {detail['reasoning']}")
        if detail.get("not_healed_reason"):
            lines.append(f"Not healed: {detail['not_healed_reason']}")
        if detail.get("healed"):
            lines.append(f"Healed successfully.")
    
    return "\n".join(lines)
```

#### Memory Store Mapping

Our `memory/` folder maps to a Dreaming memory store:

| Our File | Dream Memory Key | Content |
|----------|-----------------|---------|
| `FAILURES.md` | `failure_patterns` | Known error patterns + resolutions |
| `TIMING_FIXES.md` | `timing_fixes` | Known timing fix cache |
| `LESSONS.md` | `lessons` | Pattern scoreboard + route insights |
| `TEST_STABILITY.md` | `test_stability` | Per-test flakiness data |
| `HEALER_STATS.md` | `healer_stats` | Cache hit rates |
| `locators/*.md` | `locator_history` | Per-route locator changes |

#### Dream Execution Flow

```python
async def run_dream_retrospective(lookback_days: int = 7):
    """Run a Dreaming-enhanced retrospective."""
    
    # 1. Rule-based analysis (Phase RA1 — unchanged)
    findings = run_rule_based_analysis(lookback_days)
    
    # 2. Build session transcripts from recent runs
    transcripts = []
    for triage, health in load_recent_report_pairs(lookback_days):
        transcripts.append(build_dream_transcript(triage, health))
    
    # 3. Build current memory store snapshot
    memory_store = snapshot_memory_store()
    
    # 4. Create Dream with custom instructions
    dream = await client.dreams.create(
        model="claude-opus-4-6",
        memory_store=memory_store,
        session_transcripts=transcripts,  # up to 100
        instructions=f"""
        You are analyzing a QA automation system's recent test runs.
        
        Rule-based analysis found these findings:
        {json.dumps(findings, indent=2)}
        
        Analyze the session transcripts and memory store to:
        1. Validate or challenge each finding with evidence from the transcripts
        2. Surface patterns the rule-based analysis missed
        3. Recommend specific code changes (file, line, what to change)
        4. Identify memory entries that are stale or duplicated
        5. Prioritize: HIGH (immediate), MEDIUM (should address), LOW (nice to have)
        """
    )
    
    # 5. Poll until complete
    while dream.status != "completed":
        await asyncio.sleep(30)
        dream = await client.dreams.retrieve(dream.id)
    
    # 6. Extract recommendations from Dream output
    recommendations = parse_dream_output(dream.output)
    
    # 7. Apply optimized memory store
    if dream.optimized_memory:
        apply_memory_updates(dream.optimized_memory)
    
    # 8. Produce retrospective report
    report = build_retrospective_report(findings, recommendations)
    save_retrospective(report)
    
    return report
```

#### What Dreaming Adds That We Can't Do Manually

| Capability | Rule-Based (RA1-RA2) | With Dreaming (RA7) |
|------------|---------------------|---------------------|
| Count unhealed patterns | Yes | Yes |
| Detect C1-C5 gaps | Yes | Yes + explains why |
| Cross-session patterns | Limited (last N runs) | Full (up to 100 sessions) |
| Memory deduplication | No | Yes (automatic) |
| Stale entry pruning | No | Yes (automatic) |
| Novel insight discovery | No (only pre-coded rules) | Yes (LLM finds unexpected patterns) |
| Recommendation quality | Template-based | Context-rich with evidence |
| Memory optimization | Manual (`qa-agent memory prune`) | Automatic per Dream cycle |

### Phase RA7 Build Steps

| # | Task |
|---|------|
| 1 | Request access to Claude Managed Agents research preview |
| 2 | Build `dream_adapter.py` — converts triage/health reports to session transcripts |
| 3 | Build `memory_snapshot.py` — serializes `memory/` folder into Dream memory store format |
| 4 | Integrate Dream API: create dream, poll status, retrieve output |
| 5 | Parse Dream output into recommendation format compatible with Phase RA5 approval UI |
| 6 | Apply optimized memory store back to `memory/` files (with git diff review) |
| 7 | Custom `instructions` prompt that feeds rule-based findings (Phase RA1) into Dream |
| 8 | Dashboard: show "Dream" indicator when Dreaming is in progress (async, may take minutes-hours) |
| 9 | Fallback: if Dreaming API unavailable, fall back to Phase RA2 (local LLM synthesis) |
| 10 | Track Dream costs separately in audit trail |

### Hybrid Architecture (Final State)

```
                         ┌─────────────────────────┐
                         │    RETROSPECTIVE AGENT   │
                         └────────┬────────────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼              ▼
           ┌──────────────┐ ┌──────────┐ ┌─────────────────┐
           │ Phase RA1    │ │Phase RA7 │ │ Phase RA5       │
           │ Rule-Based   │ │ Dreaming │ │ Dashboard       │
           │ Analysis     │ │ API      │ │ Approval UI     │
           │              │ │          │ │                 │
           │ • Count      │ │ • Cross- │ │ • APPROVE       │
           │   patterns   │ │   session│ │ • REJECT        │
           │ • C1-C5 gaps │ │   insight│ │ • MODIFY        │
           │ • Strategy   │ │ • Memory │ │ • GENERATE SPEC │
           │   rates      │ │   optim  │ │ • Rollback      │
           │ • Cost trend │ │ • Novel  │ │   safety        │
           │              │ │   pattern│ │                 │
           └──────┬───────┘ └────┬─────┘ └────────┬────────┘
                  │              │                 │
                  └──────────────┘                 │
                         │ combined findings       │
                         ▼                         │
                  ┌──────────────┐                 │
                  │ Recommendations│◄──────────────┘
                  │ with evidence  │  human approval
                  └──────┬─────────┘
                         │ applied
                         ▼
              ┌─────────────────────┐
              │ Improved Agents     │
              │ • Triage rubric     │
              │ • Healer strategies │
              │ • Test configs      │
              │ • Optimized memory  │
              └─────────────────────┘
```

### Prerequisites

- Access to Claude Managed Agents research preview — **GRANTED** (active on account)
- API key with Dreams capability — existing `ANTHROPIC_API_KEY` works
- Memory store created: `memstore_019YoqVnYqpNTHYHi8mWSXHj` (name: `qa-automation-memory`, status: Active)
- Budget for Dream processing (billed at standard API token rates)
- Minimum 10 session transcripts for meaningful patterns (recommend 50-100)

### Graceful Degradation

If Dreaming API is unavailable (access not granted, API down, budget exhausted):
- Phase RA1 (rule-based) runs normally
- Phase RA2 (local LLM synthesis) activates as fallback
- Memory optimization skipped (manual `qa-agent memory prune` still available)
- Dashboard shows "Dreaming unavailable — using local analysis" indicator

---

## Relationship to Other Agents

```
                    ┌──────────────────┐
                    │  RETROSPECTIVE   │
                    │  AGENT + DREAM   │
                    └──────┬───────────┘
                           │ reads + dreams on
          ┌────────────────┼────────────────────┐
          ▼                ▼                    ▼
   ┌─────────────┐  ┌───────────┐  ┌──────────────────┐
   │  Triage     │  │  Health   │  │  Eval Reports    │
   │  Reports    │  │  Reports  │  │  + Audit Trail   │
   └──────┬──────┘  └───────────┘  └──────────────────┘
          │
          │ recommends improvements to
          ▼
   ┌─────────────┐  ┌───────────┐  ┌──────────────────┐
   │  Triage     │  │  Healer   │  │  Test Config     │
   │  Rubric     │  │  Prompts  │  │  + Stability     │
   └─────────────┘  └───────────┘  └──────────────────┘
          ▲
          │ Dreaming also optimizes
          │
   ┌──────────────┐
   │  Memory      │
   │  Store       │
   │  (14 files)  │
   └──────────────┘
```

The Retrospective Agent is the **meta-agent** — it doesn't fix tests or classify failures. It improves the agents that do. With Dreaming, it also **optimizes the memory** those agents rely on.

---

## Success Criteria

1. Retrospective analyzes triage reports and identifies recurring unhealed patterns
2. Produces actionable recommendations with specific file/line references
3. Detects confidence rubric gaps (e.g., "C2 always 0.0") with root cause
4. Identifies ineffective Healer strategies with success rate data
5. Flags deteriorating tests before they become persistent failures
6. Surfaces cost optimization opportunities with estimated savings
7. Report is human-readable (markdown) and machine-parseable (JSON)
8. Dashboard shows findings summary with priority levels
9. Can be triggered from CLI, dashboard, or automatically after N runs
10. Recommendations feed back into agent memory when applied
11. Dreaming integration consolidates memory across 50-100 sessions when available
12. Graceful fallback to local LLM synthesis when Dreaming API is unavailable
13. Memory optimization (dedup, prune, merge) runs automatically per Dream cycle
