# Comparison: Our Eval System vs Braintrust

> Side-by-side analysis of our QA automation eval + observability capabilities against [Braintrust](https://www.braintrust.dev/) — an enterprise AI evaluation and observability platform.

**Date:** 2026-09-04

---

## Full Comparison Matrix

| Capability | Our System | Braintrust | Gap |
|---|---|---|---|
| **Golden Datasets** | 68 scenarios in JSON files (35 triage, 10 generator, 15 healer, 8 planner) | Versioned datasets with UI editor, convert production traces to datasets with one click | We edit JSON files manually. No versioning, no one-click conversion from real failures |
| **Scoring** | Custom Python scorers per agent (accuracy, confidence, locator quality, timing fix) | LLM-as-judge, custom code scorers, human scoring, automated scoring | We don't have LLM-as-judge (using Claude to evaluate Claude's output quality) |
| **Experiment Comparison** | Regression detection (2% threshold), before/after score delta | Side-by-side model + prompt comparison, visual diffs, heat maps | Spec'd in EVAL_OBSERVABILITY but not built yet |
| **Tracing** | Partial — audit trail tracks tokens/cost per run, no per-scenario prompt/response | Full real-time traces: prompts, responses, tool calls, latency, cost per call | Spec'd in EVAL_OBSERVABILITY but not built yet |
| **Per-Scenario Visibility** | Scores per scenario in eval reports, but no prompt/response drill-down | Expand any row to see full input/output/trace, natural language search across traces | Spec'd (LangSmith-style table) but not built yet |
| **Dashboard** | Custom cyberpunk dashboard with health gauge, eval cards, test runner, real-time WebSocket | Web UI with experiment tables, heat maps, trace viewer, annotation queues | We have a more complete operational dashboard (test runner, health scoring). They have better eval visualization |
| **Production Logging** | Health reports + triage reports from test runs | Full-text search across millions of production logs, real-time monitoring | We only monitor test runs, not production AI behavior |
| **Human Review** | Spec'd (HUMAN_REVIEW_NOTIFICATIONS.md) — not built | Built-in annotation queues, custom annotation interfaces, inline annotation | Theirs is built, ours is spec'd |
| **CI/CD Integration** | Auto-commit eval reports to GitHub, eval gate on surgical fixes (Retrospective Agent spec) | Native CI/CD integration, eval gates in deployment pipeline | Similar concept, different execution |
| **Prompt Playground** | No — prompts are in markdown files (TRIAGE.md, HEALER.md) | Interactive prompt playground: edit, test, compare prompts in real-time | No equivalent — we edit markdown and re-run evals |
| **Dataset from Failures** | Manual — copy error from triage report, create golden scenario JSON | One-click: production failure → eval dataset entry | Major gap — converting real failures to golden scenarios is manual labor |
| **Discovery / Root Cause** | Retrospective Agent (spec'd) — rule-based analysis + Dreaming | AI-powered: natural language trace search, automatic pattern surfacing, failure diagnosis | Theirs is built + AI-powered, ours is spec'd + rule-based |
| **Multi-Model Comparison** | All agents use Sonnet, configurable via env vars | Side-by-side model comparison in the same experiment | We can change models but can't compare results visually |
| **Cost Tracking** | Cumulative odometer per agent on dashboard | Per-call cost in traces, aggregate cost analytics | Ours is run-level, theirs is call-level |
| **Token Caching Awareness** | Not tracked (pre-mortem #10 identified this gap) | Likely tracks cache tokens in cost calculation | Gap identified, mitigation in EVAL_OBSERVABILITY spec |
| **Security** | No auth on dashboard, localhost only | SOC 2, GDPR, HIPAA, SSO/SAML, granular permissions | Not comparable — we're a local dev tool, they're enterprise SaaS |
| **SDK / Framework** | Python only, tightly coupled to our codebase | Python, TypeScript, Go, Ruby, C#, framework-agnostic | Not applicable — we're one project, not a platform |
| **AI Assistant** | Retrospective Agent (spec'd) — recommends improvements | Loop Agent — auto-generates improved prompts, scorers, datasets | Same concept, theirs is built |

---

## Where We're Ahead

| Strength | Details |
|----------|---------|
| **Operational Dashboard** | Our test runner, health scoring, domain cards, cross-device WebSocket sync, eval runner with progress bars — more complete than a pure eval platform |
| **Self-Healing Pipeline** | Triage → Healer → re-run is unique to us. Braintrust evaluates but doesn't fix. We detect, classify, heal, and verify automatically |
| **Confidence Rubric** | 5-criteria C1-C5 scoring with anti-inflation guards (G1-G4) is purpose-built for failure classification. More rigorous than generic LLM scoring |
| **Flaky Test Detection** | `test_flake` classification with historical stability analysis — specific to our domain, not a generic eval feature |
| **Event-Driven Architecture** | Zero-polling WebSocket push for all dashboard updates — eval scores, health data, test results. Real-time across desktop and mobile |
| **Memory System** | 14 markdown memory files that agents read and write — cross-run learning. Braintrust doesn't have persistent agent memory |
| **Cumulative Cost Tracking** | Odometer-style token/cost that never decreases — gives lifetime spend visibility per agent |

---

## Where Braintrust Is Ahead

| Strength | Details | Our Plan to Close Gap |
|----------|---------|----------------------|
| **Full Per-Call Tracing** | Every LLM call visible: prompt, response, tokens, latency, cost. Expand any row to inspect | EVAL_OBSERVABILITY Phase EO1 — per-scenario tracing with `contextvars` isolation |
| **One-Click Dataset Creation** | Production failure → golden scenario with one click. No manual JSON editing | Could add a "Save as Golden Scenario" button on the Human Review panel |
| **Prompt Playground** | Edit prompts interactively, test against scenarios, compare results in real-time | Not currently planned. Would need a new dashboard section |
| **AI-Powered Discovery** | Natural language search across traces. "Show me all timeouts in the last week" | Retrospective Agent (spec'd) does rule-based pattern detection. Dreaming integration adds AI discovery |
| **Human Annotation Queues** | Built-in workflow for human reviewers to score, annotate, and approve agent outputs | HUMAN_REVIEW_NOTIFICATIONS spec — approval panel with RETRY/IGNORE/FORCE HEAL |
| **Side-by-Side Model Comparison** | Run same scenarios on Sonnet vs Opus, see which is better for each scenario | EVAL_OBSERVABILITY Phase EO2 — experiment comparison engine (not model-specific yet) |
| **Production Monitoring** | Real-time monitoring of AI in production with alerts and anomaly detection | We monitor test execution, not production AI behavior. Different scope |
| **Heat Map Visualization** | Color-coded score tables showing pass/fail patterns at a glance | EVAL_OBSERVABILITY Phase EO3 — LangSmith-style results table with heat map |

---

## What Building EVAL_OBSERVABILITY Closes

After building EVAL_OBSERVABILITY (Option B — in-house), here's the updated gap analysis:

| Capability | Before EVAL_OBS | After EVAL_OBS | Still a Gap? |
|---|---|---|---|
| Per-call tracing | No | Yes (50 tests, contextvars isolation) | No |
| Experiment comparison | Score delta only | Full diff with per-scenario changes | No |
| Heat map table | No | Yes (LangSmith-style, 3 view modes) | No |
| Trace viewer | No | Yes (full prompt/response, side-by-side) | No |
| One-click dataset creation | No | No | **Yes** — still manual JSON editing |
| Prompt playground | No | No | **Yes** — still edit markdown files |
| AI-powered discovery | No | Partial (Retrospective Agent + Dreaming) | **Partial** — rule-based, not natural language search |
| Production monitoring | No | No | **Yes** — different scope entirely |
| Human annotation | No | Spec'd (HUMAN_REVIEW_NOTIFICATIONS) | **Partial** — spec'd but not built |

**After EVAL_OBSERVABILITY, 4 of 8 gaps are fully closed.** The remaining gaps (one-click datasets, prompt playground, AI discovery, production monitoring) are either lower priority or out of scope for a test automation framework.

---

## Cost Comparison

| Factor | Our System | Braintrust |
|--------|-----------|-----------|
| **Platform cost** | $0 (self-hosted, code we own) | $0 free tier / $250+/month team / custom enterprise |
| **LLM API cost** | ~$0.76 per full eval run (Sonnet pricing) | Same LLM costs + Braintrust platform fee |
| **Storage** | Local disk + git (free) | Braintrust cloud storage (included in plan) |
| **Maintenance** | We maintain the code | They maintain the platform |
| **Data residency** | All data stays local | Data on Braintrust servers (SOC 2 compliant) |

---

## Recommendation

**Don't replace our system with Braintrust.** Our operational pipeline (test runner + self-healing + health scoring + confidence rubric + memory system) is purpose-built and more powerful than what any generic eval platform offers.

**Build EVAL_OBSERVABILITY (Option B)** to close the tracing and comparison gaps. This gives us 80% of Braintrust's eval visualization without the vendor dependency or cost.

**Consider Braintrust later** if:
- Team grows beyond 3 people and needs collaborative annotation workflows
- We need production AI monitoring (beyond test execution)
- Managing 100+ golden scenarios in JSON becomes unwieldy
- We want prompt playground for rapid iteration

**Consider building these in-house instead:**
- "Save as Golden Scenario" button on failure review panel → closes one-click dataset gap
- Prompt editor section on dashboard → closes prompt playground gap
- Retrospective Agent + Dreaming → closes AI discovery gap
