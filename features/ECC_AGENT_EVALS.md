# Build Spec: ECC Agent Evals

## Mission

The 12 ECC (Everything Claude Code) development agents are used daily for planning, code review, security auditing, TDD enforcement, and more. Today, none of them are evaluated -- we trust their prompt definitions but have no data on whether they actually catch what they claim to catch. A security-reviewer that misses SQL injection or a silent-failure-hunter that overlooks empty catch blocks is worse than having no agent at all, because it creates false confidence.

This build spec defines an eval framework for all 12 ECC agents. Unlike the existing 4 pipeline agent evals (triage, planner, generator, healer) which operate on QA pipeline state (`QAState`), ECC agent evals operate on **planted code samples** -- code snippets with known issues where we measure detection rate, false positive rate, and recommendation quality.

**Status:** IN PROGRESS (Phase 1-2 complete, Phase 3 next)
**Priority:** High
**Depends on:** Agent Evaluation System (existing), QA Command Center Dashboard

---

## Key Architectural Difference: Pipeline Agents vs ECC Agents

| Dimension | Pipeline Agents (existing) | ECC Agents (this spec) |
|---|---|---|
| Input | `QAState` with error, DOM, plan, etc. | Code files/snippets (Python, TypeScript) |
| Execution | `await triage(state)` -- real node call | Claude Code subagent invocation via CLI or programmatic wrapper |
| Output | Structured JSON (`failure_class`, `confidence`) | Unstructured text (review findings, severity labels) |
| Golden data | Failure scenarios, test plans | Planted code samples with known issues |
| Scoring | Exact match (`expected_class == got_class`) | Issue detection (did it find the planted bug?), false positive rate |
| Location | `qa_agent/eval/` | `qa_agent/eval/ecc/` (new subdirectory) |

---

## Agents Under Evaluation

### Tier 1: Detection Agents (measurable recall/precision)

These agents produce findings that can be scored against known planted issues.

| # | Agent | What It Does | Primary Metric | Golden Dataset Size |
|---|-------|-------------|----------------|-------------------|
| 1 | **security-reviewer** | OWASP Top 10 vulnerability detection | Vulnerability Detection Rate | 20 samples |
| 2 | **code-reviewer** | General code quality (functions >50 lines, deep nesting, mutation, missing error handling) | Issue Catch Rate | 15 samples |
| 3 | **silent-failure-hunter** | Swallowed errors, empty catches, dangerous fallbacks | Silent Failure Detection Rate | 15 samples |
| 4 | **python-reviewer** | PEP 8, type hints, Pythonic idioms, Python security | Python Issue Catch Rate | 12 samples |
| 5 | **typescript-reviewer** | Type safety, async correctness, TS security | TS Issue Catch Rate | 12 samples |
| 6 | **fastapi-reviewer** | Async correctness, Pydantic schemas, dependency injection, security | FastAPI Issue Catch Rate | 10 samples |
| 7 | **performance-optimizer** | Bottleneck identification, O(n^2) detection, memory leaks | Performance Issue Detection Rate | 10 samples |

### Tier 2: Generative Agents (output quality scoring)

These agents produce plans, fixes, or refactored code that must be evaluated for quality.

| # | Agent | What It Does | Primary Metric | Golden Dataset Size |
|---|-------|-------------|----------------|-------------------|
| 8 | **planner** (ECC) | Implementation planning with phases, risks, file paths | Plan Completeness Score | 8 scenarios |
| 9 | **tdd-guide** | RED-GREEN-REFACTOR enforcement, test-first methodology | TDD Adherence Score | 8 scenarios |
| 10 | **build-error-resolver** | Minimal-diff build fixes | Fix Correctness + Diff Minimality | 10 scenarios |
| 11 | **e2e-runner** | Playwright test creation and flaky test remediation | Test Quality Score | 8 scenarios |
| 12 | **refactor-cleaner** | Dead code detection and safe removal | Detection Accuracy + Safety Score | 10 scenarios |

---

