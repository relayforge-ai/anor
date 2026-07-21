/* Forked History SPA */
(function () {
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

  const state = {
    catalog: null,
    scenarios: [],
    route: "home",
    videoId: null,
    scenarioId: null,
    choiceId: null,
    scenarioDetail: null,
    lastFork: null,
    libraryFilter: "all",
    libraryQuery: "",
  };

  /** sessionStorage keys — survive tab refresh within the browser session */
  const ACTIVE_VIDEO_KEY = "fh:activeVideoJob";
  const LAST_FORK_KEY = "fh:lastFork";
  /** Prevent double-polling the same job (button + auto-resume) */
  let videoPollActiveId = null;
  /** Active rate-limit countdown timer (studio) */
  let rateLimitTimer = null;

  function saveActiveVideoJob(rec) {
    try {
      sessionStorage.setItem(ACTIVE_VIDEO_KEY, JSON.stringify(rec));
    } catch (_) {}
  }

  function loadActiveVideoJob() {
    try {
      const raw = sessionStorage.getItem(ACTIVE_VIDEO_KEY);
      if (!raw) return null;
      const rec = JSON.parse(raw);
      if (!rec || !rec.jobId) return null;
      return rec;
    } catch (_) {
      return null;
    }
  }

  function clearActiveVideoJob() {
    try {
      sessionStorage.removeItem(ACTIVE_VIDEO_KEY);
    } catch (_) {}
  }

  function saveLastFork(fork) {
    try {
      if (!fork || !fork.scenario_id) return;
      const raw = JSON.stringify(fork);
      // Cap storage so a pathological payload cannot fill sessionStorage
      if (raw.length > 100000) return;
      sessionStorage.setItem(LAST_FORK_KEY, raw);
    } catch (_) {}
  }

  function loadLastFork() {
    try {
      const raw = sessionStorage.getItem(LAST_FORK_KEY);
      if (!raw) return null;
      const fork = JSON.parse(raw);
      if (!fork || !fork.scenario_id) return null;
      return fork;
    } catch (_) {
      return null;
    }
  }

  function clearLastFork() {
    try {
      sessionStorage.removeItem(LAST_FORK_KEY);
    } catch (_) {}
    state.lastFork = null;
  }

  function parseRetryAfter(response) {
    if (!response || !response.headers) return 0;
    const raw = response.headers.get("Retry-After");
    if (!raw) return 0;
    const n = parseInt(String(raw).trim(), 10);
    if (Number.isFinite(n) && n > 0) return Math.min(n, 3600);
    // HTTP-date form — rare; ignore for countdown simplicity
    return 0;
  }

  function parseRateLimitRemaining(response) {
    if (!response || !response.headers) return null;
    const raw = response.headers.get("X-RateLimit-Remaining");
    if (raw == null || raw === "") return null;
    const n = parseInt(String(raw).trim(), 10);
    return Number.isFinite(n) && n >= 0 ? n : null;
  }

  function noteRateRemaining(response, kind) {
    /** Soft UX when the server reports remaining budget after success. */
    const left = parseRateLimitRemaining(response);
    if (left === null) return;
    if (left === 0) {
      toast(`${kind} rate budget used for this window`);
    } else if (left <= 2) {
      toast(`${kind} rate budget: ${left} left this window`);
    }
  }

  function clearRateLimitTimer() {
    if (rateLimitTimer) {
      clearInterval(rateLimitTimer);
      rateLimitTimer = null;
    }
  }

  function formatDuration(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${String(r).padStart(2, "0")}s`;
    return `${r}s`;
  }

  function jobTimeSuffix(st) {
    /** Elapsed since start + remaining wall-clock budget (when running). */
    if (!st || (st.status !== "running" && st.status !== "queued")) return "";
    const now = Date.now() / 1000;
    const parts = [];
    if (st.started_at && st.status === "running") {
      parts.push(`elapsed ${formatDuration(now - st.started_at)}`);
    }
    if (st.deadline_at && st.status === "running") {
      const left = st.deadline_at - now;
      if (left > 0) parts.push(`${formatDuration(left)} left`);
      else parts.push("time budget exceeded");
    } else if (st.status === "queued" && st.created_at) {
      parts.push(`waiting ${formatDuration(now - st.created_at)}`);
    }
    return parts.length ? ` · ${parts.join(" · ")}` : "";
  }

  function jobProgressLabel(st) {
    let msg = st.message || st.status || "Working…";
    if (st.status === "queued" && st.jobs_ahead != null) {
      if (st.jobs_ahead === 0) msg += " · next in line";
      else msg += ` · ${st.jobs_ahead} ahead`;
    }
    // Work-based (running) or queue (queued) estimate — both use eta_s from server
    if (
      st.eta_s != null &&
      st.eta_s > 0 &&
      (st.status === "queued" || st.status === "running")
    ) {
      msg += ` · ~${formatDuration(st.eta_s)} left`;
    }
    msg += jobTimeSuffix(st);
    return msg;
  }

  function updateStudioDockProgress(st) {
    /** Mobile dock: live % / stage while a render is tracked. */
    const dock = $("#studio-dock");
    const statusEl = $("#dock-status");
    const cancelEl = $("#dock-cancel");
    if (!dock || !statusEl) return;
    const active =
      st && (st.status === "queued" || st.status === "running");
    statusEl.hidden = !active;
    if (cancelEl) {
      cancelEl.hidden = !active;
      cancelEl.disabled = !active;
    }
    if (!active) {
      statusEl.textContent = "";
      return;
    }
    const pct =
      st.status === "queued"
        ? "…"
        : `${Math.round(Math.max(0, Math.min(100, st.pct || 0)))}%`;
    const stage = (st.stage || st.status || "").toString();
    let line = `${pct}`;
    if (stage && stage !== "queued") line += ` · ${stage}`;
    if (st.eta_s != null && st.eta_s > 0) {
      line += ` · ~${formatDuration(st.eta_s)}`;
    }
    statusEl.textContent = line;
    statusEl.title = jobProgressLabel(st);
  }

  function clearStudioDockProgress() {
    updateStudioDockProgress(null);
  }

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2800);
  }

  function money(n) {
    if (n === 0) return "Free";
    return `$${n.toFixed(2).replace(/\.00$/, "")}`;
  }

  /* ——— Routing ——— */
  function parseHash() {
    const h = (location.hash || "#/").replace(/^#\/?/, "");
    const [page, a, b] = h.split("/");
    return { page: page || "home", a, b };
  }

  function navigate(path) {
    location.hash = "#/" + path.replace(/^\//, "");
  }

  function setActiveNav(page) {
    $$(".nav-links a[data-nav]").forEach((a) => {
      const isActive = a.dataset.nav === page;
      a.classList.toggle("active", isActive);
      if (isActive) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  function showPage(id) {
    $$("[data-page]").forEach((p) => p.classList.toggle("page-hidden", p.dataset.page !== id));
    const dock = $("#studio-dock");
    if (dock) {
      // Mobile sticky actions only while studio is visible
      dock.hidden = id !== "studio";
    }
  }

  function syncStudioDock() {
    /** Mirror primary control disabled/busy state onto the mobile dock. */
    const pairs = [
      ["#btn-fork", "#dock-fork"],
      ["#btn-llm", "#dock-llm"],
      ["#btn-video", "#dock-video"],
      ["#btn-compare", "#dock-compare"],
    ];
    pairs.forEach(([srcSel, dockSel]) => {
      const src = $(srcSel);
      const d = $(dockSel);
      if (!src || !d) return;
      d.disabled = !!src.disabled;
      d.classList.toggle("busy", src.classList.contains("busy"));
    });
  }

  function setNavOpen(open) {
    const links = $("#primary-nav");
    const toggle = $("#nav-toggle");
    const backdrop = $("#nav-backdrop");
    if (!links || !toggle) return;
    links.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (backdrop) {
      backdrop.classList.toggle("open", open);
      backdrop.hidden = !open;
    }
    document.body.style.overflow = open ? "hidden" : "";
  }

  function closeNav() {
    setNavOpen(false);
  }

  /* ——— Membership strip ——— */
  function renderMemberStrip() {
    const s = FHFreemium.statusSummary(state.catalog);
    const el = $("#member-strip");
    if (!el) return;
    el.classList.toggle("is-member", s.isMember);
    el.innerHTML = s.isMember
      ? `<div><span class="dot"></span><strong>${escapeHtml(s.plan)} access</strong> — full library & studio controls unlocked${
          s.demoNote ? ` <span class="note">(${escapeHtml(s.demoNote)})</span>` : ""
        }</div>
         <div class="row">
           <button class="btn btn-ghost btn-sm" id="btn-clear-member">Reset to free</button>
         </div>`
      : `<div><span class="dot"></span><strong>Explorer</strong> · ${s.fullLeft} full episode free · then ${s.previewFraction}% previews · ${s.forksLeft} basic forks left today</div>
         <div class="row">
           <button class="btn btn-primary btn-sm" data-go="pricing">Become a Scholar — $4.99/mo</button>
           <button class="btn btn-ghost btn-sm" id="btn-demo-member">Demo unlock</button>
         </div>`;

    $("#btn-demo-member")?.addEventListener("click", async () => {
      try {
        await FHFreemium.acquireDemoToken("scholar");
        toast("Scholar unlocked (demo token). Stripe not charged.");
      } catch (e) {
        // Offline / open mode without demo endpoint — local flag only
        FHFreemium.setMember("scholar", "local demo unlock");
        toast("Scholar unlocked locally (server token unavailable).");
      }
      refreshChrome();
      route();
    });
    $("#btn-clear-member")?.addEventListener("click", () => {
      FHFreemium.clearMember();
      toast("Back to Explorer freemium.");
      refreshChrome();
      route();
    });
    el.querySelector("[data-go=pricing]")?.addEventListener("click", () => navigate("pricing"));
  }

  function refreshChrome() {
    renderMemberStrip();
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ——— Home ——— */
  function renderHome() {
    showPage("home");
    setActiveNav("home");
    const featured = (state.catalog.videos || []).filter((v) => v.featured);
    const pick = featured[0] || state.catalog.videos[0];
    const art = $("#hero-art");
    if (pick) {
      art.style.background = `linear-gradient(145deg, ${pick.poster_gradient[0]}, ${pick.poster_gradient[1]})`;
      $("#hero-feature-title").textContent = pick.title;
      $("#hero-feature-blurb").textContent = pick.blurb;
      $("#hero-watch").onclick = () => navigate("watch/" + pick.id);
    }
    const grid = $("#home-video-grid");
    grid.innerHTML = state.catalog.videos
      .map((v) => videoCardHtml(v))
      .join("");
    bindVideoCards(grid);

    const sgrid = $("#home-scenario-grid");
    sgrid.innerHTML = scenariosChronological(state.scenarios)
      .map(
        (s) => `
      <article class="card video-card" data-scenario="${escapeHtml(s.scenario_id)}">
        <div class="video-card-body" style="padding-top:1.2rem">
          <div class="row"><span class="pill">${escapeHtml(s.era || "")}</span><span class="pill">${escapeHtml(s.scenario_id)}</span></div>
          <h3 style="margin-top:0.5rem">${escapeHtml(s.title)}</h3>
          <p>${escapeHtml(s.decision_question)}</p>
          <div class="row" style="margin-top:0.6rem"><span class="btn btn-ghost btn-sm">Open in Studio →</span></div>
        </div>
      </article>`
      )
      .join("");
    sgrid.querySelectorAll("[data-scenario]").forEach((el) => {
      el.addEventListener("click", () => navigate("studio/" + el.dataset.scenario));
    });
  }

  function videoCardTagsHtml(v) {
    const tags = Array.isArray(v.tags) ? v.tags.filter(Boolean).slice(0, 4) : [];
    if (!tags.length) return "";
    return `<div class="video-card-tags" role="group" aria-label="Topics">
      ${tags
        .map(
          (t) =>
            `<button type="button" class="pill video-tag" data-lib-tag="${escapeHtml(
              String(t)
            )}" title="Search library for ${escapeHtml(String(t))}">${escapeHtml(
              String(t)
            )}</button>`
        )
        .join("")}
    </div>`;
  }

  function videoCardHtml(v) {
    const access = FHFreemium.videoAccess(v.id, state.catalog);
    const unavailable = v.available === false;
    const gatePill = unavailable
      ? `<span class="pill pill-warn">not on host</span>`
      : access.mode === "full" || access.mode === "claimable_full"
        ? `<span class="pill pill-doc">${access.mode === "claimable_full" ? "Free full" : "Unlocked"}</span>`
        : `<span class="pill pill-warn">${Math.round(access.previewFraction * 100)}% preview</span>`;
    const spec =
      v.speculation === "documented"
        ? `<span class="pill pill-doc">documented</span>`
        : `<span class="pill pill-sim">${escapeHtml(v.speculation)}</span>`;
    return `
      <article class="card video-card ${unavailable ? "video-card-unavailable" : ""}" data-video="${escapeHtml(
        v.id
      )}" data-available="${unavailable ? "0" : "1"}">
        <div class="video-card-art" style="background:linear-gradient(145deg,${v.poster_gradient[0]},${v.poster_gradient[1]})">
          <div class="video-card-play">${unavailable ? "·" : "▶"}</div>
        </div>
        <div class="video-card-body">
          <div class="video-card-meta">${spec}${gatePill}<span class="pill">${escapeHtml(v.era)}</span></div>
          <h3>${escapeHtml(v.title)}</h3>
          <p>${escapeHtml(v.blurb)}</p>
          ${videoCardTagsHtml(v)}
          <div class="note">${
            unavailable
              ? "Media missing — open Studio and queue a render"
              : escapeHtml(v.runtime_label || "")
          }</div>
        </div>
      </article>`;
  }

  function applyLibraryTagSearch(tag) {
    const q = String(tag || "").trim();
    if (!q) return;
    state.libraryQuery = q;
    const input = $("#library-search");
    if (input) input.value = q;
    saveLibraryPrefs();
    if (state.route !== "library") {
      navigate("library");
    } else {
      renderLibrary();
    }
    toast(`Library search: ${q}`);
  }

  function bindVideoCards(root) {
    root.querySelectorAll("[data-lib-tag]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        applyLibraryTagSearch(btn.getAttribute("data-lib-tag") || "");
      });
    });
    root.querySelectorAll("[data-video]").forEach((el) => {
      el.addEventListener("click", () => navigate("watch/" + el.dataset.video));
    });
  }

  const LIBRARY_PREFS_KEY = "fh:libraryPrefs";

  function saveLibraryPrefs() {
    try {
      sessionStorage.setItem(
        LIBRARY_PREFS_KEY,
        JSON.stringify({
          filter: state.libraryFilter || "all",
          query: state.libraryQuery || "",
        })
      );
    } catch (_) {}
  }

  function loadLibraryPrefs() {
    try {
      const raw = sessionStorage.getItem(LIBRARY_PREFS_KEY);
      if (!raw) return;
      const p = JSON.parse(raw);
      if (p && typeof p.filter === "string") state.libraryFilter = p.filter;
      if (p && typeof p.query === "string") state.libraryQuery = p.query;
    } catch (_) {}
  }

  function libraryEmptyHtml(reason) {
    return `
      <div class="card side-panel library-empty" style="grid-column:1/-1">
        <p class="eyebrow">Library</p>
        <h3 class="h3" style="margin-top:0">No playable episodes on this host</h3>
        <p class="lede-sm">${escapeHtml(
          reason ||
            "Render explainers from Studio (Queue video render) or copy MP4s into outputs/videos/."
        )}</p>
        <div class="row" style="margin-top:1rem">
          <a class="btn btn-primary" href="#/studio">Open Studio</a>
          <a class="btn btn-ghost" href="#/">Home</a>
        </div>
      </div>`;
  }

  /* ——— Library ——— */
  function eraSortKey(era) {
    /** Approximate chronological order: BC years negative, AD positive. */
    const s = String(era || "");
    const bc = /\bbc\b/i.test(s);
    const m = s.match(/(\d{1,4})/);
    if (!m) return 99999;
    const y = parseInt(m[1], 10);
    return bc ? -y : y;
  }

  function scenariosChronological(list) {
    return [...(list || [])].sort((a, b) => {
      const d = eraSortKey(a.era) - eraSortKey(b.era);
      if (d !== 0) return d;
      return String(a.scenario_id || "").localeCompare(String(b.scenario_id || ""));
    });
  }

  function normalizeLibraryQuery(q) {
    return String(q || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  /**
   * Filter library catalog entries by speculation/availability chip and free-text query.
   * Query matches title, subtitle, blurb, era, id, scenario_id (case-insensitive).
   */
  function filterLibraryVideos(videos, filter, query) {
    const f = filter || "all";
    let list = videos || [];
    if (f === "documented") list = list.filter((v) => v.speculation === "documented");
    else if (f === "simulated") {
      list = list.filter(
        (v) => v.speculation === "simulated" || v.speculation === "dramatized"
      );
    } else if (f === "available") list = list.filter((v) => v.available !== false);

    const q = normalizeLibraryQuery(query);
    if (!q) return list;
    const tokens = q.split(" ").filter(Boolean);
    return list.filter((v) => {
      const tagStr = Array.isArray(v.tags) ? v.tags.join(" ") : "";
      const hay = [
        v.id,
        v.scenario_id,
        v.title,
        v.subtitle,
        v.blurb,
        v.era,
        v.speculation,
        tagStr,
      ]
        .map((x) => String(x || "").toLowerCase())
        .join(" ");
      return tokens.every((t) => hay.includes(t));
    });
  }

  function bindLibraryFilters() {
    const bar = $("#library-filters");
    if (!bar || bar.dataset.bound === "1") return;
    bar.dataset.bound = "1";
    bar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-lib-filter]");
      if (!btn) return;
      state.libraryFilter = btn.getAttribute("data-lib-filter") || "all";
      saveLibraryPrefs();
      paintLibraryFilterBar();
      renderLibrary();
    });
  }

  function bindLibrarySearch() {
    const input = $("#library-search");
    if (!input || input.dataset.bound === "1") return;
    input.dataset.bound = "1";
    if (state.libraryQuery) input.value = state.libraryQuery;
    input.addEventListener("input", () => {
      state.libraryQuery = input.value || "";
      saveLibraryPrefs();
      renderLibrary();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (input.value) {
          e.preventDefault();
          input.value = "";
          state.libraryQuery = "";
          saveLibraryPrefs();
          renderLibrary();
        } else {
          input.blur();
        }
      }
    });
  }

  function paintLibraryFilterBar() {
    $$("#library-filters [data-lib-filter]").forEach((btn) => {
      const on = btn.getAttribute("data-lib-filter") === state.libraryFilter;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function renderLibrary() {
    showPage("library");
    setActiveNav("library");
    bindLibraryFilters();
    bindLibrarySearch();
    paintLibraryFilterBar();
    const searchInput = $("#library-search");
    if (searchInput && searchInput.value !== (state.libraryQuery || "")) {
      searchInput.value = state.libraryQuery || "";
    }
    const all = state.catalog.videos || [];
    const videos = filterLibraryVideos(all, state.libraryFilter, state.libraryQuery);
    const grid = $("#library-grid");
    const status = $("#library-filter-status");
    if (status) {
      const labels = {
        all: "Showing all episodes",
        documented: "Showing 📗 documented baselines only",
        simulated: "Showing 🧪 simulated / dramatized forks only",
        available: "Showing episodes with media on this host",
      };
      const q = normalizeLibraryQuery(state.libraryQuery);
      const qNote = q ? ` · search “${q}”` : "";
      status.textContent = `${labels[state.libraryFilter] || labels.all}${qNote} · ${videos.length} of ${all.length}`;
    }
    if (!all.length) {
      grid.innerHTML = libraryEmptyHtml("Catalog has no episode entries yet.");
      return;
    }
    if (!videos.length) {
      const hasQuery = !!normalizeLibraryQuery(state.libraryQuery);
      grid.innerHTML = `
        <div class="card side-panel library-empty" style="grid-column:1/-1">
          <p class="eyebrow">${hasQuery ? "Search" : "Filter"}</p>
          <h3 class="h3" style="margin-top:0">No episodes match</h3>
          <p class="lede-sm">${
            hasQuery
              ? "Try another word (era, title, or pack id), clear the search box, or switch filter chips."
              : "Try <strong>All</strong> or another speculation label. Documented and simulated cuts stay separate on purpose."
          }</p>
        </div>`;
      return;
    }
    const anyAvailable = videos.some((v) => v.available !== false);
    grid.innerHTML =
      videos.map(videoCardHtml).join("") +
      (anyAvailable
        ? ""
        : libraryEmptyHtml(
            "Episodes are listed but media files are not present. Queue a render in Studio (requires ffmpeg)."
          ));
    bindVideoCards(grid);
  }

  /* ——— Player ——— */
  let previewTimer = null;
  let previewCeiling = null;

  function clearPreviewWatch() {
    if (previewTimer) {
      clearInterval(previewTimer);
      previewTimer = null;
    }
    previewCeiling = null;
  }

  function setPlayerLoading(on, text) {
    const el = $("#player-loading");
    const label = $("#player-loading-text");
    if (!el) return;
    if (text && label) label.textContent = text;
    if (on) el.removeAttribute("hidden");
    else el.setAttribute("hidden", "");
  }

  function renderWatch(videoId) {
    showPage("watch");
    setActiveNav("library");
    const video = state.catalog.videos.find((v) => v.id === videoId);
    if (!video) {
      toast("Episode not found");
      navigate("library");
      return;
    }
    state.videoId = videoId;
    clearPreviewWatch();

    const access = FHFreemium.videoAccess(videoId, state.catalog);
    $("#watch-title").textContent = video.title;
    $("#watch-sub").textContent = video.subtitle || video.blurb;
    $("#watch-pills").innerHTML = `
      <span class="pill">${escapeHtml(video.era)}</span>
      ${
        video.speculation === "documented"
          ? `<span class="pill pill-doc">documented</span>`
          : `<span class="pill pill-sim">${escapeHtml(video.speculation)}</span>`
      }
      <span class="pill">${escapeHtml(video.runtime_label || "")}</span>
      ${video.available === false ? `<span class="pill pill-warn">unavailable</span>` : ""}`;
    $("#watch-blurb").textContent = video.blurb;
    $("#watch-studio").onclick = () => navigate("studio/" + video.scenario_id);
    const shareBtn = $("#watch-share");
    if (shareBtn) {
      shareBtn.onclick = () => shareEpisode(video.id);
      shareBtn.disabled = false;
    }

    const player = $("#player");
    const gate = $("#player-gate");
    const studioCta = $("#watch-studio");
    studioCta?.classList.remove("pulse-cta");
    player.pause();
    player.removeAttribute("src");
    player.onloadedmetadata = null;
    player.oncanplay = null;
    player.onerror = null;
    player.onended = null;
    player.load();
    gate.classList.remove("open");

    // Claim free full if available
    if (access.mode === "claimable_full") {
      FHFreemium.claimFullVideo(videoId, state.catalog);
      toast("This is your free full episode. Enjoy — after this, new titles are 25% previews.");
    }

    const access2 = FHFreemium.videoAccess(videoId, state.catalog);

    if (!video.file || video.available === false) {
      setPlayerLoading(true, "Episode media not on this host yet — queue a render in Studio.");
      refreshChrome();
      return;
    }

    setPlayerLoading(true, "Loading episode…");
    player.src = "/media/videos/" + video.file;

    player.oncanplay = () => setPlayerLoading(false);
    player.onerror = () => {
      setPlayerLoading(true, "Could not load this episode. Try Studio → Queue video render.");
    };
    // After a full playthrough, nudge viewers into the decision studio
    player.onended = () => {
      if (access2.mode === "preview") {
        // Preview ceiling usually fires first; still open paywall if they reach true end
        gate.classList.add("open");
        return;
      }
      toast("Episode complete — open Studio to fork this decision.");
      const cta = $("#watch-studio");
      if (cta) {
        cta.classList.add("pulse-cta");
        try {
          cta.focus({ preventScroll: true });
        } catch (_) {
          cta.focus();
        }
      }
      const quota = $("#watch-quota");
      if (quota && !quota.querySelector(".watch-end-note")) {
        const note = document.createElement("p");
        note.className = "note watch-end-note";
        note.setAttribute("role", "status");
        note.style.marginTop = "0.75rem";
        note.textContent =
          "You finished this cut. Pull a different thread in Studio — speculation stays labeled.";
        quota.appendChild(note);
      }
    };

    player.onloadedmetadata = () => {
      setPlayerLoading(false);
      if (access2.mode === "preview") {
        FHFreemium.markPreview(videoId);
        previewCeiling = player.duration * access2.previewFraction;
        $("#gate-copy").textContent = `Explorer includes the first ${Math.round(
          access2.previewFraction * 100
        )}% of each additional episode. Unlock Scholar for the full cut — and every fork in the studio.`;
        previewTimer = setInterval(() => {
          if (player.currentTime >= previewCeiling - 0.15) {
            player.pause();
            player.currentTime = previewCeiling;
            gate.classList.add("open");
          }
        }, 200);
      }
    };

    // side quota
    const st = FHFreemium.statusSummary(state.catalog);
    $("#watch-quota").innerHTML = st.isMember
      ? `<strong>Scholar</strong> — full access`
      : `<strong>Explorer freemium</strong><br>
         Full episodes used: ${st.fullVideosUsed} / ${st.fullVideosFree}<br>
         Additional titles: first ${st.previewFraction}% free, then membership.`;

    refreshChrome();
  }

  /* ——— Studio ——— */
  async function loadScenarioDetail(id) {
    // Conditional GET — packs are semi-static; reuse session ETag cache when possible
    try {
      const { data } = await fetchJsonRevalidatable(
        "/api/scenario/" + encodeURIComponent(id),
        "fh:cache:scenario:" + id
      );
      return data;
    } catch (e) {
      const err = new Error(
        (e && e.message) || "Scenario load failed"
      );
      err.code = (e && e.code) || "scenario_load_failed";
      throw err;
    }
  }

  /** Staged progress copy for fork simulation (authored vs LLM). */
  function forkStages(useLlm) {
    const base = [
      { id: "validate", label: "Validate decision against public pack" },
      { id: "ledger", label: "Lock what they knew (no hindsight)" },
      { id: "branch", label: useLlm ? "Request LLM re-render" : "Compose authored branch" },
      { id: "ribbon", label: "Attach provenance ribbon" },
    ];
    return base;
  }

  function renderSimProgress({ stages, activeIndex, pct, label, indeterminate }) {
    const barClass = indeterminate ? "sim-progress-bar indeterminate" : "sim-progress-bar";
    const width = Math.max(0, Math.min(100, pct || 0));
    const pctRounded = Math.round(width);
    const pctText = indeterminate ? "…" : `${pctRounded}%`;
    return `
      <div class="sim-progress" aria-busy="true">
        <div class="sim-progress-head">
          <p class="sim-progress-label">${escapeHtml(label || "Working…")}</p>
          <span class="sim-progress-pct" aria-hidden="true">${pctText}</span>
        </div>
        <div class="${barClass}" role="progressbar" aria-valuemin="0" aria-valuemax="100"
             aria-valuenow="${indeterminate ? 0 : pctRounded}"
             aria-label="${escapeHtml(label || "Simulation progress")}">
          <i style="width:${indeterminate ? 35 : width}%"></i>
        </div>
        <ul class="sim-stages">
          ${stages
            .map((s, i) => {
              let cls = "";
              if (i < activeIndex) cls = "done";
              else if (i === activeIndex) cls = "active";
              return `<li class="${cls}">${escapeHtml(s.label)}</li>`;
            })
            .join("")}
        </ul>
      </div>`;
  }

  function renderSkeletonStudio() {
    return `
      <div class="skeleton skeleton-line lg"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line sm"></div>
      <div class="skeleton skeleton-block"></div>`;
  }

  function renderForkError(message, code, opts) {
    const o = opts || {};
    const retryAfter = Math.max(0, parseInt(o.retryAfter, 10) || 0);
    const isRate = code === "rate_limited" || retryAfter > 0;
    const showRetry = !!o.retryAction;
    let waitHtml = "";
    if (isRate && retryAfter > 0) {
      waitHtml = `<p class="rate-wait" id="rate-wait-msg" aria-live="polite">Try again in <strong id="rate-wait-s">${retryAfter}</strong>s</p>`;
    } else if (isRate) {
      waitHtml = `<p class="rate-wait" id="rate-wait-msg">Rate limit reached — wait a moment, then retry.</p>`;
    }
    const retryHtml = showRetry
      ? `<div class="row rate-actions" style="margin-top:0.75rem">
           <button type="button" class="btn btn-primary btn-sm" id="btn-retry-action"${
             retryAfter > 0 ? " disabled" : ""
           } data-retry-action="${escapeHtml(o.retryAction)}">${
             retryAfter > 0 ? `Wait ${retryAfter}s` : "Try again"
           }</button>
         </div>`
      : "";
    return `
      <div class="fork-error${isRate ? " is-rate-limit" : ""}" role="alert">
        ${escapeHtml(message || "Something went wrong")}
        ${code ? `<span class="code">${escapeHtml(code)}</span>` : ""}
        ${waitHtml}
        ${retryHtml}
      </div>`;
  }

  function bindRateLimitRetry(retryAfter, onRetry) {
    clearRateLimitTimer();
    const btn = $("#btn-retry-action");
    const sEl = $("#rate-wait-s");
    if (!btn) return;
    let left = Math.max(0, parseInt(retryAfter, 10) || 0);
    const paint = () => {
      if (left > 0) {
        btn.disabled = true;
        btn.textContent = `Wait ${left}s`;
        if (sEl) sEl.textContent = String(left);
      } else {
        btn.disabled = false;
        btn.textContent = "Try again";
        const msg = $("#rate-wait-msg");
        if (msg) msg.textContent = "You can try again now.";
      }
    };
    paint();
    if (left > 0) {
      rateLimitTimer = setInterval(() => {
        left -= 1;
        if (left <= 0) {
          clearRateLimitTimer();
          left = 0;
        }
        paint();
      }, 1000);
    }
    btn.onclick = () => {
      if (btn.disabled) return;
      clearRateLimitTimer();
      if (typeof onRetry === "function") onRetry();
    };
  }

  async function renderStudio(scenarioId) {
    showPage("studio");
    setActiveNav("studio");
    if (!scenarioId) scenarioId = state.scenarios[0]?.scenario_id;
    state.scenarioId = scenarioId;

    const select = $("#studio-scenario");
    const ordered = scenariosChronological(state.scenarios);
    select.innerHTML = ordered
      .map(
        (s) =>
          `<option value="${escapeHtml(s.scenario_id)}" ${
            s.scenario_id === scenarioId ? "selected" : ""
          }>${escapeHtml(s.era || "")} · ${escapeHtml(s.scenario_id)} — ${escapeHtml(s.title)}</option>`
      )
      .join("");

    // Skeleton while pack loads
    $("#studio-question").textContent = "Loading pack…";
    $("#studio-known").textContent = "—";
    $("#studio-opening").innerHTML = renderSkeletonStudio();
    $("#choice-list").innerHTML = `
      <div class="skeleton skeleton-line lg"></div>
      <div class="skeleton skeleton-line lg" style="margin-top:0.5rem"></div>
      <div class="skeleton skeleton-line lg" style="margin-top:0.5rem"></div>`;
    $("#fork-result").innerHTML = `
      <div class="sim-progress">
        <p class="sim-progress-label">Opening decision ledger…</p>
        <div class="sim-progress-bar indeterminate"><i></i></div>
      </div>`;

    let detail;
    try {
      detail = await loadScenarioDetail(scenarioId);
    } catch (e) {
      toast(String(e.message || e));
      $("#studio-opening").textContent = "";
      if ($("#studio-sources-body")) {
        $("#studio-sources-body").innerHTML =
          `<p class="note">${escapeHtml(String(e.message || e))}</p>`;
      }
      $("#fork-result").innerHTML = renderForkError(String(e.message || e), "load_failed");
      return;
    }
    state.scenarioDetail = detail;

    $("#studio-question").textContent = detail.decision_question;
    $("#studio-known").textContent = detail.known_outcome;
    $("#studio-opening").textContent =
      (detail.opening?.cold_open || "") +
      "\n\n" +
      (detail.opening?.what_they_knew || "") +
      (detail.opening?.pressure ? "\n\nPressure: " + detail.opening.pressure : "");
    renderStudioSources(detail);

    const member = FHFreemium.isMember();
    const choices = detail.choices || [];
    const list = $("#choice-list");
    list.setAttribute("role", "radiogroup");
    list.setAttribute("aria-label", "Decision choices");
    list.innerHTML = choices
      .map((c) => {
        return `
        <button type="button" class="choice ${state.choiceId === c.id ? "selected" : ""}" data-choice="${escapeHtml(
          c.id
        )}" aria-pressed="${state.choiceId === c.id ? "true" : "false"}" aria-checked="${
          state.choiceId === c.id ? "true" : "false"
        }">
          <span class="choice-label">${escapeHtml(c.label)}</span>
          <span class="choice-meta">
            ${c.is_historical ? "★ historical baseline · " : "counterfactual · "}
            ${escapeHtml(c.speculation_level || "")}
            ${!member && !c.is_historical ? " · free basic fork" : ""}
          </span>
        </button>`;
      })
      .join("");

    const choiceBtns = list.querySelectorAll("[data-choice]");
    choiceBtns.forEach((btn, index) => {
      btn.setAttribute("role", "radio");
      btn.setAttribute("tabindex", btn.classList.contains("selected") ? "0" : "-1");
      btn.addEventListener("click", () => selectChoice(btn, choiceBtns));
      btn.addEventListener("keydown", (e) => {
        const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
        if (!keys.includes(e.key)) return;
        e.preventDefault();
        const items = [...choiceBtns];
        let next = index;
        if (e.key === "ArrowDown" || e.key === "ArrowRight") next = (index + 1) % items.length;
        if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
        if (e.key === "Home") next = 0;
        if (e.key === "End") next = items.length - 1;
        selectChoice(items[next], choiceBtns);
        items[next].focus();
      });
    });

    if (!state.choiceId || !choices.find((c) => c.id === state.choiceId)) {
      state.choiceId = choices.find((c) => c.is_historical)?.id || choices[0]?.id;
      const el = list.querySelector(`[data-choice="${state.choiceId}"]`);
      el?.classList.add("selected");
      el?.setAttribute("aria-pressed", "true");
    }

    renderStudioControls();
    // Restore last fork narrative after refresh (same scenario only)
    if (!state.lastFork || state.lastFork.scenario_id !== scenarioId) {
      const stored = loadLastFork();
      if (stored && stored.scenario_id === scenarioId) {
        state.lastFork = stored;
        if (stored.choice_id) {
          state.choiceId = stored.choice_id;
          const el = [...choiceBtns].find((b) => b.dataset.choice === stored.choice_id);
          if (el) selectChoice(el, choiceBtns);
        }
      }
    }
    const activeJob = loadActiveVideoJob();
    const resumeSame =
      activeJob &&
      activeJob.jobId &&
      (!activeJob.scenarioId || activeJob.scenarioId === scenarioId);
    if (resumeSame) {
      if (activeJob.choiceId) {
        state.choiceId = activeJob.choiceId;
        const el = [...choiceBtns].find((b) => b.dataset.choice === activeJob.choiceId);
        if (el) selectChoice(el, choiceBtns);
      }
      $("#fork-result").innerHTML = renderSimProgress({
        stages: VIDEO_STAGES,
        activeIndex: 0,
        pct: 0,
        label: "Reconnecting to render job…",
        indeterminate: true,
      });
      // Fire-and-forget resume so studio paints choices first
      tryResumeVideoJob();
    } else {
      $("#fork-result").innerHTML =
        state.lastFork && state.lastFork.scenario_id === scenarioId
          ? renderForkHtml(state.lastFork)
          : `<div class="note">Pick a decision and run a fork. Documented baselines stay honest; speculation is labeled.</div>`;
      if (state.lastFork && state.lastFork.scenario_id === scenarioId) {
        bindForkCopyButtons();
      }
    }
    renderStudioControls();
  }

  function renderStudioSources(detail) {
    /** Public sources + provenance — historical integrity surface (no master sources). */
    const body = $("#studio-sources-body");
    const countEl = $("#studio-sources-count");
    if (!body) return;
    const sources = Array.isArray(detail?.sources) ? detail.sources : [];
    const prov = detail?.provenance && typeof detail.provenance === "object" ? detail.provenance : {};
    const discipline = prov.discipline || "";
    const notes = prov.notes || "";
    const corpus = prov.corpus || "";
    if (countEl) {
      countEl.textContent = sources.length
        ? `· ${sources.length} source${sources.length === 1 ? "" : "s"}`
        : "";
    }
    const srcList = sources.length
      ? `<ul class="studio-sources-list">${sources
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("")}</ul>`
      : `<p class="note">No source list on this pack (still public ELOSTIRION framing).</p>`;
    body.innerHTML = `
      <p class="note" style="margin:0.5rem 0 0.65rem">
        <span class="pill pill-doc">📗 documented</span>
        <span class="pill pill-sim">🧪 simulated</span>
        Counterfactuals never overwrite the known outcome.
      </p>
      ${
        discipline
          ? `<p class="studio-sources-discipline"><strong>Discipline:</strong> ${escapeHtml(
              discipline
            )}</p>`
          : ""
      }
      ${notes ? `<p class="note">${escapeHtml(notes)}</p>` : ""}
      ${corpus ? `<p class="note"><strong>Corpus:</strong> ${escapeHtml(corpus)}</p>` : ""}
      <p class="note" style="margin-top:0.65rem;margin-bottom:0.35rem;text-transform:uppercase;letter-spacing:0.06em;font-size:0.7rem">Public sources</p>
      ${srcList}
      <p class="note" style="margin-top:0.75rem">Public ANOR / ELOSTIRION packs only · no MANDOS master sources.</p>`;
  }

  function selectChoice(btn, allBtns) {
    state.choiceId = btn.dataset.choice;
    allBtns.forEach((c) => {
      c.classList.remove("selected");
      c.setAttribute("aria-pressed", "false");
      c.setAttribute("aria-checked", "false");
      c.setAttribute("tabindex", "-1");
    });
    btn.classList.add("selected");
    btn.setAttribute("aria-pressed", "true");
    btn.setAttribute("aria-checked", "true");
    btn.setAttribute("tabindex", "0");
  }

  function renderStudioControls() {
    const member = FHFreemium.isMember();
    const st = FHFreemium.statusSummary(state.catalog);
    $("#studio-quota").innerHTML = member
      ? `<strong>Scholar studio</strong> — LLM re-render, seeds, export unlocked · compare free for all`
      : `<strong>Explorer studio</strong> — authored forks (${st.forksLeft} counted today), free compare & copy. LLM re-render, custom seeds & export require Scholar.`;

    const tiles = $("#control-tiles");
    const controls = [
      { id: "authored_fork", label: "Authored fork", free: true, desc: "Canon branch text, always labeled" },
      { id: "copy_narrative", label: "Copy narrative", free: true, desc: "Clipboard with speculation labels" },
      {
        id: "compare_branches",
        label: "Compare branches",
        free: true,
        desc: "Side-by-side authored summaries · labels preserved",
      },
      { id: "llm_rerender", label: "LLM re-render", free: false, desc: "Live simulation prose via LLM_URL" },
      { id: "custom_seed", label: "Custom pressure seed", free: false, desc: "Inject your own divergence seed" },
      { id: "export", label: "Export markdown", free: false, desc: "Download narrative for teaching" },
    ];
    tiles.innerHTML = controls
      .map((c) => {
        const locked = !c.free && !member;
        return `<div class="control-tile ${locked ? "locked" : ""}">
          <strong>${escapeHtml(c.label)}</strong>
          ${c.desc}
          ${locked ? `<div class="lock">Scholar</div>` : `<div class="lock" style="color:var(--ok)">Available</div>`}
        </div>`;
      })
      .join("");

    syncStudioDock();

    // custom seed field
    $("#seed-wrap").style.display = member ? "block" : "none";
    $("#btn-llm").disabled = !member;
    // Compare uses authored pack text only — free for Explorer
    if ($("#btn-compare")) $("#btn-compare").disabled = !state.scenarioDetail;
    // Copy is free for everyone; export stays Scholar
    if ($("#btn-copy")) $("#btn-copy").disabled = !state.lastFork;
    $("#btn-export").disabled = !member || !state.lastFork;
  }

  function renderForkHtml(fork) {
    const pill =
      fork.speculation_level === "documented"
        ? `<span class="pill pill-doc">documented</span>`
        : `<span class="pill pill-sim">${escapeHtml(fork.speculation_level)}</span>`;
    return `
      <div class="row" style="margin-bottom:0.6rem">${pill}
        <span class="pill">${fork.is_historical ? "historical" : "counterfactual"}</span>
        <span class="pill">source: ${escapeHtml(fork.source)}</span>
      </div>
      <div class="result-title">${escapeHtml(fork.label)}</div>
      <div class="fork-result-body">${escapeHtml(fork.narrative)}</div>
      <p class="ribbon" style="margin-top:1rem">${escapeHtml((fork.provenance_ribbon || []).join(" · "))}</p>
      <div class="row fork-result-actions" style="margin-top:0.85rem">
        <button type="button" class="btn btn-ghost btn-sm" id="btn-copy-inline">Copy narrative</button>
      </div>`;
  }

  function bindForkCopyButtons() {
    $("#btn-copy-inline")?.addEventListener("click", copyForkNarrative);
  }

  function formatForkMarkdown(f) {
    /** Labeled narrative for clipboard / export — speculation never stripped. */
    const level = f.speculation_level || "unknown";
    const hist = f.is_historical ? "historical baseline" : "counterfactual fork";
    const warn =
      level === "documented"
        ? "📗 Documented baseline — not a simulation."
        : `🧪 ${level.toUpperCase()} — labeled speculation, not established fact.`;
    return (
      `# ${f.scenario_id} — ${f.label}\n\n` +
      `${warn}\n` +
      `Path: ${hist}\n` +
      `Speculation level: ${level}\n` +
      `Source: ${f.source || "unknown"}\n\n` +
      `${f.narrative || ""}\n\n` +
      `Provenance ribbon: ${(f.provenance_ribbon || []).join(" · ")}\n` +
      `\n— Forked History / ANOR · ELOSTIRION discipline\n`
    );
  }

  async function copyTextToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    // Fallback for older browsers / insecure contexts
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      if (!document.execCommand("copy")) throw new Error("execCommand failed");
    } finally {
      document.body.removeChild(ta);
    }
  }

  function episodeSharePayload(video) {
    /** Public SPA deep-link for an episode (no secrets; share sheet / clipboard). */
    const brand =
      (state.catalog && state.catalog.brand && state.catalog.brand.name) ||
      "Forked History";
    const id = video && (video.id || video.file);
    const url = new URL(location.href);
    url.hash = "#/watch/" + encodeURIComponent(id || "");
    // Drop query/hash noise from path; keep origin+path for deep links
    const shareUrl = url.origin + url.pathname + url.search + url.hash;
    const level = (video && video.speculation) || "unknown";
    const label =
      level === "documented"
        ? "📗 Documented baseline"
        : level === "simulated" || level === "dramatized"
          ? "🧪 Labeled speculation"
          : "Episode";
    const title = `${(video && video.title) || id || "Episode"} — ${brand}`;
    const text = [
      label,
      video && video.era ? String(video.era) : "",
      (video && (video.blurb || video.subtitle)) || "",
      "Human-gated social · ANOR / ELOSTIRION discipline",
    ]
      .filter(Boolean)
      .join(" · ");
    return { title, text, url: shareUrl };
  }

  async function shareEpisode(videoId) {
    const id = videoId || state.videoId;
    const video =
      state.catalog &&
      state.catalog.videos &&
      state.catalog.videos.find((v) => v.id === id);
    if (!video) {
      toast("Episode not found");
      return;
    }
    const payload = episodeSharePayload(video);
    try {
      if (typeof navigator.share === "function") {
        await navigator.share({
          title: payload.title,
          text: payload.text,
          url: payload.url,
        });
        toast("Shared");
        return;
      }
    } catch (e) {
      // User dismissed the sheet — not an error
      if (e && (e.name === "AbortError" || e.name === "NotAllowedError")) {
        return;
      }
      // Fall through to clipboard
    }
    try {
      await copyTextToClipboard(payload.url);
      toast("Episode link copied");
    } catch (_) {
      toast("Could not share or copy link");
    }
  }

  async function copyForkNarrative() {
    if (!state.lastFork) {
      toast("Run a fork first");
      return;
    }
    const md = formatForkMarkdown(state.lastFork);
    try {
      await copyTextToClipboard(md);
      toast("Narrative copied (labels included)");
    } catch (_) {
      toast("Could not access clipboard");
    }
  }

  /** Prevent double-click / concurrent fork POSTs (burns freemium quota). */
  let forkInFlight = false;

  function isEditableTarget(el) {
    if (!el || !(el instanceof Element)) return false;
    const tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT") return true;
    if (tag === "INPUT") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      return !["button", "submit", "checkbox", "radio", "reset", "file"].includes(type);
    }
    return el.isContentEditable;
  }

  function bindStudioKeyboardShortcuts() {
    /** Ctrl/⌘+Enter basic fork; Ctrl/⌘+Shift+Enter LLM (Scholar). */
    if (document.documentElement.dataset.studioKbd === "1") return;
    document.documentElement.dataset.studioKbd = "1";
    document.addEventListener("keydown", (e) => {
      if (state.route !== "studio") return;
      if ($("#paywall")?.classList.contains("open")) return;
      if (document.body.classList.contains("boot-failed")) return;
      if (!(e.ctrlKey || e.metaKey) || e.key !== "Enter") return;
      // Allow from seed textarea; block bare text fields that aren't our studio seed
      if (isEditableTarget(e.target) && e.target.id !== "custom-seed") return;
      e.preventDefault();
      if (e.shiftKey) {
        runFork({ useLlm: true });
      } else {
        runFork({ useLlm: false });
      }
    });
  }

  async function runFork({ useLlm }) {
    if (!state.scenarioId || !state.choiceId) {
      toast("Select a scenario and a decision first.");
      return;
    }
    if (useLlm && !FHFreemium.isMember()) {
      openPaywall(
        "LLM re-render is a Scholar control",
        "Explorer can still run basic authored forks and free labeled compare. Upgrade for live simulation prose, seeds, and export."
      );
      return;
    }
    if (forkInFlight) {
      toast("A fork is already in progress…");
      return;
    }
    forkInFlight = true;

    const btn = useLlm ? $("#btn-llm") : $("#btn-fork");
    const other = useLlm ? $("#btn-fork") : $("#btn-llm");
    const stages = forkStages(useLlm);
    let stageIdx = 0;
    let tickTimer = null;

    const setBusy = (on) => {
      [btn, other, $("#btn-compare"), $("#btn-copy"), $("#btn-export")].forEach((el) => {
        if (!el) return;
        el.disabled = on;
      });
      if (btn) btn.classList.toggle("busy", on);
    };

    const paint = (idx, pct, label, indeterminate) => {
      $("#fork-result").innerHTML = renderSimProgress({
        stages,
        activeIndex: idx,
        pct,
        label,
        indeterminate,
      });
    };

    setBusy(true);
    paint(0, 8, "Validating decision…", false);

    // Advance staged UI while the network request is in flight (perceived progress).
    // Real completion snaps to 100% when the response arrives.
    tickTimer = setInterval(() => {
      if (stageIdx < stages.length - 1) {
        stageIdx += 1;
      }
      const pct = Math.min(88, 12 + stageIdx * 22 + Math.random() * 6);
      paint(
        stageIdx,
        pct,
        stages[stageIdx].label + (useLlm ? " — waiting on model…" : "…"),
        useLlm && stageIdx >= 2
      );
    }, useLlm ? 700 : 280);

    try {
      const body = {
        scenario_id: state.scenarioId,
        choice_id: state.choiceId,
        use_llm: !!useLlm && FHFreemium.isMember(),
      };
      if (FHFreemium.isMember()) {
        const seed = $("#custom-seed")?.value?.trim();
        if (seed) body.custom_seed = seed;
      }
      const r = await fetch("/api/fork", {
        method: "POST",
        headers: FHFreemium.authHeaders(),
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const err = new Error(data.error || `Fork failed (${r.status})`);
        err.code = data.code || (r.status === 429 ? "rate_limited" : "fork_failed");
        err.retryAfter = parseRetryAfter(r);
        if (r.status === 429 && !err.retryAfter) err.retryAfter = 60;
        throw err;
      }
      if (tickTimer) clearInterval(tickTimer);
      paint(stages.length - 1, 100, "Provenance attached — rendering…", false);
      // Brief beat so users see completion before narrative replaces the bar
      await new Promise((res) => setTimeout(res, 180));
      state.lastFork = data;
      saveLastFork(data);
      FHFreemium.recordFork();
      $("#fork-result").innerHTML = renderForkHtml(data);
      bindForkCopyButtons();
      renderStudioControls();
      refreshChrome();
      toast(useLlm ? "LLM fork ready" : "Fork ready");
      noteRateRemaining(r, useLlm ? "LLM fork" : "Fork");
    } catch (e) {
      if (tickTimer) clearInterval(tickTimer);
      const stagesErr = stages.map((s, i) => ({
        ...s,
      }));
      const code = e.code || "error";
      const retryAfter = e.retryAfter || 0;
      $("#fork-result").innerHTML =
        renderSimProgress({
          stages: stagesErr,
          activeIndex: stageIdx,
          pct: Math.min(88, 12 + stageIdx * 22),
          label: code === "rate_limited" ? "Rate limited" : "Simulation interrupted",
          indeterminate: false,
        }) +
        renderForkError(e.message || String(e), code, {
          retryAfter,
          retryAction: "fork",
        });
      // mark active stage as error via class patch
      const active = $("#fork-result")?.querySelector(".sim-stages li.active");
      if (active) {
        active.classList.remove("active");
        active.classList.add("error");
      }
      bindRateLimitRetry(retryAfter, () => runFork({ useLlm }));
    } finally {
      if (tickTimer) clearInterval(tickTimer);
      setBusy(false);
      forkInFlight = false;
      renderStudioControls();
    }
  }

  const VIDEO_STAGES = [
    { id: "queue", label: "Accepted by render queue" },
    { id: "fork", label: "Decision narrative" },
    { id: "script", label: "VO script & shot list" },
    { id: "still", label: "Archival stills (image)" },
    { id: "tts", label: "Narration (TTS)" },
    { id: "clip", label: "Ken Burns clips" },
    { id: "concat", label: "Final MP4 assembly" },
  ];

  function videoStageIndex(stage) {
    const map = {
      queued: 0,
      starting: 0,
      load: 1,
      fork: 1,
      script: 2,
      // Finer pipeline stages (iter 79+) — fall back to still for legacy "segment"
      still: 3,
      segment: 3,
      image: 3,
      tts: 4,
      clip: 5,
      mux: 5,
      concat: 6,
      done: 6,
      timeout: 5,
      error: 5,
    };
    return map[stage] ?? 0;
  }

  /**
   * While the tab is hidden, avoid hammering /api/video/jobs (rate budget + battery).
   * Resolves when the document becomes visible again, or after ``maxHiddenMs``
   * so we still take a slow heartbeat if the user leaves the tab for a long time.
   */
  function waitWhileDocumentHidden(maxHiddenMs = 15000) {
    if (typeof document === "undefined" || !document.hidden) {
      return Promise.resolve(false);
    }
    return new Promise((resolve) => {
      let settled = false;
      const finish = (wasHidden) => {
        if (settled) return;
        settled = true;
        document.removeEventListener("visibilitychange", onVis);
        clearTimeout(tid);
        resolve(wasHidden);
      };
      const onVis = () => {
        if (!document.hidden) finish(true);
      };
      document.addEventListener("visibilitychange", onVis);
      const tid = setTimeout(() => finish(true), maxHiddenMs);
    });
  }

  async function pollVideoJob(jobId, { resumed = false } = {}) {
    if (videoPollActiveId && videoPollActiveId === jobId) {
      return; // already polling this job
    }
    videoPollActiveId = jobId;

    const btn = $("#btn-video");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("busy");
    }
    syncStudioDock();

    const stages = VIDEO_STAGES;
    let done = false;
    let pollMs = resumed ? 400 : 500;
    const pollMax = 4000;
    const hiddenPollMs = 15000;

    const bindCancel = () => {
      const cbtn = $("#btn-cancel-job");
      if (!cbtn) return;
      cbtn.onclick = async () => {
        cbtn.disabled = true;
        try {
          const cr = await fetch("/api/video/jobs/" + encodeURIComponent(jobId), {
            method: "DELETE",
            headers: FHFreemium.authHeaders(),
          });
          const cd = await cr.json().catch(() => ({}));
          if (!cr.ok && cr.status !== 409) {
            toast(cd.error || "Cancel failed");
            cbtn.disabled = false;
            return;
          }
          toast("Cancel requested");
        } catch (e) {
          toast("Cancel failed");
          cbtn.disabled = false;
        }
      };
    };

    try {
      while (!done) {
        const pr = await fetch("/api/video/jobs/" + encodeURIComponent(jobId), {
          headers: FHFreemium.apiHeaders({ Accept: "application/json" }),
        });
        if (pr.status === 404) {
          clearActiveVideoJob();
          throw Object.assign(new Error("Job no longer on server (TTL expired)"), {
            code: "not_found",
          });
        }
        const st = await pr.json();
        if (!pr.ok) throw Object.assign(new Error(st.error || "Poll failed"), { code: st.code });

        const idx = videoStageIndex(st.stage);
        const cancelBar =
          st.status === "queued" || st.status === "running"
            ? `<div class="row" style="margin-top:0.8rem"><button type="button" class="btn btn-ghost btn-sm" id="btn-cancel-job">Cancel render</button></div>`
            : "";
        $("#fork-result").innerHTML =
          renderSimProgress({
            stages,
            activeIndex: idx,
            pct: st.pct || 0,
            label: jobProgressLabel(st),
            indeterminate: st.status === "queued",
          }) + cancelBar;
        bindCancel();
        updateStudioDockProgress(st);

        if (st.status === "completed") {
          done = true;
          clearActiveVideoJob();
          clearStudioDockProgress();
          const url = st.result?.media_url || "";
          const wasCached = !!(st.result && st.result.cached);
          const cachedNote = wasCached
            ? `<p class="note">Served from disk cache — no new stills/TTS/ffmpeg work. Use <strong>Force re-render</strong> only when you need fresh stills/VO.</p>`
            : "";
          const forceBtn = FHFreemium.isMember()
            ? `<button type="button" class="btn btn-ghost btn-sm" id="btn-force-rerender" title="Ignore disk cache and re-run stills → TTS → Ken Burns">Force re-render</button>`
            : "";
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: stages.length - 1,
              pct: 100,
              label: wasCached ? "Existing render ready" : "Render complete",
              indeterminate: false,
            }) +
            `<div style="margin-top:1rem">
              <p class="note">Async job <code>${escapeHtml(jobId)}</code> finished.</p>
              ${cachedNote}
              <div class="row" style="flex-wrap:wrap;gap:0.45rem;margin-top:0.35rem">
              ${
                url
                  ? `<a class="btn btn-primary btn-sm" href="${escapeHtml(url)}" target="_blank" rel="noopener">Open MP4</a>
                     <a class="btn btn-ghost btn-sm" href="#/library">Open library</a>
                     ${forceBtn}`
                  : forceBtn
              }
              </div>
              ${
                url
                  ? `<video controls playsinline style="width:100%;margin-top:0.8rem;border-radius:12px;border:1px solid var(--line)" src="${escapeHtml(url)}"></video>`
                  : ""
              }
            </div>`;
          bindForceRerenderButton();
          toast(
            wasCached
              ? "Existing render ready"
              : resumed
                ? "Render finished while you were away"
                : "Video ready"
          );
          // Bust catalog ETag cache so new render availability is visible
          try {
            sessionStorage.removeItem(CACHE_CATALOG + ":etag");
            sessionStorage.removeItem(CACHE_CATALOG + ":body");
          } catch (_) {}
          await refreshCatalog();
        } else if (st.status === "cancelled") {
          done = true;
          clearActiveVideoJob();
          clearStudioDockProgress();
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: idx,
              pct: st.pct || 0,
              label: "Cancelled",
              indeterminate: false,
            }) +
            `<p class="note" style="margin-top:0.8rem">Job <code>${escapeHtml(jobId)}</code> was cancelled.</p>`;
          toast("Render cancelled");
        } else if (st.status === "timed_out") {
          done = true;
          clearActiveVideoJob();
          clearStudioDockProgress();
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: idx,
              pct: st.pct || 0,
              label: "Timed out",
              indeterminate: false,
            }) +
            renderForkError(
              st.error || "Render exceeded the wall-clock timeout",
              "video_timed_out",
              { retryAction: "video" }
            );
          bindRateLimitRetry(0, () => queueVideoRender());
          toast("Render timed out");
        } else if (st.status === "failed") {
          done = true;
          clearActiveVideoJob();
          clearStudioDockProgress();
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: idx,
              pct: st.pct || 0,
              label: "Render failed",
              indeterminate: false,
            }) +
            renderForkError(st.error || "Render failed", "video_failed", {
              retryAction: "video",
            });
          bindRateLimitRetry(0, () => queueVideoRender());
          const active = $("#fork-result")?.querySelector(".sim-stages li.active");
          if (active) {
            active.classList.remove("active");
            active.classList.add("error");
          }
        } else {
          // Background tabs: wait for focus (or slow heartbeat) before next poll
          const wasHidden = await waitWhileDocumentHidden(hiddenPollMs);
          if (wasHidden) {
            // Tab just returned or heartbeat — poll soon without long backoff pile-up
            pollMs = Math.min(pollMs, 1000);
          } else {
            await new Promise((res) => setTimeout(res, pollMs));
            pollMs = Math.min(pollMax, Math.round(pollMs * 1.35));
          }
        }
      }
    } catch (e) {
      clearStudioDockProgress();
      $("#fork-result").innerHTML = renderForkError(
        e.message || String(e),
        e.code || "video_error",
        { retryAction: "video" }
      );
      bindRateLimitRetry(0, () => queueVideoRender());
    } finally {
      if (videoPollActiveId === jobId) videoPollActiveId = null;
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("busy");
      }
      renderStudioControls();
      syncStudioDock();
    }
  }

  async function tryResumeVideoJob() {
    const rec = loadActiveVideoJob();
    if (!rec?.jobId) return;
    // Only auto-resume when viewing the same scenario (or no scenario locked)
    if (rec.scenarioId && state.scenarioId && rec.scenarioId !== state.scenarioId) {
      return;
    }
    if (videoPollActiveId === rec.jobId) return;

    try {
      const pr = await fetch("/api/video/jobs/" + encodeURIComponent(rec.jobId), {
        headers: FHFreemium.apiHeaders({ Accept: "application/json" }),
      });
      if (pr.status === 404) {
        clearActiveVideoJob();
        return;
      }
      const st = await pr.json().catch(() => ({}));
      if (!pr.ok) return;

      if (rec.choiceId && !state.choiceId) {
        state.choiceId = rec.choiceId;
      }
      if (["completed", "failed", "cancelled", "timed_out"].includes(st.status)) {
        // Paint terminal once without forcing a long poll loop start flicker
        toast("Restoring finished render…");
      } else {
        toast("Resuming render status…");
      }
      await pollVideoJob(rec.jobId, { resumed: true });
    } catch (_) {
      // Keep session record — user can re-enter studio later while job TTL holds
    }
  }

  function bindForceRerenderButton() {
    const fr = $("#btn-force-rerender");
    if (!fr) return;
    fr.onclick = () => {
      if (
        !confirm(
          "Force a full re-render? This uses GPU/TTS/ffmpeg even if an MP4 already exists."
        )
      ) {
        return;
      }
      queueVideoRender({ force: true });
    };
  }

  async function queueVideoRender(opts) {
    const force = !!(opts && opts.force);
    if (!state.scenarioId || !state.choiceId) {
      toast("Select a scenario and a decision first.");
      return;
    }
    if (!FHFreemium.isMember()) {
      openPaywall(
        "Video render is a Scholar control",
        "Queue script → TTS → stills → ffmpeg on sovereign GPUs. Explorer can still run basic forks and watch the library."
      );
      return;
    }

    if (videoPollActiveId) {
      toast("A render is already being tracked — watch progress below.");
      return;
    }

    const btn = $("#btn-video");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("busy");
    }
    syncStudioDock();

    try {
      const r = await fetch("/api/video/jobs", {
        method: "POST",
        headers: FHFreemium.authHeaders(),
        body: JSON.stringify({
          scenario_id: state.scenarioId,
          choice_id: state.choiceId,
          use_llm: false,
          force: force,
        }),
      });
      const job = await r.json().catch(() => ({}));
      if (!r.ok && r.status !== 202) {
        const err = Object.assign(new Error(job.error || "Enqueue failed"), {
          code: job.code || (r.status === 429 ? "rate_limited" : "video_error"),
          retryAfter: parseRetryAfter(r),
        });
        if (r.status === 429 && !err.retryAfter) err.retryAfter = 60;
        throw err;
      }

      const jobId = job.id;
      saveActiveVideoJob({
        jobId,
        scenarioId: state.scenarioId,
        choiceId: state.choiceId,
        startedAt: Date.now(),
      });
      if (job.cache_hit || (job.result && job.result.cached)) {
        toast("Using existing render — no GPU work");
      } else if (job.deduped) {
        toast("Joined existing render job");
      } else if (force) {
        toast("Force re-render queued");
      } else {
        toast("Video job queued");
      }
      noteRateRemaining(r, "Video");
      await pollVideoJob(jobId, { resumed: false });
    } catch (e) {
      const code = e.code || "video_error";
      const retryAfter = e.retryAfter || 0;
      $("#fork-result").innerHTML = renderForkError(e.message || String(e), code, {
        retryAfter,
        retryAction: "video",
      });
      bindRateLimitRetry(retryAfter, () => queueVideoRender({ force: force }));
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("busy");
      }
      renderStudioControls();
    }
  }

  function compareBranches() {
    /** Authored pack compare only — no LLM. Free for Explorer; labels mandatory. */
    const d = state.scenarioDetail;
    if (!d) {
      toast("Open a scenario pack first");
      return;
    }
    const hist = (d.choices || []).find((c) => c.is_historical);
    const cur =
      (d.choices || []).find((c) => c.id === state.choiceId) ||
      (d.choices || []).find((c) => !c.is_historical) ||
      null;
    if (!hist) {
      toast("Pack is missing a historical baseline choice");
      return;
    }
    const curLevel = cur?.speculation_level || "simulated";
    const curPill =
      curLevel === "documented"
        ? `<span class="pill pill-doc">documented</span>`
        : `<span class="pill pill-sim">${escapeHtml(curLevel)}</span>`;
    const sameAsHist = cur && hist && cur.id === hist.id;
    const rightTitle = sameAsHist
      ? "Select a counterfactual choice to compare"
      : cur?.label || "Counterfactual";
    const rightBody = sameAsHist
      ? "Pick a non-historical decision on the left, then compare again. Documented baseline stays on the left."
      : cur?.summary || "";
    const rightArc = sameAsHist ? "" : cur?.longer_arc || "";
    $("#fork-result").innerHTML = `
      <div class="result-title">Branch compare</div>
      <p class="note" style="margin:0.35rem 0 0.75rem">
        Authored pack text only · 📗 historical baseline vs labeled fork · not a live LLM re-sim
      </p>
      <div class="grid grid-2 compare-grid" style="margin-top:0.5rem">
        <div class="card compare-pane" style="padding:1rem">
          <div class="row" style="gap:0.35rem;flex-wrap:wrap">
            <span class="pill pill-doc">📗 documented</span>
            <span class="pill">historical baseline</span>
          </div>
          <h3 style="margin:0.5rem 0">${escapeHtml(hist.label || "")}</h3>
          <p style="color:var(--ink-dim)">${escapeHtml(hist.summary || "")}</p>
          <p class="note">${escapeHtml(hist.longer_arc || "")}</p>
        </div>
        <div class="card compare-pane" style="padding:1rem">
          <div class="row" style="gap:0.35rem;flex-wrap:wrap">
            ${curPill}
            <span class="pill">${sameAsHist ? "pick a fork" : "counterfactual"}</span>
          </div>
          <h3 style="margin:0.5rem 0">${escapeHtml(rightTitle)}</h3>
          <p style="color:var(--ink-dim)">${escapeHtml(rightBody)}</p>
          ${rightArc ? `<p class="note">${escapeHtml(rightArc)}</p>` : ""}
        </div>
      </div>
      <p class="note" style="margin-top:0.85rem">
        Speculations never replace the baseline. Scholar unlocks LLM re-render for full narrative forks.
      </p>`;
  }

  function exportFork() {
    if (!FHFreemium.isMember()) {
      openPaywall("Export", "Scholar can download fork narratives as markdown. Explorer can still Copy narrative.");
      return;
    }
    if (!state.lastFork) {
      toast("Run a fork first");
      return;
    }
    const f = state.lastFork;
    const md = formatForkMarkdown(f);
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${f.scenario_id}-${f.choice_id || "fork"}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast("Markdown downloaded (labels included)");
  }

  /* ——— Pricing ——— */
  function renderPricing() {
    showPage("pricing");
    setActiveNav("pricing");
    const plans = state.catalog.pricing.plans;
    const grid = $("#pricing-grid");
    grid.innerHTML = plans
      .map((p) => {
        const price =
          p.price_monthly === 0
            ? `Free`
            : `${money(p.price_monthly)} <span>/ mo</span>`;
        const yearly =
          p.price_yearly > 0
            ? `<div class="note">or ${money(p.price_yearly)} / year</div>`
            : `<div class="note">No card required</div>`;
        return `
        <article class="card price-card ${p.highlight ? "highlight" : ""}">
          <span class="pill price-badge ${p.highlight ? "pill-warn" : ""}">${escapeHtml(p.badge)}</span>
          <div class="price-name">${escapeHtml(p.name)}</div>
          <div class="price-amount">${price}</div>
          ${yearly}
          <ul class="price-list">
            ${p.features.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}
          </ul>
          ${
            p.id === "explorer"
              ? `<button class="btn btn-ghost" data-plan="explorer">Stay on Explorer</button>`
              : `<button class="btn btn-primary" data-plan="${escapeHtml(p.id)}">Choose ${escapeHtml(
                  p.name
                )}</button>`
          }
        </article>`;
      })
      .join("");

    grid.querySelectorAll("[data-plan]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const plan = btn.dataset.plan;
        if (plan === "explorer") {
          FHFreemium.clearMember();
          toast("Explorer freemium active");
          refreshChrome();
          return;
        }
        // Stripe stub → demo unlock for now
        openPaywall(
          `Unlock ${plan}`,
          `Recommended: Scholar at $4.99/mo (or $39/yr). Checkout is stubbed for this build — demo unlock simulates membership so Ryan can review the full product.`
        );
        $("#pay-confirm").onclick = async () => {
          try {
            await FHFreemium.acquireDemoToken(plan);
            toast(`${plan} unlocked (demo token). Wire Stripe when ready.`);
          } catch (e) {
            FHFreemium.setMember(plan, "demo checkout stub");
            toast(`${plan} unlocked locally.`);
          }
          closePaywall();
          refreshChrome();
          renderPricing();
        };
      });
    });

    const ot = state.catalog.pricing.one_time;
    $("#one-time").innerHTML = `
      <div class="h3" style="margin-top:0">${escapeHtml(ot.name)} — ${money(ot.price)}</div>
      <p style="color:var(--ink-dim);margin:0.4rem 0 1rem">${escapeHtml(ot.description)}</p>
      <button class="btn btn-ghost" id="btn-pass">Demo Library Pass</button>`;
    $("#btn-pass").onclick = async () => {
      try {
        await FHFreemium.acquireDemoToken("library_pass");
      } catch (e) {
        FHFreemium.setMember("library_pass", "90-day pass demo");
      }
      toast("Library Pass demo unlocked");
      refreshChrome();
    };

    $("#pricing-notes").innerHTML = (state.catalog.pricing.notes || [])
      .map((n) => `<li>${escapeHtml(n)}</li>`)
      .join("");
  }

  /* ——— Paywall modal (focus trap + Escape + restore) ——— */
  let paywallPrevFocus = null;
  let paywallKeyHandler = null;

  function paywallFocusable() {
    const root = $("#paywall");
    if (!root) return [];
    return [
      ...root.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ),
    ].filter((el) => el.offsetParent !== null || el === document.activeElement);
  }

  function openPaywall(title, copy) {
    const wall = $("#paywall");
    if (!wall) return;
    closeNav();
    paywallPrevFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    $("#pay-title").textContent = title;
    $("#pay-copy").textContent = copy;
    wall.hidden = false;
    wall.classList.add("open");
    document.body.classList.add("modal-open");
    // Move focus into dialog after paint
    requestAnimationFrame(() => {
      const first = paywallFocusable()[0] || $("#pay-close");
      first?.focus();
    });
    if (paywallKeyHandler) {
      document.removeEventListener("keydown", paywallKeyHandler, true);
    }
    paywallKeyHandler = (e) => {
      if (!wall.classList.contains("open")) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closePaywall();
        return;
      }
      if (e.key !== "Tab") return;
      const nodes = paywallFocusable();
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || !wall.contains(document.activeElement)) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", paywallKeyHandler, true);
  }

  function closePaywall() {
    const wall = $("#paywall");
    if (!wall) return;
    wall.classList.remove("open");
    wall.hidden = true;
    document.body.classList.remove("modal-open");
    if (paywallKeyHandler) {
      document.removeEventListener("keydown", paywallKeyHandler, true);
      paywallKeyHandler = null;
    }
    const prev = paywallPrevFocus;
    paywallPrevFocus = null;
    // Restore focus to the control that opened the dialog
    if (prev && typeof prev.focus === "function" && document.contains(prev)) {
      prev.focus();
    }
  }

  /* ——— Router ——— */
  let lastRouteKey = null;
  let routeFocusReady = false; // skip focus steal on first paint after boot

  function routeKey(page, a) {
    return (page || "home") + "/" + (a || "");
  }

  function focusMainForRoute() {
    // SPA pages don't remount document title focus — move keyboard focus into main
    // so screen readers announce the new view after hash navigation.
    if (!routeFocusReady) return;
    if (document.body.classList.contains("boot-failed")) return;
    if ($("#paywall")?.classList.contains("open")) return;
    const main = $("#main-content");
    if (!main) return;
    if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");
    try {
      main.focus({ preventScroll: true });
    } catch (_) {
      main.focus();
    }
  }

  function setMetaContent(selector, content) {
    const el = document.querySelector(selector);
    if (el && content) el.setAttribute("content", content);
  }

  function syncShareMeta(title, description) {
    /** Keep og/twitter/description aligned with the SPA route for in-app share sheets. */
    if (title) {
      setMetaContent('meta[property="og:title"]', title);
      setMetaContent('meta[name="twitter:title"]', title);
    }
    if (description) {
      setMetaContent('meta[name="description"]', description);
      setMetaContent('meta[property="og:description"]', description);
      setMetaContent('meta[name="twitter:description"]', description);
    }
  }

  function updateDocumentTitle(page, param) {
    const brand = (state.catalog && state.catalog.brand && state.catalog.brand.name) || "Forked History";
    const tagline =
      (state.catalog && state.catalog.brand && state.catalog.brand.tagline) || "";
    const defaultDesc =
      tagline ||
      "Real decision points. Labeled speculation. Receipts on screen. ANOR Fork Studio.";
    let title = brand;
    let description = defaultDesc;
    if (page === "home") {
      title = tagline ? `${brand} — ${tagline}` : brand;
      description = defaultDesc;
    } else if (page === "library") {
      title = `Library — ${brand}`;
      description = `Browse documented decision episodes and labeled simulations — ${brand}.`;
    } else if (page === "watch") {
      const v =
        (state.catalog &&
          state.catalog.videos &&
          state.catalog.videos.find((x) => x.id === param || x.file === param)) ||
        null;
      const label = (v && (v.title || v.id)) || param || "Episode";
      title = `${label} — ${brand}`;
      description = (v && (v.blurb || v.subtitle)) || defaultDesc;
      if (v && v.speculation === "simulated") {
        description = `🧪 Simulated fork — ${description}`;
      } else if (v && v.speculation === "documented") {
        description = `📗 Documented baseline — ${description}`;
      }
    } else if (page === "studio") {
      const sid = param || state.scenarioId || "";
      title = sid ? `Studio · ${sid} — ${brand}` : `Studio — ${brand}`;
      description = sid
        ? `Fork ${sid} in the studio — authored branches free; LLM re-render is Scholar. Speculation always labeled.`
        : `Interactive decision studio — ${brand}. Speculation always labeled.`;
    } else if (page === "pricing") {
      title = `Membership — ${brand}`;
      description = `Explorer free · Scholar $4.99/mo — full library and studio. Funds sovereign compute.`;
    }
    document.title = title;
    syncShareMeta(title, description);
  }

  async function route() {
    const { page, a } = parseHash();
    const key = routeKey(page, a);
    const changed = key !== lastRouteKey;
    lastRouteKey = key;
    state.route = page;
    clearPreviewWatch();
    refreshChrome();
    closeNav();
    try {
      if (page === "library") await renderLibrary();
      else if (page === "watch") await renderWatch(a);
      else if (page === "studio") await renderStudio(a);
      else if (page === "pricing") await renderPricing();
      else await renderHome();
    } finally {
      updateDocumentTitle(page, a);
      if (changed) focusMainForRoute();
    }
  }

  /* ——— Conditional JSON GET (pairs with server ETag on catalog/scenarios) ——— */
  const CACHE_CATALOG = "fh:cache:catalog";
  const CACHE_SCENARIOS = "fh:cache:scenarios";

  function readSessionJson(key) {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function writeSessionJson(key, value) {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch (_) {}
  }

  /**
   * Fetch JSON with If-None-Match when we have a stored ETag.
   * On 304, return the session-cached body (browser fetch has no body on 304).
   */
  async function fetchJsonRevalidatable(url, cacheKey) {
    const etagKey = cacheKey + ":etag";
    const bodyKey = cacheKey + ":body";
    const headers = FHFreemium.apiHeaders({ Accept: "application/json" });
    try {
      const etag = sessionStorage.getItem(etagKey);
      if (etag) headers["If-None-Match"] = etag;
    } catch (_) {}

    let res;
    try {
      // cache: 'no-cache' forces revalidation (sends conditional request) rather
      // than serving a stale disk cache without checking the server.
      res = await fetch(url, { headers, cache: "no-cache" });
    } catch (e) {
      const err = new Error("Network error reaching " + url);
      err.code = "network";
      err.detail = String(e && e.message ? e.message : e);
      throw err;
    }

    if (res.status === 304) {
      const cached = readSessionJson(bodyKey);
      if (cached != null) {
        return { data: cached, status: 304, etag: headers["If-None-Match"] || null, revalidated: true };
      }
      // Stale client cache — force unconditional fetch once
      res = await fetch(url, {
        headers: FHFreemium.apiHeaders({ Accept: "application/json" }),
        cache: "reload",
      });
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const err = new Error(body.error || `Request failed (HTTP ${res.status})`);
      err.code = body.code || "http_error";
      err.detail = `GET ${url} → ${res.status}`;
      err.status = res.status;
      throw err;
    }

    const data = await res.json();
    const etag = res.headers.get("ETag");
    try {
      if (etag) sessionStorage.setItem(etagKey, etag);
      writeSessionJson(bodyKey, data);
    } catch (_) {}
    return { data, status: res.status, etag, revalidated: false };
  }

  async function refreshCatalog() {
    try {
      const { data } = await fetchJsonRevalidatable("/api/catalog", CACHE_CATALOG);
      state.catalog = data;
      return data;
    } catch (_) {
      return state.catalog;
    }
  }

  /* ——— Boot failure UI ——— */
  function showBootError(message, detail) {
    const main = $("#main-content");
    if (!main) {
      toast(message || "Failed to load");
      return;
    }
    document.body.classList.add("boot-failed");
    main.innerHTML = `
      <div class="boot-error card fade-in" id="boot-error" role="alert" aria-live="assertive">
        <p class="eyebrow">Connection</p>
        <h2 class="h-display" style="font-size:clamp(1.6rem,3vw,2.2rem);margin:0.35rem 0 0.75rem">
          Unable to open the ledger
        </h2>
        <p class="lede-sm" style="margin:0;color:var(--ink-dim)">
          ${escapeHtml(message || "The catalog could not be loaded.")}
        </p>
        ${
          detail
            ? `<p class="note" style="margin-top:0.75rem"><code>${escapeHtml(detail)}</code></p>`
            : ""
        }
        <ul class="note" style="margin:1rem 0 0;padding-left:1.2rem;color:var(--ink-dim)">
          <li>Confirm the site server is running (<code>python -m webapp.server</code>)</li>
          <li>Check <code>/api/health</code> for readiness</li>
          <li>If you hit a rate limit, wait a moment and retry</li>
        </ul>
        <div class="row" style="margin-top:1.25rem;gap:0.6rem;flex-wrap:wrap">
          <button type="button" class="btn btn-primary" id="btn-boot-retry">Retry</button>
          <a class="btn btn-ghost" href="/api/health" target="_blank" rel="noopener">Open health</a>
        </div>
      </div>`;
    $("#btn-boot-retry")?.addEventListener("click", () => {
      const btn = $("#btn-boot-retry");
      if (btn) {
        btn.disabled = true;
        btn.classList.add("busy");
        btn.textContent = "Retrying…";
      }
      location.reload();
    });
    $("#btn-boot-retry")?.focus();
  }

  /* ——— Boot ——— */
  async function boot() {
    let catalog;
    let scenarios;
    try {
      const [cat, scen] = await Promise.all([
        fetchJsonRevalidatable("/api/catalog", CACHE_CATALOG),
        fetchJsonRevalidatable("/api/scenarios", CACHE_SCENARIOS),
      ]);
      catalog = cat.data;
      scenarios = scen.data;
    } catch (e) {
      if (e && e.code === "network") {
        const err = new Error(
          "Network error — the browser could not reach the Forked History API."
        );
        err.code = "network";
        err.detail = e.detail || "";
        throw err;
      }
      throw e;
    }
    if (!catalog || !catalog.brand || !Array.isArray(scenarios)) {
      const err = new Error("Catalog payload is missing required fields.");
      err.code = "bad_catalog";
      throw err;
    }

    state.catalog = catalog;
    state.scenarios = scenarios;
    loadLibraryPrefs();

    $("#brand-name").textContent = state.catalog.brand.name;
    document.title = state.catalog.brand.name + " — " + state.catalog.brand.tagline;

    // nav
    $$("[data-nav]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        closeNav();
        navigate(a.dataset.nav === "home" ? "" : a.dataset.nav);
      });
    });
    $("#nav-upgrade")?.addEventListener("click", (e) => {
      e.preventDefault();
      closeNav();
      navigate("pricing");
    });
    $("#nav-toggle")?.addEventListener("click", () => {
      const open = $("#nav-toggle").getAttribute("aria-expanded") !== "true";
      setNavOpen(open);
      if (open) {
        const first = $("#primary-nav a[data-nav]");
        first?.focus();
      }
    });
    $("#nav-backdrop")?.addEventListener("click", closeNav);
    document.addEventListener("keydown", (e) => {
      // Paywall trap handles Escape first (capture). Nav only when modal closed.
      if (e.key === "Escape" && !$("#paywall")?.classList.contains("open")) {
        closeNav();
      }
      // "/" focuses library search when browsing the catalog (not in inputs)
      if (
        e.key === "/" &&
        !e.metaKey &&
        !e.ctrlKey &&
        !e.altKey &&
        state.route === "library" &&
        !$("#paywall")?.classList.contains("open")
      ) {
        const t = e.target;
        const tag = (t && t.tagName) || "";
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) {
          return;
        }
        const search = $("#library-search");
        if (search) {
          e.preventDefault();
          search.focus();
          search.select?.();
        }
      }
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900) closeNav();
    });

    // Backdrop click (outside .modal panel) dismisses paywall
    $("#paywall")?.addEventListener("click", (e) => {
      if (e.target === $("#paywall")) closePaywall();
    });
    // Prevent clicks inside panel from bubbling to backdrop
    $("#paywall .modal")?.addEventListener("click", (e) => e.stopPropagation());

    // studio buttons
    $("#studio-scenario")?.addEventListener("change", (e) => {
      state.choiceId = null;
      clearLastFork();
      clearRateLimitTimer();
      navigate("studio/" + e.target.value);
    });
    $("#btn-fork")?.addEventListener("click", () => runFork({ useLlm: false }));
    $("#btn-llm")?.addEventListener("click", () => runFork({ useLlm: true }));
    $("#btn-video")?.addEventListener("click", () => queueVideoRender());
    $("#btn-compare")?.addEventListener("click", compareBranches);
    $("#btn-copy")?.addEventListener("click", copyForkNarrative);
    $("#btn-export")?.addEventListener("click", exportFork);
    // Mobile dock mirrors primary actions (click-through to same handlers)
    $("#dock-fork")?.addEventListener("click", () => $("#btn-fork")?.click());
    $("#dock-llm")?.addEventListener("click", () => $("#btn-llm")?.click());
    $("#dock-video")?.addEventListener("click", () => $("#btn-video")?.click());
    $("#dock-compare")?.addEventListener("click", () => $("#btn-compare")?.click());
    $("#dock-cancel")?.addEventListener("click", () => {
      const c = $("#btn-cancel-job");
      if (c && !c.disabled) c.click();
    });
    bindStudioKeyboardShortcuts();

    // player gate buttons
    $("#gate-upgrade")?.addEventListener("click", () => navigate("pricing"));
    $("#gate-demo")?.addEventListener("click", async () => {
      try {
        await FHFreemium.acquireDemoToken("scholar");
      } catch (e) {
        FHFreemium.setMember("scholar", "demo from paywall");
      }
      closePaywall();
      toast("Scholar unlocked (demo)");
      if (state.videoId) renderWatch(state.videoId);
      refreshChrome();
    });
    $("#pay-close")?.addEventListener("click", closePaywall);
    $("#pay-demo")?.addEventListener("click", async () => {
      try {
        await FHFreemium.acquireDemoToken("scholar");
      } catch (e) {
        FHFreemium.setMember("scholar", "demo from modal");
      }
      closePaywall();
      toast("Scholar unlocked (demo)");
      refreshChrome();
      route();
    });

    window.addEventListener("hashchange", route);
    window.addEventListener("fh:entitlements", refreshChrome);
    await route();
    // After first successful paint, focus main on subsequent hash navigations
    routeFocusReady = true;
  }

  boot().catch((e) => {
    console.error(e);
    const msg =
      (e && e.message) ||
      "Failed to load catalog — is the site server running?";
    const detail = [e && e.code, e && e.detail].filter(Boolean).join(" · ");
    showBootError(msg, detail || "");
    toast(msg);
  });
})();
