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
  };

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
    sgrid.innerHTML = state.scenarios
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
          <div class="note">${
            unavailable
              ? "Media missing — open Studio and queue a render"
              : escapeHtml(v.runtime_label || "")
          }</div>
        </div>
      </article>`;
  }

  function bindVideoCards(root) {
    root.querySelectorAll("[data-video]").forEach((el) => {
      el.addEventListener("click", () => navigate("watch/" + el.dataset.video));
    });
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
  function renderLibrary() {
    showPage("library");
    setActiveNav("library");
    const videos = state.catalog.videos || [];
    const grid = $("#library-grid");
    if (!videos.length) {
      grid.innerHTML = libraryEmptyHtml("Catalog has no episode entries yet.");
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

    const player = $("#player");
    const gate = $("#player-gate");
    player.pause();
    player.removeAttribute("src");
    player.onloadedmetadata = null;
    player.oncanplay = null;
    player.onerror = null;
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
    const r = await fetch("/api/scenario/" + encodeURIComponent(id));
    if (!r.ok) {
      let msg = "Scenario load failed";
      try {
        const err = await r.json();
        if (err.error) msg = err.error;
      } catch (_) {}
      throw new Error(msg);
    }
    return r.json();
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
    return `
      <div class="sim-progress" aria-busy="true">
        <p class="sim-progress-label">${escapeHtml(label || "Working…")}</p>
        <div class="${barClass}" role="progressbar" aria-valuemin="0" aria-valuemax="100"
             aria-valuenow="${indeterminate ? 0 : Math.round(width)}"
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

  function renderForkError(message, code) {
    return `
      <div class="fork-error" role="alert">
        ${escapeHtml(message || "Something went wrong")}
        ${code ? `<span class="code">${escapeHtml(code)}</span>` : ""}
      </div>`;
  }

  async function renderStudio(scenarioId) {
    showPage("studio");
    setActiveNav("studio");
    if (!scenarioId) scenarioId = state.scenarios[0]?.scenario_id;
    state.scenarioId = scenarioId;

    const select = $("#studio-scenario");
    select.innerHTML = state.scenarios
      .map(
        (s) =>
          `<option value="${escapeHtml(s.scenario_id)}" ${
            s.scenario_id === scenarioId ? "selected" : ""
          }>${escapeHtml(s.scenario_id)} — ${escapeHtml(s.title)}</option>`
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
    $("#fork-result").innerHTML =
      state.lastFork && state.lastFork.scenario_id === scenarioId
        ? renderForkHtml(state.lastFork)
        : `<div class="note">Pick a decision and run a fork. Documented baselines stay honest; speculation is labeled.</div>`;
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
      ? `<strong>Scholar studio</strong> — LLM re-render, compare, export unlocked`
      : `<strong>Explorer studio</strong> — basic authored forks (${st.forksLeft} counted today). LLM re-render, multi-branch compare, custom seeds & export require Scholar.`;

    const tiles = $("#control-tiles");
    const controls = [
      { id: "authored_fork", label: "Authored fork", free: true, desc: "Canon branch text, always labeled" },
      { id: "llm_rerender", label: "LLM re-render", free: false, desc: "Live simulation prose via LLM_URL" },
      { id: "compare_branches", label: "Compare branches", free: false, desc: "Side-by-side historical vs fork" },
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

    // custom seed field
    $("#seed-wrap").style.display = member ? "block" : "none";
    $("#btn-llm").disabled = !member;
    $("#btn-compare").disabled = !member;
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
      <p class="ribbon" style="margin-top:1rem">${escapeHtml((fork.provenance_ribbon || []).join(" · "))}</p>`;
  }

  async function runFork({ useLlm }) {
    if (!state.scenarioId || !state.choiceId) {
      toast("Select a scenario and a decision first.");
      return;
    }
    if (useLlm && !FHFreemium.isMember()) {
      openPaywall(
        "LLM re-render is a Scholar control",
        "Explorer can still run basic authored forks. Upgrade for live simulation prose, compare, seeds, and export."
      );
      return;
    }

    const btn = useLlm ? $("#btn-llm") : $("#btn-fork");
    const other = useLlm ? $("#btn-fork") : $("#btn-llm");
    const stages = forkStages(useLlm);
    let stageIdx = 0;
    let tickTimer = null;

    const setBusy = (on) => {
      [btn, other, $("#btn-compare"), $("#btn-export")].forEach((el) => {
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
        throw err;
      }
      if (tickTimer) clearInterval(tickTimer);
      paint(stages.length - 1, 100, "Provenance attached — rendering…", false);
      // Brief beat so users see completion before narrative replaces the bar
      await new Promise((res) => setTimeout(res, 180));
      state.lastFork = data;
      FHFreemium.recordFork();
      $("#fork-result").innerHTML = renderForkHtml(data);
      renderStudioControls();
      refreshChrome();
      toast(useLlm ? "LLM fork ready" : "Fork ready");
    } catch (e) {
      if (tickTimer) clearInterval(tickTimer);
      const stagesErr = stages.map((s, i) => ({
        ...s,
      }));
      $("#fork-result").innerHTML =
        renderSimProgress({
          stages: stagesErr,
          activeIndex: stageIdx,
          pct: Math.min(88, 12 + stageIdx * 22),
          label: "Simulation interrupted",
          indeterminate: false,
        }) + renderForkError(e.message || String(e), e.code || "error");
      // mark active stage as error via class patch
      const active = $("#fork-result")?.querySelector(".sim-stages li.active");
      if (active) {
        active.classList.remove("active");
        active.classList.add("error");
      }
    } finally {
      if (tickTimer) clearInterval(tickTimer);
      setBusy(false);
      renderStudioControls();
    }
  }

  async function queueVideoRender() {
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

    const btn = $("#btn-video");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("busy");
    }

    const stages = [
      { id: "queue", label: "Accepted by render queue" },
      { id: "fork", label: "Decision narrative" },
      { id: "script", label: "VO script & shot list" },
      { id: "segment", label: "Stills · TTS · clips" },
      { id: "concat", label: "Final MP4 assembly" },
    ];

    const stageIndex = (stage) => {
      const map = { queued: 0, starting: 0, load: 1, fork: 1, script: 2, segment: 3, concat: 4, done: 4, error: 3 };
      return map[stage] ?? 0;
    };

    try {
      const r = await fetch("/api/video/jobs", {
        method: "POST",
        headers: FHFreemium.authHeaders(),
        body: JSON.stringify({
          scenario_id: state.scenarioId,
          choice_id: state.choiceId,
          use_llm: false,
        }),
      });
      const job = await r.json().catch(() => ({}));
      if (!r.ok && r.status !== 202) {
        throw Object.assign(new Error(job.error || "Enqueue failed"), { code: job.code });
      }

      const jobId = job.id;
      toast("Video job queued");
      let done = false;
      let pollMs = 500;
      const pollMax = 4000;
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
      while (!done) {
        const pr = await fetch("/api/video/jobs/" + encodeURIComponent(jobId));
        const st = await pr.json();
        if (!pr.ok) throw Object.assign(new Error(st.error || "Poll failed"), { code: st.code });

        const idx = stageIndex(st.stage);
        const cancelBar =
          st.status === "queued" || st.status === "running"
            ? `<div class="row" style="margin-top:0.8rem"><button type="button" class="btn btn-ghost btn-sm" id="btn-cancel-job">Cancel render</button></div>`
            : "";
        $("#fork-result").innerHTML =
          renderSimProgress({
            stages,
            activeIndex: st.status === "failed" ? idx : idx,
            pct: st.pct || 0,
            label: st.message || st.status,
            indeterminate: st.status === "queued",
          }) + cancelBar;
        bindCancel();

        if (st.status === "completed") {
          done = true;
          const url = st.result?.media_url || "";
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: stages.length - 1,
              pct: 100,
              label: "Render complete",
              indeterminate: false,
            }) +
            `<div style="margin-top:1rem">
              <p class="note">Async job <code>${escapeHtml(jobId)}</code> finished.</p>
              ${
                url
                  ? `<a class="btn btn-primary btn-sm" href="${escapeHtml(url)}" target="_blank" rel="noopener">Open MP4</a>
                     <video controls playsinline style="width:100%;margin-top:0.8rem;border-radius:12px;border:1px solid var(--line)" src="${escapeHtml(url)}"></video>`
                  : ""
              }
            </div>`;
          toast("Video ready");
        } else if (st.status === "cancelled") {
          done = true;
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: idx,
              pct: st.pct || 0,
              label: "Cancelled",
              indeterminate: false,
            }) + `<p class="note" style="margin-top:0.8rem">Job <code>${escapeHtml(jobId)}</code> was cancelled.</p>`;
          toast("Render cancelled");
        } else if (st.status === "failed") {
          done = true;
          $("#fork-result").innerHTML =
            renderSimProgress({
              stages,
              activeIndex: idx,
              pct: st.pct || 0,
              label: "Render failed",
              indeterminate: false,
            }) + renderForkError(st.error || "Render failed", "video_failed");
          const active = $("#fork-result")?.querySelector(".sim-stages li.active");
          if (active) {
            active.classList.remove("active");
            active.classList.add("error");
          }
        } else {
          // Exponential backoff polling — less load while queued/running long renders
          await new Promise((res) => setTimeout(res, pollMs));
          pollMs = Math.min(pollMax, Math.round(pollMs * 1.35));
        }
      }
    } catch (e) {
      $("#fork-result").innerHTML = renderForkError(e.message || String(e), e.code || "video_error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("busy");
      }
      renderStudioControls();
    }
  }

  function compareBranches() {
    if (!FHFreemium.isMember()) {
      openPaywall("Compare branches", "Scholar unlocks side-by-side historical vs counterfactual.");
      return;
    }
    const d = state.scenarioDetail;
    if (!d) return;
    const hist = d.choices.find((c) => c.is_historical);
    const cur = d.choices.find((c) => c.id === state.choiceId);
    $("#fork-result").innerHTML = `
      <div class="result-title">Branch compare</div>
      <div class="grid grid-2" style="margin-top:0.8rem">
        <div class="card" style="padding:1rem">
          <span class="pill pill-doc">historical</span>
          <h3 style="margin:0.5rem 0">${escapeHtml(hist?.label || "")}</h3>
          <p style="color:var(--ink-dim)">${escapeHtml(hist?.summary || "")}</p>
          <p class="note">${escapeHtml(hist?.longer_arc || "")}</p>
        </div>
        <div class="card" style="padding:1rem">
          <span class="pill pill-sim">${escapeHtml(cur?.speculation_level || "simulated")}</span>
          <h3 style="margin:0.5rem 0">${escapeHtml(cur?.label || "")}</h3>
          <p style="color:var(--ink-dim)">${escapeHtml(cur?.summary || "")}</p>
          <p class="note">${escapeHtml(cur?.longer_arc || "")}</p>
        </div>
      </div>`;
  }

  function exportFork() {
    if (!FHFreemium.isMember()) {
      openPaywall("Export", "Scholar can download fork narratives as markdown.");
      return;
    }
    if (!state.lastFork) {
      toast("Run a fork first");
      return;
    }
    const f = state.lastFork;
    const md = `# ${f.scenario_id} — ${f.label}\n\n` +
      `Speculation: ${f.speculation_level}\nSource: ${f.source}\n\n` +
      f.narrative +
      `\n\nRibbon: ${(f.provenance_ribbon || []).join(" · ")}\n`;
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${f.scenario_id}-${f.choice_id}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
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

  /* ——— Paywall modal ——— */
  function openPaywall(title, copy) {
    $("#pay-title").textContent = title;
    $("#pay-copy").textContent = copy;
    $("#paywall").classList.add("open");
  }
  function closePaywall() {
    $("#paywall").classList.remove("open");
  }

  /* ——— Router ——— */
  async function route() {
    const { page, a } = parseHash();
    state.route = page;
    clearPreviewWatch();
    refreshChrome();
    if (page === "library") return renderLibrary();
    if (page === "watch") return renderWatch(a);
    if (page === "studio") return renderStudio(a);
    if (page === "pricing") return renderPricing();
    return renderHome();
  }

  /* ——— Boot ——— */
  async function boot() {
    const [catRes, scenRes] = await Promise.all([fetch("/api/catalog"), fetch("/api/scenarios")]);
    state.catalog = await catRes.json();
    state.scenarios = await scenRes.json();

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
      if (e.key === "Escape") closeNav();
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900) closeNav();
    });

    // studio buttons
    $("#studio-scenario")?.addEventListener("change", (e) => {
      state.choiceId = null;
      state.lastFork = null;
      navigate("studio/" + e.target.value);
    });
    $("#btn-fork")?.addEventListener("click", () => runFork({ useLlm: false }));
    $("#btn-llm")?.addEventListener("click", () => runFork({ useLlm: true }));
    $("#btn-video")?.addEventListener("click", () => queueVideoRender());
    $("#btn-compare")?.addEventListener("click", compareBranches);
    $("#btn-export")?.addEventListener("click", exportFork);

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
  }

  boot().catch((e) => {
    console.error(e);
    toast("Failed to load catalog — is the site server running?");
  });
})();