## Golden Dataset Design

### General Principles

1. **Planted issues, not discovered ones** -- Every golden sample has a manifest of known issues with exact line numbers, severity, and category. Scoring compares agent output against this manifest.
2. **Realistic code** -- Samples are drawn from or modeled after real project code (POM classes, FastAPI endpoints, LangGraph nodes), not contrived toy examples.
3. **Difficulty gradient** -- Each agent's golden set includes easy (obvious), medium (requires context), and hard (subtle, multi-file) samples.
4. **Decoys** -- 20-30% of samples are clean code with no issues. Agents that flag clean code as problematic accumulate false positives.
5. **Git-tracked** -- All golden datasets live in `qa_agent/eval/ecc/golden/{agent_name}/` as JSON manifests + code files.

### Dataset Schema

```json
{
  "scenario_id": "sec_sql_injection_f_string",
  "agent": "security-reviewer",
  "difficulty": "easy",
  "language": "python",
  "description": "FastAPI endpoint with f-string SQL injection",
  "code_files": {
    "api/users.py": "... code with vulnerability ..."
  },
  "planted_issues": [
    {
      "issue_id": "VULN-001",
      "category": "sql_injection",
      "severity": "CRITICAL",
      "file": "api/users.py",
      "line_range": [12, 14],
      "description": "User ID interpolated directly into SQL query via f-string"
    }
  ],
  "expected_severity_min": "HIGH",
  "is_clean": false,
  "valid_until": "2027-06-01"
}
```

### Per-Agent Golden Dataset Specifications

#### 1. security-reviewer (20 samples)

| Category | Count | Difficulty | Examples |
|----------|-------|-----------|----------|
| SQL injection | 3 | Easy/Medium/Hard | f-string query, ORM raw query, dynamic table name |
| XSS | 2 | Easy/Medium | `innerHTML = userInput`, template injection |
| Hardcoded secrets | 3 | Easy/Medium/Hard | Inline API key, base64-encoded token, key in comment |
| Path traversal | 2 | Medium/Hard | Unsanitized file path, symlink bypass |
| Command injection | 2 | Medium/Hard | `os.system(user_input)`, subprocess with shell=True |
| Auth bypass | 2 | Medium/Hard | Missing auth middleware, broken RBAC check |
| SSRF | 1 | Hard | `requests.get(user_url)` without allowlist |
| Clean code (decoys) | 5 | N/A | Secure implementations with no vulnerabilities |

#### 2. code-reviewer (15 samples)

| Category | Count | Examples |
|----------|-------|----------|
| Large functions (>50 lines) | 2 | 80-line function, 120-line function |
| Deep nesting (>4 levels) | 2 | Nested if/for/try chains |
| Mutation patterns | 2 | In-place list modification, shared mutable state |
| Missing error handling | 2 | Unhandled exception paths, empty catch blocks |
| Dead code | 1 | Commented-out code, unreachable branches |
| Console.log/print | 1 | Debug logging left in production code |
| Clean code (decoys) | 5 | Well-structured code following all conventions |

#### 3. silent-failure-hunter (15 samples)

| Category | Count | Examples |
|----------|-------|----------|
| Empty catch blocks | 3 | `except: pass`, `catch {}`, `except Exception: return None` |
| Dangerous fallbacks | 3 | `.catch(() => [])`, default values hiding failures |
| Lost stack traces | 2 | `raise ValueError("error")` without `from e` |
| Log-and-forget | 2 | `logger.error(e)` then continue with bad state |
| Missing async error handling | 2 | Fire-and-forget async calls without error propagation |
| Clean code (decoys) | 3 | Proper error handling with logging and propagation |

#### 4. python-reviewer (12 samples)

| Category | Count | Examples |
|----------|-------|----------|
| PEP 8 violations | 2 | Mixed naming conventions, missing type hints |
| Anti-patterns | 2 | Mutable default arguments, bare `except` |
| Type hint issues | 2 | Missing return types, wrong generic types |
| Python security | 2 | `eval(user_input)`, pickle deserialization |
| Performance | 1 | String concatenation in loop vs join |
| Clean code (decoys) | 3 | Pythonic, well-typed code |

