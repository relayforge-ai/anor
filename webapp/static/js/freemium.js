/**
 * Client-side freemium state for Forked History.
 * Production: swap isMember / entitlements for server session + Stripe.
 */
(function (global) {
  const KEY = "forked_history_entitlements_v1";

  const DEFAULTS = {
    isMember: false,
    plan: "explorer",
    memberToken: null, // server-issued Scholar token (X-ANOR-Member)
    fullVideosUnlocked: [], // video ids fully watched/unlocked free
    previewVideos: [], // videos where preview was used
    forksToday: 0,
    forksDay: null,
    customSeedUses: 0,
    demoNote: null,
  };

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { ...DEFAULTS };
      return { ...DEFAULTS, ...JSON.parse(raw) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function save(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
    global.dispatchEvent(new CustomEvent("fh:entitlements", { detail: state }));
  }

  function getCatalogRules(catalog) {
    return (
      (catalog && catalog.freemium) || {
        full_videos_free: 1,
        preview_fraction: 0.25,
        free_forks_per_day: 3,
      }
    );
  }

  function refreshDay(state) {
    const d = today();
    if (state.forksDay !== d) {
      state.forksDay = d;
      state.forksToday = 0;
    }
    return state;
  }

  /** Correlate browser calls with [forked-history] rid= server logs (16 hex). */
  function newRequestId() {
    try {
      if (global.crypto && typeof global.crypto.randomUUID === "function") {
        return global.crypto.randomUUID().replace(/-/g, "").slice(0, 16);
      }
    } catch (_) {}
    return (
      Date.now().toString(16).slice(-8) + Math.random().toString(16).slice(2, 10)
    ).slice(0, 16);
  }

  const Freemium = {
    load,
    save,
    newRequestId,

    isMember() {
      return !!load().isMember;
    },

    setMember(plan = "scholar", note = "demo", token = null) {
      const s = load();
      s.isMember = true;
      s.plan = plan;
      s.demoNote = note;
      if (token) s.memberToken = token;
      save(s);
      return s;
    },

    memberToken() {
      return load().memberToken || null;
    },

    authHeaders(extra) {
      const h = Object.assign(
        {
          "Content-Type": "application/json",
          "X-Request-ID": newRequestId(),
        },
        extra || {}
      );
      const t = load().memberToken;
      if (t) h["X-ANOR-Member"] = t;
      return h;
    },

    /** Headers for GET/polls that do not need JSON Content-Type. */
    apiHeaders(extra) {
      return Object.assign({ "X-Request-ID": newRequestId() }, extra || {});
    },

    async acquireDemoToken(plan = "scholar") {
      const r = await fetch("/api/member/demo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": newRequestId(),
        },
        body: JSON.stringify({ plan }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const err = new Error(data.error || "Demo token failed");
        err.code = data.code;
        throw err;
      }
      const s = load();
      s.isMember = true;
      s.plan = data.plan || plan;
      s.memberToken = data.token;
      s.demoNote = "server demo token";
      save(s);
      return data;
    },

    clearMember() {
      const s = load();
      s.isMember = false;
      s.plan = "explorer";
      s.demoNote = null;
      s.memberToken = null;
      save(s);
      return s;
    },

    resetAll() {
      save({ ...DEFAULTS });
      return load();
    },

    /**
     * Video access model:
     * - member: full
     * - if video already in fullVideosUnlocked: full
     * - if free full slots remain: can claim full
     * - else: preview only (first preview_fraction)
     */
    videoAccess(videoId, catalog) {
      const s = load();
      const rules = getCatalogRules(catalog);
      if (s.isMember) {
        return { mode: "full", reason: "member", previewFraction: 1 };
      }
      if (s.fullVideosUnlocked.includes(videoId)) {
        return { mode: "full", reason: "free_full_claimed", previewFraction: 1 };
      }
      const slots = rules.full_videos_free ?? 1;
      if (s.fullVideosUnlocked.length < slots) {
        return {
          mode: "claimable_full",
          reason: "free_full_remaining",
          remaining: slots - s.fullVideosUnlocked.length,
          previewFraction: 1,
        };
      }
      return {
        mode: "preview",
        reason: "preview_only",
        previewFraction: rules.preview_fraction ?? 0.25,
      };
    },

    claimFullVideo(videoId, catalog) {
      const s = load();
      if (s.isMember) return { ok: true, state: s };
      const rules = getCatalogRules(catalog);
      if (s.fullVideosUnlocked.includes(videoId)) return { ok: true, state: s };
      if (s.fullVideosUnlocked.length >= (rules.full_videos_free ?? 1)) {
        return { ok: false, error: "no_free_full_slots", state: s };
      }
      s.fullVideosUnlocked.push(videoId);
      save(s);
      return { ok: true, state: s };
    },

    markPreview(videoId) {
      const s = load();
      if (!s.previewVideos.includes(videoId)) {
        s.previewVideos.push(videoId);
        save(s);
      }
      return s;
    },

    /**
     * Free: historical choice always; non-historical after free forks exhausted still viewable
     * as authored, but LLM + advanced controls locked.
     */
    canFork(opts = {}) {
      let s = refreshDay(load());
      const catalog = opts.catalog;
      const rules = getCatalogRules(catalog);
      if (s.isMember) return { ok: true, mode: "full", remaining: Infinity };

      const limit = rules.free_forks_per_day ?? 3;
      if (s.forksToday >= limit) {
        return {
          ok: true,
          mode: "authored_only",
          remaining: 0,
          message: "Daily free forks used — authored branches still work; LLM re-render is Scholar.",
        };
      }
      return {
        ok: true,
        mode: opts.wantLlm ? "authored_only" : "basic",
        remaining: limit - s.forksToday,
        llmLocked: !s.isMember,
      };
    },

    recordFork() {
      let s = refreshDay(load());
      s.forksToday += 1;
      save(s);
      return s;
    },

    canUseControl(control, catalog) {
      const s = load();
      if (s.isMember) return true;
      const free = (catalog && catalog.freemium && catalog.freemium.free_controls) || [];
      return free.includes(control);
    },

    statusSummary(catalog) {
      const s = refreshDay(load());
      const rules = getCatalogRules(catalog);
      const fullLeft = Math.max(0, (rules.full_videos_free ?? 1) - s.fullVideosUnlocked.length);
      const forksLeft = s.isMember
        ? "∞"
        : Math.max(0, (rules.free_forks_per_day ?? 3) - s.forksToday);
      return {
        isMember: s.isMember,
        plan: s.plan,
        fullVideosUsed: s.fullVideosUnlocked.length,
        fullVideosFree: rules.full_videos_free ?? 1,
        fullLeft,
        forksToday: s.forksToday,
        forksLeft,
        previewFraction: Math.round((rules.preview_fraction ?? 0.25) * 100),
        demoNote: s.demoNote,
      };
    },
  };

  global.FHFreemium = Freemium;
})(window);
