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

---

## Iteration 8 — 2026-07-18

### OBSERVE
Media handler loaded entire files with `read_bytes()` — memory-hostile for growing MP4s. Path checks used string `startswith` only. Catalog trusted `file` fields without safe-join when probing availability.

### PLAN
**One high-impact change:** stream media with Range support + centralized safe path join for static/media/catalog.

Expected outcome: range requests stream 64KiB chunks; traversal URLs get 403; catalog only marks available when path is under videos root.

### EXECUTE
- `webapp/paths.py` — `safe_join()`
- `_stream_file` / `_media_file` with Range + chunked read
- Catalog availability via safe_join
- Tests: `webapp/tests/test_paths_and_media.py`

### TEST
```
python3 -m unittest webapp.tests.test_paths_and_media ... (full suite)
→ paths/media OK; range 206; traversal 403
```

### RESULT
Media serving scales without loading whole files; path join no longer mis-handles `../` via `lstrip`.

---

## Iteration 9 — 2026-07-18

### OBSERVE
Freemium was client-only (`localStorage`). Anyone could `POST /api/video/jobs` or `use_llm=true` without membership. Demo unlock never contacted the server.

### PLAN
**One high-impact change:** HMAC membership tokens + server enforcement on expensive endpoints; demo unlock mints a real token.

Expected outcome: with `ANOR_MEMBER_SECRET` set, video jobs and LLM forks return 401 without `X-ANOR-Member`; basic authored forks remain free; demo endpoint issues signed tokens.

### EXECUTE
- `webapp/membership.py` — issue/verify HMAC tokens
- Gate: video enqueue; fork when `use_llm` or custom seed
- `POST /api/member/demo` (rate-limited)
- Client: `acquireDemoToken`, `authHeaders`
- Tests: `webapp/tests/test_membership.py`

### TEST
```
python3 -m unittest webapp.tests.test_membership webapp.tests.test_video_jobs ... 
→ 47 tests OK
```
- Signed tokens verify; tamper rejected
- Video/LLM without token → 401 when enforced
- Basic authored fork remains free
- Other suites green after env restore

### RESULT
Expensive ops can be server-gated for production; demo unlock mints real tokens the client attaches automatically.

---

## Iteration 10 — 2026-07-18

### OBSERVE
CSS/JS always sent `Cache-Control: no-store` (no ETag). Watch page had no loading/unavailable feedback. Video job polling used a fixed interval, hammering the server during long renders.

### PLAN
**One high-impact change:** ETag + cache for static/media, player loading UX, exponential poll backoff for video jobs.

Expected outcome: conditional 304 for CSS; player shows spinner/errors; poll interval grows 500ms→4s while jobs run.

### EXECUTE
- ETag (size+mtime) + 304; static max-age=3600; media max-age=300
- Player loading overlay + unavailable/error states
- Video job poll backoff
- Tests extended

### TEST
```
python3 -m unittest webapp.tests.test_paths_and_media ... → OK
CSS ETag + 304 verified; full regression green
```

### RESULT
Faster repeat loads for CSS/JS; clearer watch-page feedback; lighter job polling under long renders.

---

## Iteration 11 — 2026-07-18

### OBSERVE
Video jobs could not be cancelled once queued/running (GPU/time waste). Job IDs accepted any path-like string. No request correlation IDs in responses/logs.

### PLAN
**One high-impact change:** cooperative job cancel API + strict job IDs + X-Request-ID tracing.

Expected outcome: DELETE cancels queued immediately and running at next progress tick; bad job ids 400; every response includes X-Request-ID.

### EXECUTE
- `QUEUE.cancel()` + `JobCancelled` cooperative stop in progress callback
- `DELETE /api/video/jobs/{id}` (membership-gated when enforced)
- `validate_job_id` (16 hex)
- `X-Request-ID` generation/echo + log field
- Studio Cancel button while job active

### TEST
```
python3 -m unittest webapp.tests.test_video_jobs ... → OK
```
- Cancel API + strict job ids + X-Request-ID covered

### RESULT
Operators can stop wasteful renders; requests are correlatable in logs via rid=.

---

## Iteration 12 — 2026-07-18

### OBSERVE
Double-clicks / retries on "Queue video render" could spawn multiple workers for the same scenario+choice, wasting GPU. POST endpoints accepted any Content-Type.

### PLAN
**One high-impact change:** idempotent enqueue (dedupe active jobs) + require JSON Content-Type on POST.

Expected outcome: second enqueue while queued/running returns the same job with `deduped: true`; non-JSON Content-Type → 415.

### EXECUTE
- `QUEUE.enqueue` returns `(job, deduped)`; reuses active match
- API adds `deduped` field + `X-Job-Deduped` header
- Content-Type must be application/json when body present
- Tests: `test_job_dedupe.py`, content-type + API dedupe cases

### TEST
```
python3 -m unittest webapp.tests.test_job_dedupe webapp.tests.test_video_jobs \
  webapp.tests.test_security -v
→ OK (dedupe unit + 415 Content-Type + API paths)
```

### RESULT
Duplicate render clicks no longer double-spend GPU; POST bodies must be JSON.

---

## Iteration 13 — 2026-07-19

### OBSERVE
HEAD requests returned 501 (default). Video jobs could enqueue when ffmpeg was missing, only failing mid-pipeline. Library showed playable-looking cards for unavailable media with no empty-state guidance.

### PLAN
**One high-impact change:** HEAD support + ffmpeg preflight + library empty/unavailable UX.

Expected outcome: HEAD returns headers without body; enqueue fails 503 if ffmpeg missing; library explains missing media and points to Studio.

### EXECUTE
- `do_HEAD` reuses GET routing (body skipped)
- `check_render_dependencies()` at enqueue + worker start; health `ffmpeg_ok`
- Library empty state + unavailable card styling/copy
- Tests: HEAD, render deps

### TEST
```
python3 -m unittest webapp.tests.test_render_deps webapp.tests.test_paths_and_media \
  webapp.tests.test_static_assets webapp.tests.test_video_jobs ... → OK
```
- HEAD returns empty body; ffmpeg_ok in queue stats; library empty helpers present

### RESULT
Render fails closed without ffmpeg; browsers can HEAD media; library guides users when files are missing.

---

## Iteration 14 — 2026-07-19

### OBSERVE
Running video jobs had no wall-clock limit — a hung LLM/image/ffmpeg path could hold the single worker indefinitely. After a successful render, the library catalog was not refreshed so `available` stayed false until reload.

### PLAN
**One high-impact change:** per-job wall-clock timeout (cooperative via progress ticks) + refresh catalog after successful render.

Expected outcome: jobs exceed `ANOR_VIDEO_JOB_TIMEOUT_S` → `timed_out`; studio shows timeout error; library updates after complete.

### EXECUTE
- `JobTimedOut` + `deadline_at` checked in progress callback
- Status `timed_out` / stage `timeout`
- Client handles timed_out + re-fetches `/api/catalog`
- Tests: `test_job_timeout.py` with setUp/tearDown so short timeout cannot poison process-wide `QUEUE`
- Integration tests force `QUEUE.timeout_s >= 600`

### TEST
```
python3 -m unittest webapp.tests.test_job_timeout webapp.tests.test_job_dedupe \
  webapp.tests.test_render_deps webapp.tests.test_video_jobs -v
→ Ran 16 tests — OK
```
- Worker marks `timed_out` when progress ticks past deadline
- API enqueue completes under default wall-clock (no env leak)
- Dedupe / render-deps still green

### RESULT
Hung renders free the single worker after `ANOR_VIDEO_JOB_TIMEOUT_S` (default 600s). Studio surfaces timeout; library catalog refreshes after successful render.

---

## Iteration 15 — 2026-07-19

### OBSERVE
Long video renders survive page refresh on the server, but the studio UI lost poll state — users returned to a blank ledger with no progress. Queued jobs also showed no place-in-line, so with `max_concurrent=1` wait time was opaque.

### PLAN
**One high-impact change:** resume in-flight video job polling after refresh (sessionStorage) + expose `queue_position` / `jobs_ahead` on job APIs for studio feedback.

Expected outcome: refresh mid-render reconnects to the same job; progress label shows “next in line” or “N ahead”.

### EXECUTE
- `VideoJobQueue.to_public_enriched()` adds queue meta
- All job JSON responses (GET/list/POST/DELETE) use enriched payload
- Studio: `fh:activeVideoJob` sessionStorage, `pollVideoJob` / `tryResumeVideoJob`, queue-aware labels
- Tests: `test_queue_position.py`; static asset markers

### TEST
```
python3 -m unittest webapp.tests.test_queue_position webapp.tests.test_job_timeout \
  webapp.tests.test_job_dedupe webapp.tests.test_video_jobs webapp.tests.test_static_assets -v
→ Ran 18 tests — OK
```
- Running job: queue_position=0; second queued: position=1, jobs_ahead=0; third: ahead=1
- Terminal jobs: position null
- JS markers for resume + jobs_ahead present

### RESULT
Scholars can leave and return during a render without losing status; queue wait is visible instead of indeterminate silence.

---

## Iteration 16 — 2026-07-19

### OBSERVE
Media Range parsing treated suffix ranges (`bytes=-N`) as start=0/end=N (wrong slice) and fell back to full-file 200 on unsatisfiable/malformed ranges instead of 416 — bad for HTML5 video seeking and bandwidth.

### PLAN
**One high-impact change:** RFC 7233-correct single-range parsing with 416 + Content-Range `bytes */size`.

Expected outcome: closed/open/suffix ranges return 206 with correct bytes; past-EOF ranges return 416.

### EXECUTE
- `webapp/http_range.py` — `parse_byte_range()` (closed, open-ended, suffix, multi takes first)
- `_stream_file` uses parser; 416 path with no body
- Tests: `test_http_range.py` unit + integration

### TEST
```
python3 -m unittest webapp.tests.test_http_range webapp.tests.test_paths_and_media -v
→ Ran 21 tests — OK
```
- `bytes=-8` returns last 8 bytes (206)
- `bytes=999999999-` → 416 with `Content-Range: bytes */size`
- Existing range/ETag/HEAD media tests still green

### RESULT
Video players can seek reliably; unsatisfiable ranges fail closed without dumping the full MP4.

---

## Iteration 17 — 2026-07-19

### OBSERVE
Video enqueue checked ffmpeg but not free disk. Renders write stills, segment clips, and final MP4 under `outputs/` — a near-full volume fails mid-pipeline after GPU work. Health did not expose free space for operators.

### PLAN
**One high-impact change:** fail closed on insufficient free disk before enqueue (and at worker start), with health stats for free MB.

Expected outcome: enqueue returns 503 `insufficient_disk` when free space under `outputs/` is below `ANOR_MIN_FREE_DISK_MB` (default 512); health reports `disk_ok` / `disk_free_mb`.

### EXECUTE
- `check_disk_space()` + split `check_ffmpeg()` from combined `check_render_dependencies()`
- Queue stats: `disk_ok`, `disk_free_mb`, `min_free_disk_mb`
- Enqueue maps disk failures to code `insufficient_disk`
- Env: `ANOR_MIN_FREE_DISK_MB` (0 disables)
- Tests: low-disk mock, disable-with-zero, stats fields

### TEST
```
python3 -m unittest webapp.tests.test_render_deps webapp.tests.test_video_jobs \
  webapp.tests.test_job_timeout -v
→ Ran 16 tests — OK
```
- 10MB free mocked → insufficient disk
- ANOR_MIN_FREE_DISK_MB=0 → check disabled
- Video job enqueue/complete still green

### RESULT
Renders refuse to start when the volume cannot hold intermediates; operators can monitor free space via `/api/health` queue stats.

---

## Iteration 18 — 2026-07-19

### OBSERVE
When image backends return a download URL (instead of b64), the pipeline fetched it with unrestricted `urlopen` — any scheme, redirects, cloud metadata hosts, and unbounded body size (SSRF / OOM risk from untrusted secondary URLs).

### PLAN
**One high-impact change:** harden secondary media fetches (scheme allowlist, block metadata hosts, no redirects, size cap).

Expected outcome: `file://` / metadata / oversized responses rejected; OpenAI-style image URL path and Comfy view use safe GET.

### EXECUTE
- `pipeline/safe_fetch.py` — `validate_http_url`, `safe_get_bytes`, `read_response_limited`, no-redirect opener
- ImageClient URL path + Comfy view use `safe_get_bytes`
- Filename query params URL-encoded for Comfy view
- Env: `ANOR_MAX_MEDIA_BYTES` (default 25MiB)
- Tests: `pipeline.tests.test_safe_fetch`

### TEST
```
python3 -m unittest pipeline.tests.test_safe_fetch pipeline.tests.test_retry \
  pipeline.tests.test_pipeline -v
→ Ran 29 tests — OK
```
- file:// and 169.254.169.254 rejected from image API response
- Content-Length / stream over limit raise
- Mock video render + fork tests still green

### RESULT
Secondary media downloads cannot pivot to local files or cloud metadata, and cannot OOM the worker via huge bodies.

---

## Iteration 19 — 2026-07-19

### OBSERVE
Successful video renders left full `work/` trees (stills, VO audio, per-segment MP4s) plus concat `.txt` lists — ~8MB intermediates per branch while only the final MP4 is served. `build.json` also stored absolute host paths.

### PLAN
**One high-impact change:** delete intermediate work files after successful concat (opt-out via env); store relative names only in build.json.

Expected outcome: default render leaves mp4 + script.md + build.json; disk reclaimed; no absolute paths in meta.

### EXECUTE
- `cleanup_video_work()` + `ANOR_KEEP_VIDEO_WORK` opt-out
- Post-concat cleanup of `work/` and concat list file
- Segment meta / out_mp4 recorded as basenames
- Tests: cleaned by default; keep when flagged; no path leaks

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline webapp.tests.test_video_jobs -v
→ Ran 17 tests — OK
```
- work/ absent after success; present with ANOR_KEEP_VIDEO_WORK=1
- build.json has no absolute paths
- Async video job complete still green

### RESULT
Each successful render reclaims intermediate disk; debug keep flag remains for operators.

---

## Iteration 20 — 2026-07-19

### OBSERVE
Studio lost fork narratives on refresh (export/compare disabled until re-run). Rate-limit 429 responses sent `Retry-After` but the UI showed a generic error with no countdown or retry path — poor freemium feedback under limits.

### PLAN
**One high-impact change:** persist last fork in sessionStorage + rate-limit UX (Retry-After countdown and Try again).

Expected outcome: refresh restores last fork for the same scenario; 429 shows wait timer then enables retry for fork/video.

### EXECUTE
- `fh:lastFork` save/load/clear; restore on studio entry; clear on scenario change
- `parseRetryAfter` + `bindRateLimitRetry` + rate-limit styling
- Fork and video enqueue catch paths wire countdown + retry
- Static asset markers for new helpers/CSS

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_security \
  webapp.tests.test_webapp -v
→ Ran 18 tests — OK
```
- JS contains `fh:lastFork`, `parseRetryAfter`, `bindRateLimitRetry`
- CSS has `.fork-error.is-rate-limit` and `.rate-wait`
- Security rate-limit + fork happy path still green

