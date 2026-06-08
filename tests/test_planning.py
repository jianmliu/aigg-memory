"""Planning = the forward mirror of Reflection: from *beliefs + goals* to *intentions*
(`kind=plan`). A plan rests on its rationale via `derived_from` (goals + beliefs), carries
a FUTURE `valid_from`, is a revisable `candidate` proposal (never a fact, never an action),
and is re-planned (`stale`) when its rationale changes — reusing the SAME stale-propagation
and valid-time machinery reflection uses. The kernel only stores/flags plans; acting on
them belongs to the host loop."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGPlanner, parse_plans
from aigg_memory.index import CorpusIndex, select_and_count


def _unit(root: Path, slug, desc, match, **fm):
    f = {"name": slug, "description": desc, "kind": "semantic",
         "match": {"user_intent": match}, "id": slug, "status": "active"}
    f.update(fm)
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(f, desc).to_text(), encoding="utf-8")


def _seed_goal_and_belief(root: Path) -> None:
    _unit(root, "goal_master_sword", "Master the way of the sword", ["goal", "sword", "master"],
          kind="goal")
    _unit(root, "belief_keeps_losing", "The player keeps losing duels and grows frustrated",
          ["lose", "duel", "frustrated"], kind="belief", status="candidate", asserted_by="self")


# --- parse ---------------------------------------------------------------

def test_parse_plans_tolerant() -> None:
    out = parse_plans(
        '```json\n[{"slug":"p1","name":"P","description":"d","valid_from":"2026-06-08",'
        '"derived_from":["g","b"]}]\n```')
    assert out == [{"slug": "p1", "name": "P", "description": "d", "body": "", "apply": "",
                    "valid_from": "2026-06-08", "derived_from": ["g", "b"], "confidence": "medium"}]
    # no derived_from (no rationale) -> dropped; a plan must rest on something
    assert parse_plans('[{"slug":"p","name":"P","valid_from":"2026-06-08"}]') == []
    assert parse_plans('[{"name":"P","derived_from":["g"]}]') == []   # no slug
    assert parse_plans("junk") == []


def test_planner_backend_stub() -> None:
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_train","name":"Train","description":"d","valid_from":"2026-06-08",'
        '"derived_from":["goal_master_sword","belief_keeps_losing"]}]')
    plans = p.plan([{"slug": "goal_master_sword", "description": "master the sword"}],
                   now="2026-06-07")
    assert plans[0]["slug"] == "plan_train"
    assert plans[0]["derived_from"] == ["goal_master_sword", "belief_keeps_losing"]


# --- plan (generative, forward) ------------------------------------------

def test_plan_synthesizes_intention_with_rationale(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_graded_training","name":"Offer graded sword training",'
        '"description":"A graded training arc so the player can win","apply":"Start next session",'
        '"valid_from":"2026-06-08","derived_from":["goal_master_sword","belief_keeps_losing"]}]')

    out = mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)
    assert "plan_graded_training" in out["written"]

    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "plan_graded_training" / "SKILL.md").read_text())
    assert u.kind == "plan"
    assert u.frontmatter["status"] == "candidate"          # a proposal, not auto-active
    assert u.frontmatter["asserted_by"] == "self"          # the agent's intention, not a fact
    assert sorted(u.frontmatter["derived_from"]) == ["belief_keeps_losing", "goal_master_sword"]
    assert u.frontmatter["valid_from"] == "2026-06-08"     # a FUTURE intention
    assert u.frontmatter["apply"] == "Start next session"


def test_plan_validates_rationale_and_future_validity(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    # p_bad cites only a ghost -> dropped; p_ok cites a real + ghost -> ghost filtered;
    # p_past has a valid_from BEFORE now -> clamped up to now (no back-dated intentions)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"p_bad","name":"bad","description":"d","valid_from":"2026-06-08","derived_from":["ghost"]},'
        '{"slug":"p_ok","name":"ok","description":"d","valid_from":"2026-06-09",'
        '"derived_from":["goal_master_sword","ghost"]},'
        '{"slug":"p_past","name":"past","description":"d","valid_from":"2020-01-01",'
        '"derived_from":["goal_master_sword"]}]')
    out = mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)

    assert sorted(out["written"]) == ["p_ok", "p_past"]
    ok = mem.MemoryUnit.from_text((tmp_path / "memory" / "p_ok" / "SKILL.md").read_text())
    assert ok.frontmatter["derived_from"] == ["goal_master_sword"]   # ghost rationale filtered
    past = mem.MemoryUnit.from_text((tmp_path / "memory" / "p_past" / "SKILL.md").read_text())
    assert past.frontmatter["valid_from"] == "2026-06-07"            # clamped to now


def test_plan_dry_run_writes_nothing(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_x","name":"x","description":"d","valid_from":"2026-06-08",'
        '"derived_from":["goal_master_sword"]}]')
    out = mem.plan(tmp_path, "memory", p, now="2026-06-07", write=False)

    assert out["plans"] and out["written"] == []
    assert not (tmp_path / "memory" / "plan_x").exists()


# --- graph + recall (reuse derived_from / dependency_closure) ------------

def test_plan_rationale_compiles_into_graph(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_q","name":"q","description":"d","valid_from":"2026-06-08",'
        '"derived_from":["goal_master_sword","belief_keeps_losing"]}]')
    mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)

    idx = CorpusIndex(tmp_path, "memory")
    idx.sync()
    assert idx.derived_from("plan_q") == ["belief_keeps_losing", "goal_master_sword"]
    assert "plan_q" in idx.supports("goal_master_sword")    # reverse: goal -> plan resting on it
    assert idx.depends_on("plan_q") == []                   # does NOT pollute depends_on


def test_plan_recall_pulls_rationale(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_training","name":"graded training plan","description":"d",'
        '"valid_from":"2026-06-08","derived_from":["goal_master_sword","belief_keeps_losing"]}]')
    mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)

    units, _ = select_and_count(tmp_path, "memory", "graded training plan", include_deps=True)
    slugs = {u["slug"] for u in units}
    assert "plan_training" in slugs
    assert {"goal_master_sword", "belief_keeps_losing"} <= slugs   # the rationale rides along


# --- replanning = the EXISTING stale-propagation (no new code) -----------

def test_reconcile_marks_dependent_plan_stale(tmp_path: Path) -> None:
    _unit(tmp_path, "loc_sh", "User lives in Shanghai", ["lives", "location"])
    _unit(tmp_path, "loc_bj", "User lives in Beijing", ["lives", "location"])
    # a plan resting on the (soon-stale) fact
    _unit(tmp_path, "plan_visit_sh", "Plan to visit the user in Shanghai next month", ["visit"],
          kind="plan", status="candidate", asserted_by="self",
          derived_from=["loc_sh"], valid_from="2026-07-01")

    judge = type("J", (), {"judge": staticmethod(lambda a, b:
        {"relation": "temporal", "current": "loc_bj", "reason": "moved"})})()
    out = mem.reconcile(tmp_path, "memory", judge, threshold=0.3, write=True, now="2026-06-07")

    # the SAME mark_stale_dependents that flags beliefs flags plans — zero new invalidation code
    assert "plan_visit_sh" in out["stale_marked"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "plan_visit_sh" / "SKILL.md").read_text())
    assert u.frontmatter["stale"] is True
    assert u.frontmatter["status"] == "candidate"   # still a live plan, just queued for replan


# --- temporal: "what is planned for time t" (reuse valid-time index) ------

def test_as_of_surfaces_future_plan(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_future","name":"future plan","description":"d",'
        '"valid_from":"2026-06-08","derived_from":["goal_master_sword"]}]')
    mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)

    idx = CorpusIndex(tmp_path, "memory")
    after = {r["slug"] for r in idx.as_of("2026-06-09", kinds=["plan"])}
    before = {r["slug"] for r in idx.as_of("2026-06-07", kinds=["plan"])}
    assert "plan_future" in after                   # active once its future valid_from arrives
    assert "plan_future" not in before              # not yet active before then
    assert "plan_future" in {r["slug"] for r in idx.timeline(kinds=["plan"])}


# --- guards --------------------------------------------------------------

def test_plan_never_rewrites_locked_plan(tmp_path: Path) -> None:
    _seed_goal_and_belief(tmp_path)
    _unit(tmp_path, "plan_locked", "owner-set cornerstone plan", ["core"],
          kind="plan", locked=True, asserted_by="self",
          derived_from=["goal_master_sword"], valid_from="2026-06-08")
    p = AIGGPlanner(base_url="x", transport=lambda t:
        '[{"slug":"plan_locked","name":"HIJACK","description":"overwritten",'
        '"valid_from":"2026-06-08","derived_from":["goal_master_sword"]}]')
    out = mem.plan(tmp_path, "memory", p, now="2026-06-07", write=True)

    assert "plan_locked" not in out["written"]
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "plan_locked" / "SKILL.md").read_text())
    assert u.frontmatter["name"] == "plan_locked"   # untouched
