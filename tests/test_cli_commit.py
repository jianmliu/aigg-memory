"""CLI `commit` — a standalone git commit of the corpus so the plugin's session-end
hook can version what a session learned (previously only merge/compact --commit)."""
import json
from pathlib import Path

from aigg_memory import cli
from aigg_memory import memory as mem


def _unit(root: Path, slug):
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit({"name": slug, "description": "d", "kind": "semantic",
                                 "match": {"user_intent": [slug]}, "id": slug, "status": "active"}, "b").to_text())


def test_commit_creates_commit(tmp_path: Path, capsys) -> None:
    _unit(tmp_path, "a")
    rc = cli.main(["commit", "--root", str(tmp_path), "--message", "session: learned a"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["commit"] and (tmp_path / "memory" / ".git").exists()


def test_commit_noop_when_clean(tmp_path: Path, capsys) -> None:
    _unit(tmp_path, "a")
    cli.main(["commit", "--root", str(tmp_path), "--message", "first"])
    capsys.readouterr()
    rc = cli.main(["commit", "--root", str(tmp_path), "--message", "again"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["commit"] is None   # nothing to record
