"""Tests for the standalone aigg-memory HTTP API (aigg_memory.server).

dispatch() is pure (no sockets); all file IO goes through tmp_path. The memory
endpoints are the same ones an agent (MUD / inference gateway) drives directly —
no host framework needed.
"""
from pathlib import Path

from aigg_memory.server import dispatch, render_index, static_response


def _observe(root, payload, evidence="ev.jsonl", outcome=None):
    body = {"evidence": evidence, "payload": payload}
    if outcome:
        body["outcome"] = outcome
    return dispatch("POST", "/memory/observe", body, root)


def _npc(slug, name, kind="semantic", desc="", match=None, body=""):
    return {"slug": slug, "name": name, "kind": kind, "description": desc,
            "match": match or [slug], "body": body or desc}


def test_full_cycle_observe_status_consolidate_select(tmp_path: Path) -> None:
    npc = _npc("jiujianxian", "酒剑仙", "semantic", "嗜酒剑道高人", ["swordsmanship", "酒剑"], "醉中悟剑意")
    for _ in range(2):
        status, env = _observe(tmp_path, npc)
        assert status == 200 and env["ok"]

    # readiness signal — the app's trigger
    _, env = dispatch("POST", "/memory/consolidation-status", {"evidence": "ev.jsonl"}, tmp_path)
    assert env["data"]["pending"] == 2 and env["data"]["recommended"] is True

    # Dream consolidation writes the typed unit
    status, env = dispatch("POST", "/memory/consolidate", {"evidence": "ev.jsonl", "write": True}, tmp_path)
    assert status == 200 and env["data"]["gates_ok"]
    assert "memory/jiujianxian/SKILL.md" in env["data"]["written"]
    assert (tmp_path / "memory" / "jiujianxian" / "SKILL.md").exists()

    # recall: kind-filtered + kind-aware bundle
    _, env = dispatch("POST", "/memory/select", {"request": "teach me swordsmanship", "kinds": ["semantic"]}, tmp_path)
    assert [u["name"] for u in env["data"]["units"]] == ["酒剑仙"]
    assert "## Facts" in env["data"]["bundle"]

    # units list
    _, env = dispatch("POST", "/memory/units", {}, tmp_path)
    assert env["data"]["total"] == 1


def test_nested_corpus_per_entity(tmp_path: Path) -> None:
    corpus = "npcs/jiujianxian/memory"
    for _ in range(2):
        _observe(tmp_path, _npc("relation", "好感", "semantic", "affinity", ["游侠"], "好感+16"), evidence="npc.jsonl")
    dispatch("POST", "/memory/consolidate", {"evidence": "npc.jsonl", "corpus": corpus, "write": True}, tmp_path)
    assert (tmp_path / corpus / "relation" / "SKILL.md").exists()
    _, env = dispatch("POST", "/memory/units", {"corpus": corpus}, tmp_path)
    assert env["data"]["total"] == 1


def test_errors_and_unknown_route(tmp_path: Path) -> None:
    status, env = dispatch("POST", "/memory/observe", {"payload": {}}, tmp_path)
    assert status == 400 and not env["ok"]
    status, env = dispatch("POST", "/memory/consolidate", {}, tmp_path)
    assert status == 400 and not env["ok"]
    status, env = dispatch("DELETE", "/nope", {}, tmp_path)
    assert status == 404 and env["diagnostics"][0]["code"] == "AM_MEM_404"


def test_reflect_route_requires_a_model(tmp_path: Path) -> None:
    # the synthesis route is registered and guards on a configured model (no aigg_url -> 400)
    status, env = dispatch("POST", "/memory/reflect", {"corpus": "memory"}, tmp_path)
    assert status == 400 and not env["ok"]
    assert env["diagnostics"][0]["code"] == "AM_MEM_400"


def test_plan_route_requires_model_and_clock(tmp_path: Path) -> None:
    # the forward-synthesis route guards on a model (no aigg_url -> 400)...
    status, env = dispatch("POST", "/memory/plan", {"corpus": "memory"}, tmp_path)
    assert status == 400 and not env["ok"]
    # ...and on the caller's clock (`now`), since the kernel ships none
    status, env = dispatch("POST", "/memory/plan", {"corpus": "memory", "aigg_url": "http://x/v1"}, tmp_path)
    assert status == 400 and "now" in env["diagnostics"][0]["message"]


