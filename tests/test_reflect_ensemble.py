"""reflect_ensemble — cross-MODEL deliberation (not same-model repeats): N different reflectors
propose beliefs; the judge is DETERMINISTIC provenance clustering (beliefs citing the same
evidence are the same belief, §6); consensus = how many distinct models agree. Consensus is a
SYNTHESIS-TIME PRIOR stored in a separate `consensus` field — never folded into the verification
outcome tally (that would repeat train=test at the model layer). See verification_design.md.
"""
from pathlib import Path

from aigg_memory import agent, memory


class _StubReflector:
    """A model stand-in: returns a fixed list of proposed beliefs, ignoring the prompt."""
    def __init__(self, name, beliefs):
        self.name = name
        self._beliefs = beliefs

    def reflect(self, units):
        return [dict(b) for b in self._beliefs]


def _two_burns(root, corpus):
    agent.record_episode(root, corpus, "burn_pump_0", "engaged a pump at the bridge and lost",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(root, corpus, "burn_pump_1", "a pump in the market rugged me",
                         match=["pump", "trap"], kind="episodic", outcome="loss")


def _b(slug, df, predicts="loss", desc="pump is a trap"):
    return {"slug": slug, "name": slug, "description": desc, "derived_from": df, "predicts": predicts}


def test_unanimous_consensus_is_written_with_a_prior(tmp_path):
    corpus = "npcs/me/memory"
    _two_burns(tmp_path, corpus)
    # three DIFFERENT models, each wording its belief differently, all citing the same evidence
    r = [_StubReflector("gemma", [_b("trap_a", ["burn_pump_0", "burn_pump_1"], desc="pump = scam")]),
         _StubReflector("qwen", [_b("trap_b", ["burn_pump_0"], desc="avoid pump offers")]),
         _StubReflector("llama", [_b("trap_c", ["burn_pump_1"], desc="pumps are predatory")])]
    out = memory.reflect_ensemble(tmp_path, corpus, r, consensus_k=2, write=True)
    assert len(out["written"]) == 1                       # one canonical belief from the cluster
    slug = out["written"][0]
    cons = agent._all_units(tmp_path, corpus)[slug].frontmatter["consensus"]
    assert cons["agree"] == 3 and cons["of"] == 3         # 3 distinct models, provenance-clustered
    # the union of cited evidence is preserved
    assert set(agent._all_units(tmp_path, corpus)[slug].frontmatter["derived_from"]) == {"burn_pump_0", "burn_pump_1"}


def test_singleton_is_deferred_not_written(tmp_path):
    corpus = "npcs/me/memory"
    _two_burns(tmp_path, corpus)
    r = [_StubReflector("gemma", [_b("trap_a", ["burn_pump_0", "burn_pump_1"])]),
         _StubReflector("qwen", []),                       # abstains
         _StubReflector("llama", [])]                      # abstains
    out = memory.reflect_ensemble(tmp_path, corpus, r, consensus_k=2, write=True)
    assert out["written"] == []                            # 1/3 < k -> not auto-written
    assert len(out["deferred"]) == 1                       # surfaced as a candidate, not trusted


def test_predicts_conflict_is_deferred(tmp_path):
    corpus = "npcs/me/memory"
    _two_burns(tmp_path, corpus)
    # all three cite the same evidence but DISAGREE on direction -> uncertain -> defer (§8)
    r = [_StubReflector("gemma", [_b("a", ["burn_pump_0"], predicts="loss")]),
         _StubReflector("qwen", [_b("b", ["burn_pump_0"], predicts="loss")]),
         _StubReflector("llama", [_b("c", ["burn_pump_0"], predicts="gain")])]
    out = memory.reflect_ensemble(tmp_path, corpus, r, consensus_k=2, write=True)
    assert out["written"] == [] and len(out["deferred"]) == 1
    assert out["deferred"][0]["reason"] == "predicts_conflict"


def test_consensus_does_not_touch_the_verification_tally(tmp_path):
    corpus = "npcs/me/memory"
    _two_burns(tmp_path, corpus)
    r = [_StubReflector("gemma", [_b("trap_a", ["burn_pump_0", "burn_pump_1"])]),
         _StubReflector("qwen", [_b("trap_b", ["burn_pump_0", "burn_pump_1"])])]
    out = memory.reflect_ensemble(tmp_path, corpus, r, consensus_k=2, write=True)
    fm = agent._all_units(tmp_path, corpus)[out["written"][0]].frontmatter
    assert "consensus" in fm and "verification" not in fm  # prior is separate from earned trust
