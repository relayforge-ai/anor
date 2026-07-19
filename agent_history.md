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