def test_consolidate_min_count_promotes_a_single_observation(tmp_path: Path) -> None:
    payload = {"slug": "likes_dark_mode", "name": "dark mode", "kind": "semantic",
               "description": "user prefers dark mode", "match": ["dark mode"]}
    dispatch("POST", "/memory/observe", {"evidence": "ev.jsonl", "payload": payload}, tmp_path)
    # default min_count=2: a one-off observation is NOT promoted (chatter guard)
    _, env = dispatch("POST", "/memory/consolidate", {"evidence": "ev.jsonl", "write": True}, tmp_path)
    assert env["data"]["written"] == []
    # min_count=1: it lands immediately — the MUD/explicit path for a single deliberate observation
    _, env = dispatch("POST", "/memory/consolidate",
                      {"evidence": "ev.jsonl", "write": True, "min_count": 1}, tmp_path)
    assert len(env["data"]["written"]) == 1


def test_remember_writes_a_fact_in_one_call(tmp_path: Path) -> None:
    # the host's deterministic "remember this NPC fact now" — one call, no LLM, no repetition gate
    _, env = dispatch("POST", "/memory/remember", {"evidence": "npc.jsonl", "corpus": "npcs/sage/memory",
        "payload": {"name": "Player likes swords", "kind": "semantic",
                    "description": "the player keeps asking about swordsmanship", "match": ["swords"]}}, tmp_path)
    assert env["ok"] and len(env["data"]["written"]) == 1
    assert env["data"]["slug"] == "player_likes_swords"   # derived from name
    # the unit is really on disk in the NPC's corpus
    assert (tmp_path / "npcs" / "sage" / "memory" / "player_likes_swords" / "SKILL.md").exists()


def test_llm_endpoints_accept_claude_cli_backend_without_url(tmp_path: Path) -> None:
    # the per-op routing gap (paper §7/#5): every LLM endpoint accepts backend=claude-cli in
    # place of aigg_url. Empty corpus -> no candidate pairs -> the model is never invoked, so
    # this exercises only the validation + construction path.
    paths = ("/memory/reconcile", "/memory/detect-contradictions", "/memory/infer-temporal",
             "/memory/infer-deps", "/memory/curate")
    for path in paths:
        status, env = dispatch("POST", path, {"backend": "claude-cli", "corpus": "memory"}, tmp_path)
        assert status != 400, f"{path} rejected backend=claude-cli: {env}"
    for path in paths:  # and with no model configured at all, the 400 guard still holds
        status, _ = dispatch("POST", path, {"corpus": "memory"}, tmp_path)
        assert status == 400, f"{path} should still require a model"


def test_ingest_accepts_claude_cli_backend(tmp_path: Path, monkeypatch) -> None:
    import aigg_memory.extract as ex
    seen = {}

    class _Stub:
        name = "stub"

        def __init__(self, base_url, **kw):
            seen.update(kw, base_url=base_url)

        def extract(self, transcript):
            return []

    monkeypatch.setattr(ex, "AIGGExtractor", _Stub)
    status, env = dispatch("POST", "/memory/ingest", {"transcript": "hi", "evidence": "ev.jsonl",
                                                      "extractor": "aigg", "backend": "claude-cli"}, tmp_path)
    assert status == 200 and env["ok"], env
    assert seen.get("backend") == "claude-cli"


