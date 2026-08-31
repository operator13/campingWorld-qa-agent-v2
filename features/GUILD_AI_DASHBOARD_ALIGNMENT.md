# Feature: Guild.AI Dashboard Alignment

> Align the QA Command Center dashboard with Guild.AI Insights Dashboard best practices — actionable observability, cost drill-downs, cache efficiency, and period-over-period trend analysis.

**Status:** PLANNED
**Priority:** Medium
**Depends on:** QA Command Center Dashboard, Agent Evaluation System, Audit Trail

---

## Full Dashboard Visual — With Guild.AI Enhancements

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  QA COMMAND CENTER                                              ● LIVE  UTC     │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐  │
│  │ SYSTEM      │   │ DOMAIN STATUS (4-column grid)     │   │                  │  │
│  │ HEALTH      │   │ ┌──────┐┌──────┐┌──────┐┌──────┐ │   │                  │  │
│  │  ┌───────┐  │   │ │★Cart ││★Chkt ││★Sign ││Good  │ │   │                  │  │
│  │  │ 98.7% │  │   │ │100%  ││100%  ││100%  ││Sam   │ │   │                  │  │
│  │  │HEALTHY│  │   │ │8/8   ││4/4   ││10/10 ││100%  │ │   │                  │  │
│  │  └───────┘  │   │ └──────┘└──────┘└──────┘└──────┘ │   │                  │  │
│  │ Tests: 127  │   │ ┌──────┐┌──────┐┌──────┐┌──────┐ │   │                  │  │
│  │ Pass:  126  │   │ │Footer││Home  ││Nav   ││Prodct│ │   │                  │  │
│  │ Fail:    1  │   │ │100%  ││100%  ││100%  ││100%  │ │   │                  │  │
│  └─────────────┘   │ └──────┘└──────┘└──────┘└──────┘ │   │                  │  │
│                     │ ┌──────┐┌──────┐┌──────┐┌──────┐ │   │                  │  │
│                     │ │Reg   ││RVPrt ││RVSale││RVDtl │ │   │                  │  │
│                     │ │100%  ││100%  ││100%  ││100%  │ │   │                  │  │
│                     │ └──────┘└──────┘└──────┘└──────┘ │   │                  │  │
│                     │ ┌──────┐┌──────┐                 │   │                  │  │
│                     │ │Search││Store ││                 │   │                  │  │
│                     │ │100%  ││100%  ││                 │   │                  │  │
│                     │ └──────┘└──────┘                 │   │                  │  │
│                     └──────────────────────────────────┘   │                  │  │
│                                                                                  │
├────────────── NEW: KPI STRIP ────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ TOTAL SPEND  │  │ TOTAL TOKENS │  │ CACHE HIT    │  │ AVG COST/EVAL       │  │
│  │   $3.14      │  │   495.6K     │  │ RATE  67.3%  │  │   $0.19             │  │
│  │  +$0.65 ▲    │  │  +121.5K ▲   │  │ ████████░░░  │  │  -$0.02 ▼          │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                                  │
├────────────── AGENT EVALUATION (with trend arrows + hover tooltips) ─────────────┤
│                                                                                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌────────────────┐  │
│  │ TRIAGE          │ │ PLANNER         │ │ GENERATOR       │ │ HEALER         │  │
│  │                 │ │                 │ │                 │ │                │  │
│  │    85.7%        │ │   100.0%        │ │   100.0%        │ │    94.0%       │  │
│  │    PASS         │ │    PASS         │ │    PASS         │ │    PASS        │  │
│  │   ▲ +2.1%      │ │   ─ 0.0%       │ │   ─ 0.0%       │ │   ▼ -2.0%     │  │
│  │                 │ │                 │ │                 │ │                │  │
│  │ TOKENS 271.1K ▲ │ │ TOKENS 79.0K ▲ │ │ TOKENS 23.9K ▲ │ │ TOKENS 121K ▲ │  │
│  │ COST   $1.31  ▲ │ │ COST  $0.90  ▲ │ │ COST  $0.18  ▲ │ │ COST  $0.66 ▲ │  │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ └────────────────┘  │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │  On hover, tooltip appears above card:                                     │  │
│  │  ┌──────────────────────────────────────────┐                              │  │
│  │  │ TRIAGE  Failure Classifier               │                              │  │
│  │  │                                          │                              │  │
│  │  │ Analyzes test failures and classifies    │                              │  │
│  │  │ them as locator drift, app defect, or    │                              │  │
│  │  │ timing flake using a 5-criteria rubric.  │                              │  │
│  │  │                                          │                              │  │
│  │  │ Cost Breakdown (last run):               │  ← NEW: cost drill-down     │  │
│  │  │   Input:  57,442 tokens  ($0.17)         │                              │  │
│  │  │   Output: 10,065 tokens  ($0.15)         │                              │  │
│  │  │   Total: $0.32                           │                              │  │
│  │  │                                          │                              │  │
│  │  │ Historical: 4 runs, avg $0.33/run        │  ← NEW: historical stats    │  │
│  │  │                                          │                              │  │
│  │  │ Model: Claude Opus                       │                              │  │
│  │  │ Eval: 35 golden scenarios                │                              │  │
│  │  │                                          │                              │  │
│  │  │ ┌──────────────┐ ┌──────────────────┐    │                              │  │
│  │  │ │Drift detect  │ │Defect identify   │    │                              │  │
│  │  │ └──────────────┘ └──────────────────┘    │                              │  │
│  │  │ ┌──────────────┐ ┌──────────────────┐    │                              │  │
│  │  │ │Flake recog   │ │History matching  │    │                              │  │
│  │  │ └──────────────┘ └──────────────────┘    │                              │  │
│  │  └──────────────────────────────────────────┘                              │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
├────────────── NEW: CACHE EFFICIENCY + OPTIMIZATION SIGNALS ──────────────────────┤
│                                                                                  │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │ CACHE EFFICIENCY             │  │ OPTIMIZATION SIGNALS                     │  │
│  │                              │  │                                          │  │
│  │ Hit Rate: 67.3%              │  │ ⚡ Healer cache rate dropped below 50%  │  │
│  │ ████████████████░░░░░░░░     │  │ ⚡ Triage cost +40% vs last period      │  │
│  │                              │  │ ✓ Generator maintaining stable usage    │  │
│  │ Cache Hits:  42              │  │ ✓ All agents passing eval thresholds    │  │
│  │ LLM Calls:   21             │  │                                          │  │
│  │ Est. Saved:  $3.28           │  │                                          │  │
│  └──────────────────────────────┘  └──────────────────────────────────────────┘  │
│                                                                                  │
├────────────── NEW: DOMAIN RESOURCE HEATMAP ──────────────────────────────────────┤
│                                                                                  │
│  DOMAIN TEST DURATION                                                            │
│  ★ Cart       ████████████████████████████  85.9s  (critical, 2.0x weight)      │
│  ★ Checkout   ████████████████             44.6s  (critical, 2.0x weight)      │
│  ★ Sign In    █████████████████████████    71.8s  (critical, 1.5x weight)      │
│    Homepage   █████████████████████████    71.8s                                │
│    Nav        ███████████████████████████  82.4s                                │
│    Search     ██████████████████           52.3s                                │
│    Product    ████████████████████         58.7s                                │
│    Register   ██████████████               37.7s                                │
│    Store Loc  █████████████████████████    71.8s                                │
│    RVs Sale   █████████████████████████    71.8s                                │
│    RV Detail  █████████████████████████    71.8s                                │
│    Good Sam   ██████████████               37.7s                                │
│    RV Parts   ███████████                  29.3s                                │
│    Footer     ███████████████████████████  85.9s                                │
│                                                                                  │
├────────────── TEST RUNNER + RUN HISTORY (existing, unchanged) ───────────────────┤
│                                                                                  │
│  ┌────────────────────────────┐  ┌──────────────────────────────────────────┐    │
│  │ TEST RUNNER                │  │ RUN HISTORY                              │    │
│  │                     ● IDLE │  │                                          │    │
│  │ Workers [1][2][●3][4]      │  │ TIMESTAMP    TESTS PASS FAIL HLTH  STAT │    │
│  │ Retries [●0][1]            │  │ 08-30 22:52   127  126    1  99.3  HLTH │    │
│  │ Self-Heal [OFF][●ON]       │  │ 08-30 22:52     1    0    1   --  HEAL │    │
│  │                            │  │ 08-30 20:55   127  127    0 100.0  HLTH │    │
│  │ [▶ RUN SELECTED] [▶ ALL]  │  │ 08-30 20:24   127  125    2  98.7  HLTH │    │
│  │                            │  │                                          │    │
│  │ ○ ★ Cart      8 tests     │  │  ← Click any row to open HTML report    │    │
│  │ ○ ★ Checkout  4 tests     │  │                                          │    │
│  │ ○ ★ Sign In  10 tests     │  │                                          │    │
│  │ ○   Search    9 tests     │  │                                          │    │
│  │ ○   Product   9 tests     │  │                                          │    │
│  │ ○   Homepage 13 tests     │  │                                          │    │
│  │ ○   Nav      14 tests     │  │                                          │    │
│  │ ○   Register  6 tests     │  │                                          │    │
│  │ ○   Store Loc 10 tests    │  │                                          │    │
│  │ ○   RVs Sale 10 tests     │  │                                          │    │
│  │ ○   RV Detail 10 tests    │  │                                          │    │
│  │ ○   Good Sam  6 tests     │  │                                          │    │
│  │ ○   RV Parts  5 tests     │  │                                          │    │
│  │ ○   Footer   13 tests     │  │                                          │    │
│  │                            │  │                                          │    │
│  │ CONSOLE OUTPUT ▾           │  │                                          │    │
│  │ ┌────────────────────────┐ │  │                                          │    │
│  │ │ ✓ cart.spec.ts:12...  │ │  │                                          │    │
│  │ │ ✓ cart.spec.ts:18...  │ │  │                                          │    │
│  │ └────────────────────────┘ │  │                                          │    │
│  └────────────────────────────┘  └──────────────────────────────────────────┘    │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘

