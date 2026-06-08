"""Agent-loop convenience layer — the in-process contract a host (e.g. aigg-monopoly) imports.

A thin, **domain-agnostic** wrapper over the kernel that packages the decision/sleep/allocation
hooks proven in the eval lab (E1 individual discernment, E2 social discernment, E5 anti-
manipulation, E4 legibility). It knows nothing of any game — `topic`/`marker` are arbitrary
strings — so the kernel stays reusable and the product's vocabulary lives in the product.

    from aigg_memory import agent
    d = agent.discernment(root, corpus, opp_type, talent=t)   # decision-time q
    if d["q"] <= 0: ...engage...                                # else avoid
    agent.record_episode(root, corpus, slug, desc, asserted_by=caller)  # outcome
    agent.sleep(root, corpus, reflector=r, planner=p, now=now)          # consolidate
    skill = agent.track_record(root, corpus)["skill"]          # legible reputation

Provenance does real work here: a belief I asserted myself (or `reflect`'s "self") is the
**faculty** channel (learned, E1); a belief asserted by someone else is the **social** channel
(a warning relayed to me, E2). One corpus, two channels, split by `asserted_by`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from aigg_memory.memory import MemoryUnit, load_corpus


def _agent_id(corpus: str) -> str:
    """The agent's own id from `npcs/<id>/memory`; else 'self' (the default single-agent corpus)."""
    parts = corpus.strip("/").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "npcs" else "self"


def _is_self(asserted_by, self_id: str) -> bool:
    return asserted_by in (None, "self", self_id)


def _active_beliefs(root, corpus) -> List[Tuple[str, MemoryUnit]]:
    out = []
    for key, text in load_corpus(root, corpus).items():
        u = MemoryUnit.from_text(text)
        if u.kind == "belief" and u.frontmatter.get("status") != "archived":
            out.append((Path(key).parent.name, u))
    return out


def _matches(slug: str, u: MemoryUnit, topic: str, marker: Optional[str]) -> bool:
    terms = " ".join((u.frontmatter.get("match") or {}).get("user_intent") or [])
    hay = f"{slug} {u.frontmatter.get('description', '')} {terms}".lower()
    return topic.lower() in hay and (marker is None or marker.lower() in hay)


# --- decision time --------------------------------------------------------

def believes(root: Union[str, Path], corpus: str, topic: str, *, marker: Optional[str] = "trap") -> bool:
    """True if the agent's memory holds an active belief about `topic` (optionally carrying a
    `marker`, e.g. 'trap'/'manipulator'). The bare recall primitive behind a decision."""
    return any(_matches(s, u, topic, marker) for s, u in _active_beliefs(root, corpus))


def discernment(root: Union[str, Path], corpus: str, topic: str, *, talent: float = 0.0,
                marker: Optional[str] = "trap", self_id: Optional[str] = None,
                faculty_weight: float = 1.0, social_weight: float = 1.0) -> Dict:
    """q = clamp(talent + faculty + social), the discernment a host reads at decision time.
    faculty = a matching belief I learned myself (E1); social = a matching belief a peer warned
    me with (E2) — split by `asserted_by`. Returns {q, faculty, social}."""
    sid = self_id or _agent_id(corpus)
    faculty = social = 0.0
    for s, u in _active_beliefs(root, corpus):
        if _matches(s, u, topic, marker):
            if _is_self(u.frontmatter.get("asserted_by"), sid):
                faculty = 1.0
            else:
                social = 1.0
    q = max(0.0, min(1.0, talent + faculty_weight * faculty + social_weight * social))
    return {"q": q, "faculty": faculty, "social": social}


# --- sleep / consolidation ------------------------------------------------

def record_episode(root: Union[str, Path], corpus: str, slug: str, description: str, *,
                   match: Optional[List[str]] = None, asserted_by: Optional[str] = None,
                   kind: str = "episodic", derived_from: Optional[List[str]] = None) -> None:
    """Write the outcome of an engagement into memory (an episode, or a relayed belief). The
    host's `observe`-equivalent; provenance (`asserted_by`) is who the experience came from."""
    fm: Dict = {"name": slug, "description": description, "kind": kind,
                "match": {"user_intent": match or [slug]}, "id": slug, "status": "active"}
    if asserted_by:
        fm["asserted_by"] = asserted_by
    if derived_from:
        fm["derived_from"] = list(derived_from)
    path = Path(root) / corpus / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MemoryUnit(fm, description).to_text(), encoding="utf-8")


def sleep(root: Union[str, Path], corpus: str, *, reflector=None, planner=None,
          now: Optional[str] = None, reflect_threshold: float = 0.2, embedder=None) -> Dict:
    """The deep cadence: reflect (episodes -> beliefs; learned discernment) then plan
    (goals+beliefs -> intentions). In-process kernel calls; each runs only if its client is given."""
    from aigg_memory import memory
    out: Dict = {}
    if reflector is not None:
        out["reflected"] = memory.reflect(root, corpus, reflector, write=True,
                                          threshold=reflect_threshold, embedder=embedder)
    if planner is not None and now:
        out["planned"] = memory.plan(root, corpus, planner, now=now, write=True, embedder=embedder)
    return out


# --- allocation / reputation (H-legibility) -------------------------------

def track_record(root: Union[str, Path], corpus: str, *, self_id: Optional[str] = None) -> Dict:
    """A legible skill estimate from the provenance-stamped, git-versioned history: how many
    distinct traps the agent learned to recognize *itself* (self-asserted beliefs), weighted by
    the evidence (`derived_from`) behind them. Lets capital be allocated by demonstrated skill
    rather than by current wealth (which is mostly luck) — the patron's legibility lever."""
    sid = self_id or _agent_id(corpus)
    learned = evidence = 0
    for _s, u in _active_beliefs(root, corpus):
        if _is_self(u.frontmatter.get("asserted_by"), sid):
            learned += 1
            evidence += len(u.frontmatter.get("derived_from") or [])
    return {"learned": learned, "evidence": evidence, "skill": round(learned + 0.1 * evidence, 3)}
