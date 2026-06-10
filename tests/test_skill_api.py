"""aigg_memory.skill — the thin skill-ecosystem layer over the kernel (docs/aigg_skill_design.md):
import_skills (registry → candidate units), route (capped, confidence-weighted closure), report
(one invocation outcome → an episode feeding verify_skill). Deterministic; no LLM."""
from pathlib import Path

from aigg_memory import skill, agent, memory


def _manifest():
    return [
        {"slug": "git-bisect", "name": "git bisect helper", "category": "git",
         "description": "drive git bisect to find a regression commit"},
        {"slug": "pdf-edit", "name": "nano pdf", "category": "docs",
         "description": "edit PDFs with natural language"},
    ]


def test_import_skills_lands_candidates_with_provenance(tmp_path: Path) -> None:
    corpus = "skills"
    out = skill.import_skills(tmp_path, corpus, _manifest(), registry="openclaw", tier=3)
    assert out["imported"] == 2
    units = agent._all_units(tmp_path, corpus)
    u = units["openclaw__git_bisect"]
    assert u.kind == "procedural"
    assert u.frontmatter["status"] == "candidate"        # S1: import != trust
    assert u.frontmatter["asserted_by"] == "openclaw"
    assert u.frontmatter.get("tier") == 3
    # re-import is idempotent (same slug, no duplicate)
    assert skill.import_skills(tmp_path, corpus, _manifest(), registry="openclaw", tier=3)["imported"] == 0


def test_tier_policy_quarantines_untrusted(tmp_path: Path) -> None:
    corpus = "skills"
    skill.import_skills(tmp_path, corpus, _manifest(), registry="openclaw", tier=3,
                        tier_policy={3: "needs_review"})
    u = agent._all_units(tmp_path, corpus)["openclaw__git_bisect"]
    assert u.frontmatter["status"] == "needs_review"     # tier3 -> held until vetted


def test_route_returns_capped_confidence_weighted_closure(tmp_path: Path) -> None:
    corpus = "skills"
    skill.import_skills(tmp_path, corpus, _manifest(), registry="openclaw", tier=1,
                        tier_policy={1: "active"})       # active so they're routable
    hits = skill.route(tmp_path, corpus, "help me bisect a git regression", k=3)
    assert hits and hits[0]["slug"] == "openclaw__git_bisect"
    assert len(hits) <= 3                                # S2: capped closure

    # confidence-weighted: a skill with a poor track record is gated out at a high theta
    for i in range(3):
        skill.report(tmp_path, corpus, "openclaw__git_bisect", "failure", episode=f"inv_{i}")
    skill.verify(tmp_path, corpus)                       # V1 sweep -> low confidence + stale
    hits = skill.route(tmp_path, corpus, "help me bisect a git regression", k=3, min_confidence=0.6)
    assert all(h["slug"] != "openclaw__git_bisect" for h in hits)   # refuted skill not routed


def test_report_and_verify_accrue_track_record(tmp_path: Path) -> None:
    corpus = "skills"
    skill.import_skills(tmp_path, corpus, _manifest(), registry="openclaw", tier=1,
                        tier_policy={1: "active"})
    skill.report(tmp_path, corpus, "openclaw__pdf_edit", "success", episode="inv_0")
    skill.report(tmp_path, corpus, "openclaw__pdf_edit", "success", episode="inv_1")
    res = skill.verify(tmp_path, corpus, write=True)
    assert abs(res["openclaw__pdf_edit"]["confidence"] - 0.75) < 1e-9
