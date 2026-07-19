"""Interactive history-fork engine.

Loads a public scenario packet, presents the historical baseline, accepts a
viewer choice, and returns a fork narrative. Uses LLM_URL when available;
falls back to authored branch text when offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from .clients import LLMClient, PipelineError
from .config import PipelineConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = REPO_ROOT / "scenarios" / "public"


@dataclass
class ForkResult:
    scenario_id: str
    choice_id: str
    is_historical: bool
    speculation_level: str
    label: str
    narrative: str
    source: str  # "authored" | "llm"
    provenance_ribbon: list[str]
    image_prompt: str
    vo_script: str

    def to_dict(self) -> dict:
        return asdict(self)


def list_scenarios(directory: Path = PUBLIC_DIR) -> list[dict[str, str]]:
    out = []
    for p in sorted(directory.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append(
            {
                "scenario_id": data["scenario_id"],
                "title": data["title"],
                "era": data.get("era", ""),
                "decision_question": data.get("decision_question", ""),
                "path": str(p),
            }
        )
    return out


def load_scenario(scenario_id: str, directory: Path = PUBLIC_DIR) -> dict:
    path = directory / f"{scenario_id}.json"
    if not path.exists():
        # allow bare path
        path = Path(scenario_id)
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _choice(scenario: dict, choice_id: str) -> dict:
    for c in scenario["choices"]:
        if c["id"] == choice_id:
            return c
    raise KeyError(f"Unknown choice_id={choice_id!r} for {scenario['scenario_id']}")


def _authored_narrative(scenario: dict, choice: dict) -> str:
    parts = [
        f"# {scenario['title']}",
        "",
        f"**Decision:** {scenario['decision_question']}",
        f"**Choice:** {choice['label']}",
        f"**Speculation level:** {choice['speculation_level']}"
        + (" (historical baseline)" if choice.get("is_historical") else " — SPECULATION"),
        "",
        choice.get("summary", ""),
        "",
        f"**Immediate:** {choice.get('immediate', '')}",
        f"**Near term:** {choice.get('near_term', '')}",
        f"**Longer arc:** {choice.get('longer_arc', '')}",
        "",
        f"**Documented baseline:** {scenario['known_outcome']}",
        "",
        scenario.get("provenance", {}).get("notes", ""),
    ]
    return "\n".join(parts).strip()


def _llm_fork(scenario: dict, choice: dict, llm: LLMClient) -> str:
    system = (
        "You are an ELOSTIRION alternate-history narrator for a public educational product. "
        "Rules (non-negotiable):\n"
        "1. Keep the factual baseline accurate. Never invent primary-source quotes.\n"
        "2. If the branch is not historical, label speculation clearly as SPECULATION / SIMULATED.\n"
        "3. Decision-point framing: what did they know then, not what we know now.\n"
        "4. Write 350–500 words in vivid but restrained documentary prose.\n"
        "5. End with a one-line provenance ribbon using tags documented/dramatized/simulated."
    )
    user = json.dumps(
        {
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "known_outcome": scenario["known_outcome"],
            "opening": scenario["opening"],
            "chosen_branch": choice,
            "sources": scenario.get("sources", []),
        },
        ensure_ascii=False,
        indent=2,
    )
    return llm.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.5,
        max_tokens=900,
    )


def run_fork(
    scenario_id: str,
    choice_id: str,
    cfg: Optional[PipelineConfig] = None,
    use_llm: bool = True,
    directory: Path = PUBLIC_DIR,
) -> ForkResult:
    cfg = cfg or PipelineConfig.from_env()
    scenario = load_scenario(scenario_id, directory=directory)
    choice = _choice(scenario, choice_id)

    narrative = None
    source = "authored"
    if use_llm and not cfg.mock_media and cfg.llm_url:
        try:
            narrative = _llm_fork(scenario, choice, LLMClient(cfg))
            source = "llm"
        except PipelineError:
            narrative = None

    if not narrative:
        narrative = _authored_narrative(scenario, choice)
        source = "authored"

    ribbon = [
        f"baseline:documented",
        f"branch:{choice.get('speculation_level', 'simulated')}",
        f"choice:{choice_id}",
        f"generator:{source}",
    ]

    return ForkResult(
        scenario_id=scenario["scenario_id"],
        choice_id=choice_id,
        is_historical=bool(choice.get("is_historical")),
        speculation_level=choice.get("speculation_level", "simulated"),
        label=choice["label"],
        narrative=narrative,
        source=source,
        provenance_ribbon=ribbon,
        image_prompt=choice.get("image_prompt")
        or scenario.get("style_lock")
        or scenario["title"],
        vo_script=choice.get("vo_script") or choice.get("summary") or narrative[:500],
    )


def scenario_payload(scenario_id: str, directory: Path = PUBLIC_DIR) -> dict[str, Any]:
    """API-safe scenario view (no internal keys)."""
    s = load_scenario(scenario_id, directory=directory)
    return {
        "scenario_id": s["scenario_id"],
        "title": s["title"],
        "era": s.get("era"),
        "location": s.get("location"),
        "datetime": s.get("datetime"),
        "known_outcome": s["known_outcome"],
        "decision_question": s["decision_question"],
        "opening": s["opening"],
        "choices": [
            {
                "id": c["id"],
                "label": c["label"],
                "is_historical": c.get("is_historical", False),
                "speculation_level": c.get("speculation_level"),
                "summary": c.get("summary"),
            }
            for c in s["choices"]
        ],
        "sources": s.get("sources", []),
        "provenance": s.get("provenance", {}),
        "tags": s.get("tags", []),
    }
