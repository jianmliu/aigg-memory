"""bundle = a single deterministic plaintext archive of a corpus, so the whole
multi-file memory round-trips through ONE object on a DSN (e.g. Autonomys Auto Drive,
which encrypts client-side on upload). Kernel stays crypto-free; the host pipes the
bundle through Auto Drive's encrypted upload/download. Deterministic so an unchanged
corpus yields identical bytes -> the same CID -> no re-upload."""
import json
from pathlib import Path

from aigg_memory import memory as mem


def _unit(root: Path, slug, desc):
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit({"name": slug, "description": desc, "kind": "semantic",
                                 "match": {"user_intent": [slug]}, "id": slug, "status": "active"}, desc).to_text())


def test_bundle_roundtrips_the_corpus(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    _unit(src, "a", "alpha")
    _unit(src, "b", "beta")

    payload = mem.export_bundle(src, "memory")
    mem.import_bundle(dst, "memory", payload)

    assert mem.load_corpus(dst, "memory") == mem.load_corpus(src, "memory")


def test_bundle_is_deterministic(tmp_path: Path) -> None:
    _unit(tmp_path, "b", "beta")
    _unit(tmp_path, "a", "alpha")               # inserted out of order
    assert mem.export_bundle(tmp_path, "memory") == mem.export_bundle(tmp_path, "memory")
    # keys are sorted so byte-identity doesn't depend on filesystem order
    keys = list(json.loads(mem.export_bundle(tmp_path, "memory"))["units"].keys())
    assert keys == sorted(keys)