#### 5. typescript-reviewer (12 samples)

| Category | Count | Examples |
|----------|-------|----------|
| Type safety | 3 | `any` usage, missing null checks, type assertions |
| Async correctness | 2 | Missing `await`, unhandled promise rejection |
| React patterns | 2 | Missing deps array, stale closure, index keys |
| Node.js security | 2 | `eval()`, unvalidated request body |
| Clean code (decoys) | 3 | Well-typed, safe TypeScript code |

#### 6. fastapi-reviewer (10 samples)

| Category | Count | Examples |
|----------|-------|----------|
| Async issues | 2 | Sync DB call in async handler, missing `await` |
| Pydantic misuse | 2 | No response model, mutable default in schema |
| Missing middleware | 2 | No rate limiting, no CORS, no auth dependency |
| Dependency injection | 1 | Manual instantiation instead of `Depends()` |
| Clean code (decoys) | 3 | Well-structured FastAPI endpoints |

#### 7. performance-optimizer (10 samples)

| Category | Count | Examples |
|----------|-------|----------|
| Algorithmic | 3 | O(n^2) in nested loops, redundant sorting, unnecessary copies |
| Memory leaks | 2 | Growing list in closure, unclosed file handles |
| N+1 queries | 2 | DB query in loop without batching |
| Clean code (decoys) | 3 | Already-optimized code |

#### 8. planner (ECC) (8 scenarios)

| Scenario Type | Count | Expected Output Quality |
|---------------|-------|------------------------|
| Simple feature | 2 | Phases, file paths, dependencies |
| Complex refactor | 2 | Migration plan, backwards compatibility |
| Multi-service change | 2 | Cross-boundary considerations |
| Clean requirement (well-defined) | 2 | Complete plan without over-engineering |

#### 9. tdd-guide (8 scenarios)

| Scenario Type | Count | Expected Output Quality |
|---------------|-------|------------------------|
| New function | 2 | Test written before implementation |
| Bug fix | 2 | Regression test covers the bug |
| Refactor | 2 | Tests pass before and after |
| Edge case heavy | 2 | Boundary conditions tested |

#### 10. build-error-resolver (10 scenarios)

| Error Type | Count | Expected Behavior |
|------------|-------|------------------|
| TypeScript type errors | 3 | Minimal type annotation fix |
| Import resolution | 2 | Correct path fix |
| Missing dependency | 2 | Package install, not code rewrite |
| Config errors | 1 | Config-only fix |
| Clean build (decoys) | 2 | "Build already passing" response |

#### 11. e2e-runner (8 scenarios)

| Scenario Type | Count | Expected Output Quality |
|---------------|-------|------------------------|
| New user flow | 2 | POM + spec with semantic locators |
| Flaky test fix | 2 | Proper wait strategy, not `waitForTimeout` |
| Broken locator update | 2 | Minimal diff, assertions preserved |
| Test already passing (decoys) | 2 | No unnecessary changes |

#### 12. refactor-cleaner (10 scenarios)

| Scenario Type | Count | Expected Behavior |
|---------------|-------|------------------|
| Unused exports | 3 | Correctly identified and removed |
| Duplicate functions | 2 | Consolidated with correct choice |
| Unused dependencies | 2 | Removed from package.json |
| Live code (decoys) | 3 | Code NOT removed (false positive check) |

---

## Scoring Functions

### Tier 1: Detection Agents -- Issue-Level Scoring

Each detection agent is scored on four metrics:

| Metric | Formula | Threshold |
|--------|---------|-----------|
| **Recall (Detection Rate)** | Planted issues found / total planted issues | Agent-specific (see below) |
| **Precision** | True findings / (true findings + false positives) | >= 80% |
| **Severity Accuracy** | Correct severity / total findings | >= 70% |
| **False Positive Rate** | False positives on clean samples / total clean samples | <= 20% |

