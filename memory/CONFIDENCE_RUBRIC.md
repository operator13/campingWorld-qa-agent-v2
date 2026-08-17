# Triage Confidence Rubric

## Scoring Criteria (each 0.0-0.2, total 0.0-1.0)

### C1: Error type signal (0.0-0.2)
- 0.2 — Clear signal: `selector-not-found` (drift) or `AssertionError: wrong value` (defect)
- 0.1 — Moderate signal: `TimeoutError` (could be either)
- 0.0 — No signal: generic error, no pattern match

### C2: DOM evidence (0.0-0.2)
- 0.2 — Element exists in DOM but with different selector/name (drift)
- 0.2 — Element completely absent AND no similar element (defect)
- 0.1 — Element partially matches (renamed but similar structure)
- 0.0 — No DOM snapshot available

### C3: Historical pattern match (0.0-0.2)
- 0.2 — Identical error signature seen before with known resolution
- 0.1 — Similar error on same route, different element
- 0.0 — No matching history

### C4: Human calibration alignment (0.0-0.2)
- 0.2 — Past human decisions agree with this classification
- 0.1 — Mixed human decisions on similar errors
- 0.0 — Humans have overridden this pattern before (reduce confidence)

### C5: Consistency check (0.0-0.2)
- 0.2 — Multiple independent signals agree (error type + DOM + history)
- 0.1 — Two signals agree, one contradicts
- 0.0 — Signals conflict or only one signal available

## Anti-Inflation Guards

- **Guard 1:** First time seeing this error pattern → cap at 0.7
- **Guard 2:** Humans have overridden this classification 2+ times → cap at 0.6
- **Guard 3:** DOM snapshot unavailable → cap at 0.5
- **Guard 4:** TimeoutError alone (no DOM evidence) → cap at 0.6
