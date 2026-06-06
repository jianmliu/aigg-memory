"""The claude-cli backend: instead of HTTP, shell out to `claude -p` so the memory
loop runs on the user's Claude Code login (subscription, no API key). The transport is
the same injectable seam used elsewhere; here it spawns a (stubbed) `claude` process,
feeds the user text on stdin, and parses the text answer."""
from pathlib import Path

from aigg_memory.extract import AIGGCurator, AIGGExtractor, AIGGReconciler


def _stub_claude(tmp_path: Path, prints: str, monkeypatch) -> None:
    """Point AIGG_MEMORY_CLAUDE_CMD at a tiny python that ignores its args, drains stdin,
    and prints `prints` — standing in for `claude -p`."""
    stub = tmp_path / "claude_stub.py"
    stub.write_text("import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n" % prints)
    monkeypatch.setenv("AIGG_MEMORY_CLAUDE_CMD", f"python3 {stub}")


def test_extractor_claude_cli_backend(tmp_path: Path, monkeypatch) -> None:
    _stub_claude(tmp_path, '[{"slug":"likes_dark","name":"likes_dark","kind":"semantic",'
                           '"description":"prefers dark mode","match":["dark"],"body":"dark"}]', monkeypatch)
    ex = AIGGExtractor(base_url="", backend="claude-cli")
    obs = ex.extract("user: remember I prefer dark mode")
    assert obs and obs[0]["slug"] == "likes_dark"


def test_reconciler_claude_cli_backend(tmp_path: Path, monkeypatch) -> None:
    _stub_claude(tmp_path, '{"relation":"temporal","current":"b","reason":"moved"}', monkeypatch)
    judge = AIGGReconciler(base_url="", backend="claude-cli")
    v = judge.judge({"slug": "a", "description": "in Shanghai"}, {"slug": "b", "description": "in Beijing"})
    assert v == {"relation": "temporal", "current": "b", "reason": "moved"}


def test_curator_claude_cli_backend_failure_raises(tmp_path: Path, monkeypatch) -> None:
    # a non-zero exit (e.g. not logged in) surfaces as an error, not a silent empty result
    stub = tmp_path / "fail.py"
    stub.write_text("import sys\nsys.exit(3)\n")
    monkeypatch.setenv("AIGG_MEMORY_CLAUDE_CMD", f"python3 {stub}")
    cur = AIGGCurator(base_url="", backend="claude-cli")
    try:
        cur.judge([{"slug": "x", "description": "d"}])
        assert False, "expected RuntimeError on non-zero exit"
    except RuntimeError as exc:
        assert "claude -p failed" in str(exc)