### RESULT
Explorers keep fork results across refresh; rate limits are actionable instead of dead-end errors.

---

## Iteration 21 — 2026-07-19

### OBSERVE
Expensive POSTs (fork/video/demo) were rate-limited, but all other `/api/*` GETs (catalog, scenarios, job polls) were unlimited — a single client could scrape or flood cheaply. Health probes needed to stay unrestricted.

### PLAN
**One high-impact change:** global per-client API rate limit for `/api/*` with `/api/health` exempt.

Expected outcome: excess API traffic returns 429 `api_rate_limited` + Retry-After; health always 200; defaults 180 req / 60s.

### EXECUTE
- `API_LIMITER` + `check_api_rate` / `api_rate_exempt` in `security.py`
- `_enforce_api_rate` on GET/POST/DELETE for `/api/*`
- Health exposes `api_rate_limit` / `api_rate_window_s`
- Env: `ANOR_API_RATE_LIMIT` / `ANOR_API_RATE_WINDOW`
- Tests: catalog flood, health exempt, unit helpers; video jobs use generous limiter

### TEST
```
python3 -m unittest webapp.tests.test_security webapp.tests.test_video_jobs -v
→ Ran 21 tests — OK
```
- Catalog trips 429 with `api_rate_limited` + Retry-After
- Health still 200 after API budget exhausted
- Job poll suite not poisoned by global ceiling

### RESULT
Scrape/flood of catalog and poll endpoints is capped without breaking operator health checks.

---

## Iteration 22 — 2026-07-19

### OBSERVE
Successful renders cleaned `work/`, but failed / cancelled / timed-out jobs left stills, VO audio, and partial clips on disk — wasting space and fighting the free-disk preflight.

### PLAN
**One high-impact change:** always clean intermediate work on non-success (unless `ANOR_KEEP_VIDEO_WORK`).

Expected outcome: mid-pipeline failure removes `work/` and concat list; keep-flag still retains intermediates for debug.

### EXECUTE
- `render_video` try/finally: on failure path call `cleanup_video_work`
- Test: mock ffmpeg failure → work/ absent

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline.TestVideoPipeline -v
→ Ran 4 tests — OK
```
- Failed render cleans work/
- Success still cleans; KEEP flag still retains

### RESULT
Failed renders no longer accumulate multi-MB debris under `outputs/videos/`.

---

## Iteration 23 — 2026-07-19

### OBSERVE
Scholar paywall dialog was a visual overlay only: no focus trap, Escape closed the nav instead of the modal, no `aria-labelledby`/`describedby`, focus was not restored, and background could still scroll — poor accessibility for freemium upgrade flows.

### PLAN
**One high-impact change:** accessible paywall dialog (focus trap, Escape, labels, restore focus, body scroll lock).

Expected outcome: keyboard users stay inside the modal until dismiss; screen readers get dialog labels; focus returns to the opener.

### EXECUTE
- `openPaywall` / `closePaywall` with focus trap, Escape (capture), restore focus
- `hidden` + `aria-labelledby` / `aria-describedby` on dialog
- `body.modal-open` overflow lock; backdrop click to dismiss
- Static asset tests for paywall a11y markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 9 tests — OK
```
- HTML dialog attributes present
- JS focus trap / Escape / restore markers present
- Index/catalog still green

### RESULT
Paywall upgrade flow is keyboard- and screen-reader-usable without trapping background interaction.

---

## Iteration 24 — 2026-07-19

### OBSERVE
`client_key` always trusted `X-Forwarded-For`, so any client could spoof a new IP per request and bypass all rate limiters. Unsupported verbs (PUT/PATCH/TRACE) returned vague 501s without `Allow`.

### PLAN
**One high-impact change:** only honor proxy client headers when `ANOR_TRUST_PROXY` is set; return 405 + Allow for unsupported methods.

Expected outcome: spoofed XFF cannot reset rate buckets by default; PUT/PATCH return 405 with Allow.

### EXECUTE
- `trust_proxy()` + hardened `client_key()` (XFF / X-Real-IP only when trusted)
- `do_PUT`/`PATCH`/`TRACE`/`CONNECT` → 405 `method_not_allowed`
- Health exposes `trust_proxy`
- Tests: XFF ignored by default; spoof cannot bypass; 405 + Allow

### TEST
```
python3 -m unittest webapp.tests.test_security -v
→ Ran 19 tests — OK
```
- Default client_key uses TCP peer despite XFF
- Spoofed XFF still hits global API 429
- PUT → 405 with Allow header

### RESULT
Rate limits bind to real peers unless operators explicitly trust a reverse proxy; HTTP method surface is explicit.

---

## Iteration 25 — 2026-07-19

### OBSERVE
`GET /api/video/jobs` returned the last 30 jobs for *all* clients — scenario choices, errors, and job ids leaked across tenants. The SPA only polls by job id, so a global list was unnecessary.

### PLAN
**One high-impact change:** scope job listing to the requesting client (`owner_key` at enqueue).

Expected outcome: list returns only the caller's jobs; `owner_key` never appears in public JSON.

### EXECUTE
- `VideoJob.owner_key` (internal) + `enqueue(..., owner_key=)`
- `list_for_owner()` for privacy-scoped listing
- GET list uses `client_key`; response includes `scoped: true`
- Tests: unit privacy filter + API list contains own job only

### TEST
```
python3 -m unittest webapp.tests.test_job_privacy \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_enqueue_and_complete \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_list_jobs_scoped_to_client -v
→ Ran 4 tests — OK
```
- client-a list excludes client-b jobs
- to_public omits owner_key
- API list includes own enqueued job; `scoped` true

### RESULT
Video job inventory is no longer a cross-tenant leak; clients still poll by id from the enqueue response.

---

## Iteration 26 — 2026-07-19

### OBSERVE
Concurrent writers for the same `scenario_id-choice_id` output dir could interleave stills/clips/concat (tests and multi-worker hosts), producing corrupt MP4s and flaky ffmpeg exit 254.

### PLAN
**One high-impact change:** exclusive render lock per output directory (fcntl cross-process + in-process lock).

Expected outcome: second writer fails fast with `RenderLockBusy`; first writer holds lock until complete/fail.

### EXECUTE
- `acquire_render_lock` / `release_render_lock` / `RenderLockBusy`
- Worker acquires lock before `render_video`, releases in `finally`
- Tests: second acquire busy; independent dirs OK

### TEST
```
python3 -m unittest webapp.tests.test_render_lock \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_enqueue_and_complete \
  webapp.tests.test_job_timeout -v
→ Ran 6 tests — OK
```
- Double lock → RenderLockBusy
- Full enqueue→complete still green

### RESULT
Same-path renders cannot corrupt each other's intermediates or final MP4.

---

## Iteration 27 — 2026-07-19

### OBSERVE
Video jobs already exposed `started_at` and `deadline_at`, but the studio progress label never showed elapsed time or remaining wall-clock budget — long renders (up to 600s) felt stuck.

### PLAN
**One high-impact change:** surface elapsed + remaining time in the studio progress label during queue/run.

Expected outcome: running jobs show “elapsed Xm · Ys left”; queued jobs show wait age.

### EXECUTE
- `formatDuration` + `jobTimeSuffix` in app.js
- `jobProgressLabel` appends time suffix
- Static asset markers for helpers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 5 tests — OK
```
- JS contains formatDuration, jobTimeSuffix, deadline_at, elapsed

### RESULT
Scholars can see how long a render has run and how much wall-clock budget remains.

---

## Iteration 28 — 2026-07-19

### OBSERVE
Job list was scoped to the caller, but `GET`/`DELETE` by job id still returned or cancelled any job for anyone who knew the id (IDOR) — status, errors, and cancel control leaked across clients.

### PLAN
**One high-impact change:** enforce `owner_key` on job get and cancel; return 404 on mismatch (no existence oracle).

Expected outcome: foreign job ids look not-found; same-client poll/cancel still work.

### EXECUTE
- `VideoJobQueue.visible_to(job, owner_key)`
- GET and DELETE check ownership before public payload / cancel
- Unit tests for visibility rules

### TEST
```
python3 -m unittest webapp.tests.test_job_privacy \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_enqueue_and_complete \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_cancel_queued_or_running_job \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_list_jobs_scoped_to_client -v
→ Ran 6 tests — OK
```
- owner-only visibility unit cases
- Same-client enqueue/poll/cancel green

### RESULT
Knowing a job id is no longer enough to read or cancel another client's render.

---

## Iteration 29 — 2026-07-19

### OBSERVE
Public `/api/health` (rate-limit exempt) returned full security limits, pipeline endpoint config, and video inventory — free reconnaissance for attackers and scrapers.

### PLAN
**One high-impact change:** slim public health (readiness only); full detail via `ANOR_HEALTH_DETAIL` or `X-ANOR-Health-Token`.

Expected outcome: default health has site/version/ready/ffmpeg_ok/disk_ok only; operators unlock detail explicitly.

### EXECUTE
- `_health_payload` + `_health_detail_authorized` (hmac token compare)
- Env: `ANOR_HEALTH_DETAIL`, `ANOR_HEALTH_TOKEN`
- Tests: slim public, detail flag, token header; updated consumers

### TEST
```
python3 -m unittest webapp.tests.test_health_privacy webapp.tests.test_security_headers \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_health_includes_queue \
  webapp.tests.test_security.TestForkEndpointSecurity.test_health_exempt_from_global_api_limit -v
→ Ran 8 tests — OK
```
- Public omits security/pipeline/videos_present
- Detail with env or correct token

### RESULT
Health probes stay cheap and available without advertising rate limits or fleet inventory.

---

## Iteration 30 — 2026-07-19

### OBSERVE
SPA boot only toasted on catalog failure — no page-level error, no retry control, and non-OK HTTP responses were still parsed as JSON (opaque failures when the API was down or rate-limited).

### PLAN
**One high-impact change:** robust boot error handling with an accessible full-page error panel and Retry.

Expected outcome: network/HTTP/JSON failures show “Unable to open the ledger” with retry + health link; success path unchanged.

### EXECUTE
- Validate fetch ok + JSON shape in `boot()`
- `showBootError()` with `role="alert"`, retry, health link
- CSS `.boot-error` / `body.boot-failed`
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 9 tests — OK
```
- JS contains showBootError, btn-boot-retry, ledger copy
- Index/catalog still green

### RESULT
Users see a clear recovery path when the site API is unreachable instead of a blank shell and a fleeting toast.

---

## Iteration 31 — 2026-07-19

### OBSERVE
Catalog and scenarios always returned full JSON with `no-store`, so SPA reloads re-downloaded unchanged bodies and burned global API rate budget. `Server` also advertised the CPython version.

### PLAN
**One high-impact change:** weak ETag + short public cache for catalog/scenarios; hide Python version in Server header.

Expected outcome: conditional GET → 304; Server is product token only.

### EXECUTE
- `_json_revalidatable()` for catalog (30s) and scenarios (60s)
- `version_string()` / empty `sys_version` — no Python fingerprint
- Tests: ETag, 304, Server header

### TEST
```
python3 -m unittest webapp.tests.test_webapp -v
→ Ran 6 tests — OK
```
- Catalog ETag present; If-None-Match → 304
- Server contains ForkedHistory, not Python

### RESULT
Repeat catalog/scenario loads can revalidate cheaply; HTTP Server header no longer fingerprints the runtime.

---

## Iteration 32 — 2026-07-19

### OBSERVE
Failed video jobs put raw exception text into `job.error` for client polls — ffmpeg failures often embedded absolute host paths (`/Users/.../outputs/...`), leaking layout via the public job API.

### PLAN
**One high-impact change:** sanitize client-facing job errors (redact absolute paths); keep full text in server logs.

Expected outcome: public `error` has `<anor>` / `<path>/file` only; stderr still has full detail.

### EXECUTE
- `sanitize_public_error()` in `jobs.py`
- Use for failed + timed_out job errors
- Operator log line with full exception
- Tests: unit redaction + worker failure path

### TEST
```
python3 -m unittest webapp.tests.test_error_sanitize -v
→ Ran 4 tests — OK
```
- Repo root and `/Users/...` redacted
- Worker failed job public error path-free

### RESULT
Browser-visible job errors no longer disclose host filesystem layout.

---

## Iteration 33 — 2026-07-19

### OBSERVE
Server catalog/scenarios already returned ETags (iter 31), but the SPA always fetched full bodies — browsers rarely send If-None-Match for fetch(), so 304 savings never applied.

### PLAN
**One high-impact change:** client-side revalidation with stored ETag + session body cache.

Expected outcome: second boot/catalog load can 304 and use sessionStorage body; post-render refresh busts catalog cache.

### EXECUTE
- `fetchJsonRevalidatable` + sessionStorage etag/body keys
- Boot uses it for catalog + scenarios
- `refreshCatalog` after video complete (cache bust then revalidate)
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 11 tests — OK
```
- JS contains fetchJsonRevalidatable, If-None-Match, fh:cache:catalog
- Server ETag 304 still green

### RESULT
SPA reloads can revalidate catalog/scenarios instead of always downloading full JSON.

---

## Iteration 34 — 2026-07-19

### OBSERVE
Job errors were path-sanitized (iter 32), but HTTP API exceptions for fork/enqueue/scenario validation still returned raw `str(e)` — absolute paths could leak via 400/422/503 JSON.

### PLAN
**One high-impact change:** route client-facing API exceptions through `sanitize_public_error` (+ optional server log).

Expected outcome: fork_failed / enqueue_failed / invalid_scenario messages are path-redacted.

### EXECUTE
- `Handler._client_error()` using `sanitize_public_error`
- Fork, scenario GET validation, enqueue error paths
- Log full exception for fork_failed / enqueue_failed
- API test with mocked run_fork boom

### TEST
```
python3 -m unittest webapp.tests.test_error_sanitize \
  webapp.tests.test_security.TestForkEndpointSecurity.test_bad_scenario_id \
  webapp.tests.test_webapp.TestWebapp.test_fork -v
→ Ran 7 tests — OK
```
- Mocked fork failure response has `<anor>`, no `/Users/`

### RESULT
JSON API errors match job-error path hygiene across the product surface.

---

## Iteration 35 — 2026-07-19

### OBSERVE
Hash-based SPA navigation never moved focus into the new view — keyboard and screen-reader users could stay on the previous control with no announcement that the page changed.

### PLAN
**One high-impact change:** after route renders complete, focus `#main-content` on navigation (skip first boot paint and open paywall).

Expected outcome: hash changes focus main with `preventScroll`; first load does not steal focus.

### EXECUTE
- `focusMainForRoute` + `routeFocusReady` gate
- `route()` awaits page render then focuses main when key changes
- Close nav on navigate
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 5 tests — OK
```
- JS contains focusMainForRoute, routeFocusReady, preventScroll

### RESULT
SPA route changes are discoverable to assistive tech without disrupting initial load focus.

---

## Iteration 36 — 2026-07-19

### OBSERVE
`document.title` was set once at boot and never updated on hash routes — browser tabs, history, and AT all showed the same home tagline for Library / Studio / Watch / Pricing.

### PLAN
**One high-impact change:** update `document.title` per route (episode title on watch, scenario id on studio).

Expected outcome: titles like `Library — Forked History`, `{episode} — Forked History`, `Studio · ELO-003 — Forked History`.

### EXECUTE
- `updateDocumentTitle(page, param)` after each route render
- Watch uses catalog episode title when available
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 5 tests — OK
```
- JS contains updateDocumentTitle, Library —, Membership —

