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

---

## Iteration 3 — 2026-07-18

### OBSERVE
Backend security + HTTP retries landed. Studio UX still showed a flat "Simulating fork…" note during potentially multi-second LLM calls — no progress, no skeleton on pack load, weak error presentation, limited a11y live updates.

### PLAN
**One high-impact change:** immersive, accessible progress feedback for studio fork + pack loading.

Expected outcome: users see staged progress (validate → ledger → branch → ribbon), skeleton while packs load, structured errors with codes, reduced-motion respect.

### EXECUTE
- CSS: `.sim-progress`, stages, skeleton shimmer, `.fork-error`, `.btn.busy`, `prefers-reduced-motion`
- JS: `renderSimProgress`, `forkStages`, `renderSkeletonStudio`, staged timers during fetch, better 429/error handling
- HTML: `aria-live="polite"` on `#fork-result`
- Tests: `webapp/tests/test_static_assets.py`

### TEST
```
python3 -m unittest webapp.tests.test_static_assets pipeline.tests.test_retry \
  pipeline.tests.test_pipeline webapp.tests.test_security webapp.tests.test_webapp -v
→ 29 tests OK
```
- CSS/JS/HTML markers for progress, skeleton, aria-live present
- Prior security + retry + pipeline suites green

### RESULT
Studio now communicates work-in-progress for forks and pack loads; errors surface with codes. Next: async video job queue or dependency audit.

---

## Iteration 4 — 2026-07-18

### OBSERVE
Video renders are multi-second (TTS + stills + ffmpeg) and would block any synchronous HTTP handler. No queue existed — only CLI `pipeline.cli video`. Studio could not kick off a render without freezing the browser request.

### PLAN
**One high-impact change:** in-process async video job queue with progress polling.

Expected outcome: `POST /api/video/jobs` returns 202 immediately; clients poll status/pct/stage; worker runs `render_video` with progress callbacks; rate-limited.

### EXECUTE
- `webapp/jobs.py` — ThreadPool queue, TTL purge, public job DTO
- `render_video(..., on_progress=)` progress hooks
- API: POST/GET `/api/video/jobs`, GET `/api/video/jobs/{id}`
- Rate limit `ANOR_VIDEO_RATE_LIMIT` (default 3 / 5 min)
- Studio: **Queue video render** (Scholar) with live progress + player on complete
- Tests: `webapp/tests/test_video_jobs.py`

### TEST
```
python3 -m unittest webapp.tests.test_video_jobs webapp.tests.test_static_assets \
  pipeline.tests.test_retry pipeline.tests.test_pipeline \
  webapp.tests.test_security webapp.tests.test_webapp -v
→ 33 tests OK
```
- Enqueue returns 202; poll reaches completed with media_url
- Bad scenario rejected; health exposes queue stats
- Full regression green

### RESULT
Long video renders no longer block HTTP. Studio can queue + poll with real pipeline progress.

---

## Iteration 5 — 2026-07-18

### OBSERVE
API hardening and video queue exist, but responses lacked a full browser security header set (only nosniff). CI ran a thin subset of tests and had no dependency vulnerability scan. Google Fonts require a deliberate CSP allowlist.

### PLAN
**One high-impact change:** security response headers + automated dependency audit in CI.

Expected outcome: every response carries CSP/frame/referrer/permissions policies; `scripts/dep_audit.py` checks pins and runs pip-audit; CI covers full webapp/pipeline suite.

### EXECUTE
- `security_headers()` in `webapp/security.py`; applied on all responses
- `scripts/dep_audit.py` — pin audit + optional pip-audit
- CI expanded: full unittest set + dep_audit + pip-audit
- Tests: `webapp/tests/test_security_headers.py`, `scripts/tests/test_dep_audit.py`

### TEST
```
python3 -m unittest webapp.tests.test_security_headers webapp.tests.test_video_jobs \
  webapp.tests.test_static_assets webapp.tests.test_security webapp.tests.test_webapp \
  pipeline.tests.test_retry pipeline.tests.test_pipeline -v
→ 36 tests OK
python3 scripts/dep_audit.py → OK (0 loose pins)
python3 scripts/tests/test_dep_audit.py → 3 OK
```
- HTML/JSON responses include CSP, X-Frame-Options DENY, nosniff, Referrer-Policy
- sim deps now have upper bounds

### RESULT
Browser-facing surface hardened; dependency drift is audited in CI.

---

## Iteration 6 — 2026-07-18

### OBSERVE
Mobile CSS hid all non-button nav links (`display: none`), so phones only saw Scholar CTA — Home/Library/Studio unreachable. Weak keyboard support on decision choices; no skip link or focus-visible styling. Video job results still included absolute `out_mp4` paths.

### PLAN
**One high-impact change:** fix mobile navigation and accessibility (keyboard + focus + skip link); stop leaking absolute paths in job payloads.

Expected outcome: usable drawer nav under 900px; arrow-key choice radios; visible focus rings; job API returns only `media_url`.

### EXECUTE
- Mobile hamburger + drawer + backdrop; Escape/resize close
- Skip link, `:focus-visible`, radiogroup keyboard for choices
- Strip absolute paths from video job results
- Tests extended in `test_static_assets` + `test_video_jobs`

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_video_jobs \
  webapp.tests.test_security_headers webapp.tests.test_security webapp.tests.test_webapp \
  pipeline.tests.test_retry pipeline.tests.test_pipeline -v
→ 37 tests OK
```
- Static checks for skip-link, nav-toggle, focus-visible, keyboard handlers
- Video job payload has media_url only (no absolute paths)

### RESULT
Mobile users can reach all primary routes; keyboard and screen-reader paths improved; job API no longer leaks host filesystem paths.

---

## Iteration 7 — 2026-07-18

### OBSERVE
Scenario packs were loaded with JSON parse only — no structural validation. `list_scenarios` exposed absolute `path` fields; `/api/health` leaked `videos_dir` absolute path. Corrupt packs could crash the studio mid-fork.

### PLAN
**One high-impact change:** validate public pack structure on load + remove remaining path leaks from public APIs.

Expected outcome: invalid packs rejected with clear errors; catalog/health never return host filesystem paths; all three ELO packs still pass.

### EXECUTE
- `pipeline/validate.py` — stdlib schema checks (required fields, one historical choice, speculation levels)
- `load_scenario` / `list_scenarios` validate; list skips invalid packs; no `path` field
- Health: `videos_count` / `scenarios_count` instead of absolute dirs
- API maps `ScenarioValidationError` → 422
- Tests: `pipeline/tests/test_validate.py`

### TEST
```
python3 -m unittest pipeline.tests.test_validate pipeline.tests.test_pipeline \
  pipeline.tests.test_retry webapp.tests.test_security_headers \
  webapp.tests.test_security webapp.tests.test_webapp \
  webapp.tests.test_static_assets webapp.tests.test_video_jobs -v
→ 46 tests OK
```
- Real packs validate; corrupt packs rejected
- list/health free of host absolute paths

### RESULT
Scenario state is structurally trustworthy at the boundary; remaining path-leak surfaces cleaned.
