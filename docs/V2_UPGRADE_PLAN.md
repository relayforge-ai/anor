# ANOR V2 Upgrade Plan

Created from the 2026-06-12 continuous improvement audit.

## Current verified state

- ANOR is the decision-tree scenario simulator runtime for MANDOS-style high-stakes reasoning evaluations.
- The public repo intentionally excludes evaluator keys and real scenario content.
- `sim/mandos_sim.py` supports screenplay validation, sanitization, mock-mode traversal, classifier/scorer provider separation, and immutable run logs.
- Before this audit pass, the repo had no in-repo tests, no GitHub Actions workflow, and no V2 upgrade plan.

## Linear tracking

- Portfolio parent: not linked in this repair pass.
- ANOR V2 follow-up: not created in this repair pass.

## V2 scope

1. Keep evaluator keys and real incident content out of the public runtime repo unless licensing and source-hygiene rules explicitly allow release.
2. Require CI for dependency install, syntax checks, synthetic screenplay validation, sanitizer behavior, mock engine traversal, and dependency consistency.
3. Add schema fixtures for scenario packets, sanitization maps, run logs, and reports.
4. Document evaluator-model separation, variance runs, human adjudication, and report limitations before publishing comparative benchmark claims.
5. Add safe sample scenarios that exercise branching without exposing real incident or proprietary evaluator content.

## Done means

- Default branch has a green simulator CI gate.
- Runtime changes cannot break sanitization, schema validation, or mock traversal silently.
- Public docs clearly separate candidate packets, evaluator keys, and MANDOS benchmark content.
- Benchmark claims remain provenance-backed and caveated.