### RESULT
Browser chrome and assistive tech reflect the current SPA view.

---

## Iteration 37 — 2026-07-19

### OBSERVE
Server already logs `rid=` / echoes `X-Request-ID`, but the SPA almost never sent one — multi-step studio actions (catalog → fork → video poll) could not be stitched together in logs.

### PLAN
**One high-impact change:** generate a 16-hex `X-Request-ID` on every client API call (auth + GET helpers).

Expected outcome: freemium authHeaders, apiHeaders, catalog revalidation, scenario load, and job polls all carry correlatable request ids.

### EXECUTE
- `newRequestId` + `apiHeaders` in freemium.js
- `authHeaders` / demo token / app.js fetches use them
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 5 tests — OK
```
- freemium has newRequestId, X-Request-ID, apiHeaders
- app uses FHFreemium.apiHeaders

### RESULT
Browser actions are correlatable with server `[forked-history] rid=` log lines.

---

## Iteration 38 — 2026-07-19

### OBSERVE
Studio fork buttons could be double-activated before `setBusy` applied (or via rate-limit retry while still settling), risking duplicate POSTs and burning freemium fork quota.

### PLAN
**One high-impact change:** process-wide `forkInFlight` re-entrancy guard around `runFork`.

Expected outcome: second concurrent call toasts and returns; flag cleared in `finally`.

### EXECUTE
- `forkInFlight` gate + toast “already in progress”
- Clear in `finally` with setBusy(false)
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 5 tests — OK
```
- JS contains forkInFlight and toast copy

### RESULT
Double-clicks no longer enqueue parallel fork simulations.

---

## Iteration 39 — 2026-07-19

### OBSERVE
Studio reloads the full scenario pack on every studio visit (`/api/scenario/:id` ~3KB) with no ETag, while catalog/scenarios already revalidated. Switching packs repeatedly re-downloaded unchanged JSON.

### PLAN
**One high-impact change:** ETag + short cache for scenario detail; client revalidates via session cache key per id.

Expected outcome: second GET of same scenario can 304; studio uses `fetchJsonRevalidatable`.

### EXECUTE
- Server: `_json_revalidatable(scenario_payload, max_age=120)`
- Client: `loadScenarioDetail` → `fh:cache:scenario:{id}`
- Tests: scenario ETag 304 + static markers

### TEST
```
python3 -m unittest webapp.tests.test_webapp webapp.tests.test_static_assets -v
→ Ran 12 tests — OK
```
- ELO-003 detail ETag + If-None-Match → 304

### RESULT
Studio pack loads revalidate cheaply when the public pack is unchanged.

---

## Iteration 40 — 2026-07-19

### OBSERVE
No HSTS option for production HTTPS; unknown API 404s echoed the request path (minor recon / log-noise).

### PLAN
**One high-impact change:** optional `Strict-Transport-Security` via env; generic API 404 without path echo.

Expected outcome: ANOR_HSTS_MAX_AGE enables HSTS; `/api/no-such` returns `{code:not_found}` only.

### EXECUTE
- `hsts_header_value()` + wire into `security_headers()`
- Env: ANOR_HSTS_MAX_AGE / SUBDOMAINS / PRELOAD
- Catch-all API 404 omits `path`
- Tests: HSTS on/off, 404 hygiene

### TEST
```
python3 -m unittest webapp.tests.test_security_headers -v
→ Ran 5 tests — OK
```
- Default no HSTS; max-age=31536000 + includeSubDomains when configured
- Unknown API 404 has code, no path

### RESULT
Production can enable HSTS without code changes; unknown endpoints reveal less.

---

## Iteration 41 — 2026-07-19

### OBSERVE
`QUEUE.stats()` / health called `ffmpeg -version` on every probe — expensive subprocess spam under frequent health checks and job list stats.

### PLAN
**One high-impact change:** short-TTL cache for ffmpeg probe (default 30s); live `force=True` at enqueue/worker.

Expected outcome: repeated stats hit cache; enqueue still fail-closed with a fresh probe.

### EXECUTE
- `check_ffmpeg(force=...)` + `clear_ffmpeg_cache()`
- Env `ANOR_FFMPEG_CHECK_CACHE_S` (0 disables)
- Enqueue + worker use `force=True`
- Tests: cache hit count + missing ffmpeg still detected

### TEST
```
python3 -m unittest webapp.tests.test_render_deps \
  webapp.tests.test_video_jobs.TestVideoJobsAPI.test_health_includes_queue -v
→ Ran 8 tests — OK
```
- Cached path: one subprocess.run for three check_ffmpeg calls
- force=True runs each time

### RESULT
Health/queue stats no longer spawn ffmpeg on every request while renders still preflight live.

---

## Iteration 42 — 2026-07-19

### OBSERVE
`/api/catalog` re-read `catalog.json` and `stat` every video file on each request to set `available` — wasteful under boot + library reloads even with client ETags.

### PLAN
**One high-impact change:** short-TTL cache of the built catalog payload, invalidated when catalog.json or video pack fingerprint changes.

Expected outcome: second build within TTL skips re-stat; new renders still invalidate via fingerprint.

### EXECUTE
- `build_catalog_payload()` + `clear_catalog_cache()`
- Env `ANOR_CATALOG_CACHE_S` (default 15, 0 = off)
- Fingerprint: catalog mtime + pack dir / mp4 mtimes
- Tests: cache hit skips is_file; disabled rebuilds

### TEST
```
python3 -m unittest webapp.tests.test_catalog_cache \
  webapp.tests.test_webapp.TestWebapp.test_catalog \
  webapp.tests.test_webapp.TestWebapp.test_catalog_etag_304 -v
→ Ran 5 tests — OK
```

### RESULT
Catalog GETs reuse a built payload briefly without re-statting media on every hit.

---

## Iteration 43 — 2026-07-19

### OBSERVE
Catalog cache (iter 42) could keep stale `available: false` for up to the TTL after a successful render if filesystem mtime fingerprint did not change quickly enough — library would lag behind new MP4s.

### PLAN
**One high-impact change:** clear catalog cache when a video job completes successfully.

Expected outcome: post-render catalog rebuild sees new files immediately.

### EXECUTE
- On job `completed`, call `clear_catalog_cache()` from worker
- Tests: clear forces rebuild; job complete nulls cache

### TEST
```
python3 -m unittest webapp.tests.test_catalog_cache -v
→ Ran 5 tests — OK
```
- Successful mock render leaves `_catalog_cache is None`

### RESULT
New renders show as available on the next catalog fetch without waiting out the cache TTL.

---

## Iteration 44 — 2026-07-19

### OBSERVE
In-process rate limiters retained a dict entry per client key forever — under many distinct peers (or header floods with trust-proxy) memory could grow without bound on a long-lived server.

### PLAN
**One high-impact change:** purge stale limiter keys and cap map size (`ANOR_RATE_LIMIT_MAX_KEYS`, default 10_000).

Expected outcome: empty/expired keys dropped periodically; overflow evicts coldest keys.

### EXECUTE
- `RateLimiter._purge_stale_locked` / `_enforce_max_keys_locked`
- `key_count()` for tests
- Env documented in `.env.example`
- Tests: stale purge after window; max_keys cap

### TEST
```
python3 -m unittest webapp.tests.test_security.TestApiRateHelpers \
  webapp.tests.test_security.TestForkEndpointSecurity.test_rate_limit_trips -v
→ Ran 5 tests — OK
```

### RESULT
Rate-limit maps stay bounded for long-running Forked History processes.

---

## Iteration 45 — 2026-07-19

### OBSERVE
Frequent `/api/health` probes filled access logs; missing media 404s echoed filenames; users without JS got a blank shell with no guidance.

### PLAN
**One high-impact change:** silence health access logs by default; noscript guidance; generic media 404.

Expected outcome: health silent unless `ANOR_LOG_HEALTH=1`; noscript explains JS requirement; media 404 uses `code: not_found` only.

### EXECUTE
- `log_message` skips `/api/health` unless env opt-in
- `<noscript>` block in index.html
- Media missing-file 404 omits `path`
- Tests: access log + noscript

### TEST
```
python3 -m unittest webapp.tests.test_access_log \
  webapp.tests.test_static_assets.TestStaticProgressUI.test_index_noscript_guidance \
  webapp.tests.test_paths_and_media.TestMediaStreaming.test_traversal_media_forbidden -v
→ Ran 4 tests — OK
```

### RESULT
Ops logs stay quieter under probes; non-JS visitors see a clear message; media 404s are less chatty.

---

## Iteration 46 — 2026-07-19

### OBSERVE
After a full episode finished, watch mode offered no completion feedback — Studio CTA sat static while freemium preview already had a hard paywall gate mid-play.

### PLAN
**One high-impact change:** `ended` handler for full watches — toast, pulse Studio CTA, status note.

Expected outcome: finishing a full cut focuses Studio CTA with reduced-motion-safe emphasis; preview still opens paywall.

### EXECUTE
- `player.onended` for full vs preview
- CSS `.pulse-cta` + prefers-reduced-motion outline
- Clear handlers/classes on re-render
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 6 tests — OK
```

### RESULT
Viewers are guided from finished episode into the decision studio without leaving the watch page.

---

## Iteration 47 — 2026-07-19

### OBSERVE
Video job polling kept hitting `/api/video/jobs/{id}` on a 0.5–4s cadence even when the tab was backgrounded — burning global API rate budget and battery during long renders.

### PLAN
**One high-impact change:** pause aggressive polls while `document.hidden`; slow heartbeat every 15s; poll immediately on focus return.

Expected outcome: background tabs wait on visibilitychange (or 15s max); visible tabs keep existing backoff.

### EXECUTE
- `waitWhileDocumentHidden()`
- Poll loop uses it before backoff sleep
- Static markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 6 tests — OK
```

### RESULT
Background studio tabs no longer hammer the video job API during long sovereign renders.

---

## Iteration 48 — 2026-07-19

### OBSERVE
429 responses only set `Retry-After` by parsing the error message string. Clients and CORS frontends could not rely on standard `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers for structured backoff.

### PLAN
**One high-impact change:** attach rate-limit metadata on `ValidationError` for all 429 paths; emit `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining`; expose those headers over CORS.

Expected outcome: exhausted fork/API/video/demo limits return machine-readable rate headers without message parsing.

### EXECUTE
- `ValidationError.limit|remaining|retry_after` optional fields
- `check_*_rate` populates them on trip
- `_validation_error` sets headers (structured first, message parse fallback)
- CORS `Access-Control-Expose-Headers` includes the new names
- `test_rate_limit_trips` asserts header values

### TEST
```
python3 -m unittest webapp.tests.test_security webapp.tests.test_security_headers webapp.tests.test_health_privacy -v
→ Ran 29 tests — OK
```

### RESULT
SPA and reverse proxies can read standard rate-limit headers on 429 without scraping English error text.

---

## Iteration 49 — 2026-07-19

### OBSERVE
`/api/scenarios` and detailed health re-ran `list_scenarios()` (read + validate every public JSON) on every request. Catalog already had a short TTL cache; the pack index did not.

### PLAN
**One high-impact change:** TTL + mtime/size fingerprint cache for the public pack list; wire into `/api/scenarios` and health `scenarios_count`.

Expected outcome: repeated boot/library hits reuse the list; pack edits invalidate via fingerprint; `ANOR_SCENARIOS_CACHE_S=0` disables.

### EXECUTE
- `list_scenarios_cached()` / `clear_scenarios_list_cache()` / `_scenarios_dir_fingerprint()`
- Default TTL 30s (`ANOR_SCENARIOS_CACHE_S`)
- `.env.example` knob
- Tests: `webapp/tests/test_scenarios_cache.py`

### TEST
```
python3 -m unittest webapp.tests.test_scenarios_cache webapp.tests.test_catalog_cache \
  webapp.tests.test_webapp webapp.tests.test_health_privacy -v
→ Ran 20 tests — OK
```

### RESULT
Studio boot and health no longer re-validate every public pack JSON on each hit.

---

## Iteration 50 — 2026-07-19

### OBSERVE
`GET /api/scenario/:id` still called `scenario_payload()` (disk read + full validation + projection) on every request before ETag hashing. Studio pack switches and repeat visits paid that cost even when the pack file was unchanged.

### PLAN
**One high-impact change:** in-process per-pack detail cache with mtime/size fingerprint, shared TTL knob, and max 64 entries (evict oldest). Do not cache missing packs.

Expected outcome: warm studio loads reuse the projected payload; pack edits invalidate; `ANOR_SCENARIOS_CACHE_S=0` disables.

### EXECUTE
- `scenario_payload_cached()` / `clear_scenario_payload_cache()` / `_scenario_file_fingerprint()`
- Wire `/api/scenario/:id` to the cache
- `.env.example` documents detail caching under `ANOR_SCENARIOS_CACHE_S`
- Tests: `webapp/tests/test_scenario_payload_cache.py`

### TEST
```
python3 -m unittest webapp.tests.test_scenario_payload_cache \
  webapp.tests.test_scenarios_cache \
  webapp.tests.test_webapp.TestWebapp.test_scenario_detail_etag_304 -v
→ Ran 12 tests — OK
```

### RESULT
Studio pack detail GETs reuse validated payloads until TTL or file fingerprint changes.

---

## Iteration 51 — 2026-07-19

### OBSERVE
Foundation is solid (security, queue, caches). Highest product gap on the priority menu: **no deploy path**. Zero Dockerfile/compose; site only runs via local `python -m webapp.server`. Dawes/Ganymede need an image with env-driven `LLM_URL` / `IMAGE_URL` / `TTS_URL` and mock fallback.

### PLAN
**One high-impact change:** portable Docker image + compose (ffmpeg, public packs only, mock media default, host.docker.internal for fleet URLs). Hygiene tests without requiring a Docker daemon.

Expected outcome: `docker compose --env-file .env up --build` boots Forked History; secrets never baked in.

### EXECUTE
- `Dockerfile` (python:3.12-slim + ffmpeg, CMD webapp.server 0.0.0.0:8787)
- `docker-compose.yml` (endpoint env vars, video volume, healthcheck)
- `.dockerignore` (excludes `.env`, outputs, drafts)
- `DEPLOY.md` + README pointer
- Tests: `scripts/tests/test_deploy_config.py`

### TEST
```
python3 -m unittest scripts.tests.test_deploy_config webapp.tests.test_webapp \
  pipeline.tests.test_pipeline -v
