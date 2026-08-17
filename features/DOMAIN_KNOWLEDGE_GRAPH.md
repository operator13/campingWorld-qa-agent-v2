# Feature: Domain Knowledge Graph

> Promote the flat `ontology.yaml` taxonomy to a property graph with typed relationships — enabling coverage queries, impact analysis, and cross-agent reasoning.

**Status:** PLANNED
**Priority:** Low (only when the flat taxonomy isn't enough)
**Depends on:** Core framework (Phases 0-4), Memory feature

---

## The Problem

Today `ontology.yaml` is a flat registry: features → routes → components. It can't answer relational questions like:
- "Which acceptance criteria have no test covering them?"
- "This element changed — which tests are affected?"
- "What's the coverage gap between Figma designs and test cases?"

These queries require *relationships* between entities, not just lists.

## The Solution

A lightweight property graph (starting with `rdflib` or `networkx` in Python, graduating to Neo4j only if query complexity demands it) with typed relationships between all domain entities.

---

## A. Entity Model

```
Feature ──has_route──→ Route ──has_page──→ Page ──has_component──→ Component ──has_element──→ Element
    │                    │                                              │
    │                    ├──tested_by──→ TestCase ──verifies──→ AcceptanceCriterion
    │                    │                   │
    │                    │                   └──uses──→ PageObject
    │                    │
    │                    └──designed_in──→ FigmaFrame
    │
    └──tracked_in──→ JiraEpic
                        │
                        └──has_issue──→ JiraIssue
                                          │
                                          └──affects──→ Feature
```

### Entity types

| Entity | Properties | Source |
|--------|-----------|--------|
| Feature | name, description | ontology.yaml |
| Route | path, testid_prefix | ontology.yaml + config |
| Component | name, type | Figma MCP |
| Element | role, name, testid, state | Design Reader |
| TestCase | id, title, steps, expected | Planner |
| AcceptanceCriterion | text, source | Intake (Jira/Figma) |
| PageObject | route, class_name, locators | Generator |
| FigmaFrame | node_id, file_key, name | Design Reader |
| Defect | ticket_key, failure_class, route | Defect Report |

### Relationship types

| Relationship | From → To | Meaning |
|-------------|-----------|---------|
| `has_route` | Feature → Route | Feature is served on this route |
| `has_element` | Component → Element | Component contains this element |
| `tested_by` | Route → TestCase | This route is covered by this test |
| `verifies` | TestCase → AC | This test verifies this criterion |
| `affects` | Defect → Feature | This bug affects this feature |
| `uses` | TestCase → PageObject | This test imports this page object |
| `designed_in` | Route → FigmaFrame | This route's design is in this frame |
| `drifted` | Element → Element | This element's locator changed |

---

## B. Queries This Enables

```python
# Coverage gap: which ACs have no test?
uncovered = graph.query("AC WHERE NOT EXISTS (TestCase --verifies--> AC)")

# Impact analysis: element changed, which tests break?
affected = graph.query("TestCase --uses--> PageObject --has_element--> Element[name='Submit']")

# Defect clustering: which features have the most bugs?
hotspots = graph.query("Feature <--affects-- Defect GROUP BY Feature ORDER BY COUNT DESC")

# Design coverage: which Figma frames have no tests?
untested = graph.query("FigmaFrame WHERE NOT EXISTS (Route --designed_in--> FigmaFrame --tested_by--> TestCase)")
```

---

## C. Build Phases

### Phase KG1 — Graph construction from existing data
| # | Task | Status |
|---|------|--------|
| 1 | Choose graph library (`networkx` for v1 — in-process, no infrastructure) | TODO |
| 2 | Build graph from `ontology.yaml` (features, routes, components) | TODO |
| 3 | Populate from Planner output (TestCases, ACs) | TODO |
| 4 | Populate from Generator output (PageObjects, Elements) | TODO |
| 5 | Persist graph to disk (JSON or pickle alongside metrics.db) | TODO |

**Tests:**
- Unit: graph construction from ontology.yaml
- Unit: entities and relationships are queryable
- Unit: graph serializes/deserializes correctly

**Done when:** A graph is built from existing pipeline data after each run.

### Phase KG2 — Coverage queries
| # | Task | Status |
|---|------|--------|
| 1 | "Uncovered ACs" query | TODO |
| 2 | "Untested routes" query | TODO |
| 3 | Coverage report in eval harness | TODO |
| 4 | CLI command: `qa-agent coverage` | TODO |

**Done when:** Coverage gaps are queryable and reported.

### Phase KG3 — Impact analysis
| # | Task | Status |
|---|------|--------|
| 1 | "Element changed → affected tests" query | TODO |
| 2 | "Route changed → affected features" query | TODO |
| 3 | Integration with per-commit mode: use impact analysis to select tests | TODO |

**Done when:** A change to one element can identify all affected tests.

### Phase KG4 — Graduate to Neo4j (if needed)
| # | Task | Status |
|---|------|--------|
| 1 | Evaluate whether `networkx` queries are too slow or limited | TODO |
| 2 | If yes: migrate to Neo4j with Cypher queries | TODO |
| 3 | Docker Compose setup for local Neo4j | TODO |

**Done when:** Decision made and executed (may stay on networkx if sufficient).

---

## D. Assumptions

- Start with `networkx` (Python, in-process, zero infrastructure).
- Graph is rebuilt after each run (not incrementally updated in v1).
- Queries are run at reporting time, not real-time during agent execution.
- `ontology.yaml` remains the source of truth for features/routes.

## E. Not in Scope

- RDF/SPARQL (overkill for this use case)
- Graph visualization UI (CLI output is sufficient for v1)
- Real-time graph updates during agent execution
- Cross-project graph federation