**Per-Agent Recall Thresholds:**

| Agent | Recall Threshold | Rationale |
|-------|-----------------|-----------|
| security-reviewer | >= 85% | Missing a vulnerability is unacceptable |
| code-reviewer | >= 75% | Some issues are stylistic judgment calls |
| silent-failure-hunter | >= 80% | Swallowed errors are high-impact |
| python-reviewer | >= 75% | Includes style issues with subjective boundaries |
| typescript-reviewer | >= 75% | Includes style issues with subjective boundaries |
| fastapi-reviewer | >= 80% | API correctness is critical |
| performance-optimizer | >= 70% | Performance issues can be subjective |

**Matching Algorithm:**

Agent output is unstructured text. To match findings against the manifest:

1. Extract findings from agent output using regex patterns for severity labels (`[CRITICAL]`, `[HIGH]`, etc.) and file/line references
2. For each extracted finding, fuzzy-match against planted issues using:
   - File name match (exact)
   - Line proximity (within +/- 5 lines of planted issue)
   - Category keyword overlap (>= 50% keyword match)
3. A planted issue is "found" if at least one extracted finding matches it
4. An extracted finding that matches no planted issue is a false positive

```python
@dataclass(frozen=True)
class FindingMatch:
    planted_issue_id: str
    agent_finding_text: str
    file_match: bool
    line_proximity: int  # 0 = exact, higher = further away
    category_overlap: float  # 0.0 to 1.0
    matched: bool  # True if all criteria met
```

### Tier 2: Generative Agents -- Output Quality Scoring

| Agent | Metrics | Method |
|-------|---------|--------|
| **planner** | Plan Completeness, Phase Independence, Risk Coverage | LLM-as-judge with rubric |
| **tdd-guide** | TDD Adherence, Test Coverage, Edge Cases | Check test-before-code ordering, count test cases vs requirements |
| **build-error-resolver** | Fix Correctness, Diff Minimality, No Side Effects | Apply fix, run `tsc --noEmit`, measure diff size, run existing tests |
| **e2e-runner** | Locator Quality, Assertion Density, No Hard Waits | Reuse existing `score_locator_quality`, `score_test_validity` |
| **refactor-cleaner** | True Positive Rate, No Live Code Removed, Tests Pass | Verify removed code is actually dead, verify live code untouched |

### LLM-as-Judge Rubric (for planner, tdd-guide)

Use Claude Haiku as the judge (cost-effective for rubric scoring). The judge receives:

1. The original scenario/requirement
2. The agent's output
3. A scoring rubric with 5 dimensions rated 1-5

```json
{
  "rubric": {
    "completeness": "Does the output cover all requirements? (1=missing most, 5=all covered)",
    "actionability": "Are steps specific enough to implement? (1=vague, 5=exact file paths and code changes)",
    "correctness": "Is the approach technically sound? (1=wrong approach, 5=optimal)",
    "risk_awareness": "Are risks and edge cases identified? (1=none, 5=comprehensive)",
    "convention_adherence": "Does output follow project conventions? (1=ignores, 5=fully aligned)"
  }
}
```

Score = average of 5 dimensions, normalized to 0-1. Threshold: >= 0.70.

---

## Architecture

### Directory Structure

```
qa_agent/eval/ecc/
├── __init__.py
├── ecc_eval_runner.py          # Orchestrates all ECC evals
├── agent_invoker.py            # Wraps Claude Code agent invocation
├── finding_extractor.py        # Parses agent text output into structured findings
├── finding_matcher.py          # Matches extracted findings against planted issues
├── llm_judge.py                # LLM-as-judge for generative agents
├── golden/
│   ├── security-reviewer/
│   │   ├── manifest.json       # 20 scenarios with planted issues
│   │   └── samples/            # Code files referenced by manifest
│   ├── code-reviewer/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── silent-failure-hunter/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── python-reviewer/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── typescript-reviewer/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── fastapi-reviewer/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── performance-optimizer/
│   │   ├── manifest.json
│   │   └── samples/
│   ├── planner/
│   │   ├── manifest.json
│   │   └── scenarios/
│   ├── tdd-guide/
│   │   ├── manifest.json
│   │   └── scenarios/
│   ├── build-error-resolver/
│   │   ├── manifest.json
│   │   └── scenarios/
│   ├── e2e-runner/
│   │   ├── manifest.json
│   │   └── scenarios/
│   └── refactor-cleaner/
│       ├── manifest.json
│       └── scenarios/
├── reports/
│   └── {agent_name}/
│       └── {timestamp}.json    # Scorecards per agent
└── config.py                   # Thresholds, budget caps, model configs
```

