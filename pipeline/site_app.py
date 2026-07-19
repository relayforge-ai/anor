"""Interactive fork site — stdlib HTTP server, no hard deps.

Viewers pick a scenario, change the decision, and watch history fork.
LLM-driven when LLM_URL is set; authored branches offline.
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import PipelineConfig
from .fork_engine import list_scenarios, run_fork, scenario_payload

STATIC = Path(__file__).resolve().parent / "static"


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ANOR Fork — watch history split</title>
<style>
  :root {
    --bg: #0f1115; --panel: #1a1f29; --ink: #e8e6e3; --muted: #9aa3b2;
    --accent: #c9a227; --line: #2a3140; --ok: #3d9a6a; --warn: #c97b27;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Iowan Old Style", "Palatino Linotype", Palatino, serif;
    background: radial-gradient(1200px 600px at 10% -10%, #1c2433, var(--bg));
    color: var(--ink); min-height: 100vh;
  }
  header {
    padding: 1.5rem 1.25rem 0.5rem; max-width: 960px; margin: 0 auto;
  }
  header h1 { margin: 0; font-size: 1.6rem; letter-spacing: 0.02em; }
  header p { color: var(--muted); margin: 0.4rem 0 0; max-width: 42rem; }
  main { max-width: 960px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }
  .grid { display: grid; gap: 1rem; }
  @media (min-width: 800px) { .grid.two { grid-template-columns: 1fr 1fr; } }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 1rem 1.1rem;
  }
  .card h2 { margin: 0 0 0.6rem; font-size: 1.05rem; color: var(--accent); }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.3rem; }
  select, button {
    width: 100%; font: inherit; padding: 0.65rem 0.75rem; border-radius: 8px;
    border: 1px solid var(--line); background: #12161e; color: var(--ink);
  }
  button {
    background: linear-gradient(180deg, #d4b03a, #a8841c); color: #1a1405;
    font-weight: 700; border: none; cursor: pointer; margin-top: 0.75rem;
  }
  button:disabled { opacity: 0.5; cursor: wait; }
  .pill {
    display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem;
    border-radius: 999px; border: 1px solid var(--line); color: var(--muted);
    margin-right: 0.35rem;
  }
  .pill.doc { color: var(--ok); border-color: #2f6b4c; }
  .pill.sim { color: var(--warn); border-color: #7a4e16; }
  #opening, #result { white-space: pre-wrap; line-height: 1.45; }
  #result { min-height: 8rem; }
  footer { max-width: 960px; margin: 0 auto; padding: 0 1.25rem 2rem; color: var(--muted); font-size: 0.85rem; }
  a { color: var(--accent); }
  .ribbon { font-family: ui-monospace, monospace; font-size: 0.8rem; color: var(--muted); }
</style>
</head>
<body>
<header>
  <h1>ANOR Fork</h1>
  <p>Change the decision. Watch history split. Documented baselines stay honest;
     counterfactuals are labeled speculation — ELOSTIRION discipline.</p>
</header>
<main class="grid two">
  <section class="card">
    <h2>1 · Scenario</h2>
    <label for="scenario">Public pack</label>
    <select id="scenario"></select>
    <div id="meta" style="margin-top:0.8rem"></div>
    <div id="opening" style="margin-top:0.8rem;color:var(--muted);font-size:0.95rem"></div>
  </section>
  <section class="card">
    <h2>2 · Decision</h2>
    <label for="choice">What do they do?</label>
    <select id="choice"></select>
    <button id="run">Fork history</button>
    <p class="ribbon" id="health" style="margin-top:0.8rem"></p>
  </section>
  <section class="card" style="grid-column: 1 / -1">
    <h2>3 · The fork</h2>
    <div id="result">Pick a branch and press <em>Fork history</em>.</div>
  </section>
</main>
<footer>
  Public packs only · No MANDOS master sources · Human-gated publishing ·
  Endpoints via <code>LLM_URL</code> / <code>IMAGE_URL</code> / <code>TTS_URL</code>
</footer>
<script>
async function j(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
const scenarioEl = document.getElementById('scenario');
const choiceEl = document.getElementById('choice');
const metaEl = document.getElementById('meta');
const openingEl = document.getElementById('opening');
const resultEl = document.getElementById('result');
const healthEl = document.getElementById('health');
const runBtn = document.getElementById('run');
let current = null;

function pill(level, hist) {
  const cls = level === 'documented' || hist ? 'doc' : 'sim';
  const label = hist ? 'historical baseline' : level;
  return `<span class="pill ${cls}">${label}</span>`;
}

async function loadList() {
  const items = await j('/api/scenarios');
  scenarioEl.innerHTML = items.map(s =>
    `<option value="${s.scenario_id}">${s.scenario_id} — ${s.title}</option>`
  ).join('');
  await loadScenario();
  const h = await j('/api/health');
  healthEl.textContent = `LLM: ${h.llm} · IMAGE: ${h.image} · TTS: ${h.tts}`;
}

async function loadScenario() {
  current = await j('/api/scenario/' + scenarioEl.value);
  metaEl.innerHTML = `
    ${pill('documented', true)}
    <span class="pill">${current.era || ''}</span>
    <div style="margin-top:0.6rem"><strong>${current.decision_question}</strong></div>
    <div style="margin-top:0.4rem;color:var(--muted);font-size:0.9rem"><em>Known outcome:</em> ${current.known_outcome}</div>`;
  openingEl.textContent = (current.opening.cold_open || '') + "\n\n" + (current.opening.what_they_knew || '');
  choiceEl.innerHTML = current.choices.map(c =>
    `<option value="${c.id}">${c.label}${c.is_historical ? ' ★' : ''}</option>`
  ).join('');
}

runBtn.addEventListener('click', async () => {
  runBtn.disabled = true;
  resultEl.textContent = 'Simulating fork…';
  try {
    const body = { scenario_id: scenarioEl.value, choice_id: choiceEl.value };
    const fork = await j('/api/fork', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    resultEl.innerHTML = `
      ${pill(fork.speculation_level, fork.is_historical)}
      <span class="pill">source: ${fork.source}</span>
      <div style="margin:0.6rem 0 0.3rem"><strong>${fork.label}</strong></div>
      <div>${fork.narrative.replace(/</g,'&lt;')}</div>
      <p class="ribbon" style="margin-top:0.8rem">${fork.provenance_ribbon.join(' · ')}</p>`;
  } catch (e) {
    resultEl.textContent = 'Error: ' + e.message;
  } finally {
    runBtn.disabled = false;
  }
});
scenarioEl.addEventListener('change', loadScenario);
loadList();
</script>
</body>
</html>
"""


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    cfg = PipelineConfig.from_env()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[site] {self.address_string()} {fmt % args}")

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._send(code, raw, "application/json; charset=utf-8")

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/scenarios":
                self._json(200, list_scenarios())
                return
            if path == "/api/health":
                from .clients import healthcheck

                self._json(200, healthcheck(cfg))
                return
            if path.startswith("/api/scenario/"):
                sid = urllib.parse.unquote(path[len("/api/scenario/") :])
                try:
                    self._json(200, scenario_payload(sid))
                except FileNotFoundError:
                    self._json(404, {"error": "not found"})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/api/fork":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
                result = run_fork(
                    data["scenario_id"],
                    data["choice_id"],
                    cfg=cfg,
                    use_llm=True,
                )
                self._json(200, result.to_dict())
            except Exception as e:
                self._json(400, {"error": str(e)})

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"ANOR Fork site → http://{host}:{port}")
    print(json.dumps(cfg.describe(), indent=2))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()
