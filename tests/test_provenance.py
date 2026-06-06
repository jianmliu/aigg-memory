"""asserted_by = who asserted a fact (an EOA / principal id — just a string; the host
does any signature verification, the kernel stays crypto-free). It is provenance you
can carry to the unit, and an authority gate: a corpus can accept facts only from an
allowed principal (e.g. the owner profile only from the owner's EOA), so authority is
enforced by the asserter, not only by which root the write was routed to."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory.extract import HeuristicExtractor, ingest_transcript
from aigg_memory.store import EvidenceStore


def _obs(root: Path, slug, asserted_by=None):
    store = EvidenceStore(root / "ev.jsonl", domain=mem.memory_domain())
    s = {"slug": slug, "name": slug, "kind": "semantic",
         "description": f"fact {slug}", "match": [slug], "body": f"fact {slug}"}
    if asserted_by is not None:
        s["asserted_by"] = asserted_by
    store.record("observation", s)
    return store.load()


def test_asserted_by_carried_to_unit(tmp_path: Path) -> None:
    records = _obs(tmp_path, "fact1", asserted_by="0xOWNER")
    mem.consolidate_corpus(tmp_path, records, write=True, min_promote_count=1)
    unit = mem.MemoryUnit.from_text((tmp_path / "memory" / "fact1" / "SKILL.md").read_text())
    assert unit.frontmatter["asserted_by"] == "0xOWNER"


def test_authority_gate_accepts_only_allowed_principal(tmp_path: Path) -> None:
    # one fact asserted by the owner, one by a stranger, in the same evidence store
    store = EvidenceStore(tmp_path / "ev.jsonl", domain=mem.memory_domain())
    store.record("observation", {"slug": "owner_fact", "name": "owner_fact", "kind": "semantic",
                                 "description": "owner says X", "match": ["x"], "body": "x", "asserted_by": "0xOWNER"})
    store.record("observation", {"slug": "stranger_fact", "name": "stranger_fact", "kind": "semantic",
                                 "description": "stranger says Y", "match": ["y"], "body": "y", "asserted_by": "0xBOB"})
    mem.consolidate_corpus(tmp_path, store.load(), write=True, min_promote_count=1,
                           allowed_principals={"0xOWNER"})
    assert (tmp_path / "memory" / "owner_fact" / "SKILL.md").exists()         # owner accepted
    assert not (tmp_path / "memory" / "stranger_fact" / "SKILL.md").exists()  # stranger dropped


def test_gate_drops_unsigned_when_allowlist_set(tmp_path: Path) -> None:
    records = _obs(tmp_path, "anon_fact", asserted_by=None)                   # no asserter
    mem.consolidate_corpus(tmp_path, records, write=True, min_promote_count=1,
                           allowed_principals={"0xOWNER"})
    assert not (tmp_path / "memory" / "anon_fact" / "SKILL.md").exists()      # can't verify -> dropped


def test_ingest_stamps_asserted_by(tmp_path: Path) -> None:
    transcript = "user: remember that I prefer dark mode\n"
    records = ingest_transcript(transcript, HeuristicExtractor(), tmp_path / "ev.jsonl", asserted_by="0xBOB")
    assert records and all(r["summary"]["asserted_by"] == "0xBOB" for r in records)