### Agent Invocation

ECC agents are Claude Code subagents. The invoker wraps `claude` CLI calls:

```python
async def invoke_ecc_agent(
    agent_name: str,
    prompt: str,
    code_files: dict[str, str],
    *,
    timeout_seconds: int = 120,
    model_override: str | None = None,
) -> AgentResponse:
    """Invoke an ECC agent via Claude Code CLI and capture its output."""
```

### Finding Extraction

Agent output is unstructured markdown/text. The extractor uses patterns:

```python
SEVERITY_PATTERNS = [
    r"\[CRITICAL\]",
    r"\[HIGH\]",
    r"\[MEDIUM\]",
    r"\[LOW\]",
    r"\*\*CRITICAL\*\*",
    r"\*\*HIGH\*\*",
    r"Severity:\s*(CRITICAL|HIGH|MEDIUM|LOW)",
]

FILE_LINE_PATTERNS = [
    r"File:\s*([^\s:]+):(\d+)",
    r"([^\s]+\.(?:py|ts|tsx|js)):(\d+)",
    r"line\s+(\d+)\s+(?:of|in)\s+([^\s]+)",
]
```

---

## Dashboard Integration

### Full Dashboard Layout

The complete dashboard with both pipeline and ECC agent sections:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    QA COMMAND CENTER                                         │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  ┌─────────────────────┐                                                                     │
│  │    HEALTH GAUGE      │    [14 DOMAIN CARDS - existing]                                    │
│  │      100.0%          │    Cart | Checkout | Sign-In | Search | Product | Homepage | ...   │
│  │     HEALTHY          │                                                                    │
│  └─────────────────────┘                                                                     │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  PIPELINE AGENT EVALS (existing)                                        [▶ EVAL ALL]         │
│                                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │   TRIAGE      │  │   PLANNER    │  │  GENERATOR   │  │   HEALER     │                     │
│  │   85.7%       │  │   99.4%      │  │   97.5%      │  │   98.0%      │                     │
│  │   [PASS]      │  │   [PASS]     │  │   [PASS]     │  │   [PASS]     │                     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘                     │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  DEVELOPMENT AGENT EVALS (new)                                     [▶ EVAL ECC AGENTS]       │
│                                                                                              │
│  Tier 1: Detection Agents                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │  SECURITY-    │  │  CODE-       │  │  SILENT-     │  │  PYTHON-     │                     │
│  │  REVIEWER     │  │  REVIEWER    │  │  FAILURE-    │  │  REVIEWER    │                     │
│  │  85.0%        │  │  78.0%       │  │  HUNTER      │  │  80.0%       │                     │
│  │  Recall ██▓   │  │  Recall ███  │  │  82.0%       │  │  Recall ███  │                     │
│  │  Prec   ████  │  │  Prec   ███  │  │  Recall ███▓ │  │  Prec   ████ │                     │
│  │  FP     ████  │  │  FP     ████ │  │  Prec   ████ │  │  FP     ███  │                     │
│  │  [PASS]       │  │  [PASS]      │  │  FP     ████ │  │  [PASS]      │                     │
│  │  $0.48  20sc  │  │  $0.36  15sc │  │  [PASS]      │  │  $0.29  12sc │                     │
│  └──────────────┘  └──────────────┘  │  $0.27  15sc │  └──────────────┘                     │
│                                       └──────────────┘                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                                       │
│  │  TYPESCRIPT-  │  │  FASTAPI-    │  │  PERFORMANCE-│                                       │
│  │  REVIEWER     │  │  REVIEWER    │  │  OPTIMIZER   │                                       │
│  │  76.0%        │  │  82.0%       │  │  72.0%       │                                       │
│  │  Recall ███   │  │  Recall ███▓ │  │  Recall ██▓  │                                       │
│  │  Prec   ████  │  │  Prec   ████ │  │  Prec   ███  │                                       │
│  │  FP     ████  │  │  FP     ████ │  │  FP     ████ │                                       │
│  │  [PASS]       │  │  [PASS]      │  │  [PASS]      │                                       │
│  │  $0.29  12sc  │  │  $0.24  10sc │  │  $0.18  10sc │                                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                                       │
│                                                                                              │
│  Tier 2: Generative Agents                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  PLANNER      │  │  TDD-        │  │  BUILD-ERROR-│  │  E2E-        │  │  REFACTOR-   │   │
│  │  (ECC)        │  │  GUIDE       │  │  RESOLVER    │  │  RUNNER      │  │  CLEANER     │   │
│  │  78.0%        │  │  82.0%       │  │  90.0%       │  │  85.0%       │  │  88.0%       │   │
│  │  Quality ███▓ │  │  Quality ███▓│  │  Quality ████│  │  Quality ████│  │  Quality ████│   │
│  │  Compl   ████ │  │  Compl   ████│  │  Compl   ████│  │  Compl   ████│  │  Compl   ████│   │
│  │  Action  ███  │  │  Action  ███ │  │  Action  ████│  │  Action  ████│  │  Action  ████│   │
│  │  [PASS]       │  │  [PASS]      │  │  [PASS]      │  │  [PASS]      │  │  [PASS]      │   │
│  │  $1.80   8sc  │  │  $0.24   8sc │  │  $0.18  10sc │  │  $0.24   8sc │  │  $0.18  10sc │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                                              │
│  ┌────────────────────────────────────────────────────────────────┐                          │
│  │  COST ODOMETER          Total: $4.77  |  Runs: 12  |  ▲ $0.32 │                          │
│  └────────────────────────────────────────────────────────────────┘                          │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  TEST RUNNER (existing)                                                                      │
│  [Domain checkboxes] [Workers] [Retries] [Self-heal] [▶ RUN TESTS]                          │
│                                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  RUN HISTORY (existing)                                                                      │
│  Timestamp | Total | Passed | Failed | Health | Status                                       │
│                                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Card Designs

