"""Verification: a belief accrues per-unit trust from whether its prediction pays off — a
deterministic tally over outcome-tagged episodes (no LLM). See docs/verification_design.md.

Three statistical/adversarial properties under test (the review fixes):
- derivation evidence is the PRIOR, not a test — the episodes a belief is `derived_from` justified
  creating it (training set); only OTHER in-scope episodes count as tests (no train=test reuse);
- scope comes from the EVIDENCE as well as the belief's own wording (the §6 move) — a real model's
  oddly-worded belief is still tested by episodes matching its cited sources;
- a peer's episode is NOT a test unless the host trusts the witness (`witnesses=`) — otherwise an
  adversary could refute my trap-belief by relaying fake outcome=gain episodes (the verification
  axis must not bypass the provenance axis).
"""
from pathlib import Path

from aigg_memory import agent, memory


def _burn(root: Path, corpus: str, slug: str, desc: str, **kw) -> None:
    agent.record_episode(root, corpus, slug, desc, match=kw.pop("match", ["pump", "trap"]),
                         kind="episodic", outcome=kw.pop("outcome", "loss"), **kw)


def _trap_belief(root: Path, corpus: str, *, cites, predicts="loss", match=None) -> None:
    agent.record_episode(root, corpus, "trap_pump", "pump offers are pump-and-dump traps",
                         match=match or ["pump", "trap"], kind="belief", asserted_by="self",
                         derived_from=list(cites), predicts=predicts)


