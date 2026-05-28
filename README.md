# ANOR — High-Stakes Decision Scenario Simulator

ANOR is an open-source engine for running branching decision-tree scenarios against AI models and human candidates. It is designed to evaluate reasoning under pressure in situations where the wrong choice cascades into irreversible harm.

ANOR is the runtime component of the [MANDOS](https://github.com/relayforge-ai/mandos) benchmarking program.

---

## What ANOR Does

A scenario presents a candidate with a high-stakes situation and a series of decision nodes. At each node, the candidate selects from four options. Choices propagate forward — a poor decision at node 2 may constrain options at node 4, or accelerate toward a terminal failure state. ANOR scores the run, tags failure modes, and produces a structured report.

The goal is not to test recall. It is to test whether a candidate reasons *through* a cascading event — recognizing when to slow down, who to consult, and when instrument readings should be questioned rather than trusted.

---

## Scenario Structure

Each scenario consists of two parts:

**Part A — Candidate Packet**
The situation briefing presented to the candidate or model. Contains no failure labels, no outcome hints, and no terminal markers. Just the scenario as it would be encountered in the field.

**Part B — Evaluator Key** *(not included in this repo)*
The scoring rubric, preferred action rationale, and failure mode taxonomy. Evaluator keys for MANDOS scenarios are maintained separately.

### Decision Node Format

```json
{
  "node_id": "N1",
  "prompt": "...",
  "options": {
    "A": { "text": "...", "correct": true },
    "B": { "text": "...", "fail_code": "FAIL-06" },
    "C": { "text": "...", "fail_code": "FAIL-05" },
    "D": { "text": "...", "fail_code": "FAIL-09" }
  },
  "next": {
    "A": "N2",
    "B": "N2",
    "C": "N3_degraded",
    "D": "TERMINAL_01"
  }
}
```

A typical scenario contains 6 decision nodes with 4 options each. Option A is always the preferred action. B, C, and D represent distinct failure modes.

---

## Failure Mode Taxonomy

ANOR uses a structured taxonomy to classify decision errors. Each failure mode maps to a category of human factors breakdown observed in real incident investigations.

| Code | Name | Description |
|------|------|-------------|
| FAIL-05 | Expert Exclusion | Proceeding without consulting the appropriate domain expert |
| FAIL-06 | Procedural Deficiency | Deviating from or bypassing established procedure |
| FAIL-07 | Instrument Over-Reliance | Trusting instrument readings over direct observation or expert judgment |
| FAIL-08 | MOC Deflection | Using Management of Change process as a delay or avoidance mechanism |
| FAIL-09 | Field Exposure Escalation | Unnecessarily exposing personnel to hazardous conditions |

Scenarios may activate multiple failure codes in a single run. The terminal outcome label reflects the dominant failure mode.

---

## Running a Scenario

```bash
python sim/mandos_sim.py --scenario path/to/scenario.json --model gpt-4o
```

ANOR supports any model accessible via API. Results are written to `outputs/` as structured JSON and rendered as a human-readable report.

### Output Structure

```
outputs/
  run_<id>/
    raw_responses.json
    scored_trace.json
    report.md
```

The report includes: overall pass/fail, per-node choices, failure codes triggered, and terminal outcome if reached.

---

## Scenario Authoring

Scenarios must conform to the ANOR scenario schema. See [`schema/scenario_schema.json`](schema/scenario_schema.json) for the full spec.

Authoring guidelines:

- Part A must be self-contained — the candidate should not need external knowledge to understand the situation
- Each distractor option (B/C/D) must be plausible under time pressure
- Terminal outcomes must be reachable via at least two distinct failure paths
- Evaluator keys are maintained separately and are not committed to this repository

---

## Repository Layout

```
anor/
├── sim/
│   ├── mandos_sim.py     # main runner
│   ├── branch.py         # decision tree traversal
│   └── report.py         # output formatter
├── schema/
│   └── scenario_schema.json
├── examples/
│   └── sample_scenario.json
├── LICENSE
└── README.md
```

---

## License

ANOR engine code is released under the [MIT License](LICENSE).

Scenario content (Part A packets and Part B evaluator keys) is not included in this repository. MANDOS benchmark scenarios are released under CC-BY-NC-4.0. Academic and non-commercial research use is free. Commercial licensing is available — contact [relayforge.tools](https://relayforge.tools).

---

## About

ANOR is developed by [RelayForge](https://relayforge.tools) as part of the MANDOS human factors benchmarking program.

> *ANOR* is Quenya for the Sun — it illuminates what was obscured.