**Detection Agent Card:**

```
┌─────────────────────────────────────┐
│  SECURITY-REVIEWER           [PASS] │
│                                     │
│  Recall:     85.0% (17/20)     ██▓  │
│  Precision:  90.0%             ████ │
│  FP Rate:     0.0% (0/5)      ████ │
│  Sev Acc:    76.5%             ██▓  │
│                                     │
│  Last run: Sep 3, 18:15             │
│  Cost: $0.42 (23K tokens)          │
│  Trend: ▲ +3.2% vs previous        │
└─────────────────────────────────────┘
```

**Generative Agent Card:**

```
┌─────────────────────────────────────┐
│  PLANNER (ECC)               [PASS] │
│                                     │
│  Quality:    78.0%             ███▓ │
│  Complete:   85.0%             ████ │
│  Actionable: 72.0%             ███  │
│  Convention: 80.0%             ████ │
│                                     │
│  Last run: Sep 3, 18:15             │
│  Cost: $1.24 (45K tokens)          │
│  Trend: ─ 0.0% vs previous         │
└─────────────────────────────────────┘
```

### New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/eval/ecc/scores` | GET | Latest scorecard for all 12 ECC agents |
| `/api/eval/ecc/scores/{agent}` | GET | Scorecard for a specific ECC agent |
| `/api/eval/ecc/run` | POST | Trigger eval run for one or all ECC agents |
| `/api/eval/ecc/history/{agent}` | GET | Historical scorecards for trend display |