Legend:
  ── Existing sections (already built)
  ── NEW sections (Guild.AI alignment additions)

  ▲ Green trend arrow (improved vs previous)
  ▼ Red trend arrow (regressed vs previous)
  ─ Gray (unchanged)
  ⚡ Amber optimization warning
  ✓ Green positive signal
  ★ Critical domain marker
```

---

## The Problem

Our dashboard covers core observability (health scores, agent evals, test runner, real-time WebSocket updates), but Guild.AI's philosophy identifies gaps in how we surface cost intelligence, optimization signals, and trend analysis:

1. **No cache hit rates visible** — Healer tracks cache hits in `HEALER_STATS.md` but this isn't surfaced on the dashboard. Users can't see how much LLM cost the memory cache is saving.
2. **No period-over-period trends** — no way to see "this week vs last week" for tokens, cost, health, or eval scores. Guild emphasizes that "optimization compounds when you can measure it."
3. **No per-scenario cost drill-down** — can't identify which eval scenarios or test domains consume the most tokens. Guild recommends segmenting metrics to enable targeted intervention.
4. **No cost optimization signals** — no alerts or indicators when cost is trending up, when cache efficiency drops, or when a specific agent is consuming disproportionate resources.
5. **No auth/access control** — dashboard is open to anyone on the network. Guild recommends role-based access for financial data.

---

## Guild.AI Principles Applied

| Guild.AI Principle | Current State | Target State |
|---|---|---|
| **"Visibility precedes optimization"** | Per-agent tokens/cost shown | + Cache savings, cost breakdown, optimization signals |
| **Actionable Observability** | Per-agent scores | + Per-scenario drill-down, cost drivers identified |
| **Real-Time Feedback** | Event-driven WebSocket push | Already aligned |
| **Signal Over Precision** | Estimated at list prices | + Clearly labeled "estimated at list price" |
| **KPI Strip** | Tokens + cost per agent | + Cache hit rate, output ratio, period-over-period |
| **Drill-down Analysis** | Agent-level only | + Scenario-level, domain-level cost breakdown |
| **Optimization Compounds** | Cumulative cost tracking | + Trend arrows, cost velocity, efficiency metrics |

---

## What We're Building

### 1. KPI Summary Strip

A horizontal strip at the top of the Agent Evaluation section showing system-wide metrics:

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOTAL SPEND    TOTAL TOKENS    CACHE HIT RATE    AVG COST/EVAL     │
│  $3.14          495.6K          67.3%             $0.19             │
│  +$0.65 ▲       +121.5K ▲      +2.1% ▲          -$0.02 ▼          │
└──────────────────────────────────────────────────────────────────────┘
```