def test_derivation_evidence_is_prior_not_test(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump at the bridge and lost gcc")
    _burn(tmp_path, corpus, "burn_pump_1", "followed a pump call in the market, total loss")
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0", "burn_pump_1"])
    # the cited burns JUSTIFIED the belief; they are not independent confirmations
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", write=True)
    assert out["hits"] == 0 and out["misses"] == 0
    assert abs(out["confidence"] - 0.5) < 1e-9            # untested -> the Laplace prior
    assert out["stale"] is False                          # 0.5 is not refuted
    # a NEW, uncited in-scope loss IS a test
    _burn(tmp_path, corpus, "burn_pump_2", "a third pump rugged me near the docks")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", write=True)
    assert out["hits"] == 1 and abs(out["confidence"] - 2 / 3) < 1e-9
    fm = agent._all_units(tmp_path, corpus)["trap_pump"].frontmatter
    assert fm["verification"]["hits"] == 1


def test_out_of_scope_good_opportunity_is_not_a_miss(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    agent.record_episode(tmp_path, corpus, "engaged_real", "engaged a real fund and gained",
                         match=["real", "fund"], kind="episodic", outcome="gain")
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0"])
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["misses"] == 0                             # the gain is out of scope -> ignored


def test_an_in_scope_payoff_is_a_miss_and_can_refute(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    _burn(tmp_path, corpus, "burn_pump_1", "another pump, another loss")
    # an uncited pump that paid off — contradicts predicts=loss -> a miss
    _burn(tmp_path, corpus, "pump_paid", "engaged a pump and gained", outcome="gain", match=["pump"])
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0", "burn_pump_1"])
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", write=True, refute_threshold=0.4)
    assert out["hits"] == 0 and out["misses"] == 1
    assert abs(out["confidence"] - 1 / 3) < 1e-9          # (0+1)/(0+1+2)
    assert out["stale"] is True                           # 0.333 < 0.4 -> refuted -> stale
    assert agent._all_units(tmp_path, corpus)["trap_pump"].frontmatter.get("stale") is True


def test_predicts_inferred_from_derived_from_when_absent(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    _burn(tmp_path, corpus, "burn_pump_1", "another pump, another loss")
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0", "burn_pump_1"], predicts=None)
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["predicts"] == "loss"                      # majority outcome of derived_from episodes
    assert out["hits"] == 0 and out["misses"] == 0        # …which are prior, not tests


def test_neutral_outcomes_are_ignored(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    _burn(tmp_path, corpus, "pump_meh", "looked at a pump, did nothing", outcome="neutral", match=["pump"])
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0"])
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["hits"] == 0 and out["misses"] == 0        # neutral neither confirms nor refutes


def test_scope_comes_from_evidence_not_belief_wording(tmp_path: Path) -> None:
    """A real model may word the belief with no shared keywords (§6); the scope vocabulary is the
    UNION of the belief's terms and its cited evidence's terms, so the test still lands."""
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")             # match: pump, trap
    agent.record_episode(tmp_path, corpus, "deceptive_offers", "deceptive offer schemes cause loss",
                         match=["deceptive", "schemes"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0"], predicts="loss")           # no 'pump' anywhere
    _burn(tmp_path, corpus, "burn_pump_2", "a new pump rugged me", match=["pump"])  # uncited test
    out = memory.verify_belief(tmp_path, corpus, "deceptive_offers")
    assert out["hits"] == 1 and abs(out["confidence"] - 2 / 3) < 1e-9


def test_peer_episodes_do_not_count_unless_trusted(tmp_path: Path) -> None:
    """The verification axis must not bypass the provenance axis: an adversary's relayed
    outcome=gain episode cannot refute my trap-belief; a TRUSTED witness's loss is a free test."""
    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0"])
    # poison: the shill relays "pump paid off!" into my corpus
    agent.record_episode(tmp_path, corpus, "pump_moon", "the pump mooned, easy gains",
                         match=["pump"], kind="episodic", outcome="gain", asserted_by="shill")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump")
    assert out["misses"] == 0 and out["stale"] is False   # untrusted witness ignored by default
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", witnesses=["shill"])
    assert out["misses"] == 1                             # counting it is the host's explicit choice
    # observational learning: a trusted peer's loss confirms my belief without my risk
    agent.record_episode(tmp_path, corpus, "oracle_burned", "oracle engaged a pump and lost",
                         match=["pump"], kind="episodic", outcome="loss", asserted_by="oracle")
    out = memory.verify_belief(tmp_path, corpus, "trap_pump", witnesses=["oracle"])
    assert out["hits"] == 1 and out["misses"] == 0


def test_dream_deep_runs_a_verify_stage(tmp_path: Path) -> None:
    """Minimal Dream wiring: the deep pass scores every active, non-locked/pinned belief after
    reflect — confirmed beliefs accrue confidence + last_tested (the host's `now`), refuted ones
    go stale (re-reflect is DEFERRED to a later pass), owner cornerstones are never touched."""
    from aigg_memory.memory import MemoryUnit

    corpus = "npcs/me/memory"
    # distinct wording — dream's deep pass runs compact first and would merge identical episodes
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump at the bridge and lost gcc")
    _burn(tmp_path, corpus, "burn_pump_1", "followed a pump call in the market, total loss")
    _burn(tmp_path, corpus, "burn_pump_2", "a third pump rugged me near the docks")   # uncited test
    _trap_belief(tmp_path, corpus, cites=["burn_pump_0", "burn_pump_1"])   # tests: burn_2 -> 1 hit
    agent.record_episode(tmp_path, corpus, "pump_is_fine", "pump offers are fine",
                         match=["pump"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0"], predicts="gain")    # tests: burn_1+2 -> 2 misses
    fm = {"name": "locked_pump_ok", "description": "owner says pump ok", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": "locked_pump_ok", "status": "active",
          "predicts": "gain", "locked": True}              # would be refuted — but owner-locked
    p = tmp_path / corpus / "locked_pump_ok" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(MemoryUnit(fm, "owner says pump ok").to_text(), encoding="utf-8")

    out = memory.dream(tmp_path, corpus, [], deep=True, write=True, now="2026-06-10T08:00")

    v = out["verified"]
    assert v["trap_pump"]["hits"] == 1 and abs(v["trap_pump"]["confidence"] - 2 / 3) < 1e-9
    assert v["trap_pump"]["stale"] is False
    assert v["pump_is_fine"]["misses"] == 2 and v["pump_is_fine"]["stale"] is True
    assert "locked_pump_ok" not in v                       # cornerstones are skipped entirely
    units = agent._all_units(tmp_path, corpus)
    assert units["trap_pump"].frontmatter["verification"]["last_tested"] == "2026-06-10T08:00"
    assert units["pump_is_fine"].frontmatter.get("stale") is True
    assert "verification" not in units["locked_pump_ok"].frontmatter
    assert units["locked_pump_ok"].frontmatter.get("stale") is None      # untouched


def test_verify_belief_never_flags_a_locked_belief_stale(tmp_path: Path) -> None:
    from aigg_memory.memory import MemoryUnit

    corpus = "npcs/me/memory"
    _burn(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost")
    fm = {"name": "locked_pump_ok", "description": "owner says pump ok", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": "locked_pump_ok", "status": "active",
          "predicts": "gain", "locked": True}
    p = tmp_path / corpus / "locked_pump_ok" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(MemoryUnit(fm, "owner says pump ok").to_text(), encoding="utf-8")
    out = memory.verify_belief(tmp_path, corpus, "locked_pump_ok", write=True, refute_threshold=0.4)
    assert out["misses"] == 1 and out["stale"] is True     # the verdict is reported…
    fm2 = agent._all_units(tmp_path, corpus)["locked_pump_ok"].frontmatter
    assert fm2.get("stale") is None and "verification" not in fm2   # …but the unit is not written


# --- V1: deployment verification for skills (kind=procedural), aigg_skill_design.md -------

def _skill(root: Path, corpus: str, slug: str = "git_bisect_helper", **fm_extra) -> None:
    from aigg_memory.memory import MemoryUnit
    fm = {"name": slug, "description": "drive git bisect to find a regression",
          "kind": "procedural", "match": {"user_intent": ["git", "bisect"]},
          "id": slug, "status": "candidate", "asserted_by": "openclaw:alice", **fm_extra}
    p = root / corpus / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(MemoryUnit(fm, "how to bisect").to_text(), encoding="utf-8")


def _invocation(root: Path, corpus: str, slug: str, skill: str, outcome: str, **kw) -> None:
    agent.record_episode(root, corpus, slug, f"invoked {skill}: {outcome}",
                         match=["invocation"], kind="episodic", outcome=outcome,
                         source_events=[skill], **kw)


def test_skill_invocations_accrue_confidence(tmp_path: Path) -> None:
    """V1: an invocation episode references the skill DIRECTLY (source_events) — no match-term
    fuzz; predicts=success is implicit; the tally is the skill's track record."""
    corpus = "npcs/me/memory"
    _skill(tmp_path, corpus)
    _invocation(tmp_path, corpus, "inv_0", "git_bisect_helper", "success")
    _invocation(tmp_path, corpus, "inv_1", "git_bisect_helper", "success")
    agent.record_episode(tmp_path, corpus, "unrelated", "ate lunch",  # no reference -> ignored
                         match=["git"], kind="episodic", outcome="success")
    out = memory.verify_skill(tmp_path, corpus, "git_bisect_helper", write=True)
    assert out["hits"] == 2 and out["misses"] == 0
    assert abs(out["confidence"] - 0.75) < 1e-9 and out["stale"] is False
    fm = agent._all_units(tmp_path, corpus)["git_bisect_helper"].frontmatter
    assert fm["verification"]["hits"] == 2


def test_skill_failures_refute(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _skill(tmp_path, corpus)
    _invocation(tmp_path, corpus, "inv_0", "git_bisect_helper", "success")
    _invocation(tmp_path, corpus, "inv_1", "git_bisect_helper", "failure")
    _invocation(tmp_path, corpus, "inv_2", "git_bisect_helper", "failure")
    out = memory.verify_skill(tmp_path, corpus, "git_bisect_helper", write=True)
    assert out["hits"] == 1 and out["misses"] == 2
    assert abs(out["confidence"] - 0.4) < 1e-9            # (1+1)/(3+2)
    assert out["stale"] is True                           # refuted -> re-review
    assert agent._all_units(tmp_path, corpus)["git_bisect_helper"].frontmatter.get("stale") is True


def test_skill_witness_gate_blocks_review_stuffing(tmp_path: Path) -> None:
    """Review-stuffing a registry skill is the same attack as pump-poisoning: a peer's glowing
    invocation reports don't count unless the host trusts the witness."""
    corpus = "npcs/me/memory"
    _skill(tmp_path, corpus)
    for i in range(3):   # the author astroturfs successes
        _invocation(tmp_path, corpus, f"stuffed_{i}", "git_bisect_helper", "success",
                    asserted_by="openclaw:alice")
    out = memory.verify_skill(tmp_path, corpus, "git_bisect_helper")
    assert out["hits"] == 0                                # untrusted witness -> not a test
    out = memory.verify_skill(tmp_path, corpus, "git_bisect_helper", witnesses=["openclaw:alice"])
    assert out["hits"] == 3                                # counting them is the host's choice


def test_locked_curated_skill_scored_but_never_written(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    _skill(tmp_path, corpus, locked=True, status="active")  # a curated cornerstone
    _invocation(tmp_path, corpus, "inv_0", "git_bisect_helper", "failure")
    _invocation(tmp_path, corpus, "inv_1", "git_bisect_helper", "failure")
    out = memory.verify_skill(tmp_path, corpus, "git_bisect_helper", write=True)
    assert out["misses"] == 2 and out["stale"] is True     # verdict reported…
    fm = agent._all_units(tmp_path, corpus)["git_bisect_helper"].frontmatter
    assert "verification" not in fm and fm.get("stale") is None   # …unit untouched


def test_verify_endpoint_dispatches_by_kind(tmp_path: Path) -> None:
    from aigg_memory.server import dispatch
    corpus = "npcs/me/memory"
    _skill(tmp_path, corpus)
    _invocation(tmp_path, corpus, "inv_0", "git_bisect_helper", "success")
    status, env = dispatch("POST", "/memory/verify",
                           {"corpus": corpus, "slug": "git_bisect_helper", "write": True}, tmp_path)
    assert status == 200 and env["ok"]
    v = env["data"]["verified"]["git_bisect_helper"]
    assert v["hits"] == 1 and abs(v["confidence"] - 2 / 3) < 1e-9
