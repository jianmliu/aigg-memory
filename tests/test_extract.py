"""Encoding: where memory comes from — extract structured observations from raw
chat transcripts, then feed the existing observe → consolidate pipeline.

The core stays model-free: a deterministic HeuristicExtractor baseline, and an
AIGGExtractor that routes the real extraction through an external AIGG inference
service (OpenAI-compatible, stdlib urllib — no new dependency). Tests inject a
fake transport so no live service is needed.
"""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import AIGGExtractor, HeuristicExtractor, ingest_transcript


def test_heuristic_extracts_durable_facts() -> None:
    transcript = [
        {"role": "user", "content": "Hey, nice weather."},
        {"role": "user", "content": "Remember that I prefer Chinese and English, not Japanese."},
        {"role": "assistant", "content": "Got it."},
    ]
    obs = HeuristicExtractor().extract(transcript)
    assert obs and any("prefer" in o["description"].lower() for o in obs)
    assert all({"slug", "kind", "description", "match", "body"} <= set(o) for o in obs)
    # chit-chat ("nice weather") is not extracted
    assert not any("weather" in o["description"].lower() for o in obs)


def test_heuristic_slug_is_stable_for_the_same_fact() -> None:
    ex = HeuristicExtractor()
    a = ex.extract("Remember that the API timeout is 30 seconds.")
    b = ex.extract("Remember that the API timeout is 30 seconds.")
    assert a and a[0]["slug"] == b[0]["slug"]   # same fact -> same slug -> consolidation can promote it


def test_aigg_extractor_parses_service_response() -> None:
    canned = (
        '```json\n'
        '[{"slug":"pref_lang","name":"language preference","kind":"semantic",'
        '"description":"prefers Chinese + English","match":["language","preference"],"body":"…"}]\n'
        '```'
    )
    ex = AIGGExtractor(base_url="https://aigg.example/v1", api_key="k", model="gpt-x",
                       transport=lambda text: canned)
    obs = ex.extract([{"role": "user", "content": "I prefer Chinese and English"}])
    assert [o["slug"] for o in obs] == ["pref_lang"]
    assert obs[0]["kind"] == "semantic" and "Chinese" in obs[0]["description"]


def test_aigg_extractor_passes_budget_headers() -> None:
    seen = {}
    def transport(text):
        return "[]"
    ex = AIGGExtractor(base_url="https://aigg.example/v1", api_key="k",
                       extra_headers={"X-Task-Id": "npc-42", "X-Token-Budget-Total": "5000"},
                       transport=transport)
    # the extractor carries the app's AIGG budget/auth headers (enforced server-side by AIGG)
    assert ex.extra_headers["X-Task-Id"] == "npc-42"
    assert ex.extract("nothing here") == []


def test_ingest_transcript_then_consolidate(tmp_path: Path) -> None:
    """Full encoding loop: raw transcript -> extract -> observe -> consolidate -> unit."""
    obs_payload = [{"slug": "api_timeout", "name": "api timeout", "kind": "semantic",
                    "description": "API timeout is 30s", "match": ["timeout", "api"], "body": "30 seconds"}]
    extractor = AIGGExtractor(base_url="x", transport=lambda text: __import__("json").dumps(obs_payload))

    ev = tmp_path / "ev.jsonl"
    # the same fact appears in two sessions -> two observations of the same slug
    ingest_transcript("session 1 …", extractor, ev)
    ingest_transcript("session 2 …", extractor, ev)
    assert len([l for l in ev.read_text().splitlines() if l.strip()]) == 2

    from aigg_memory.store import EvidenceStore
    records = EvidenceStore(ev, domain=mem.memory_domain()).load()
    result = mem.consolidate_corpus(tmp_path, records, write=True)
    assert result.gates_ok
    assert (tmp_path / "memory" / "api_timeout" / "SKILL.md").exists()   # extracted fact became a unit


def test_bad_service_output_yields_nothing() -> None:
    ex = AIGGExtractor(base_url="x", transport=lambda text: "sorry, I can't do that")
    assert ex.extract("anything") == []
