"""POST /memory/dream — so an HTTP-driven app (e.g. a MUD firing an NPC's sleep) can
run the offline maintenance pass per entity in one call, scoped to that entity's corpus.
The light path (consolidate, no model) is exercised here; the deep path needs a model."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.server import dispatch
from aigg_memory.store import EvidenceStore


def test_dream_endpoint_consolidates_per_corpus(tmp_path: Path) -> None:
    # an NPC's evidence, scoped to its own corpus npcs/<id>/memory
    store = EvidenceStore(tmp_path / "ev.jsonl", domain=mem.memory_domain())
    store.record("observation", {"slug": "met_player_alex", "name": "met_player_alex",
                                 "kind": "episodic", "description": "The hero Alex visited the shop",
                                 "match": ["alex", "hero"], "body": "Alex came by."})

    status, env = dispatch("POST", "/memory/dream",
                           {"evidence": "ev.jsonl", "corpus": "npcs/sage/memory",
                            "write": True, "min_count": 1}, tmp_path)
    assert status == 200 and env["ok"] is True
    assert env["data"]["consolidated"]["written"]          # a unit was promoted
    assert "reconciled" not in env["data"]                 # no model -> light only
    assert (tmp_path / "npcs" / "sage" / "memory" / "met_player_alex" / "SKILL.md").exists()


def test_dream_endpoint_rejects_traversal_corpus(tmp_path: Path) -> None:
    status, env = dispatch("POST", "/memory/dream",
                           {"evidence": "ev.jsonl", "corpus": "../../etc"}, tmp_path)
    assert status == 400 and env["ok"] is False            # corpus guard still applies
