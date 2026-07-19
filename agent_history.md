# Agent history — Forked History / ANOR hardening loop

## Iteration 1 — 2026-07-18

### OBSERVE
Architecture:
- `webapp/` — stdlib HTTP SPA server (catalog, scenarios, fork, media)
- `pipeline/` — fork engine, video render, env-based LLM/IMAGE/TTS
- `scenarios/public/` — ELO decision packs
- `sim/` — industrial sim engine (separate)

High-risk gaps on product surface:
- `/api/fork` had **no rate limiting** (LLM cost / GPU drain / DoS)
- **no body size cap**, weak `custom_seed` handling
- `load_scenario()` accepted arbitrary filesystem paths (path read risk)
- scenario GET ids not format-validated

### PLAN
**One high-impact change:** harden `/api/fork` + scenario loading — rate limits, input validation/sanitization, path-safe pack loading.

Expected outcome: abuse of fork/LLM endpoints returns 429/400 cleanly; traversal ids cannot leave `scenarios/public/`.

### EXECUTE
- Added `webapp/security.py` (sliding-window rate limiter, validators, seed sanitizer; env-tunable)
- Updated `webapp/server.py` to enforce limits on POST `/api/fork` and GET `/api/scenario/:id`
- Hardened `pipeline/fork_engine.load_scenario` to id-only under public dir
- Tests: `webapp/tests/test_security.py`

### TEST
```
python3 -m unittest webapp.tests.test_security webapp.tests.test_webapp pipeline.tests.test_pipeline -v
→ 21 tests OK
```
- Validation rejects `../` scenario ids (400)
- Path traversal on GET `/api/scenario/` blocked (400)
- Rate limiter returns 429 after window budget
- Happy-path fork still 200
- Existing pipeline tests green

### RESULT
Security baseline for the product API is in place. Next iterations can target async video jobs, UI progress feedback, or dependency audit.

---

## Iteration 2 — 2026-07-18

### OBSERVE
After iter 1, `/api/fork` is rate-limited and validated. Remaining reliability gap: `pipeline/clients.py` treated every upstream LLM/IMAGE/TTS failure as terminal — no backoff for 429/5xx/connection blips common on local GPU boxes (Dawes/Nauvoo warm-up).

### PLAN
**One high-impact change:** exponential-backoff retries for all pipeline HTTP calls.

Expected outcome: transient 429/502/503/URLError recover without failing the fork/video job; permanent 4xx still fail fast.

### EXECUTE
- `with_exponential_backoff()` + richer `PipelineError` (`retryable`, `status_code`, `attempts`)
- Wired into `_request_json` / `_request_bytes` (covers LLM, image, TTS HTTP paths)
- Env: `ANOR_HTTP_RETRIES`, `ANOR_HTTP_RETRY_BASE`, `ANOR_HTTP_RETRY_MAX`, `ANOR_HTTP_RETRY_JITTER`
- Tests: `pipeline/tests/test_retry.py`
- Documented knobs in `.env.example`; exposed policy via `/api/health` → `http_retry`

### TEST
```
python3 -m unittest pipeline.tests.test_retry pipeline.tests.test_pipeline \
  webapp.tests.test_security webapp.tests.test_webapp -v
→ 26 tests OK
```
- First-try success, flaky→ok, 400 no-retry, 429 exhausts budget, PipelineError retryable flag

### RESULT
Upstream media/LLM calls are resilient to brief outages without masking real validation errors.
