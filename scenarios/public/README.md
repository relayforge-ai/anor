# Public scenario packets

These packets are **shareable** decision-point scenarios for the interactive fork
site and the video pipeline. They draw only from ELOSTIRION public canon framing:

- Real historical decision points
- Documented baseline (what actually happened)
- Explicit speculation labels for counterfactual branches
- Provenance tags: `documented` | `dramatized` | `simulated`

They are **not** MANDOS master sources, evaluator keys, or internal industrial
screenplays. Do not add master-source material here.

## Schema

See `schema/fork_scenario.schema.json`.

## Packs

| ID | Title | Era | Decision |
|----|-------|-----|----------|
| ELO-003 | Hannibal after Cannae | 216 BC | March on Rome? |
| ELO-004 | Caesar at the Rubicon | 49 BC | Cross with the army or stand down? |
| ELO-009 | Dunkirk — the halt that bought a fleet | 1940 | Press armor or halt? |
| ELO-001 | Stalin's dacha, Barbarossa | 1941 | Accept the invasion reports? |
| ELO-007 | EXCOMM — quarantine or strike? | 1962 | Naval quarantine vs airstrike/invasion? |
| ELO-013 | Arkhipov on B-59 | 1962 | Authorize nuclear torpedo? |

Each pack is self-contained JSON suitable for offline browsing and for LLM-driven
fork generation when `LLM_URL` is configured.
