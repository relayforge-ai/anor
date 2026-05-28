# ANOR Sim Engine — v0.1

A Python state machine that runs decision-tree scenarios against AI models. Reads a
screenplay JSON + sanitization map, presents each node to a model under test,
classifies responses against the screenplay's available actions, advances state,
and writes an immutable run log.

## What it does

1. **Schema-validates** the screenplay. Refuses to run if required keys are missing. Does not patch — returns to author.
2. **Sanitizes** every output boundary: facility name, person names, dates, regulator names → generic role labels and relative time.
3. **Maintains conversation memory** across nodes. The operator model accumulates context — at T+33 it remembers what it did at T+0.
4. **Classifies** each response into exact / partial / novel / no_action using an LLM classifier (temperature 0, reasoning logged verbatim).
5. **Branches** on classification: optimal action → prevention path; anything else → continuation path. Novel actions are assessed for trajectory.
6. **Bypasses sanitization** for the `historical_outcome` terminal message only — Pillar 4 (Memorial Obligation). Victim names appear there and only there.
7. **Writes a run log** with file naming `{scenario_id}-{model_shortname}-{date}-{seq}.json`.
8. **Scores post-hoc** against the rubric (separate pass; can be re-run on a saved log via `--score-only`).

## Install

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...    # for the operator model under test
export XAI_API_KEY=xai-...             # for the Grok classifier + scorer
```

The default `run-config.json` runs Claude as the operator and **Grok as
the classifier and scorer**. This is deliberate: a Claude classifier
evaluating a Claude operator has a shared-training-data bias. Spreading the
work across model families means nobody can lie too much in one direction.

To run a different setup (e.g. all-Claude during dev, or Grok-as-operator,
or three different families across operator/classifier/scorer), edit the
config fields — `model_provider` / `classifier_provider` / `scorer_provider`.
Each can independently be `anthropic` or `openai_compatible`. The
`openai_compatible` setting works with xAI, OpenAI, OpenRouter, Together,
local llama.cpp, anything that speaks the OpenAI chat completions schema.

## Run

```bash
# Standard run against the live API
python mandos_sim.py \
    --screenplay your-scenario-screenplay.json \
    --map        your-scenario-sanitization-map.json \
    --config     run-config.json

# Mock mode — exercises the state machine without API calls, picks optimal at each node
python mandos_sim.py --screenplay ... --map ... --config ... --mock

# Skip the post-hoc scoring pass
python mandos_sim.py ... --no-score

# Re-score a saved run log (no re-run, no operator API calls)
python mandos_sim.py --screenplay your-scenario.json --score-only runs/your-run.json
```

## Tests

End-to-end tests require a scenario file (screenplay JSON + sanitization map). A
small synthetic test scenario (3 nodes, no real incident data) is on the roadmap —
see *Next likely work* below.

## Honest caveats (read these)

**1. The classifier and scorer use a DIFFERENT model family than the operator
by default.** Default config: operator = Claude (Anthropic), classifier +
scorer = Grok (xAI). This is intentional — using a Claude classifier on
a Claude operator creates a shared-training-data bias risk. Grok has a
different training lineage and rhetorical priors, so its judgments are less
likely to be sympathetic to a Claude operator's specific failure modes.

This is novel methodology. Treat early results as *interesting but not yet
validated* until you've:
  - Spot-checked a sample of classifications by hand (the
    `classifier_reasoning` field on every node trace is logged verbatim)
  - Run the same scenario with the classifier provider swapped (Anthropic
    classifier vs. Grok classifier) and compared whether outcomes differ
  - Optionally introduced a third family (OpenAI) and looked at
    three-way agreement

If two of three classifiers agree on a classification, that's a stronger
signal than any single classifier alone. Eventually this is the right way
to use the abstraction — the engine is already structured for it.

**2. Post-hoc rubric scoring is also LLM-evaluated.** Same caveat. Fail-mode
triggers in the rubric are written in prose and require semantic evaluation.
A human review of the first ~5 runs is the right way to calibrate.

**3. Novel-action trajectory assessment is a second LLM call.** When the
operator does something not in `actions_available`, the engine asks the
classifier whether the novel action leads toward prevention, continuation, or
escalation. Logged in `novel_actions[].assessment.reasoning`. This is the
piece most likely to need human spot-checking on edge cases.

**4. Terminal-condition triggers are not evaluated programmatically.** The
engine uses the screenplay's `if_optimal_next_node` / `if_actual_next_node`
fields and terminal marker strings (PREVENTED, PARTIAL_MITIGATION,
HISTORICAL_OUTCOME, ESCALATION) for routing. The prose `trigger` fields in
`terminal_conditions` are descriptive, not executable.

**5. State accumulation is shallow merge.** `state_change` dicts are merged
into `world_state` with `dict.update()`. Nested state would need a deep
merge.

**6. The engine logs the sanitized prompt at each node** (in
`sanitized_prompts[]`). This is intentional — it lets you verify after the
fact that no identifier leaked to the model. The master source for any
scenario should never be committed to a public repository.

## File-by-file

| File | What |
|------|------|
| `mandos_sim.py` | The engine. Single file, sectioned for readability. |
| `run-config.example.json` | Template config. Copy to `run-config.json` and edit. |
| `requirements.txt` | `anthropic>=0.40.0` — that's it. |
| `configs/` | Pre-built configs for common model combinations. |

## Next likely work (not built)

- Multi-run loop with temperature sweep for variance characterization
- Aggregate benchmark log builder
- Deep-merge `state_change` for scenarios that need nested state
- A small synthetic test scenario (3 nodes) that lets you exercise the engine without a real screenplay

---

*ANOR — decision-tree scenario simulator*
*The sim engine is the sanitization layer. Physics is never sanitized.*
*Names are never shown before the terminal condition.*