def test_verify_endpoint_sweeps_beliefs(tmp_path: Path) -> None:
    """/memory/verify — the MUD's deterministic verification sweep (no LLM): scores every active,
    non-locked/pinned belief against outcome-tagged episodes; refuted -> stale; locked skipped."""
    from aigg_memory import agent
    from aigg_memory.memory import MemoryUnit

    corpus = "npcs/me/memory"
    agent.record_episode(tmp_path, corpus, "burn_pump_0", "engaged a pump at the bridge, lost",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(tmp_path, corpus, "burn_pump_1", "pump call in the market went to zero",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(tmp_path, corpus, "burn_pump_2", "a third pump rugged me near the docks",
                         match=["pump"], kind="episodic", outcome="loss")    # uncited -> a test
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump offers are traps",
                         match=["pump", "trap"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0", "burn_pump_1"], predicts="loss")
    agent.record_episode(tmp_path, corpus, "pump_is_fine", "pump offers are fine",
                         match=["pump"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0"], predicts="gain")
    fm = {"name": "locked_pump_ok", "description": "owner says ok", "kind": "belief",
          "match": {"user_intent": ["pump"]}, "id": "locked_pump_ok", "status": "active",
          "predicts": "gain", "locked": True}
    p = tmp_path / corpus / "locked_pump_ok" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(MemoryUnit(fm, "owner says ok").to_text(), encoding="utf-8")

    status, env = dispatch("POST", "/memory/verify",
                           {"corpus": corpus, "write": True, "now": "2026-06-10T09:00"}, tmp_path)
    assert status == 200 and env["ok"]
    v = env["data"]["verified"]
    # trap_pump cites burn_0/1 (prior); burn_2 is its one test -> 1 hit -> 2/3
    assert abs(v["trap_pump"]["confidence"] - 2 / 3) < 1e-9 and v["trap_pump"]["stale"] is False
    # pump_is_fine cites burn_0; burn_1+burn_2 are tests -> 2 misses -> 0.25 -> refuted
    assert v["pump_is_fine"]["misses"] == 2 and v["pump_is_fine"]["stale"] is True
    assert "locked_pump_ok" not in v
    # written back, with the host's clock
    fm2 = agent._all_units(tmp_path, corpus)["trap_pump"].frontmatter
    assert fm2["verification"]["last_tested"] == "2026-06-10T09:00"
    # slug filter: verify just one belief
    status, env = dispatch("POST", "/memory/verify", {"corpus": corpus, "slug": "trap_pump"}, tmp_path)
    assert status == 200 and list(env["data"]["verified"]) == ["trap_pump"]


def test_discernment_endpoint_reads_belief_evidence(tmp_path: Path) -> None:
    """The HTTP face of agent.discernment — so a non-Python host (the MUD) can decide BY memory:
    relevant (provenance/text) AND confident (verification ≥ θ)."""
    from aigg_memory import agent, memory
    corpus = "npcs/trader/memory"
    # a self-learned trap-belief, derived from a burn, then a fresh uncited burn verifies it
    agent.record_episode(tmp_path, corpus, "burn_pump_0", "engaged a pump and lost",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(tmp_path, corpus, "burn_pump_1", "a second pump rugged me",
                         match=["pump", "trap"], kind="episodic", outcome="loss")
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump offers are traps",
                         match=["pump", "trap"], kind="belief", asserted_by="self",
                         derived_from=["burn_pump_0"], predicts="loss")  # burn_1 is the test
    memory.verify_belief(tmp_path, corpus, "trap_pump", write=True)      # 1 hit -> 2/3

    status, env = dispatch("POST", "/memory/discernment",
                           {"corpus": corpus, "topic": "pump", "mode": "provenance"}, tmp_path)
    assert status == 200 and env["ok"]
    d = env["data"]
    assert d["faculty"] == 1.0 and d["q"] == 1.0 and abs(d["confidence"] - 2 / 3) < 1e-3
    # a high-stakes θ above the belief's confidence zeroes the discernment
    _, env = dispatch("POST", "/memory/discernment",
                      {"corpus": corpus, "topic": "pump", "mode": "provenance", "min_confidence": 0.8}, tmp_path)
    assert env["data"]["q"] == 0.0 and env["data"]["faculty"] == 0.0
    # topic is required
    status, _ = dispatch("POST", "/memory/discernment", {"corpus": corpus}, tmp_path)
    assert status == 400


def test_remember_preserves_verification_fields(tmp_path: Path) -> None:
    """The HTTP path must be able to land an outcome-tagged episode — it is the input the whole
    verification axis tallies. Previously `outcome`/`predicts`/payload `source_events` were
    silently dropped at promotion, so a non-Python host could never feed `verify`."""
    _, env = dispatch("POST", "/memory/remember", {"evidence": "npc.jsonl", "corpus": "npcs/sage/memory",
        "payload": {"slug": "burn_pump_0", "kind": "episodic", "description": "engaged a pump and lost",
                    "match": ["pump", "trap"], "outcome": "loss", "source_events": ["skill_x"]}}, tmp_path)
    assert env["ok"] and env["data"]["written"]
    from aigg_memory import agent
    fm = agent._all_units(tmp_path, "npcs/sage/memory")["burn_pump_0"].frontmatter
    assert fm["outcome"] == "loss"
    assert "skill_x" in fm["source_events"]          # payload provenance survives (plus event ids)
    # and predicts on a belief payload
    dispatch("POST", "/memory/remember", {"evidence": "npc.jsonl", "corpus": "npcs/sage/memory",
        "payload": {"slug": "trap_pump", "kind": "belief", "description": "pump offers are traps",
                    "match": ["pump"], "predicts": "loss", "derived_from": ["burn_pump_0"]}}, tmp_path)
    fm = agent._all_units(tmp_path, "npcs/sage/memory")["trap_pump"].frontmatter
    assert fm["predicts"] == "loss"


def test_healthz_and_ui(tmp_path: Path) -> None:
    status, env = dispatch("GET", "/healthz", {}, tmp_path)
    assert status == 200 and env["data"]["version"] == 1

    html = render_index()
    assert "<!doctype html" in html.lower() and "aigg-memory" in html
    for hook in ("/memory/select", "/memory/units", "/healthz"):
        assert hook in html
    content_type, body = static_response("/")
    assert content_type.startswith("text/html") and b"<!doctype html" in body.lower()
    assert static_response("/memory/select") is None
