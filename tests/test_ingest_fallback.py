"""Model extraction must be safe to actually rely on: if the AIGG / local model is
unreachable, `ingest --extractor aigg --fallback-heuristic` degrades to the
zero-dependency heuristic instead of losing the session's memory."""
import json
from pathlib import Path

from aigg_memory import cli

# a guaranteed-dead endpoint: connection refused is immediate and deterministic
_DEAD = "http://127.0.0.1:9/v1"


def test_aigg_failure_falls_back_to_heuristic(tmp_path: Path, capsys) -> None:
    transcript = tmp_path / "t.txt"
    transcript.write_text("user: remember that I prefer dark mode\n", encoding="utf-8")
    ev = tmp_path / "ev.jsonl"

    rc = cli.main(["ingest", "--transcript", str(transcript), "--evidence", str(ev),
                   "--extractor", "aigg", "--aigg-url", _DEAD, "--fallback-heuristic"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["extractor"] == "heuristic"      # fell back
    assert out["extracted"] >= 1                # the heuristic still caught the "remember that" cue
    assert ev.exists()


def test_aigg_failure_without_fallback_errors(tmp_path: Path, capsys) -> None:
    transcript = tmp_path / "t.txt"
    transcript.write_text("user: remember that I prefer dark mode\n", encoding="utf-8")
    rc = cli.main(["ingest", "--transcript", str(transcript), "--evidence", str(tmp_path / "ev.jsonl"),
                   "--extractor", "aigg", "--aigg-url", _DEAD])
    assert rc == 1                              # surfaced, not silently swallowed
