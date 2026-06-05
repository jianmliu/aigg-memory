"""Safe-by-default hardening for `serve` so it can face a trusted network without
the obvious footguns: corpus path-traversal is rejected, the token compare is
constant-time, and (in the http shell) the bind defaults to localhost.
"""
import pytest

from aigg_memory.memory import validate_corpus
from aigg_memory.server import _authorized, dispatch


# --- corpus path traversal (the real hole: corpus came raw from the body) ---

def test_validate_corpus_allows_plain_and_nested() -> None:
    assert validate_corpus("memory") == "memory"
    assert validate_corpus("npcs/alice/memory") == "npcs/alice/memory"   # nested IS supported


@pytest.mark.parametrize("bad", ["../etc", "a/../../b", "/etc/passwd", "", "  ",
                                 ".", "a/./b", "a/..", "..\\b", "C:/x"])
def test_validate_corpus_rejects_traversal(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_corpus(bad)


def test_dispatch_rejects_traversal_corpus(tmp_path) -> None:
    status, env = dispatch("POST", "/memory/units", {"corpus": "../../etc"}, tmp_path)
    assert status == 400 and env["ok"] is False


def test_dispatch_allows_valid_corpus(tmp_path) -> None:
    status, env = dispatch("POST", "/memory/units", {"corpus": "memory"}, tmp_path)
    assert status == 200 and env["ok"] is True


# --- constant-time token check (no token configured == open, by design) -----

def test_authorized_open_when_no_token() -> None:
    assert _authorized("", None) is True
    assert _authorized("anything", "") is True


def test_authorized_matches_bearer() -> None:
    assert _authorized("Bearer s3cret", "s3cret") is True
    assert _authorized("Bearer wrong", "s3cret") is False
    assert _authorized("", "s3cret") is False