→ Ran 23 tests — OK
```

### RESULT
Forked History has a config-driven deploy path for Dawes now / Ganymede later; offline mock remains the safe default.

---

## Iteration 52 — 2026-07-19

### OBSERVE
Only three public decision packs (ELO-001/003/013). Library/studio depth was thin; ELO-001 had a pack but no catalog video row. Deploy/hardening foundation is in place — content is the highest-value gap.

### PLAN
**One high-impact change:** add public pack **ELO-007** (EXCOMM quarantine vs strike/invasion), wire catalog entries, validate all packs in tests.

Expected outcome: studio lists four packs; historical quarantine is `documented`; strike/invasion are `simulated`; no MANDOS material.

### EXECUTE
- `scenarios/public/ELO-007.json` (schema + sources + provenance + speculation levels)
- Catalog: ELO-007 historical + surgical_strike; also ELO-001-historical row
- README pack table
- Tests: core set includes ELO-007; `test_schema_fields` walks every public pack

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  webapp.tests.test_webapp webapp.tests.test_catalog_cache webapp.tests.test_scenarios_cache -v
→ Ran 38 tests — OK
```

### RESULT
Public library gains the Cuban Missile Crisis presidential decision point, complementary to Arkhipov (ELO-013), with labels intact.

---

## Iteration 53 — 2026-07-19

### OBSERVE
SPA shell only had a bare `meta description`. No Open Graph, Twitter card, theme-color, favicon, or JSON-LD — weak share previews and SEO for the product surface.

### PLAN
**One high-impact change:** share/SEO metadata shell + route-synced og/twitter/description; SVG favicon.

Expected outcome: crawlers and share sheets get brand title/description; SPA updates meta on library/watch/studio/pricing.

### EXECUTE
- `index.html`: og:*, twitter:*, theme-color, robots, JSON-LD `WebApplication`
- `static/favicon.svg` (fork glyph)
- `syncShareMeta` / `setMetaContent` in `updateDocumentTitle` (preserves 📗/🧪 on watch)
- Tests: `test_index_share_and_seo_metadata` + JS markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_paths_and_media \
  webapp.tests.test_webapp -v