**Metrics:**
- **Total Spend** — cumulative cost across all agents (sum of all eval report `token_usage.cost_usd`)
- **Total Tokens** — cumulative tokens consumed
- **Cache Hit Rate** — percentage of healer fixes resolved from memory vs LLM calls (from `HEALER_STATS.md`)
- **Avg Cost/Eval** — average cost per eval run (total cost / number of runs with token data)
- **Period delta** — change vs previous period (arrow up/down + delta value)

### 2. Cache Efficiency Card

Surface the Healer's cache performance on the dashboard:

```
┌─────────────────────────┐
│  CACHE EFFICIENCY       │
│                         │
│  Hit Rate: 67.3%        │
│  ████████████░░░░░      │
│                         │
│  Cache Hits: 42         │
│  LLM Calls: 21         │
│  Est. Saved: $3.28      │
└─────────────────────────┘
```

**Data source:** `memory/HEALER_STATS.md` (already tracks `cache_hits` and `llm_calls`)

**Estimated savings calculation:**
```
saved = cache_hits * avg_llm_cost_per_fix
```

### 3. Period-over-Period Trend Arrows

Add trend indicators to each agent eval card showing direction vs previous eval run:

```
┌─────────────────────┐
│  TRIAGE              │
│  85.7%  PASS         │
│  ▲ +2.1%            │  ← Score trend vs previous run
│                      │
│  TOKENS  271.1K ▲    │  ← Token trend
│  COST    $1.31  ▲    │  ← Cost trend
└─────────────────────┘
```

