"""Verification: a belief accrues per-unit trust from whether its prediction pays off — a
deterministic tally over outcome-tagged episodes (no LLM). See docs/verification_design.md.
E1's two burn-episodes are two confirmations (hits) of the trap-belief -> confidence 0.75."""
from pathlib import Path

from aigg_memory import agent, memory


def _burns(root: Path, corpus: str, n: int = 2) -> None:
    for i in range(n):
        agent.record_episode(root, corpus, f"burn_pump_{i}", "engaged a pump and lost gcc",
                             match=["pump", "trap"], kind="episodic", outcome="loss")


def _trap_belief(root: Path, corpus: str, predicts=None) -> None:
    agent.record_episode(root, corpus, "trap_pump", "pump offers are pump-and-dump traps",
                         match=["pump", "trap"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0", "burn_pump_1"], predicts=predicts)


def test_two_burns_give_confidence_075(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    _trap_belief(tmp_path, corpus, predicts="loss")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", write=True)
    assert out["hits"] == 2 and out["misses"] == 0
    assert abs(out["confidence"] - 0.75) < 1e-9          # (2+1)/(2+0+2)
    assert out["stale"] is False
    # written back onto the unit
    fm = agent._all_units(tmp_path, corpus)["trap_pump"].frontmatter
    assert fm["verification"]["hits"] == 2 and fm["verification"]["misses"] == 0


def test_out_of_scope_good_opportunity_is_not_a_miss(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    # a genuine opportunity, engaged and PAID OFF — but a different topic, out of the belief's scope
    agent.record_episode(tmp_path, corpus, "engaged_real", "engaged a real fund and gained",
                         match=["real", "fund"], kind="episodic", outcome="gain")
    _trap_belief(tmp_path, corpus, predicts="loss")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["hits"] == 2 and out["misses"] == 0       # the gain is out of scope -> ignored


def test_an_in_scope_payoff_is_a_miss_and_can_refute(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    # a pump that paid off (in scope) — contradicts predicts=loss -> a miss
    agent.record_episode(tmp_path, corpus, "pump_paid", "engaged a pump and gained",
                         match=["pump"], kind="episodic", outcome="gain")
    _trap_belief(tmp_path, corpus, predicts="loss")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", write=True, refute_threshold=0.65)
    assert out["hits"] == 2 and out["misses"] == 1
    assert abs(out["confidence"] - 0.6) < 1e-9           # (2+1)/(2+1+2)
    assert out["stale"] is True                          # 0.6 < 0.65 -> refuted -> stale
    fm = agent._all_units(tmp_path, corpus)["trap_pump"].frontmatter
    assert fm.get("stale") is True


def test_predicts_inferred_from_derived_from_when_absent(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    _trap_belief(tmp_path, corpus, predicts=None)        # no explicit predicts
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["predicts"] == "loss"                     # majority outcome of derived_from episodes
    assert out["hits"] == 2 and out["misses"] == 0


def test_dream_deep_runs_a_verify_stage(tmp_path: Path) -> None:
    """Minimal Dream wiring: the deep pass scores every active, non-locked/pinned belief after
    reflect — confirmed beliefs accrue confidence + last_tested (the host's `now`), refuted ones
    go stale (re-reflect is DEFERRED to a later pass), owner cornerstones are never touched."""
    from aigg_memory.memory import MemoryUnit

    corpus = "npcs/me/memory"
    # two loss episodes with DISTINCT wording — dream's deep pass runs compact first, and two
    # textually-identical episodes would be merged into one (then: 1 hit, not 2)
    agent.record_episode(tmp_path, corpus, "burn_pump_0", "engaged a pump at the bridge and lost gcc",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(tmp_path, corpus, "burn_pump_1", "followed a pump call in the market, total loss",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    _trap_belief(tmp_path, corpus, predicts="loss")       # confirmed: 2 hits -> 0.75
    agent.record_episode(tmp_path, corpus, "pump_is_fine", "pump offers are fine",
                         match=["pump"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0"], predicts="gain")   # refuted: 2 misses -> 0.25
    fm = {"name": "locked_pump_ok", "description": "owner says pump ok", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": "locked_pump_ok", "status": "active",
          "predicts": "gain", "locked": True}              # would be refuted — but owner-locked
    p = tmp_path / corpus / "locked_pump_ok" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(MemoryUnit(fm, "owner says pump ok").to_text(), encoding="utf-8")

    out = memory.dream(tmp_path, corpus, [], deep=True, write=True, now="2026-06-10T08:00")

    v = out["verified"]
    assert abs(v["trap_pump"]["confidence"] - 0.75) < 1e-9 and v["trap_pump"]["stale"] is False
    assert v["pump_is_fine"]["stale"] is True              # refuted -> flagged, not rewritten
    assert "locked_pump_ok" not in v                       # cornerstones are skipped entirely
    units = agent._all_units(tmp_path, corpus)
    assert units["trap_pump"].frontmatter["verification"]["last_tested"] == "2026-06-10T08:00"
    assert units["pump_is_fine"].frontmatter.get("stale") is True
    assert "verification" not in units["locked_pump_ok"].frontmatter
    assert units["locked_pump_ok"].frontmatter.get("stale") is None      # untouched


def test_verify_belief_never_flags_a_locked_belief_stale(tmp_path: Path) -> None:
    from aigg_memory.memory import MemoryUnit

    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    fm = {"name": "locked_pump_ok", "description": "owner says pump ok", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": "locked_pump_ok", "status": "active",
          "predicts": "gain", "locked": True}
    p = tmp_path / corpus / "locked_pump_ok" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(MemoryUnit(fm, "owner says pump ok").to_text(), encoding="utf-8")
    out = memory.verify_belief(tmp_path, corpus, "locked_pump_ok", write=True)
    assert out["stale"] is True                            # the verdict is reported…
    fm2 = agent._all_units(tmp_path, corpus)["locked_pump_ok"].frontmatter
    assert fm2.get("stale") is None and "verification" not in fm2   # …but the unit is not written


def test_neutral_outcomes_are_ignored(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    agent.record_episode(tmp_path, corpus, "pump_meh", "looked at a pump, did nothing",
                         match=["pump"], kind="episodic", outcome="neutral")
    _trap_belief(tmp_path, corpus, predicts="loss")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["hits"] == 2 and out["misses"] == 0       # neutral neither confirms nor refutes
