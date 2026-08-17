# Feature: Auto-Threshold Tuning & Self-Learning Triage

> Triage automatically improves its classification accuracy by learning from human corrections — adjusting confidence thresholds and failure-pattern recognition without manual intervention.

**Status:** PLANNED
**Priority:** High
**Depends on:** Core framework (Phases 0-4), Memory feature

---

## The Problem

Today `CONF_SURE = 0.75` and `MAX_ATTEMPTS = 3` are static constants. The observability module can *detect* when Triage accuracy drops, but a human must manually adjust the thresholds. Meanwhile, Triage makes the same classification mistakes repeatedly because it doesn't learn from past corrections.

## The Solution

A closed-loop system where:
1. Every human correction becomes a labelled training example
2. Triage's prompt is enriched with recent corrections (few-shot calibration)
3. Thresholds auto-adjust based on measured accuracy — more cases go to humans when accuracy is low, fewer when it's high

---

## A. How It Works

### Feedback loop

```
Triage classifies → Human corrects (when unsure) → Correction stored
                                                          ↓
                                          Triage prompt enriched with corrections
                                          Thresholds adjusted from accuracy stats
                                                          ↓
                                              Next run: Triage is more accurate
```

### Threshold adjustment algorithm

```python
def auto_tune(db: MetricsDB) -> dict:
    accuracy = db.compute_triage_accuracy()

    if accuracy["total_audited"] < 20:
        return {"action": "skip", "reason": "insufficient data"}

    if accuracy["accuracy"] < 0.70:
        # Accuracy poor → raise CONF_SURE (send more to humans)
        new_conf = min(CONF_SURE + 0.05, 0.95)
        return {"action": "raise", "new_conf_sure": new_conf}

    if accuracy["accuracy"] > 0.90 and CONF_SURE > 0.60:
        # Accuracy excellent → lower CONF_SURE (trust Triage more)
        new_conf = max(CONF_SURE - 0.05, 0.60)
        return {"action": "lower", "new_conf_sure": new_conf}

    return {"action": "hold", "reason": "accuracy within acceptable range"}
```

### Few-shot calibration in Triage prompt

```
## Recent corrections (learn from these)
- Error: "TimeoutError waiting for button 'Submit'" → You said: locator_drift (0.82)
  Human corrected to: app_defect. Why: the button was removed, not renamed.
- Error: "AssertionError: expected 'OK' got ''" → You said: app_defect (0.91)
  Human confirmed: correct.
- Error: "Element not found: [data-testid=cart-total]" → You said: locator_drift (0.60)
  Human corrected to: locator_drift (you were right but underconfident — raise confidence for testid-not-found errors).
```

---

## B. Build Phases

### Phase AT1 — Automatic threshold adjustment
| # | Task | Status |
|---|------|--------|
| 1 | `auto_tune()` function that reads accuracy + recommends threshold changes | TODO |
| 2 | Apply threshold changes to `config.py` at runtime (not file edits) | TODO |
| 3 | Tuning bounds: `CONF_SURE` stays within [0.60, 0.95] | TODO |
| 4 | Minimum sample size before tuning activates (e.g. 20 audited calls) | TODO |
| 5 | Tuning log: record every adjustment with timestamp and reason | TODO |

**Tests:**
- Unit: accuracy < 0.70 → CONF_SURE raised
- Unit: accuracy > 0.90 → CONF_SURE lowered
- Unit: bounds enforced (never below 0.60, never above 0.95)
- Unit: insufficient data → no change
- Integration: simulated accuracy drop triggers threshold raise

**Done when:** Thresholds adjust automatically based on measured accuracy.

### Phase AT2 — Few-shot Triage calibration
| # | Task | Status |
|---|------|--------|
| 1 | Select N most recent human corrections from Memory | TODO |
| 2 | Format as few-shot examples in Triage system prompt | TODO |
| 3 | Cap at ~500 tokens to avoid prompt bloat | TODO |
| 4 | Include both corrections AND confirmations (learn from both) | TODO |
| 5 | Weight recent examples higher than old ones | TODO |

**Tests:**
- Unit: calibration examples are formatted correctly in prompt
- Unit: token cap is enforced
- Unit: both corrections and confirmations included
- Integration: Triage accuracy improves on a golden set after calibration injection

**Done when:** Triage prompt includes recent human feedback; accuracy measurably improves.

### Phase AT3 — Pattern-based classification shortcuts
| # | Task | Status |
|---|------|--------|
| 1 | Build error signature → classification lookup table from past data | TODO |
| 2 | If an error signature has been classified 5+ times with >90% agreement, skip LLM | TODO |
| 3 | Deterministic fast path: known patterns classified instantly | TODO |
| 4 | Fallback to LLM for unknown patterns | TODO |

**Done when:** Recurring failure patterns are classified without an LLM call.

---

## C. Assumptions

- Tuning is per-project (each app has its own accuracy profile).
- Threshold changes apply at runtime via config override, not by editing files.
- Minimum 20 audited calls before auto-tuning activates (avoid overfitting to small samples).
- Few-shot examples are capped at 5 most recent corrections.
- The system never lowers `CONF_SURE` below 0.60 (always some human oversight).

## D. Not in Scope

- Fine-tuning the LLM itself on past classifications
- Automated A/B testing of different thresholds
- Multi-project threshold sharing
