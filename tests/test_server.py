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