→ Ran 22 tests — OK
```

### RESULT
Forked History link previews and route titles carry brand + speculation-aware descriptions without hardcoding a production host.

---

## Iteration 54 — 2026-07-19

### OBSERVE
ELO-007 public pack shipped, but social pipeline only had batch-001 (Cannae / Arkhipov / Barbarossa). No captions or Postiz skeleton for EXCOMM cuts; human-gate drafts lag content.

### PLAN
**One high-impact change:** batch-002 DRAFTS for ELO-007 (historical + strike + invasion) with Postiz draft payload and hygiene tests.

Expected outcome: Ryan-reviewable captions; `status: draft` + placeholder integrations; invasion YT-only; 🧪 labels on simulations; no auto-publish.

### EXECUTE
- `content/drafts/batch-002/*` (3 cut MDs, `postiz-drafts.json`, README)
- Parent `content/drafts/README.md` batch table
- Tests: `scripts/tests/test_social_drafts.py`

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 12 tests — OK
```

### RESULT
EXCOMM social creative is staged as drafts only, paired with batch-001 Arkhipov for a coherent Missile Crisis arc.

---

## Iteration 55 — 2026-07-19

### OBSERVE
`ImageClient` already supported Comfy + OpenAI-images + mock, but: (1) remote failures killed whole video renders; (2) little unit coverage of backend selection / b64 path; (3) healthcheck hid resolved backends; (4) CI omitted newer webapp/scripts tests.

### PLAN
**One high-impact change:** harden image path for real `IMAGE_URL` — optional mock fallback on outages (not SSRF rejects), health reports backends, dedicated tests, CI suite completeness.

Expected outcome: with `IMAGE_URL` set, OpenAI/Comfy still preferred; on non-policy failure default fallback writes placeholder + sidecar; CI runs full unit surface.

### EXECUTE
- `ImageClient.generate`: extract `_openai_images`; `ANOR_IMAGE_FALLBACK_MOCK` (default on); SSRF still hard-fails
- `healthcheck`: `image_backend`, `image_fallback_mock`, `tts_backend`
- Tests: `pipeline/tests/test_image_client.py`
- CI: add image/scenarios/deploy/social/dep_audit modules
- `.env.example` documents fallback knob

### TEST
```
python3 -m unittest pipeline.tests.test_image_client pipeline.tests.test_safe_fetch \
  scripts.tests.test_deploy_config scripts.tests.test_social_drafts \
  scripts.tests.test_dep_audit webapp.tests.test_scenarios_cache \
  webapp.tests.test_scenario_payload_cache -v
→ Ran 51 tests — OK
```

### RESULT
Real image endpoints light up when configured; mock remains the safe offline path and optional outage safety net without weakening SSRF guards.

---

## Iteration 56 — 2026-07-19

### OBSERVE
Public library had four packs (Cannae, Barbarossa, EXCOMM, Arkhipov). No 1940 Channel campaign decision; studio/catalog depth still thin relative to product ambition.

### PLAN
**One high-impact change:** add public pack **ELO-009** (Dunkirk halt order) with documented historical path + labeled press-armor / air-heavy branches; catalog + tests.

Expected outcome: five public packs; halt = documented; press = simulated; no MANDOS material.

### EXECUTE
- `scenarios/public/ELO-009.json`
- Catalog: ELO-009-historical + ELO-009-press_armor
- README pack table
- Tests: core set includes ELO-009; fork label assertions

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  webapp.tests.test_webapp webapp.tests.test_catalog_cache -v
→ Ran 35 tests — OK
```

### RESULT
Studio/library gain Dunkirk as a WW2 operational decision point with speculation labels intact.

---

## Iteration 57 — 2026-07-19

### OBSERVE
ELO-009 Dunkirk pack shipped; social pipeline stopped at batch-002 (EXCOMM). No Ryan-reviewable captions or Postiz skeleton for the halt / press / air-heavy cuts.

### PLAN
**One high-impact change:** batch-003 DRAFTS for ELO-009 with human-gate Postiz payload and extended hygiene tests.

Expected outcome: draft-only captions; 📗/🧪 labels; placeholder integrations; no auto-publish.

### EXECUTE
- `content/drafts/batch-003/*` (3 cut MDs, postiz-drafts.json, README)
- Parent drafts README table
- Tests: batch-003 presence + pack reference + label checks

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 16 tests — OK
```

### RESULT
Dunkirk social creative is staged as drafts only, aligned with the new public pack.

---

## Iteration 58 — 2026-07-19

### OBSERVE
Docker image ran as **root** by default — unnecessary privilege for a stdlib HTTP product site with a writable video volume.

### PLAN
**One high-impact change:** non-root runtime (uid 10001 `anor`), writable `outputs/`, compose `user` match, docs for volume ownership.

Expected outcome: container process is not root; healthcheck and CMD still work; operators know how to fix old volumes.

### EXECUTE
- Dockerfile: `useradd`/`groupadd` 10001, `chown /app`, `USER anor`
- compose: `user: "10001:10001"`
- DEPLOY.md: security runtime + volume chown note
- Tests: assert USER anor, uid, user before CMD

### TEST
```
python3 -m unittest scripts.tests.test_deploy_config -v
→ Ran 6 tests — OK
```

### RESULT
Forked History container drops root by default; env-driven endpoints unchanged.

---

## Iteration 59 — 2026-07-19

### OBSERVE
Explorer users could run forks but only Scholar could leave the page with a file (`Export .md`). No free clipboard path; labels risked being stripped in ad-hoc copy-paste from the DOM.

### PLAN
**One high-impact change:** free **Copy narrative** for everyone, shared `formatForkMarkdown` that always embeds 📗/🧪 labels; Export stays Scholar and reuses the same formatter.

Expected outcome: one click copies labeled markdown; inline + toolbar buttons; export paywall still points free users to copy.

### EXECUTE
- `formatForkMarkdown` / `copyForkNarrative` / `copyTextToClipboard` / `bindForkCopyButtons`
- `#btn-copy` + inline `#btn-copy-inline` after fork/resume
- Control tile “Copy narrative” free
- Static asset tests for markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 14 tests — OK
```

### RESULT
Studio clipboard path is free and label-preserving; download export remains a Scholar control.

---

## Iteration 60 — 2026-07-19

### OBSERVE
Six eras of product surface still only five public packs after Dunkirk; no late-Republic threshold decision between Cannae and modern crises.

### PLAN
**One high-impact change:** add public pack **ELO-004** (Caesar at the Rubicon) with documented crossing + labeled stand-down / negotiate branches; catalog + tests.

Expected outcome: six public packs; historical = documented armed crossing; stand_down = simulated; no MANDOS material.

### EXECUTE
- `scenarios/public/ELO-004.json`
- Catalog: ELO-004-historical + ELO-004-stand_down
- README pack table
- Tests: core set + fork label assertions

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  webapp.tests.test_webapp webapp.tests.test_catalog_cache webapp.tests.test_scenarios_cache -v
→ Ran 42 tests — OK
```

### RESULT
Studio/library gain the Rubicon as a playable civil-war threshold with speculation labels intact.

---

## Iteration 61 — 2026-07-19

### OBSERVE
ELO-004 Rubicon pack shipped; social drafts stopped at batch-003 (Dunkirk). No Ryan-reviewable captions for crossing / stand-down / negotiate cuts.

### PLAN
**One high-impact change:** batch-004 DRAFTS for ELO-004 with human-gate Postiz payload and hygiene tests.

Expected outcome: draft-only captions; 📗/🧪 labels; placeholder integrations; no auto-publish.

### EXECUTE
- `content/drafts/batch-004/*` (3 cut MDs, postiz-drafts.json, README)
- Parent drafts README table
- Tests: batch-004 presence + pack reference + label checks

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 20 tests — OK
```

### RESULT
Rubicon social creative is staged as drafts only, aligned with the new public pack.

---

## Iteration 62 — 2026-07-19

### OBSERVE
Rate-limit headers only appeared on **429**. Successful `/api/fork`, video enqueue, and demo-token responses did not report remaining budget, so the SPA could not warn before the hard limit.

### PLAN
**One high-impact change:** return `(error, rate_headers)` from endpoint rate checks; attach `X-RateLimit-Limit/Remaining` on success; SPA soft-toast when remaining is low.

Expected outcome: first fork returns Remaining=limit-1; clients can throttle; 429 path unchanged.

### EXECUTE
- `rate_limit_headers` + tuple returns from `check_fork_rate` / `check_video_job_rate` / `check_demo_token_rate`
- Server attaches headers on 200/202 success
- SPA: `parseRateLimitRemaining` / `noteRateRemaining`
- Tests: `test_fork_success_exposes_rate_remaining` + static markers

### TEST
```
python3 -m unittest webapp.tests.test_security webapp.tests.test_static_assets \
  webapp.tests.test_webapp webapp.tests.test_membership -v
→ Ran 43 tests — OK
```

### RESULT
Expensive endpoints advertise remaining quota on success; studio warns when the window is nearly spent.

---

## Iteration 63 — 2026-07-19

### OBSERVE
Library grew to ~10 catalog cuts across 6 packs with no filter UI. Documented and simulated episodes mixed in one grid; studio pack select was filename order, not chronology.

### PLAN
**One high-impact change:** library filter toolbar (All / Documented / Simulated / On this host) + chronological pack ordering on home and studio.

Expected outcome: users can browse only 📗 or only 🧪; packs listed ancient→modern; a11y toolbar + live status count.

### EXECUTE
- `#library-filters` + `filterLibraryVideos` / `bindLibraryFilters`
- `eraSortKey` / `scenariosChronological` for home + studio select
- CSS active filter state
- Static asset tests

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 14 tests — OK
```

### RESULT
Library respects historical integrity labels as first-class browse filters; packs read in time order.

---

## Iteration 64 — 2026-07-19

### OBSERVE
`ImageClient` had outage mock-fallback + tests; `TTSClient` still failed hard on remote/system TTS errors (killing long video jobs) and had no length cap or unit coverage.

### PLAN
**One high-impact change:** optional silent-audio fallback on TTS failure (`ANOR_TTS_FALLBACK_MOCK`), clip VO text (`ANOR_TTS_MAX_CHARS`), dedicated tests + CI.

Expected outcome: remote TTS outages finish with silent wav + sidecar; empty text rejected; strict mode still raises.

### EXECUTE
- `TTSClient.mock_fallback_enabled` / `_clip_text` / `_openai_audio` / `_http_wav`
- health: `tts_fallback_mock`
- `.env.example` knobs; CI includes `test_tts_client`
- Tests: `pipeline/tests/test_tts_client.py`

### TEST
```
python3 -m unittest pipeline.tests.test_tts_client pipeline.tests.test_image_client \
  pipeline.tests.test_pipeline.TestVideoPipeline -v
→ Ran 25 tests — OK
```

### RESULT
TTS lights up when `TTS_URL` is set; mock silent path remains the offline/outage safety net for video renders.

---

## Iteration 65 — 2026-07-19

### OBSERVE
`PIPELINE.md` still described a pre-product layout (no webapp/Docker/pack inventory/draft batches). Ops docs lagged six public packs and human-gate social batches.

### PLAN
**One high-impact change:** refresh PIPELINE.md to current architecture + pack/draft tables + fuller test entrypoint; hygiene test that every on-disk pack ID appears in the doc.

Expected outcome: single operator map stays honest; CI fails if a new pack ships without doc mention.

### EXECUTE
- Rewrite `PIPELINE.md` (packs, webapp, DEPLOY, drafts, fallbacks, tests)
- `scripts/tests/test_pipeline_docs.py`
- CI includes docs hygiene

### TEST
```
python3 -m unittest scripts.tests.test_pipeline_docs scripts.tests.test_deploy_config \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 21 tests — OK
```

### RESULT
Pipeline documentation matches the live product surface; pack list cannot drift silently.

---

## Iteration 66 — 2026-07-19

### OBSERVE
Six public packs spanned antiquity and mid-20th century but had no WWI July Crisis decision point — a core ELOSTIRION-style alliance cascade gap.

### PLAN
**One high-impact change:** add public pack **ELO-005** (blank cheque) with documented support path + labeled restrain/localize branches; catalog + docs + tests.

Expected outcome: seven public packs; historical = documented; restrain = simulated; PIPELINE/README inventory updated.

### EXECUTE
- `scenarios/public/ELO-005.json`
- Catalog: ELO-005-historical + ELO-005-restrain
- README + PIPELINE pack tables
- Fork label tests

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  scripts.tests.test_pipeline_docs webapp.tests.test_webapp webapp.tests.test_catalog_cache -v
→ Ran 44 tests — OK
```

### RESULT
Studio/library gain the July Crisis as a playable Great Power decision with speculation labels intact.

---

## Iteration 67 — 2026-07-19

### OBSERVE
ELO-005 July Crisis pack shipped; social drafts stopped at batch-004 (Rubicon). No Ryan-reviewable captions for blank-cheque / restrain / localize cuts.

### PLAN
**One high-impact change:** batch-005 DRAFTS for ELO-005 with human-gate Postiz payload and hygiene tests.

Expected outcome: draft-only captions; 📗/🧪 labels; placeholder integrations; no auto-publish.

### EXECUTE
- `content/drafts/batch-005/*` (3 cut MDs, postiz-drafts.json, README)
- Parent drafts README + PIPELINE batch table
- Tests: batch-005 presence + pack reference + labels

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts scripts.tests.test_pipeline_docs \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 29 tests — OK
```

### RESULT
July Crisis social creative is staged as drafts only, aligned with the new public pack.

---

## Iteration 68 — 2026-07-19

### OBSERVE
Branch compare only used authored pack summaries with speculation labels, yet was gated as Scholar — free users could not see 📗 vs 🧪 side-by-side without paying.

### PLAN
**One high-impact change:** unlock authored branch compare for Explorer; strengthen label chrome; keep LLM re-render/export as Scholar.

Expected outcome: free compare of historical baseline vs selected counterfactual with mandatory pills; guidance when both panes are the baseline.

### EXECUTE
- `compareBranches` free path + clearer 📗/🧪 UI
- Control tiles + studio quota + index/README freemium copy
- Responsive compare grid CSS
- Static asset tests for compare markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 14 tests — OK
```

### RESULT
Explorer can study labeled branch differences without a membership wall; Scholar remains the path for LLM narrative and export.

---

## Iteration 69 — 2026-07-19

### OBSERVE
Studio loaded opening + known outcome + choices but buried pack `sources` and `provenance` (already in the API payload). Users could fork without seeing the public source list or ELOSTIRION discipline notes.

### PLAN
**One high-impact change:** collapsible Studio “Sources & provenance” panel with public source list, discipline/notes/corpus, and 📗/🧪 reminder — no MANDOS material.

Expected outcome: every pack open surfaces citations and integrity language without cluttering the default UI.

### EXECUTE
- `#studio-sources` details element in index
- `renderStudioSources(detail)` after pack load
- CSS for summary/list
- Static tests for markers

### TEST
```
python3 -m unittest webapp.tests.test_static_assets webapp.tests.test_webapp -v
→ Ran 14 tests — OK
```

### RESULT
Studio makes receipts first-class: public sources and speculation discipline are one click from the decision list.

---

## Iteration 70 — 2026-07-19

### OBSERVE
JSON/API and text responses were always sent uncompressed. Growing catalog/scenario payloads and SPA boot paid full bandwidth on every cold load; no `Accept-Encoding` handling.

### PLAN
**One high-impact change:** optional gzip for compressible bodies ≥512B when the client accepts gzip (`ANOR_GZIP`, default on). Media streaming unchanged.

Expected outcome: `/api/catalog` with `Accept-Encoding: gzip` returns `Content-Encoding: gzip` + `Vary: Accept-Encoding` and a smaller body.

### EXECUTE
- `_maybe_gzip` / `_client_accepts_gzip` / `_gzip_enabled` on `_send`
- `.env.example` `ANOR_GZIP`
- Tests: gzip and identity catalog paths

### TEST
```
python3 -m unittest webapp.tests.test_webapp webapp.tests.test_paths_and_media \
  webapp.tests.test_security_headers -v
→ Ran 22 tests — OK
```

### RESULT
Text and JSON responses compress when beneficial; reverse proxies and browsers can cut library boot cost without code changes on the SPA.

---

## Iteration 71 — 2026-07-19

### OBSERVE
Seven public packs jumped from Barbarossa (1941) to EXCOMM/Arkhipov (1962) with no early Cold War occupation crisis — the Berlin Blockade/Airlift is a canonical decision point still missing.

### PLAN
**One high-impact change:** add public pack **ELO-006** (airlift vs force corridors vs bargain) with documented airlift path and labeled counterfactuals; catalog + docs + tests.

Expected outcome: eight public packs; historical = documented airlift; force_corridors = simulated.

### EXECUTE
- `scenarios/public/ELO-006.json`
- Catalog: ELO-006-historical + ELO-006-force_corridors
- README + PIPELINE pack tables
- Fork label tests

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  scripts.tests.test_pipeline_docs webapp.tests.test_webapp webapp.tests.test_catalog_cache -v
→ Ran 48 tests — OK
```

### RESULT
Studio/library gain the Berlin Airlift as a playable early Cold War logistics decision with speculation labels intact.

---

## Iteration 72 — 2026-07-19

### OBSERVE
ELO-006 Berlin Airlift pack shipped; social drafts stopped at batch-005. No Ryan-reviewable captions for airlift / force / negotiate cuts.

### PLAN
**One high-impact change:** batch-006 DRAFTS for ELO-006 with human-gate Postiz payload and hygiene tests.

Expected outcome: draft-only captions; 📗/🧪 labels; placeholder integrations; no auto-publish.

### EXECUTE
- `content/drafts/batch-006/*` (3 cut MDs, postiz-drafts.json, README)
- Parent drafts README + PIPELINE batch table
- Tests: batch-006 presence + pack reference + labels

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts scripts.tests.test_pipeline_docs \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 33 tests — OK
```

### RESULT
Berlin Airlift social creative is staged as drafts only, aligned with the new public pack.

---

## Iteration 73 — 2026-07-19

### OBSERVE
Studio fork actions required mouse clicks; no keyboard accelerator for the primary path after choosing a decision — weaker power-user and a11y flow once a pack is open.

### PLAN
**One high-impact change:** Ctrl/⌘+Enter runs basic fork; Ctrl/⌘+Shift+Enter runs LLM (Scholar); on-screen kbd hint + `aria-keyshortcuts`.

Expected outcome: from studio (including seed field), modifiers+Enter trigger the correct fork without leaving the keyboard.

### EXECUTE
- `bindStudioKeyboardShortcuts` / `isEditableTarget`
- Hint under studio buttons; titles on fork/LLM buttons
- CSS for `<kbd>` chips
- Static asset tests

### TEST
```
python3 -m unittest webapp.tests.test_static_assets -v
→ Ran 7 tests — OK
```

### RESULT
Studio primary and Scholar LLM forks are reachable by keyboard without sacrificing paywall or editable-field safety.

---

## Iteration 74 — 2026-07-19

### OBSERVE
Nine-pack arc still lacked a Normandy D-Day weather/go decision between Barbarossa (1941) and Berlin (1948) — a flagship Allied command crisis.

### PLAN
**One high-impact change:** add public pack **ELO-008** (Overlord go / delay / postpone) with documented 6 June go and labeled counterfactuals; catalog + docs + tests.

Expected outcome: nine public packs; historical = documented go; delay_longer = simulated.

### EXECUTE
- `scenarios/public/ELO-008.json`
- Catalog: ELO-008-historical + ELO-008-delay_longer
- README + PIPELINE pack tables
- Fork label tests

### TEST
```
python3 -m unittest pipeline.tests.test_pipeline pipeline.tests.test_validate \
  scripts.tests.test_pipeline_docs webapp.tests.test_webapp webapp.tests.test_catalog_cache -v
→ Ran 50 tests — OK
```

### RESULT
Studio/library gain Overlord’s weather-bound go decision with speculation labels intact.

---

## Iteration 75 — 2026-07-19

### OBSERVE
ELO-008 Overlord pack shipped; social drafts stopped at batch-006. No Ryan-reviewable captions for go / delay / postpone cuts.

### PLAN
**One high-impact change:** batch-007 DRAFTS for ELO-008 with human-gate Postiz payload and hygiene tests.

Expected outcome: draft-only captions; 📗/🧪 labels; placeholder integrations; no auto-publish.

### EXECUTE
- `content/drafts/batch-007/*` (3 cut MDs, postiz-drafts.json, README)
- Parent drafts README + PIPELINE batch table
- Tests: batch-007 presence + pack reference + labels

### TEST
```
python3 -m unittest scripts.tests.test_social_drafts scripts.tests.test_pipeline_docs \
  pipeline.tests.test_pipeline.TestPublicPacks -v
→ Ran 37 tests — OK
```

### RESULT
Overlord / D-Day social creative is staged as drafts only, aligned with the new public pack.

---

## Iteration 76 — 2026-07-19

### OBSERVE
ThreadingHTTPServer handlers had no per-request socket timeout (`BaseHTTPRequestHandler.timeout` default None). Slow or stalled clients could pin worker threads indefinitely (slowloris-style risk on the freemium surface).

### PLAN
**One high-impact change:** env-driven request timeout (`ANOR_REQUEST_TIMEOUT_S`, default 60s) applied to `Handler.timeout`; disable with `0`/`off`.

Expected outcome: each connection has a finite read timeout; startup log prints `req_timeout`.

### EXECUTE
- `request_timeout_s()` + `Handler.timeout` sync at import and `run_server`
- Server version `ForkedHistory/1.21`
- `.env.example` knob; `webapp/tests/test_request_timeout.py`; CI

### TEST
```
python3 -m unittest webapp.tests.test_request_timeout webapp.tests.test_webapp \
  webapp.tests.test_security -v
→ Ran 39 tests — OK
```

### RESULT
Product HTTP surface bounds hung clients without changing happy-path fork/catalog behavior.

---

## Iteration 77 — 2026-07-19

### OBSERVE
Main was green after pytest pin (`5cd696e`). Image path had Comfy txt2img but: (1) SD 1.5-era defaults, not SDXL+Real-ESRGAN on Dawes; (2) no process-level serialize for shared VRAM with Ollama; (3) Ken Burns forced 720p and downscaled stills before zoompan (no headroom); (4) sample path unvalidated against live Comfy.

Live probe `http://dawes:8188`: ckpt `sd_xl_base_1.0.safetensors`, upscale `RealESRGAN_x4plus.pth`.

### PLAN
**One high-impact change:** end-to-end archival still pipeline — SDXL Comfy graph + Real-ESRGAN 4×, serialized Comfy jobs, 1080p Ken Burns with zoom headroom, mock fallback preserved, Flux.1-dev rejected.

### EXECUTE
- `ImageClient`: `_COMFY_LOCK`, `build_comfy_workflow` (SDXL + UpscaleModelLoader/ImageUpscaleWithModel), still size 1024×576, Flux.1-dev hard reject
- `video_pipeline.ken_burns_filter` / `_ken_burns_clip` → default 1920×1080, no pre-crop to frame
- Style prefix archival sepia/chiaroscuro/grain; defaults in `.env.example`, `PIPELINE.md`, compose
- Tests: workflow structure, comfy mock path, Ken Burns dims, flux reject

### TEST
```
ANOR_MOCK_MEDIA=1 PYTHONPATH=. python -m unittest <full CI module list> -v
→ Ran 241 tests — OK
python -m compileall -q sim pipeline webapp scripts
PYTHONPATH=sim python -m pytest -q sim/tests → 3 passed
python scripts/dep_audit.py --pip-audit --require-pip-audit → clean

Live (not CI): IMAGE_URL=http://dawes:8188 → 2 stills 4096×2304 + Ken Burns 1920×1080
```

### RESULT
Monetizable image path is live-validated on Dawes SDXL+ESRGAN; CI/offline mock path unchanged. Sample assets under outputs/samples (gitignored).

---

## Iteration 78 — 2026-07-19

### OBSERVE
Image path green on main (`b99609b`). Operators still lacked a one-shot still CLI for social/review (full video is heavy). ELO-013 already has batch-001 drafts.

### PLAN
**One high-impact change:** `pipeline.cli still` — generate one archival PNG from freeform prompt or pack `image_prompt`, optional silent Ken Burns MP4.

### EXECUTE
- CLI `still` with `--prompt` / `--scenario` / `--choice` / `--out` / `--ken-burns`
- Tests `pipeline/tests/test_cli_still.py`; CI module list; PIPELINE quick start

### TEST
```
Full local CI (unittest incl. test_cli_still + compileall + pytest + pip-audit) → OK
```

### RESULT
Content ops can mint stills (+ optional 1080p Ken Burns) without a full video render.

---

## Iteration 79 — 2026-07-20

### OBSERVE
Main green after still CLI. Studio video progress treated stills/TTS/clips as one flat stage; no queue wait ETA; mobile users scrolled past primary actions on long studio pages.

### PLAN
**One high-impact change:** finer render progress ladder + queue `eta_s` + mobile studio dock + progress % polish.

### EXECUTE
- `video_pipeline`: stages `still` / `tts` / `clip` with segment n/N messages
- `jobs.to_public_enriched`: `eta_s` (queued: jobs_ahead × ANOR_VIDEO_ETA_PER_JOB_S; running: deadline remaining)
- SPA: VIDEO_STAGES ladder, percent readout, sticky `#studio-dock` ≤720px, scroll-padding / reduced-motion
- Tests: static assets, queue position ETA

### TEST
```
Full local CI (unittest suite + compileall + pytest + pip-audit) → OK
```

### RESULT
Operators and Scholars see real pipeline stages and wait estimates; phones keep Fork/LLM/Video/Compare reachable.

---

## Iteration 80 — 2026-07-20

### OBSERVE
Re-queue after a finished MP4 re-ran full still→TTS→ffmpeg. Costly on Dawes and common after refresh/compare.

### PLAN
**One high-impact change:** disk cache hit on enqueue — return completed job with `result.cached` when MP4 exists; `force=true` re-renders.

### EXECUTE
- `find_cached_video` / `media_url_for`; enqueue short-circuit; server skips dep check on cache; SPA toast + UI note
- Tests: cache hit no worker, force bypass, tiny-file ignore

### TEST
```
Full local CI → OK
```

### RESULT
Scholars get instant “existing render” when media is already on disk; GPU/TTS watts preserved.

---

## Iteration 81 — 2026-07-21

### OBSERVE
Main green after cache-hit video. Running `eta_s` was wall-clock timeout budget (misleading during long still/TTS). Mobile dock lacked live % / cancel; video fail paths had no Try again.

### PLAN
**One high-impact change:** work-based running ETA + dock progress/cancel + fail retry.

### EXECUTE
- `estimate_running_eta_s` (pct extrapolation, deadline cap); wire in `to_public_enriched`
- SPA: show `~… left` for running; dock status strip + Cancel; retryAction on fail/timeout
- Tests: `test_running_eta`; static needles; CI module list

### TEST
```
Full local CI (unittest + compileall + pytest + pip-audit) → OK
```

### RESULT
Scholars see honest remaining-time estimates during render; phones keep cancel + stage progress reachable.

---

## Iteration 82 — 2026-07-21

### OBSERVE
Main green after work-based ETA. Disk cache hit saved GPU but Scholars had no studio path to intentionally re-render after Comfy/style upgrades (`force` API only).

### PLAN
**One high-impact change:** studio Force re-render (`force: true`) with confirm + API test.

### EXECUTE
- `queueVideoRender({ force })` posts `force`; toast on force queue
- Completion UI: Force re-render (Scholar) + confirm dialog
- `test_cache_hit_flags_and_force_bypasses`; static needles

### TEST
```
Full local CI → OK
```

### RESULT
Default path stays cache-cheap; deliberate re-renders available after confirm.

---

## Iteration 83 — 2026-07-21

### OBSERVE
Main green. Library had speculation/availability chips but no text search — weak freemium browse as catalog grows.

### PLAN
**One high-impact change:** library free-text search (title/era/id) + `/` focus + Esc clear.

### EXECUTE
- `filterLibraryVideos(videos, filter, query)` multi-token AND
- `#library-search` toolbar, CSS, `/` keyboard, empty-state copy
- Tests: `test_library_search`; CI module list

### TEST
```
Full local CI → OK
```

### RESULT
Explorers can find packs by era/title without scrolling the full grid.

---

## Iteration 84 — 2026-07-21

### OBSERVE
Main green after library search. Catalog already carries `tags` but cards hid them; filter/search prefs reset on refresh.

### PLAN
**One high-impact change:** topic tags on video cards (click → search) + session-persisted library prefs.

### EXECUTE
- `videoCardTagsHtml` / `applyLibraryTagSearch`; tags in search haystack
- `fh:libraryPrefs` sessionStorage for filter + query
- CSS + tests

### TEST
```
Full local CI → OK
```

### RESULT
Explorers browse by theme (Cold War, Cannae, …) and keep library context across in-tab navigations.

---

## Iteration 85 — 2026-07-21

### OBSERVE
Main green after library tags. Watch page lacked one-tap share of public deep links (distribution without auto-publish).

### PLAN
**One high-impact change:** Share episode via Web Share API + clipboard fallback; labeled speculation in share text.

### EXECUTE
- `episodeSharePayload` / `shareEpisode`; `#watch-share` button
- Tests: `test_share_episode`; CI module list

### TEST
```
Full local CI → OK
```

### RESULT
Explorers can share episode URLs with 📗/🧪 labels; social draft publish remains human-gated.

---

## Iteration 86 — 2026-07-21

### OBSERVE
Main green. Content gap: no 1961 Bay of Pigs pack (Cold War stack had 1948/62 only). Job tests flaky when local `outputs/` had cached MP4s.

### PLAN
**One high-impact change:** public pack ELO-010 Bay of Pigs + batch-008 human-gate drafts + catalog; force=True on worker-path unit tests.

### EXECUTE
- `scenarios/public/ELO-010.json` (historical / scrub / dense_air)
- Catalog videos; `content/drafts/batch-008/*`; PIPELINE + public README
- Social draft tests; pack list; `force=True` in timeout/sanitize/catalog-cache tests

### TEST
```
Full local CI → 263 tests OK + pip-audit clean
```

### RESULT
Studio/library gain a labeled 1961 Cold War decision pack; social drafts staged for Ryan only.

---

## Iteration 87 — 2026-07-21

### OBSERVE
Main green after ELO-010. Studio hid whether the selected branch already had an MP4 (cache hit vs full GPU). Operator health lacked still/upscale/frame sizes.

### PLAN
**One high-impact change:** studio media-on-host strip + choice badges; healthcheck still/upscale/frame fields.

### EXECUTE
- `paintStudioMediaStrip` / `findCatalogVideo`; choice meta "MP4 on host"
- `healthcheck`: image_still_size, image_upscale(+model), video_frame_size
- Tests: health fields; static needles

### TEST
```
Full local CI → 263 OK + pip-audit clean
```

### RESULT
Scholars see cache vs render cost before enqueue; operators see image pipeline geometry in health detail.

---

## Iteration 88 — 2026-07-21

### OBSERVE
Main green. Catalog covered only ~19 of ~30 public pack choices — studio media strip and library missed counterfactual branches.

### PLAN
**One high-impact change:** complete freemium catalog coverage for every public choice + regression test.

### EXECUTE
- Added 11 missing `webapp/data/catalog.json` video rows (all packs)
- `test_catalog_covers_every_public_pack_choice`

### TEST
```
Full local CI → 264 OK + pip-audit clean
```

### RESULT
Every public decision branch is listable in Library and status-aware in Studio.

---

## Iteration 89 — 2026-07-21

### OBSERVE
Main green after full catalog coverage. Watch page was a dead end after play — no path to sibling branches or tag-adjacent cuts.

### PLAN
**One high-impact change:** related cuts on watch (same pack + tag overlap ranking).

### EXECUTE
- `relatedEpisodes` / `paintWatchRelated`; `#watch-related` grid
- CSS + tests; CI module list

### TEST
```
Full local CI → 267 OK + pip-audit clean
```

### RESULT
Explorers discover counterfactual siblings and thematically related episodes without returning to Library.

---

## Iteration 90 — 2026-07-21

### OBSERVE
Main green. Re-rendering the same image prompts re-paid SDXL+ESRGAN on Dawes (shared low-VRAM with Ollama).

### PLAN
**One high-impact change:** content-addressed still cache for identical prompt/geometry/model keys.

### EXECUTE
- `ImageClient.still_cache_key` / hit-store under `outputs/still_cache` (default on for remote)
- Env knobs; health `still_cache` flag; unit tests; image tests isolate with ANOR_STILL_CACHE=0

### TEST
```
Full local CI → 269 OK + pip-audit clean
```

### RESULT
Identical archival stills skip the GPU path on subsequent video jobs — lower fleet cost.

---

## Iteration 91 — 2026-07-21

### OBSERVE
Main green after still cache. VO re-synthesis still re-paid TTS for identical scripts on re-renders.

### PLAN
**One high-impact change:** content-addressed TTS cache parallel to still cache.

### EXECUTE
- `TTSClient.tts_cache_key` / hit-store under `outputs/tts_cache` (default on for non-mock)
- Env knobs; health `tts_cache`; unit tests with ANOR_TTS_CACHE=0 isolation

### TEST
```
Full local CI → 271 OK + pip-audit clean
```

### RESULT
Identical narration clips skip remote/system TTS on subsequent video jobs.

---

## Iteration 92 — 2026-07-21

### OBSERVE
Main green at 93f465b (TTS cache). Mid-flight Ken Burns clip cache was already in `pipeline/video_pipeline.py` + `.env.example` but untested/uncommitted — re-mux cost still paid on identical still+audio re-renders.

### PLAN
**One high-impact change:** finish content-addressed Ken Burns clip cache — unit tests, health flag, full CI, ship.

### EXECUTE
- Kept `clip_cache_key` / hit-store under `outputs/clip_cache` (size+mtime+head fingerprint of still+audio + frame geometry)
- Default on via `ANOR_CLIP_CACHE=1`; dir override documented in `.env.example`
- Health detail reports `clip_cache`
- Tests: key stability, hit skips ffmpeg encode (sidecar + no `-vf` encode), disabled path encodes without storing

### TEST
```
Full local CI → 274 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Identical Ken Burns muxes skip ffmpeg zoompan on subsequent video jobs when still+audio fingerprints match — completes the still → TTS → clip cost ladder.

---

## Iteration 93 — 2026-07-21

### OBSERVE
Main green at 709feff after still/TTS/clip cost ladder. Image path + mock fallback solid. Freemium home still had no return path to recently opened cuts — Explorers lose context between sessions.

### PLAN
**One high-impact change:** client-only Continue watching strip for freemium retention.

### EXECUTE
- `FHFreemium.recordWatch` / `recentWatches` / `clearWatchHistory` (localStorage, de-duped, max 8)
- Home `#home-continue` grid + Clear; painted from catalog match
- Record on watch open; CSS + static asset needles

### TEST
```
Full local CI → 274 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers and Scholars resume recent cuts from the home page without accounts or analytics — privacy-preserving freemium polish.

---

## Iteration 94 — 2026-07-21

### OBSERVE
Main green after Continue watching. Library filters only sorted by speculation/host availability — Explorers could not list titles they already unlocked vs preview-only.

### PLAN
**One high-impact change:** freemium access chips in Library (Unlocked / Preview only).

### EXECUTE
- `filterLibraryVideos` modes `unlocked` (full + claimable_full) and `preview`
- HTML filter chips + status labels + empty-state guidance
- Library search tests for access chips

### TEST
```
Full local CI → 275 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can browse what they can finish now vs paywall-gated previews without hunting pills on every card.

---

## Iteration 95 — 2026-07-21

### OBSERVE
Main green after freemium library access filters. Social pipeline still missing drafts for four public choice cuts (ELO-013 surface_delay, ELO-001 forks, ELO-003 recon) — catalog-complete packs without human-gate captions.

### PLAN
**One high-impact change:** batch-009 gap-fill social drafts + regression that every public choice has a draft file.

### EXECUTE
- `content/drafts/batch-009/` — four ELO-*.md cuts, Postiz draft JSON, README
- Root drafts README: batch-008 + batch-009 index
- Tests: batch-009 present/pack-only; `test_every_public_choice_has_a_draft_file`; speculation labels

### TEST
```
Full local CI → 278 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Every public pack choice now has a human-gate draft under content/drafts/ — never auto-publish; Ryan still flips draft→schedule.

---

## Iteration 96 — 2026-07-21

### OBSERVE
Main green after full social-draft coverage. Freemium SPA had no crawl policy or sitemap — discovery depended on manual share only; `/api/*` and media still waste crawl budget if bots wander.

### PLAN
**One high-impact change:** public `/robots.txt` + `/sitemap.xml` for freemium SEO.

### EXECUTE
- `build_robots_txt` / `build_sitemap_xml` / `public_base_url` (ANOR_PUBLIC_URL or Host)
- Sitemap: home, library, pricing, studio, each pack, each catalog episode (hash deep links)
- robots: Allow SPA/static; Disallow /api/ and /media/; Sitemap absolute URL
- index.html sitemap link; .env.example; tests + CI module list

### TEST
```
Full local CI → 284 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Crawlers can find the freemium surface and public pack/episode deep links without indexing job/API noise.

---

## Iteration 97 — 2026-07-21

### OBSERVE
Main green after robots/sitemap. Continue watching only reopened episodes at 0:00 — Explorers lost mid-preview progress; full unlocks restarted too.

### PLAN
**One high-impact change:** local resume playback position for freemium watch.

### EXECUTE
- `FHFreemium.saveWatchPosition` / `getWatchPosition` / `clearWatchPosition` (localStorage, min 5s, clear near end)
- Player: throttle save on timeupdate/pause; seek on loadedmetadata; clear on ended
- Clamp resume inside Explorer preview ceiling; Clear continue also wipes positions

### TEST
```
Full local CI → 284 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Watch sessions resume mid-cut on the same device without accounts or analytics — freemium retention for previews and free unlocks.

---

## Iteration 98 — 2026-07-21

### OBSERVE
Main green after resume playback. Library/home episode grids followed catalog insertion order (Cannae → 1962 → … → Dunkirk), not museum chronology — packs already sorted chronologically on home.

### PLAN
**One high-impact change:** chronological sort for catalog episode cards (era → pack → documented first).

### EXECUTE
- `videosChronological` shared helper
- Library filter results + home episode grid use it
- Status line notes chronological order; static/library tests

### TEST
```
Full local CI → 284 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Freemium library and home read as a decision museum timeline instead of a file-append dump.

---

## Iteration 99 — 2026-07-21

### OBSERVE
Main green after chronological library. Public canon had no interwar Munich decision pack; freemium catalog and social drafts stopped at 10 packs / 30 cuts. ELO-001 historical was also unfeatured.

### PLAN
**One high-impact change:** ship public pack ELO-011 (Munich 1938) end-to-end — pack, catalog, drafts, docs.

### EXECUTE
- `scenarios/public/ELO-011.json` — historical / stand_firm / limited_deal (labeled)
- Catalog: 3 video rows + feature ELO-001-historical
- `content/drafts/batch-010/` human-gate captions + Postiz skeleton
- README / PIPELINE / social tests for batch-010

### TEST
```
Full local CI → 286 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
New monetizable decision pack on Munich with freemium library coverage and draft-only social pipeline; mock-media path unchanged.

---

## Iteration 100 — 2026-07-21

### OBSERVE
Main green after ELO-011. Still cache keyed only on prompt/geometry/model/upscale — changing ANOR_COMFY_STEPS/CFG/sampler could return a still rendered under different quality knobs (wrong cache hit, stale look) or force operators to wipe cache manually.

### PLAN
**One high-impact change:** include Comfy quality fingerprint in still-cache keys (seed still excluded for cost sharing).

### EXECUTE
- `ImageClient.comfy_quality_fingerprint` (steps/CFG/sampler/scheduler)
- `still_cache_key(..., quality=)` wired for comfy backend only
- Tests for quality sensitivity; .env.example note

### TEST
```
Full local CI → 287 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Still cache remains a GPU cost saver for identical prompts, without serving wrong quality after knob changes.

---

## Iteration 101 — 2026-07-21

### OBSERVE
Main green after still-cache quality keys. Home hero always took `featured[0]` (catalog insertion order) — freemium discovery stuck on the same pack every visit despite 11 featured historical cuts.

### PLAN
**One high-impact change:** daily rotating featured hero (`pickFeaturedOfDay`).

### EXECUTE
- UTC date hash over chronological featured pool
- Hero badge "Featured today"; static/library needles

### TEST
```
Full local CI → 287 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers see a different featured decision each day without server state or analytics — broader freemium discovery of the public catalog.

---

## Iteration 102 — 2026-07-21

### OBSERVE
Main green after daily featured hero. Resume position was silent — library/home/continue cards gave no visual cue that mid-watch progress exists, so freemium retention depended on muscle memory.

### PLAN
**One high-impact change:** "Resume N%" pills on episode cards when local watch position exists.

### EXECUTE
- `resumePillHtml` + `video-card-resume` / `video-card-has-resume` styles
- Wired into `videoCardHtml` for library, home, continue, related
- Static asset needles

### TEST
```
Full local CI → 287 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers see which cuts have mid-episode progress on this device and re-open with confidence — still client-only, no analytics.

---

## Iteration 103 — 2026-07-21

### OBSERVE
Main green after Resume pills. Library still had no way to list only mid-watch cuts — Explorers hunted resume badges among 33 titles.

### PLAN
**One high-impact change:** Library filter chip "In progress" for local mid-episode positions.

### EXECUTE
- `filterLibraryVideos` mode `in_progress` via `getWatchPosition`
- Sort most-recently-watched first; status + empty-state copy
- HTML chip + library/static tests

### TEST
```
Full local CI → 287 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Freemium library can focus on unfinished cuts on this device — pairs with Resume pills and Continue watching.

---

## Iteration 104 — 2026-07-21

### OBSERVE
Main green after In progress library filter. Clip cache keyed still+audio+frame size+fps only — zoom max / ramp / min-scale were hardcoded and not in the key, so quality knob changes (or future env tuning) could reuse wrong Ken Burns muxes.

### PLAN
**One high-impact change:** Ken Burns quality fingerprint in clip-cache keys + env-tunable zoom/FPS knobs.

### EXECUTE
- `ken_burns_params` / `ken_burns_quality_fingerprint` (fps, zoom_max, zoom_delta, min_scale)
- Wire into `ken_burns_filter` + `clip_cache_key`
- Tests for quality sensitivity; .env.example knobs

### TEST
```
Full local CI → 288 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Clip cache remains an ffmpeg cost saver without serving stale motion after Ken Burns quality changes.

---

## Iteration 105 — 2026-07-21

### OBSERVE
Main green after clip-cache quality keys. Opening Studio without a deep link always fell back to `scenarios[0]` (catalog/API order), not the last pack the Explorer worked on — weak freemium return path after library/watch retention work.

### PLAN
**One high-impact change:** remember last Studio pack in localStorage and restore on bare `#/studio`.

### EXECUTE
- `saveLastStudioScenario` / `loadLastStudioScenario` / `resolveStudioScenarioId`
- Prefer route id → last device pack → chronological first public pack
- Persist on every successful studio open; static needles

### TEST
```
Full local CI → 288 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers reopen Studio on the same decision pack across visits without accounts — device-only, no analytics.

---

## Iteration 106 — 2026-07-21

### OBSERVE
Main green after last Studio pack recall. Reopening a pack still defaulted to the historical branch unless a session fork/job restored a choice — Explorers lost their last counterfactual selection across visits.

### PLAN
**One high-impact change:** remember last Studio choice per pack in localStorage.

### EXECUTE
- `saveLastStudioChoice` / `loadLastStudioChoice` map (`fh:lastStudioChoices`)
- Restore remembered choice when opening a pack; save on every `selectChoice`
- Still overridden by last-fork / active video job when present; static needles

### TEST
```
Full local CI → 288 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Studio restores both pack and branch on freemium return visits — device-only, no analytics.

---

## Iteration 107 — 2026-07-21

### OBSERVE
Main green after Studio choice recall. Public catalog lacked a Napoleonic culmination pack between Rubicon/Cannae ancient set and modern wars — freemium library had a chronological gap around 1815.

### PLAN
**One high-impact change:** ship public pack ELO-012 (Waterloo 1815) end-to-end.

### EXECUTE
- `scenarios/public/ELO-012.json` — historical / break_contact / commit_early (labeled)
- Catalog: 3 video rows (featured historical); `content/drafts/batch-011/` human-gate
- README / PIPELINE / social tests for batch-011

### TEST
```
Full local CI → 290 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
New monetizable Waterloo decision pack with freemium catalog coverage and draft-only social pipeline; mock-media path unchanged.

---

## Iteration 108 — 2026-07-21

### OBSERVE
Main green after ELO-012. Clip-cache quality fingerprint covered motion knobs only — x264 tune and AAC bitrate were hardcoded and not in the key, so encode-quality changes could reuse wrong muxes. Health did not surface Ken Burns quality for fleet ops.

### PLAN
**One high-impact change:** include encode params in clip quality fingerprint; report in health; env-tunable tune/bitrate.

### EXECUTE
- `clip_encode_params` (validated x264 tune + audio bitrate)
- Wire into `_ken_burns_clip` ffmpeg args + `ken_burns_quality_fingerprint`
- Health `ken_burns_quality`; tests; .env.example

### TEST
```
Full local CI → 290 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Clip cache stays correct across encode-quality tuning; operators can read motion+encode fingerprint from health detail.

---

## Iteration 109 — 2026-07-21

### OBSERVE
Main green after encode quality in clip cache. Home Studio CTA always said "Open the fork studio" → bare `#/studio` even when a last pack was stored — freemium return path required remembering the pack id.

### PLAN
**One high-impact change:** home hero Studio button resumes last pack when present.

### EXECUTE
- `paintHomeStudioCta` — `#hero-studio` deep-links to `#/studio/{last}` with "Resume Studio · {id}"
- Falls back to open Studio when no last pack; static needles

### TEST
```
Full local CI → 290 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Home hero surfaces device Studio continuity next to Continue watching / featured rotation.

---

## Iteration 110 — 2026-07-21

### OBSERVE
Main green after home Resume Studio CTA. Chronological library still rendered a flat card grid — eras were only pills on cards, so the freemium museum timeline was hard to scan as history grows (36 cuts).

### PLAN
**One high-impact change:** era section headers in the chronological library grid.

### EXECUTE
- `libraryGridHtml({ groupByEra })` inserts `.library-era-head` between era groups
- Skip grouping for In progress (recency order)
- CSS + library tests

### TEST
```
Full local CI → 290 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Library reads as a dated museum ledger (216 BC → … → 1962) instead of an undifferentiated card wall.

---

## Iteration 111 — 2026-07-21

### OBSERVE
Main green after library era headers. Cost ladder (still/TTS/clip caches) was invisible in render outputs — operators could not tell from build.json which segments skipped GPU/TTS/ffmpeg.

### PLAN
**One high-impact change:** record per-segment cache hits + summary in build.json.

### EXECUTE
- `media_cache_hit_sidecar` for still/tts/clip hit notes
- Segment fields `still_cache_hit` / `tts_cache_hit` / `clip_cache_hit`
- Top-level `cache: { still_hits, tts_hits, clip_hits, segments }`
- Unit tests for sidecar helper + render_mock_mp4 assertions

### TEST
```
Full local CI → 291 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Each video render leaves auditable cost-ladder accounting for fleet ops without logging secrets or absolute paths.

---

## Iteration 112 — 2026-07-21

### OBSERVE
Main green after build.json cache accounting. Studio only celebrated full disk-cache hits — ladder assists (still/TTS/clip reuse mid-render) were invisible to freemium operators and Explorers. Home episode grid also lacked the new era headers.

### PLAN
**One high-impact change:** surface cost-ladder cache summary on video job results + home era grouping.

### EXECUTE
- `VideoBuildResult.cache` → job `result.cache` (public ints only)
- Complete message / Studio note / toast when any hits > 0
- Home `#home-video-grid` uses `libraryGridHtml({ groupByEra: true })`
- Static needles for Cost ladder UI

### TEST
```
Full local CI → 291 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Studio shows when a render reused stills/TTS/Ken Burns work; home episodes read as a museum timeline matching Library.

---

## Iteration 113 — 2026-07-21

### OBSERVE
Main green after cost-ladder Studio feedback. Chronological library had era section heads but no jump navigation — long museum lists still required manual scrolling through 12 eras / 36 cuts.

### PLAN
**One high-impact change:** era jump chips that scroll to library era sections.

### EXECUTE
- `eraSectionId` on `.library-era-head` anchors
- `#library-era-jumps` chip bar (hidden when &lt;2 eras or In progress)
- Smooth scroll + flash highlight; CSS + library tests

### TEST
```
Full local CI → 291 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can jump 216 BC → 1815 → 1962 without scrubbing the full freemium catalog.

---

## Iteration 114 — 2026-07-21

### OBSERVE
Main green after era jump chips. Video builds recorded ladder cache hits but not deliverable size/duration — ops and Studio could not show how heavy a finished cut was without probing the filesystem.

### PLAN
**One high-impact change:** record final MP4 bytes + duration in build.json and job results; show in Studio.

### EXECUTE
- `out_mp4_bytes` / `duration_s` on meta + `VideoBuildResult`
- Job `result.bytes` / `result.duration_s` (public-safe)
- Studio "Deliverable: Xm Ys · Z MB" note; pipeline + static tests

### TEST
```
Full local CI → 291 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Every render leaves auditable size/runtime metrics for cost ops and freemium Studio feedback without path leaks.

---

## Iteration 115 — 2026-07-21

### OBSERVE
Main green after b348f96 (deliverable size/duration on full renders). Disk-cache short-circuit jobs only set `result.cached=true` — no `bytes` / `duration_s` / ladder `cache` summary — so Studio's Deliverable note stayed empty on the freemium happy path (re-open existing cut). Catalog available rows also lacked runtime/size despite sibling `build.json`.

### PLAN
**One high-impact change:** enrich disk-cache job hits and catalog available rows with deliverable metrics from `build.json`.

### EXECUTE
- `read_cached_video_metrics(mp4)` — public-safe `bytes`, `duration_s`, ladder `cache` from sibling build.json (MP4 size fallback)
- Enqueue cache-hit path merges metrics into job `result` (same shape as full render)
- `build_catalog_payload` attaches `bytes` / `duration_s` when media is available
- Unit tests: helper, cache-hit job, API cache_hit, catalog enrichment

### TEST
```
Full local CI → 294 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Cache-hit Studio jobs and freemium catalog rows now surface deliverable size/runtime without re-rendering or path leaks.

---

## Iteration 116 — 2026-07-21

### OBSERVE
Main green after 682f80a (catalog + disk-cache job metrics). Library cards and watch still showed static `runtime_label` ("~4 min draft") even when host `duration_s` / `bytes` were on the catalog payload — freemium Explorers could not see actual deliverable cost/size at browse time.

### PLAN
**One high-impact change:** prefer host-measured duration/size on library and watch surfaces.

### EXECUTE
- `videoRuntimeLabel(v)` + `formatBytes` in app.js
- Library cards + watch pills use measured metrics when present; fall back to authored `runtime_label`
- Studio deliverable note reuses `formatBytes`
- Static + library search contract tests

### TEST
```
Full local CI → 295 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Freemium library/watch show real runtime and size for on-host cuts instead of stale draft estimates.

---

## Iteration 117 — 2026-07-21

### OBSERVE
Main green after 44d0ec8. Clip cache already cost-laddered re-muxes but grew unbounded on grind hosts (~625 entries / ~35MB locally, no max). Still/TTS caches smaller; freemium runtime polish shipped. Engine disk budget was the gap.

### PLAN
**One high-impact change:** LRU soft cap for Ken Burns clip cache (mtime, touch-on-hit).

### EXECUTE
- `clip_cache_max_bytes` / `prune_clip_cache` (ANOR_CLIP_CACHE_MAX_MB default 512; 0 = unlimited)
- Prune after each successful store; touch cache file on hit for true LRU
- Health reports `clip_cache_max_mb` (no paths)
- `.env.example` + unit tests for prune order and default

### TEST
```
Full local CI → 297 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Long grind hosts keep clip-cache reuse without unbounded disk growth; ops can see the soft budget on health.

---

## Iteration 118 — 2026-07-21

### OBSERVE
Main green after 17e9f3e (clip-cache LRU). Still and TTS content-addressed caches still unbounded — SDXL+ESRGAN stills are multi-MB and will dominate disk once Comfy path is exercised hard on grind hosts.

### PLAN
**One high-impact change:** LRU soft caps for still + TTS caches (same pattern as clip).

### EXECUTE
- Shared `prune_media_cache_dir` + `_cache_max_bytes` in clients.py
- `ANOR_STILL_CACHE_MAX_MB` default 1024; `ANOR_TTS_CACHE_MAX_MB` default 256; 0 = unlimited
- Prune after store; touch on hit; health `still_cache_max_mb` / `tts_cache_max_mb`
- `.env.example` + unit tests

### TEST
```
Full local CI → 301 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Full cost ladder (still / TTS / clip) has disk budgets so long grind + real Comfy stills cannot fill the host unbounded.

---

## Iteration 119 — 2026-07-21

### OBSERVE
Main green after 3f08272 (still/TTS/clip soft caps). Health reported max_mb budgets but not live usage — ops could not see how full cost-ladder caches were vs budget without shell access.

### PLAN
**One high-impact change:** report still/TTS/clip cache file counts + used MB on pipeline health (detail path only via existing privacy gate).

### EXECUTE
- `media_cache_dir_usage` helper (public-safe files/bytes, no paths)
- healthcheck: `*_cache_files` + `*_cache_used_mb` for still, tts, clip
- Unit tests for usage helper + health keys; privacy tests still slim by default

### TEST
```
Full local CI → 302 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Operators see cost-ladder disk usage vs soft caps on detailed health without path leaks or public recon expansion.

---

## Iteration 120 — 2026-07-21

### OBSERVE
Main green after f76e3ee (cache usage on health). Freemium library kept museum chronological order but mixed host inventories buried playable cuts among "not on host" cards — Explorers on grind fleets with partial renders scrolled past ready media.

### PLAN
**One high-impact change:** prefer on-host media within chronological library/home order; mark ready cuts when inventory is mixed.

### EXECUTE
- `videosChronological`: available before missing (after era → pack → documented)
- Library status: "chronological (on-host first within era)"
- `video-card-on-host` pill only when catalog mixes available/unavailable
- Static + library contract tests

### TEST
```
Full local CI → 302 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Partial host inventories surface playable cuts first within each era without breaking the museum timeline.

---

## Iteration 121 — 2026-07-21

### OBSERVE
Main green after e37e8c8. Watch player was fixed at 1× — documentary / archival VO episodes reward slower or faster listening, and freemium Explorers had no device-local speed control (browser native menus are inconsistent).

### PLAN
**One high-impact change:** watch playback speed chips (0.75×–1.5×) with localStorage preference.

### EXECUTE
- `#player-speed` control bar under the stage (0.75 / 1 / 1.25 / 1.5)
- `fh:playbackRate` load/save; re-apply on media metadata load
- CSS + static asset contract tests

### TEST
```
Full local CI → 302 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can skim or slow documentary cuts with a preference that sticks on-device and never hits the network.

---

## Iteration 122 — 2026-07-21

### OBSERVE
Main green after 79d8215 (playback speed). Watch still relied on native browser chrome for seek/play — inconsistent across mobile/desktop, and J/K-style skimming was missing for documentary VO.

### PLAN
**One high-impact change:** watch keyboard shortcuts with Explorer preview ceiling respect.

### EXECUTE
- `seekWatchPlayer` / `toggleWatchPlayback` / `bindWatchKeyboardShortcuts`
- Space/K play-pause; J/← −10s; L/→ +10s (no capture in inputs; disabled when gate/paywall open)
- Forward seek clamps to freemium preview ceiling + toast
- `#player-kbd-hint` + CSS; static contract tests

### TEST
```
Full local CI → 302 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can keyboard-skim narrated cuts without bypassing the freemium preview gate.

---

## Iteration 123 — 2026-07-21

### OBSERVE
Main green after 09b119e (watch seek/play keys). Mute and fullscreen still required browser chrome; mute did not stick across episodes on the same device.

### PLAN
**One high-impact change:** M mute (device preference) + F fullscreen on the watch player.

### EXECUTE
- `toggleWatchMute` / `applyPlaybackMuted` with `fh:playbackMuted`
- `toggleWatchFullscreen` (stage → video → webkitEnterFullscreen)
- Wire into watch keyboard map; re-apply mute on media load
- Hint text + static contract tests

### TEST
```
Full local CI → 302 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Watch keyboard suite covers play, seek, mute, and fullscreen without network or freemium-gate bypass.

---

## Iteration 124 — 2026-07-21

### OBSERVE
Main green after b263372 (mute/fullscreen). Watch had related cards and keyboard seek but no chronological prev/next binge path — Explorers finished a cut and had to return to Library to continue the museum timeline.

### PLAN
**One high-impact change:** chronological prev/next episode navigation on watch (buttons + keys).

### EXECUTE
- `adjacentEpisodes` / `goAdjacentEpisode` / `paintWatchAdjacent` using `videosChronological`
- `#watch-adjacent` prev/next + position label
- Keys `[`/`p` previous, `]`/`n` next (work even when freemium gate is open)
- CSS + static/related contract tests

### TEST
```
Full local CI → 303 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can binge the freemium library in museum order without dumping back to the grid after each cut.

---

## Iteration 125 — 2026-07-21

### OBSERVE
Main green after 38e6433 (prev/next binge nav). Full playthrough still only pulsed Studio — no post-end next-cut CTA and no optional auto-advance, so binge flow stalled at episode end.

### PLAN
**One high-impact change:** end-of-episode next-cut CTA + optional device-local auto-next.

### EXECUTE
- `handleWatchEpisodeEnded` with next button in watch quota note
- `fh:autoNextEpisode` checkbox (3s advance; off by default; never on Explorer preview)
- Clear auto-next timer on route change; pulse Next when a cut finishes
- Static + related contract tests

### TEST
```
Full local CI → 303 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Full-access viewers can continue the museum timeline immediately after a cut ends, with optional hands-free auto-next on-device only.

---

## Iteration 126 — 2026-07-21

### OBSERVE
Main green after d31d7f3 (auto-next binge). SPA already refreshed og:title/description per route, but og:url and link[rel=canonical] stayed empty/static — shared episode previews and freemium discovery lost deep-link URLs.

### PLAN
**One high-impact change:** route-aware og:url + canonical for SPA deep links.

### EXECUTE
- `publicShareUrl` / `routeHashPath` aligned with episode share payload shape
- `syncShareMeta` updates og:url and canonical on every route
- Shell meta/link tags in index.html; share + static SEO tests

### TEST
```
Full local CI → 304 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Watch/studio/library routes emit absolute deep-link URLs in share meta without secrets or path leaks.

---

## Iteration 127 — 2026-07-21

### OBSERVE
Main green after 349d339 (og:url/canonical). Binge next/prev walked strict chronological neighbors — on partial grind hosts that landed Explorers on "not on host" dead ends and stalled auto-next.

### PLAN
**One high-impact change:** binge adjacent nav prefers playable on-host cuts (skip missing media).

### EXECUTE
- `adjacentEpisodes({ preferAvailable })` walks past `available === false`
- Next/prev/auto-next use on-host binge; toast when skips occur
- Position label notes "on-host binge" when inventory is mixed
- Related + static contract tests

### TEST
```
Full local CI → 304 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Partial host inventories binge onto ready media instead of dead "not on host" stops.

---

## Iteration 128 — 2026-07-21

### OBSERVE
Main green after ab9251e (on-host binge). Studio offered Open MP4 after renders, but the freemium watch page did not — Explorers with host media had no direct deliverable link beside Share/Studio.

### PLAN
**One high-impact change:** Open MP4 control on watch when media is available on host.

### EXECUTE
- `#watch-open-mp4` + `paintWatchOpenMp4` (public `/media/videos/…`, download filename from id)
- Hidden when unavailable; title includes measured runtime/size when known
- Share + static contract tests

### TEST
```
Full local CI → 305 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Watch matches Studio’s host-deliverable affordance for on-host cuts without path leaks or auto-publish.

---

## Iteration 129 — 2026-07-21

### OBSERVE
Main green after 8bd433c. Freemium surface and cost ladder were solid; public catalog still lacked a US Civil War decision point (eras jumped 1815 → 1914). Social drafts and freemium library need matching pack coverage for monetizable expansion.

### PLAN
**One high-impact change:** ship public pack ELO-014 (Gettysburg 1863) end-to-end with catalog + human-gate drafts.

### EXECUTE
- `scenarios/public/ELO-014.json` — historical / refuse_charge / wide_turn (labeled)
- Catalog rows (3), `batch-012` drafts + postiz skeleton, README/PIPELINE tables
- Social draft regression tests for batch-012

### TEST
```
Full local CI → 307 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Public library gains a labeled Gettysburg decision point with draft-only social captions; no MANDOS, no auto-publish.

---

## Iteration 130 — 2026-07-21

### OBSERVE
Main green after 5f53780 (ELO-014). Partial host inventories left "not on host" cards and watch pages with a vague Studio CTA — no deep link to the exact branch, so operators re-picked choice before queueing a render.

### PLAN
**One high-impact change:** Studio deep links with scenario + choice from missing-media surfaces.

### EXECUTE
- `openStudioForCut` → `#/studio/{scenario}/{choice}`
- Library unavailable cards: "Queue in Studio" button (preselects branch)
- Watch unavailable: Studio button becomes "Queue this cut in Studio"
- `renderStudio` accepts choice hash segment; route/SEO share meta include choice
- Tests for queue CTA + static needles

### TEST
```
Full local CI → 308 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Missing media flows land in Studio on the right branch for one-click queue — lower friction for freemium partial inventories.

---

## Iteration 131 — 2026-07-21

### OBSERVE
Main green after c7365c5 (Studio deep links). Missing-media CTAs preselected the branch but left operators to hunt Queue video — friction on partial host inventories after landing in Studio.

### PLAN
**One high-impact change:** one-shot queue-video intent after missing-media deep links.

### EXECUTE
- `fh:intentQueueVideo` session flag from `openStudioForCut({ queueIntent })`
- `applyQueueVideoIntent` pulses Queue video + dock, focuses for Scholars
- Library/watch missing-media paths set queueIntent
- Static + library contract tests

### TEST
```
Full local CI → 308 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Missing-media → Studio flow ends on a highlighted Queue video control so Scholars can finish the render without re-finding the button.

---

## Iteration 132 — 2026-07-21

### OBSERVE
Main green after 85e0cda (queue intent pulse). Studio render-complete UI led with raw Open MP4 / library — freemium product loop (render → watch player with resume/speed/share) was one click further than it should be.

### PLAN
**One high-impact change:** primary Watch episode CTA after video job completion.

### EXECUTE
- Completed job panel: primary `Watch episode` → `#/watch/{id}` (pulse), Open MP4 secondary
- Refresh catalog + repaint studio media strip after success
- Toasts mention Watch episode; static needles

### TEST
```
Full local CI → 308 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Render → freemium watch is one primary click; raw MP4 remains available without becoming the default path.

---

## Iteration 133 — 2026-07-21

### OBSERVE
Main green after 16e03b2 (Watch episode CTA). Freemium SPA had SEO, share, and install-adjacent chrome (theme-color, apple-touch-icon) but no Web App Manifest — mobile/desktop "install app" and home-screen shortcuts were missing.

### PLAN
**One high-impact change:** add public site.webmanifest for installable freemium surface.

### EXECUTE
- `webapp/static/site.webmanifest` (name, start_url, Library/Studio shortcuts, SVG icons)
- `rel=manifest` in index.html
- Serve `.webmanifest` as `application/manifest+json` with static cache
- Static + HTTP path tests (no secrets/MANDOS)

### TEST
```
Full local CI → 309 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can install Forked History as a standalone shell with Library/Studio shortcuts; no service worker, no offline secrets.

---

## Iteration 134 — 2026-07-21

### OBSERVE
Main green after 10a87d0 (webmanifest). Studio keyboard covered fork/LLM only — Scholars completing missing-media deep links still needed the mouse for Queue video after the pulse CTA.

### PLAN
**One high-impact change:** Ctrl/⌘+Shift+V queues video render from Studio keyboard map.

### EXECUTE
- `bindStudioKeyboardShortcuts` handles Shift+V → `queueVideoRender()`
- Studio kbd hint + btn-video title updated
- Static contract tests

### TEST
```
Full local CI → 309 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Scholar keyboard path: deep-link branch → Ctrl+Shift+V queue (paywall still enforced for Explorers).

---

## Iteration 135 — 2026-07-21

### OBSERVE
Main green after 94d911a. Episode share lived only on the watch page — library/home/related grids had no one-tap deep-link share for freemium discovery.

### PLAN
**One high-impact change:** Share control on episode cards (library, home, related).

### EXECUTE
- `video-card-share` on every catalog card → `shareEpisode` (stopPropagation)
- Card action row layout (runtime/queue + Share)
- CSS + share/library/static tests (no auto-publish wording that fails the guard test)

### TEST
```
Full local CI → 310 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Explorers can share labeled episode deep links from any grid without entering watch first; social stays human-gated.

---

## Iteration 136 — 2026-07-21

### OBSERVE
Main green after fa64cd0 (card Share). Watch keyboard covered play/seek/mute/full/episode nav but not share — freemium deep-link sharing still required the Share episode button.

### PLAN
**One high-impact change:** S key shares the current watch episode deep link.

### EXECUTE
- `bindWatchKeyboardShortcuts`: S → `shareEpisode` (works with preview gate open)
- Player kbd hint + watch-share title
- Static + share tests

### TEST
```
Full local CI → 310 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Watch keyboard suite includes share for freemium discovery without leaving the player.

---

## Iteration 137 — 2026-07-21

### OBSERVE
Main green after e1eab17. Studio media strip only said "MP4 on this host" — Scholars could not see host-measured runtime/size before deciding to Force re-render (GPU cost).

### PLAN
**One high-impact change:** surface deliverable metrics on the Studio media strip.

### EXECUTE
- `paintStudioMediaStrip` shows `videoRuntimeLabel` (duration/size from catalog/build.json)
- Open MP4 link next to Open episode when media is present
- Queue video tooltip includes host deliverable metrics when available
- Static contract tests

### TEST
```
Full local CI → 310 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Scholars see on-host deliverable cost in Studio before re-paying the cost ladder.

---

## Iteration 138 — 2026-07-21

### OBSERVE
Main green after e4d9205. Daily "Featured today" hero rotated over all featured rows including missing-media cuts — partial grind hosts could hero a dead "not on host" episode.

### PLAN
**One high-impact change:** prefer on-host media in pickFeaturedOfDay.

### EXECUTE
- Filter featured/pool to `available !== false` when any playable cuts exist
- Deterministic daily hash unchanged within the filtered pool
- Library + static contract tests

### TEST
```
Full local CI → 310 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Home hero prefers playable host inventory while staying a stable daily rotation.

---

## Iteration 139 — 2026-07-21

### OBSERVE
Main green after 21546d3 (featured on-host). Continue watching kept pure recency — missing-media cuts could lead the home strip on partial grind hosts.

### PLAN
**One high-impact change:** prefer on-host playable cuts first in Continue watching.

### EXECUTE
- `paintHomeContinue` splits playable vs missing; playable first, recency within each bucket
- Static contract needle for ordering helper

### TEST
```
Full local CI → 310 OK + compileall + pip-audit clean + sim pytest 3 passed
```

### RESULT
Home continue strip leads with resume-able host media; missing cuts stay available via Queue in Studio.

---

## Iteration 140 — 2026-07-21

### OBSERVE
Main green after fd78a8a (continue-watching on-host). Content gap: ELO-015 Appomattox scenario JSON existed untracked without catalog rows, social drafts, or docs — freemium-heavy stretch left Civil War endgame pack incomplete.

### PLAN
**One high-impact change:** ship public pack ELO-015 (Appomattox 1865) end-to-end — catalog, batch-013 human-gate drafts, docs, social tests.

### EXECUTE
- Keep `scenarios/public/ELO-015.json` (historical / harsher_terms / delay_for_orders)
- Append 3 catalog videos (featured historical cut)
- `content/drafts/batch-013/*` markdown + postiz-drafts.json + README (status draft, no auto-publish)
- Update scenarios/public/README, PIPELINE.md, content/drafts/README
- Extend scripts/tests/test_social_drafts.py for batch-013 + labeled cuts

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Public Appomattox pack live for site/library + human-gate social drafts. No MANDOS. No auto-publish.

---

## Iteration 141 — 2026-07-21

### OBSERVE
Main green after 7555a33 (ELO-015 Appomattox). Comfy image path + lock already solid; freemium binge nav showed only global chronological index — easy to lose place inside a 3-branch decision pack.

### PLAN
**One high-impact change:** show pack branch position on the watch adjacent bar (branch N/M of this decision).

### EXECUTE
- `packBranchPosition(video)` — same-scenario cuts in museum order
- `paintWatchAdjacent` appends `branch i/n of this decision`
- Static contract needles in related + static asset tests

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Watch binge UX surfaces decision-pack progress alongside library chronology.

---

## Iteration 142 — 2026-07-21

### OBSERVE
Main green after 6c15cc0 (pack branch position). End-of-cut copy treated every finish the same — finishing the last branch of a 3-cut decision felt identical to finishing a middle branch.

### PLAN
**One high-impact change:** freemium pack-completion messaging when the last branch of a decision ends (decisionComplete).

### EXECUTE
- Detect onLastBranch + nextLeavesPack via packBranchPosition + adjacent next
- End note: "every branch of this decision" + Next branch vs Next era labels
- Toasts + Studio pulse after full pack; static contract needles

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Watch completion celebrates full decision packs and points to next era or Studio.

---

## Iteration 143 — 2026-07-21

### OBSERVE
Main green after 7df7f4b (pack completion UX). Clip-cache ladder already solid with tests. Content risk remains: only 3 sample packs validated in CI; mid-ship packs (scenario without catalog) could reach main again.

### PLAN
**One high-impact change:** CI integrity for all public packs + catalog ↔ choice coverage.

### EXECUTE
- `test_all_public_packs_pass_validation` — every ELO-*.json via validate + load_scenario
- `test_list_scenarios_covers_every_public_file`
- `test_catalog_matches_public_packs` — id convention, file path, speculation match, no missing cuts

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Incomplete public packs fail CI before freemium/library/social ship.

---

## Iteration 144 — 2026-07-21

### OBSERVE
Main green after 41a5bcb (catalog integrity CI). ELO-015 complete. Related strip scored same-pack first but only lightly penalized missing media — cross-pack suggestions could lead with "not on host" on partial grind inventories.

### PLAN
**One high-impact change:** partition relatedEpisodes — same-pack → on-host others → missing others.

### EXECUTE
- After score sort, stable partition into samePack / playableOther / missingOther
- paintWatchRelated note when cross-pack on-host fills
- Static contract needles

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Related discovery keeps pack siblings for Studio queue and prefers playable host media for nearby topics.

---

## Iteration 145 — 2026-07-21

### OBSERVE
Main green after c38c4a3 (related on-host). Library still defaulted to "all" — partial grind hosts surface dozens of not-on-host cards before playable inventory.

### PLAN
**One high-impact change:** smart first-visit Library default to "On this host" when inventory is mixed.

### EXECUTE
- `applySmartLibraryDefault()` after `loadLibraryPrefs()` when no session prefs
- Only when some available and some missing; full/empty hosts stay on All
- Static contract needles in library + static asset tests

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Explorers on partial hosts land on playable library media without manual filter.

---

## Iteration 146 — 2026-07-21

### OBSERVE
Main green after 083a402 (smart library default). Home pack grid and Studio scenario select stayed pure chronology — packs with no host MP4 mixed ahead of packs with playable cuts on partial grind fleets.

### PLAN
**One high-impact change:** `scenariosForDiscovery` — packs with on-host media first when inventory is mixed.

### EXECUTE
- `packIdsWithHostMedia` + `scenariosForDiscovery` (chrono within buckets)
- Home scenario cards: on-host / not-on-host pills; order via discovery helper
- Studio select + default resolveStudioScenarioId use same order (●/○ marks)
- Static contract needles

### TEST
```
Full local CI (unittest as ci.yml + compileall + dep_audit --pip-audit + sim pytest)
```

### RESULT
Freemium pack discovery leads with renderable host inventory on partial fleets.
