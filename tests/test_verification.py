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


def test_neutral_outcomes_are_ignored(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burns(tmp_path, corpus)
    agent.record_episode(tmp_path, corpus, "pump_meh", "looked at a pump, did nothing",
                         match=["pump"], kind="episodic", outcome="neutral")
    _trap_belief(tmp_path, corpus, predicts="loss")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["hits"] == 2 and out["misses"] == 0       # neutral neither confirms nor refutes
