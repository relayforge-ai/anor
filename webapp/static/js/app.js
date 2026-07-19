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
      a.classList.toggle("active", a.dataset.nav === page);
    });
  }

  function showPage(id) {
    $$("[data-page]").forEach((p) => p.classList.toggle("page-hidden", p.dataset.page !== id));
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

    $("#btn-demo-member")?.addEventListener("click", () => {
      FHFreemium.setMember("scholar", "demo unlock for Ryan review");
      toast("Scholar unlocked (demo). Stripe not charged.");
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
    const gatePill =
      access.mode === "full" || access.mode === "claimable_full"
        ? `<span class="pill pill-doc">${access.mode === "claimable_full" ? "Free full" : "Unlocked"}</span>`
        : `<span class="pill pill-warn">${Math.round(access.previewFraction * 100)}% preview</span>`;
    const spec =
      v.speculation === "documented"
        ? `<span class="pill pill-doc">documented</span>`
        : `<span class="pill pill-sim">${escapeHtml(v.speculation)}</span>`;
    return `
      <article class="card video-card" data-video="${escapeHtml(v.id)}">
        <div class="video-card-art" style="background:linear-gradient(145deg,${v.poster_gradient[0]},${v.poster_gradient[1]})">
          <div class="video-card-play">▶</div>
        </div>
        <div class="video-card-body">
          <div class="video-card-meta">${spec}${gatePill}<span class="pill">${escapeHtml(v.era)}</span></div>
          <h3>${escapeHtml(v.title)}</h3>
          <p>${escapeHtml(v.blurb)}</p>
          <div class="note">${escapeHtml(v.runtime_label || "")}</div>
        </div>
      </article>`;
  }

  function bindVideoCards(root) {
    root.querySelectorAll("[data-video]").forEach((el) => {
      el.addEventListener("click", () => navigate("watch/" + el.dataset.video));
    });
  }

  /* ——— Library ——— */
  function renderLibrary() {
    showPage("library");
    setActiveNav("library");
    $("#library-grid").innerHTML = state.catalog.videos.map(videoCardHtml).join("");
    bindVideoCards($("#library-grid"));
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
      <span class="pill">${escapeHtml(video.runtime_label || "")}</span>`;
    $("#watch-blurb").textContent = video.blurb;
    $("#watch-studio").onclick = () => navigate("studio/" + video.scenario_id);

    const player = $("#player");
    const gate = $("#player-gate");
    player.pause();
    player.removeAttribute("src");
    player.load();

    // Claim free full if available
    if (access.mode === "claimable_full") {
      FHFreemium.claimFullVideo(videoId, state.catalog);
      toast("This is your free full episode. Enjoy — after this, new titles are 25% previews.");
    }

    const access2 = FHFreemium.videoAccess(videoId, state.catalog);
    player.src = "/media/videos/" + video.file;
    gate.classList.remove("open");

    player.onloadedmetadata = () => {
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
    if (!r.ok) throw new Error("Scenario load failed");
    return r.json();
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

    let detail;
    try {
      detail = await loadScenarioDetail(scenarioId);
    } catch (e) {
      toast(String(e.message || e));
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
    // Free: all choices visible for viewing; non-historical get "basic" only
    // Advanced multi-compare locked
    const list = $("#choice-list");
    list.innerHTML = choices
      .map((c) => {
        const lockedAdvanced = !member && !c.is_historical;
        return `
        <button type="button" class="choice ${state.choiceId === c.id ? "selected" : ""}" data-choice="${escapeHtml(
          c.id
        )}">
          <span class="choice-label">${escapeHtml(c.label)}</span>
          <span class="choice-meta">
            ${c.is_historical ? "★ historical baseline · " : "counterfactual · "}
            ${escapeHtml(c.speculation_level || "")}
            ${!member && !c.is_historical ? " · free basic fork" : ""}
          </span>
        </button>`;
      })
      .join("");

    list.querySelectorAll("[data-choice]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.choiceId = btn.dataset.choice;
        list.querySelectorAll(".choice").forEach((c) => c.classList.remove("selected"));
        btn.classList.add("selected");
      });
    });

    // default historical
    if (!state.choiceId || !choices.find((c) => c.id === state.choiceId)) {
      state.choiceId = choices.find((c) => c.is_historical)?.id || choices[0]?.id;
      list.querySelector(`[data-choice="${state.choiceId}"]`)?.classList.add("selected");
    }

    renderStudioControls();
    $("#fork-result").innerHTML =
      state.lastFork && state.lastFork.scenario_id === scenarioId
        ? renderForkHtml(state.lastFork)
        : `<div class="note">Pick a decision and run a fork. Documented baselines stay honest; speculation is labeled.</div>`;
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
    const access = FHFreemium.canFork({ catalog: state.catalog, wantLlm: useLlm });
    if (useLlm && !FHFreemium.isMember()) {
      openPaywall(
        "LLM re-render is a Scholar control",
        "Explorer can still run basic authored forks. Upgrade for live simulation prose, compare, seeds, and export."
      );
      return;
    }

    const btn = useLlm ? $("#btn-llm") : $("#btn-fork");
    btn.disabled = true;
    $("#fork-result").innerHTML = `<div class="note">Simulating fork…</div>`;
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Fork failed");
      state.lastFork = data;
      FHFreemium.recordFork();
      $("#fork-result").innerHTML = renderForkHtml(data);
      renderStudioControls();
      refreshChrome();
      toast(useLlm ? "LLM fork ready" : "Fork ready");
    } catch (e) {
      $("#fork-result").innerHTML = `<div class="note" style="color:var(--danger)">${escapeHtml(
        e.message || e
      )}</div>`;
    } finally {
      btn.disabled = false;
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
        $("#pay-confirm").onclick = () => {
          FHFreemium.setMember(plan, "demo checkout stub");
          closePaywall();
          toast(`${plan} unlocked (demo). Wire Stripe when ready.`);
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
    $("#btn-pass").onclick = () => {
      FHFreemium.setMember("library_pass", "90-day pass demo");
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
        navigate(a.dataset.nav === "home" ? "" : a.dataset.nav);
      });
    });
    $("#nav-upgrade")?.addEventListener("click", (e) => {
      e.preventDefault();
      navigate("pricing");
    });

    // studio buttons
    $("#studio-scenario")?.addEventListener("change", (e) => {
      state.choiceId = null;
      state.lastFork = null;
      navigate("studio/" + e.target.value);
    });
    $("#btn-fork")?.addEventListener("click", () => runFork({ useLlm: false }));
    $("#btn-llm")?.addEventListener("click", () => runFork({ useLlm: true }));
    $("#btn-compare")?.addEventListener("click", compareBranches);
    $("#btn-export")?.addEventListener("click", exportFork);

    // player gate buttons
    $("#gate-upgrade")?.addEventListener("click", () => navigate("pricing"));
    $("#gate-demo")?.addEventListener("click", () => {
      FHFreemium.setMember("scholar", "demo from paywall");
      closePaywall();
      toast("Scholar unlocked (demo)");
      if (state.videoId) renderWatch(state.videoId);
      refreshChrome();
    });
    $("#pay-close")?.addEventListener("click", closePaywall);
    $("#pay-demo")?.addEventListener("click", () => {
      FHFreemium.setMember("scholar", "demo from modal");
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
