"""bundle = the corpus packaged for a DSN — and memory is GIT-format, so the bundle
must carry the **git history** (commit/log/diff/restore, the audit trail), not just a
flattened snapshot. It's a `git bundle`: the whole versioned repo round-trips through
one object on a decentralized store (e.g. Autonomys Auto Drive, which encrypts the
bytes client-side on upload). Kernel stays crypto-free."""
from pathlib import Path

from aigg_memory import memory as mem
from aigg_memory import versioning as vcs


def _unit(root: Path, slug, desc):
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit({"name": slug, "description": desc, "kind": "semantic",
                                 "match": {"user_intent": [slug]}, "id": slug, "status": "active"}, desc).to_text())


def test_bundle_carries_history_not_just_a_snapshot(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    _unit(src, "a", "alpha"); vcs.commit(src / "memory", "remember a")
    _unit(src, "b", "beta");  vcs.commit(src / "memory", "remember b")

    data = mem.export_bundle(src, "memory")
    assert isinstance(data, (bytes, bytearray)) and data            # a binary git bundle

    mem.import_bundle(dst, "memory", data)
    # working tree restored ...
    assert mem.load_corpus(dst, "memory") == mem.load_corpus(src, "memory")
    # ... AND the full git history came across (this is the point — not a snapshot)
    log = vcs.log(dst / "memory")
    assert any("remember a" in l for l in log) and any("remember b" in l for l in log)


def test_imported_history_is_usable(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    _unit(src, "a", "alpha"); vcs.commit(src / "memory", "c1")
    _unit(src, "b", "beta");  vcs.commit(src / "memory", "c2")
    mem.import_bundle(dst, "memory", mem.export_bundle(src, "memory"))

    # diff between two restored commits works -> the history is real, not a single snapshot
    d = vcs.diff(dst / "memory", "HEAD~1", "HEAD")
    assert any("b" in str(v) for v in d.values())