**Implementation:**
- Compare latest eval report score vs second-to-latest
- Arrow: `▲` green (improved), `▼` red (regressed), `─` gray (unchanged)
- Delta shown as absolute difference

### 4. Per-Agent Cost Breakdown Tooltip

Expand the agent hover tooltip to include cost breakdown:

```
┌──────────────────────────────────────┐
│  TRIAGE  Failure Classifier          │
│                                      │
│  Cost Breakdown (last run):          │
│    Input tokens:  57,442  ($0.17)    │
│    Output tokens: 10,065  ($0.15)    │
│    Total: $0.32                      │
│                                      │
│  Historical:                         │
│    4 eval runs                       │
│    Avg cost/run: $0.33               │
│    Cost trend: stable                │
└──────────────────────────────────────┘
```

### 5. Domain Cost Heatmap

Show which test domains consume the most resources during test runs:

```
DOMAIN RESOURCE USAGE
  Cart ████████████████ 18.2s  (critical)
  Checkout ███████████  12.1s  (critical)
  Homepage ██████████   10.3s
  Nav ████████████████   15.8s
  ...
```

**Data source:** Health reports already track `duration_ms` per domain. Surface this as a visual heatmap showing which domains are most expensive to test.

### 6. Cost Optimization Signals

Add visual indicators when optimization opportunities are detected:

```
┌──────────────────────────────────────────────┐
│  OPTIMIZATION SIGNALS                         │
│                                               │
│  ⚡ Healer cache hit rate dropped below 50%   │
│  ⚡ Triage cost increased 40% vs last period  │
│  ✓ Generator maintaining stable token usage   │
└──────────────────────────────────────────────┘
```

**Rules engine:**
- Cache hit rate < 50% → alert (memory may need refreshing)
- Cost increased > 25% vs previous run → alert
- Token count stable within 5% → positive signal
- Agent accuracy dropped > 5% → alert (model regression)

---

## Architecture

