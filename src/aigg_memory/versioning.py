"""Memory as a versioned store — git semantics over the corpus.

The corpus is plain `<slug>/SKILL.md` text, so it is **directly versionable**.
Consolidation / compaction / edits become **commits**; nothing is destroyed — a
"forgotten" unit leaves HEAD (the active set) but stays in history and can be
restored. `diff` / `log` audit and `restore` undoes; the derived `.aimm-index.db`
+ `MemoryMakefile` are gitignored. Push / merge (shared / multi-agent memory) are
plain git on top.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

_GITIGNORE = ".aimm-index.db\nMemoryMakefile\n"
_UNIT_SUFFIX = "/SKILL.md"


def _git(root: Union[str, Path], *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)


def _is_repo(root: Path) -> bool:
    return (root / ".git").exists()


def ensure_repo(root: Union[str, Path]) -> None:
    """git init the corpus (idempotent) + gitignore the derived artifacts."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if not _is_repo(root):
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "memory@aigg.local", check=False)
        _git(root, "config", "user.name", "aigg-memory", check=False)
    gitignore = root / ".gitignore"
    if not gitignore.exists() or _GITIGNORE not in gitignore.read_text(encoding="utf-8"):
        gitignore.write_text(_GITIGNORE, encoding="utf-8")


def commit(root: Union[str, Path], message: str) -> Optional[str]:
    """Commit the current corpus state. Returns the short hash, or None if the
    working tree is unchanged (nothing to record)."""
    root = Path(root)
    ensure_repo(root)
    _git(root, "add", "-A")
    if not _git(root, "status", "--porcelain").stdout.strip():
        return None
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def log(root: Union[str, Path], n: int = 20) -> List[str]:
    """The memory history: recent commits, newest first ('<hash> <message>')."""
    root = Path(root)
    if not _is_repo(root):
        return []
    out = _git(root, "log", f"-{n}", "--pretty=%h %s", check=False).stdout
    return [line for line in out.splitlines() if line]


def diff(root: Union[str, Path], base: str = "HEAD~1", head: str = "HEAD") -> Dict[str, List[str]]:
    """Unit-level diff between two memory states: {added, modified, removed} slugs."""
    root = Path(root)
    empty = {"added": [], "modified": [], "removed": []}
    if not _is_repo(root):
        return empty
    result = _git(root, "diff", "--name-status", "--no-renames", base, head, check=False)
    if result.returncode != 0:
        return empty
    added, modified, removed = [], [], []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[-1].endswith(_UNIT_SUFFIX):
            continue
        slug = Path(parts[-1]).parent.name
        code = parts[0][0]
        (added if code == "A" else removed if code == "D" else modified).append(slug)
    return {"added": sorted(added), "modified": sorted(modified), "removed": sorted(removed)}


def restore(root: Union[str, Path], ref: str) -> None:
    """Non-destructively bring the corpus working tree back to a past state — so a
    'forgotten' unit can be recovered. The caller can then `commit` the restore.
    Raises ValueError for an unknown ref (e.g. HEAD~1 with only one commit)."""
    root = Path(root)
    ensure_repo(root)
    result = _git(root, "checkout", ref, "--", ".", check=False)
    if result.returncode != 0:
        raise ValueError(f"cannot restore {ref!r}: {result.stderr.strip() or 'unknown ref'}")
