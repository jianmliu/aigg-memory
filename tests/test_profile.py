"""The self-profile = the 'pinned' tier over existing units: the small, stable set
(identity + durable preferences) that is ALWAYS injected at session start, vs the
rest of memory which is recalled on demand. Pinned is an orthogonal salience flag,
not a new store and not a `kind`."""
import json
from pathlib import Path

from aigg_memory import cli
from aigg_memory import memory as mem
from aigg_memory.index import CorpusIndex


def _unit(root: Path, slug, desc="d", pinned=None):
    fm = {"name": slug, "description": desc, "kind": "semantic",
          "match": {"user_intent": [slug]}, "id": slug, "status": "active"}
    if pinned is not None:
        fm["pinned"] = pinned
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(fm, desc).to_text(), encoding="utf-8")


# --- (1) pinned frontmatter via edit ---------------------------------------

def test_edit_pins_and_unpins(tmp_path: Path) -> None:
    _unit(tmp_path, "name_is_alex", "User's name is Alex")
    mem.edit_unit(tmp_path, "memory", "name_is_alex", pinned=True)
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "name_is_alex" / "SKILL.md").read_text())
    assert u.frontmatter["pinned"] is True
    mem.edit_unit(tmp_path, "memory", "name_is_alex", pinned=False)
    u = mem.MemoryUnit.from_text((tmp_path / "memory" / "name_is_alex" / "SKILL.md").read_text())
    assert u.frontmatter["pinned"] is False


def test_merge_keeps_pin_if_either_side_pinned(tmp_path: Path) -> None:
    out = mem._merge_frontmatter({"name": "x", "pinned": True}, {"name": "x"})
    assert out["pinned"] is True


# --- (2/3) indexed profile query -------------------------------------------

def test_index_profile_returns_only_pinned_active(tmp_path: Path) -> None:
    _unit(tmp_path, "name_is_alex", "User's name is Alex", pinned=True)
    _unit(tmp_path, "likes_dark", "Prefers dark mode", pinned=True)
    _unit(tmp_path, "talked_weather", "Discussed weather once")          # not pinned
    rows = CorpusIndex(tmp_path, "memory").profile()
    assert {r["slug"] for r in rows} == {"name_is_alex", "likes_dark"}


def test_archived_pinned_excluded_from_profile(tmp_path: Path) -> None:
    _unit(tmp_path, "old_job", "Worked at Acme", pinned=True)
    mem.edit_unit(tmp_path, "memory", "old_job", status="archived")
    assert CorpusIndex(tmp_path, "memory").profile() == []


# --- (3) CLI surface --------------------------------------------------------

def test_cli_pin_then_profile(tmp_path: Path, capsys) -> None:
    _unit(tmp_path, "name_is_alex", "User's name is Alex")
    assert cli.main(["edit", "name_is_alex", "--root", str(tmp_path), "--pin"]) == 0
    capsys.readouterr()
    assert cli.main(["profile", "--root", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [u["slug"] for u in out["profile"]] == ["name_is_alex"]