### Dashboard Button

Add "EVAL ECC AGENTS" button alongside existing "EVAL ALL" button.

---

## Token Cost Tracking

### Estimated Cost Per Full Eval Run

| Agent | Model | Scenarios | Est. Cost |
|-------|-------|-----------|-----------|
| security-reviewer | Sonnet | 20 | ~$0.48 |
| code-reviewer | Sonnet | 15 | ~$0.36 |
| silent-failure-hunter | Sonnet | 15 | ~$0.27 |
| python-reviewer | Sonnet | 12 | ~$0.29 |
| typescript-reviewer | Sonnet | 12 | ~$0.29 |
| fastapi-reviewer | Sonnet | 10 | ~$0.24 |
| performance-optimizer | Sonnet | 10 | ~$0.18 |
| planner (ECC) | Opus | 8 | ~$1.80 |
| tdd-guide | Sonnet | 8 | ~$0.24 |
| build-error-resolver | Sonnet | 10 | ~$0.18 |
| e2e-runner | Sonnet | 8 | ~$0.24 |
| refactor-cleaner | Sonnet | 10 | ~$0.18 |
| LLM-as-judge | Haiku | ~16 | ~$0.02 |
| **TOTAL** | | **148** | **~$4.77** |

### Cost Controls

1. **Per-agent budget cap** -- Each agent eval has a max budget (2x estimated cost)
2. **Scenario-level timeout** -- 120 seconds per scenario
3. **Selective runs** -- CLI supports running a single agent's eval
4. **Cost odometer** -- Dashboard shows cumulative cost across all ECC eval runs
5. **Dry-run mode** -- Validate golden datasets without agent invocation

---

## CLI Interface

```bash
# Run all ECC agent evals
qa-agent eval --ecc

# Run specific ECC agent eval
qa-agent eval --ecc --agent security-reviewer

# Run a tier (detection or generative)
qa-agent eval --ecc --tier detection
qa-agent eval --ecc --tier generative

# Baseline mode (record metrics, no pass/fail)
qa-agent eval --ecc --baseline

# Dry run (validate golden datasets, no agent invocation)
qa-agent eval --ecc --dry

# Compare two runs
qa-agent eval --ecc compare {run-a} {run-b}

# Show cost summary
qa-agent eval --ecc --cost-report
```

---

## Implementation Phases

### Phase 1: Foundation + 3 Detection Agents (Week 1-2) — COMPLETE

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `qa_agent/eval/ecc/` package structure | `__init__.py` | Done |
| 2 | Build `agent_invoker.py` -- wraps Claude Code CLI | `agent_invoker.py` | Done |
| 3 | Build `finding_extractor.py` -- parses agent output | `finding_extractor.py` | Done |
| 4 | Build `finding_matcher.py` -- matches findings vs manifest | `finding_matcher.py` | Done |
| 5 | Build `config.py` -- thresholds, budget caps | `config.py` | Done |
| 6 | Create security-reviewer golden dataset (20 scenarios) | `golden/security-reviewer/` | Done |
| 7 | Create code-reviewer golden dataset (15 scenarios) | `golden/code-reviewer/` | Done |
| 8 | Create silent-failure-hunter golden dataset (15 scenarios) | `golden/silent-failure-hunter/` | Done |
| 9 | Build `ecc_eval_runner.py` -- orchestrator | `ecc_eval_runner.py` | Done |
| 10 | Add `--ecc` flag to CLI | `qa_agent/cli.py` | Done |
| 11 | Run baselines for 3 agents | Manual | Pending |
| 12 | Write tests (31 tests, 744 total passing) | `tests/test_ecc_eval.py` | Done |

### Phase 2: Remaining Detection Agents (Week 3) — COMPLETE

