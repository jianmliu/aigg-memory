"""CLI `recall` — daemonless recall so the Claude Code plugin's hooks can shell out
to it directly (no long-running serve). Mirrors POST /memory/select."""
import json
from pathlib import Path

from aigg_memory import cli
from aigg_memory import memory as mem


def _unit(root: Path, slug, desc, match):
    fm = {"name": slug, "description": desc, "kind": "semantic",
          "match": {"user_intent": match}, "id": slug, "status": "active"}
    p = root / "memory" / slug / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mem.MemoryUnit(fm, desc).to_text(), encoding="utf-8")


def test_recall_ranks_relevant_unit_first(tmp_path: Path, capsys) -> None:
    _unit(tmp_path, "likes_concise", "user prefers concise answers", ["concise"])
    _unit(tmp_path, "weather", "weather forecast", ["weather"])

    # hybrid is recall-oriented (may surface weak matches) — the relevant unit ranks first
    rc = cli.main(["recall", "please be concise", "--root", str(tmp_path), "--n-best", "3"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["units"][0]["slug"] == "likes_concise"
    assert out["total_in_corpus"] == 2


def test_recall_keyword_empty_on_no_match(tmp_path: Path, capsys) -> None:
    _unit(tmp_path, "weather", "weather forecast", ["weather"])
    # keyword is precise: a request with no declared trigger term recalls nothing
    rc = cli.main(["recall", "nothing relevant here", "--root", str(tmp_path), "--retriever", "keyword"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["units"] == []
