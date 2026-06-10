"""aigg-skill — a skill-ecosystem manager as a thin layer over the memory kernel.

A skill *is* a `kind=procedural` memory unit, so ecosystem management is memory management: the
registry's four pain points (routing, deduplication, trust, maintenance) are kernel operations
(`select`+closure, `compact`, provenance+`verify_skill`, stale/`reconcile`/`curate`). This module
adds only the skill-specific glue — import, route, report — and reuses the kernel for the rest.
See docs/aigg_skill_design.md.
"""
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from aigg_memory import agent
from aigg_memory.index import select_and_count
from aigg_memory.memory import verify_skill as _verify_skill, verify_beliefs  # noqa: F401


def _slug(registry: str, name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", f"{registry}__{name}".lower()).strip("_")


def import_skills(root: Union[str, Path], corpus: str, manifest: Iterable[Dict], *,
                  registry: str, tier: Optional[int] = None,
                  tier_policy: Optional[Dict[int, str]] = None) -> Dict:
    """Land a registry manifest into the corpus as `kind=procedural` units. Per SkillsBench S1
    (import ≠ trust) the default `status` is `candidate`; `tier_policy` maps a tier to a status
    (e.g. {3: "needs_review"}) so an untrusted tier is held until vetted. Idempotent by slug.
    Each item: {slug|name, description?, category?, ...}. Returns {imported, skipped}."""
    root = Path(root)
    status = (tier_policy or {}).get(tier, "candidate")
    existing = set(agent._all_units(root, corpus))
    imported = skipped = 0
    for item in manifest:
        name = item.get("name") or item.get("slug") or ""
        slug = _slug(registry, item.get("slug") or name)
        if slug in existing:
            skipped += 1
            continue
        desc = item.get("description", "")
        terms = [t for t in re.split(r"[-_\s]+", (item.get("slug") or name).lower()) if len(t) > 2][:6]
        cat = item.get("category")
        fm: Dict = {"name": name, "description": desc, "kind": "procedural",
                    "match": {"user_intent": terms or [name.lower()]}, "id": slug,
                    "status": status, "asserted_by": registry}
        if tier is not None:
            fm["tier"] = tier
        if cat:
            fm["category"] = cat
        p = root / corpus / slug / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        from aigg_memory.memory import MemoryUnit
        p.write_text(MemoryUnit(fm, item.get("body") or desc).to_text(), encoding="utf-8")
        existing.add(slug)
        imported += 1
    return {"imported": imported, "skipped": skipped}


def route(root: Union[str, Path], corpus: str, task: str, *, k: int = 3,
          min_confidence: Optional[float] = None, retriever: str = "semantic",
          embedder=None) -> List[Dict]:
    """Pick skills for a task: the kernel's `select` over `kind=procedural`, capped at `k` (S2:
    route a small focused closure, not a registry dump), then optionally gated by each skill's
    verified track record (`min_confidence`, the V1 confidence). Deterministic (S4). Skills flagged
    `stale` (refuted by verification) are dropped."""
    units, _ = select_and_count(root, corpus, task, n_best=max(k * 2, k), kinds=["procedural"],
                                include_deps=True, retriever=retriever, embedder=embedder)
    fm = agent._all_units(root, corpus)   # the index projection omits stale/verification; read them here
    out: List[Dict] = []
    for u in units:
        meta = fm.get(u["slug"])
        front = meta.frontmatter if meta else {}
        if front.get("stale"):
            continue                      # refuted by verification — not routable
        if min_confidence is not None:
            c = (front.get("verification") or {}).get("confidence")
            if c is not None and float(c) < min_confidence:
                continue
        out.append({**u, "confidence": (front.get("verification") or {}).get("confidence")})
        if len(out) >= k:
            break
    return out


def report(root: Union[str, Path], corpus: str, skill_slug: str, outcome: str, *,
           episode: Optional[str] = None, witness: Optional[str] = None) -> None:
    """Record one invocation outcome (success/failure/neutral) as an episode that references the
    skill (`source_events=[skill_slug]`) — the V1 signal `verify_skill` tallies. `witness` is the
    asserter (default self); a peer's report only counts in `verify` if the host trusts it."""
    slug = episode or f"invoke_{skill_slug}_{outcome}"
    agent.record_episode(root, corpus, slug, f"invoked {skill_slug}: {outcome}",
                         match=["invocation", skill_slug], kind="episodic", outcome=outcome,
                         source_events=[skill_slug], asserted_by=witness)


def verify(root: Union[str, Path], corpus: str, *, write: bool = True,
           refute_threshold: float = 0.5, now: Optional[str] = None,
           witnesses: Optional[List[str]] = None) -> Dict[str, Dict]:
    """V1 sweep: `verify_skill` over every active, non-locked/pinned procedural unit. Confirmed
    skills accrue confidence; refuted ones go `stale` (dropped from routing)."""
    root = Path(root)
    out: Dict[str, Dict] = {}
    from aigg_memory.memory import load_corpus, MemoryUnit
    for p, c in load_corpus(root, corpus).items():
        if not p.endswith("/SKILL.md"):
            continue
        u = MemoryUnit.from_text(c)
        if (u.kind or "semantic") != "procedural" or u.frontmatter.get("status") == "archived":
            continue
        if u.frontmatter.get("locked") or u.frontmatter.get("pinned"):
            continue
        s = Path(p).parent.name
        out[s] = _verify_skill(root, corpus, s, write=write, refute_threshold=refute_threshold,
                               now=now, witnesses=witnesses)
    return out