| # | Task | Status |
|---|------|--------|
| 1 | Create python-reviewer golden dataset (12 scenarios) | Done |
| 2 | Create typescript-reviewer golden dataset (12 scenarios) | Done |
| 3 | Create fastapi-reviewer golden dataset (10 scenarios) | Done |
| 4 | Create performance-optimizer golden dataset (10 scenarios) | Done |
| 5 | Run baselines for all 4 new agents | Pending |
| 6 | Tune finding_extractor patterns for agent-specific output formats | Pending |

### Phase 3: Generative Agents + LLM Judge (Week 4)

| # | Task |
|---|------|
| 1 | Build `llm_judge.py` -- LLM-as-judge with Haiku |
| 2 | Create planner (ECC) golden scenarios (8) |
| 3 | Create tdd-guide golden scenarios (8) |
| 4 | Create build-error-resolver golden scenarios (10) |
| 5 | Create e2e-runner golden scenarios (8) |
| 6 | Create refactor-cleaner golden scenarios (10) |
| 7 | Add generative scoring path to `ecc_eval_runner.py` |
| 8 | Reuse existing `score_locator_quality`, `score_test_validity` for e2e-runner |
| 9 | Run baselines for all 5 generative agents |
| 10 | Write tests for `llm_judge.py` |

### Phase 4: Dashboard Integration (Week 5)

| # | Task | File |
|---|------|------|
| 1 | Add `/api/eval/ecc/scores` endpoints | `server.py` |
| 2 | Add `/api/eval/ecc/run` endpoint | `server.py` |
| 3 | Add `/api/eval/ecc/history/{agent}` endpoint | `server.py` |
| 4 | Add "DEVELOPMENT AGENT EVALS" section to HTML | `index.html` |
| 5 | Add ECC eval card rendering | `app.js` |
| 6 | Add cyberpunk styling for ECC cards | `styles.css` |
| 7 | Add "EVAL ECC AGENTS" button with WebSocket progress | `app.js` |
| 8 | Add cost odometer card | `app.js` |

### Phase 5: Regression Detection + CI (Week 6)

| # | Task |
|---|------|
| 1 | Extend regression detector for ECC scorecard format |
| 2 | Add ECC eval to CI pipeline (triggers on `.claude/agents/*.md` changes) |
| 3 | Alert on agent regression (recall drops >5% or crosses threshold) |
| 4 | Cost trend tracking with alerts |

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent output format varies | HIGH | Robust extraction with multiple pattern variants, fallback unstructured match |
| LLM non-determinism | HIGH | Track variance across runs, flag agents with >10% variance |
| High token cost (~$5/run) | MEDIUM | Single-agent runs, tier-based runs, dry-run mode, budget caps |
| Agent invocation latency (~25min full run) | MEDIUM | Sequential agents, concurrent scenarios (max 3 parallel), WebSocket progress |
| Golden dataset staleness | MEDIUM | `valid_until` dates, quarterly review, retire trivial scenarios |
| False positive inflation | MEDIUM | 20-30% clean-code decoy samples, FP rate threshold <= 20% |
| Planner name collision (ECC vs pipeline) | LOW | Use `planner-ecc` as eval identifier, label "PLANNER (ECC)" in dashboard |

---

## Success Criteria

- [ ] All 12 ECC agents have golden datasets with planted issues/scenarios
- [ ] Detection agents scored on recall, precision, severity accuracy, and false positive rate
- [ ] Generative agents scored on output quality via LLM-as-judge or deterministic checks
- [ ] CLI supports `qa-agent eval --ecc` with per-agent and per-tier filtering
- [ ] Dashboard shows "DEVELOPMENT AGENT EVALS" section separate from pipeline agents
- [ ] Each eval card shows score, trend, last run time, and cost
- [ ] Regression detection alerts when recall drops >5% or crosses threshold
- [ ] Token cost tracked per agent and per run, with budget caps enforced
- [ ] All tests pass (18 unit tests across 3 test files)
- [ ] Full eval run completes in <30 minutes with cost <$10
- [ ] No ECC eval code pollutes existing pipeline eval paths