### API Changes

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/eval/kpi` | System-wide KPI strip data (total spend, tokens, cache rate, avg cost) |
| `GET` | `/api/cache/stats` | Cache hit rate, hits, misses, estimated savings |
| `GET` | `/api/eval/trends` | Per-agent score/cost trends with period-over-period deltas |
| `GET` | `/api/domains/resources` | Per-domain duration and resource usage |

### Data Sources

| Metric | Source |
|--------|--------|
| Total spend / tokens | Sum of `token_usage` across all eval reports |
| Cache hit rate | `memory/HEALER_STATS.md` (cache_hits / (cache_hits + llm_calls)) |
| Period trends | Compare latest vs previous eval report per agent |
| Domain resources | Health reports `duration_ms` per domain |
| Optimization signals | Computed from trends + thresholds |

### Files to Modify

| File | Change |
|------|--------|
| `qa_agent/dashboard/server.py` | Add 4 new API endpoints |
| `qa_agent/dashboard/static/app.js` | KPI strip, cache card, trend arrows, cost tooltip, signals |
| `qa_agent/dashboard/static/styles.css` | KPI strip styling, trend arrows, heatmap, signal alerts |
| `qa_agent/dashboard/static/index.html` | KPI strip section, cache card, signals section |

---

## Build Phases

### Phase GA1 — KPI Strip + Cache Stats (~0.5 day)

| # | Task |
|---|------|
| 1 | `GET /api/eval/kpi` — aggregate total spend, tokens, avg cost across all eval reports |
| 2 | `GET /api/cache/stats` — parse `HEALER_STATS.md` for cache hits/misses, compute rate |
| 3 | KPI strip HTML/CSS above Agent Evaluation section |
| 4 | Cache efficiency display (hit rate bar, estimated savings) |
| 5 | WebSocket event `kpi:updated` triggered after eval completes |

### Phase GA2 — Period-over-Period Trends (~0.5 day)

| # | Task |
|---|------|
| 1 | `GET /api/eval/trends` — compare latest vs previous eval per agent |
| 2 | Trend arrows on agent cards (score, tokens, cost) |
| 3 | Color coding: green (improved), red (regressed), gray (stable) |
| 4 | Delta values shown on hover or inline |

### Phase GA3 — Cost Drill-Down (~0.5 day)

| # | Task |
|---|------|
| 1 | Expand agent tooltip with cost breakdown (input/output tokens, per-token cost) |
| 2 | Historical stats (run count, avg cost/run, cost trend) |
| 3 | Domain resource heatmap from health report durations |
| 4 | `GET /api/domains/resources` endpoint |

### Phase GA4 — Optimization Signals (~0.5 day)

| # | Task |
|---|------|
| 1 | Rules engine: cache drop, cost spike, accuracy regression, stable usage |
| 2 | Signals card or inline alerts on dashboard |
| 3 | Cyberpunk styling: neon warnings, pulse animations for active signals |
| 4 | Signals refresh on eval:updated WebSocket event |

---

## Cyberpunk Styling

- **KPI strip:** Dark glass panel with neon cyan numbers, amber trend arrows
- **Cache efficiency:** Horizontal progress bar with cyan fill, glow effect
- **Trend arrows:** `▲` green glow, `▼` red glow, `─` gray
- **Optimization signals:** Amber/red pulsing border for warnings, green for positive
- **Domain heatmap:** Gradient bars from dark to neon cyan based on duration
- **Cost tooltip:** Same glassmorphism popup as agent info tooltip

---

## Success Criteria

1. KPI strip shows total spend, tokens, cache hit rate, avg cost — updates in real-time via WebSocket
2. Cache efficiency visible: hit rate percentage, estimated savings in USD
3. Each agent card shows trend arrow (▲/▼/─) for score and cost vs previous run
4. Agent tooltip includes input/output token breakdown with per-category cost
5. Domain resource heatmap shows relative test execution cost
6. Optimization signals fire when: cache rate < 50%, cost spike > 25%, accuracy drops > 5%
7. All new data updates via event-driven WebSocket push (no polling)
8. Mobile responsive — KPI strip stacks vertically on iPhone

---

## Guild.AI Alignment Checklist

- [ ] "You cannot cut what you cannot see" — cache savings and cost drivers visible
- [ ] Metrics segmented by agent, scenario, domain — not just org-wide totals
- [ ] Real-time refresh as sessions complete — WebSocket push
- [ ] Estimated costs clearly labeled as list-price estimates
- [ ] Period-over-period changes shown for trend detection
- [ ] Drill-down from agent → scenario → token breakdown
- [ ] Optimization feedback loop: signal → investigate → act → measure
