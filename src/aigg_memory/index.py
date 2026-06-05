"""A derived corpus index (SQLite, stdlib — no new dependency).

The index is a **cache**, never the source of truth: the `<slug>/SKILL.md` units
are. It maps `slug → routing metadata` + an inverted `term → slug` table so recall
queries a compact index instead of re-parsing every file. Built/updated at
consolidate time (build-time, expensive), read cheaply at recall time (run-time) —
the cost principle. Invalidated incrementally by file mtime; deletable and fully
regenerable. A `vectors` table is reserved for a future semantic retriever.

Lives at `<root>/<corpus>/.aimm-index.db` (not matched by the `*/SKILL.md` glob).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

_INDEX_FILE = ".aimm-index.db"
_UNIT_SUFFIX = "/SKILL.md"


class CorpusIndex:
    def __init__(self, root: Union[str, Path], corpus: str = "memory") -> None:
        self.root = Path(root)
        self.corpus = corpus
        self.corpus_dir = self.root / corpus
        self.db_path = self.corpus_dir / _INDEX_FILE

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "CREATE TABLE IF NOT EXISTS units("
            "slug TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER, name TEXT, kind TEXT, "
            "description TEXT, body TEXT, status TEXT, match_json TEXT)"
        )
        con.execute("CREATE TABLE IF NOT EXISTS terms(term TEXT, slug TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_terms_slug ON terms(slug)")
        # the dependency graph (target: prerequisites) — the MemoryMakefile data.
        # rel ∈ {deps, references, supersedes}; reverse query gives the blast radius.
        con.execute("CREATE TABLE IF NOT EXISTS deps(slug TEXT, target TEXT, rel TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_deps_slug ON deps(slug)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_deps_target ON deps(target)")
        # reserved for the semantic retriever (vectors keyed by slug + model)
        con.execute("CREATE TABLE IF NOT EXISTS vectors(slug TEXT, model TEXT, vec BLOB, PRIMARY KEY(slug, model))")
        return con

    def _scan_disk(self) -> Dict[str, Tuple[int, int, Path]]:
        on_disk: Dict[str, Tuple[int, int, Path]] = {}
        if not self.corpus_dir.exists():
            return on_disk
        for entry in os.scandir(self.corpus_dir):
            if not entry.is_dir():
                continue
            skill = Path(entry.path) / "SKILL.md"
            if not skill.exists():
                continue
            st = skill.stat()
            on_disk[entry.name] = (st.st_mtime_ns, st.st_size, skill)
        return on_disk

    def sync(self) -> None:
        """Incrementally reconcile the index with the corpus: reparse only files
        whose (mtime, size) changed; drop units that vanished."""
        if not self.corpus_dir.exists():
            return
        from aigg_memory.memory import MemoryUnit  # lazy to avoid an import cycle

        con = self._connect()
        try:
            on_disk = self._scan_disk()
            indexed = {slug: (m, s) for slug, m, s in con.execute("SELECT slug, mtime_ns, size FROM units")}
            for slug, (mtime_ns, size, skill) in on_disk.items():
                if indexed.get(slug) == (mtime_ns, size):
                    continue  # unchanged
                unit = MemoryUnit.from_text(skill.read_text(encoding="utf-8"))
                con.execute(
                    "INSERT OR REPLACE INTO units VALUES(?,?,?,?,?,?,?,?,?)",
                    (slug, mtime_ns, size, unit.name, unit.kind or "semantic",
                     unit.frontmatter.get("description", ""), unit.body,
                     unit.frontmatter.get("status", "active"),
                     json.dumps(unit.match_terms, ensure_ascii=False)),
                )
                con.execute("DELETE FROM terms WHERE slug=?", (slug,))
                terms = sorted({t.lower() for t in unit.match_terms if t})
                con.executemany("INSERT INTO terms(term, slug) VALUES(?, ?)", [(t, slug) for t in terms])
                con.execute("DELETE FROM deps WHERE slug=?", (slug,))
                edges = [(slug, str(target), rel)
                         for rel in ("deps", "references", "supersedes")
                         for target in (unit.frontmatter.get(rel) or [])]
                con.executemany("INSERT INTO deps(slug, target, rel) VALUES(?, ?, ?)", edges)
                con.execute("DELETE FROM vectors WHERE slug=?", (slug,))  # force re-embed on change
            for slug in indexed:
                if slug not in on_disk:
                    con.execute("DELETE FROM units WHERE slug=?", (slug,))
                    con.execute("DELETE FROM terms WHERE slug=?", (slug,))
                    con.execute("DELETE FROM deps WHERE slug=?", (slug,))
                    con.execute("DELETE FROM vectors WHERE slug=?", (slug,))
            con.commit()
        finally:
            con.close()

    def size(self) -> int:
        if not self.db_path.exists():
            return 0
        con = self._connect()
        try:
            return con.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        finally:
            con.close()

    def query(self, request: str, kinds: Optional[List[str]] = None, n_best: int = 5) -> List[Dict]:
        """Keyword recall over the inverted index: a unit's declared match term
        matches when it is a substring of the request (same semantics as a scan,
        but over a compact terms table instead of every file)."""
        self.sync()
        if not self.db_path.exists():
            return []
        from aigg_memory.memory import unit_path  # lazy

        con = self._connect()
        try:
            req = (request or "").lower()
            matched = [t for (t,) in con.execute("SELECT DISTINCT term FROM terms") if t and t in req]
            if not matched:
                return []
            placeholders = ",".join("?" * len(matched))
            scores = {slug: n for slug, n in con.execute(
                f"SELECT slug, COUNT(*) FROM terms WHERE term IN ({placeholders}) GROUP BY slug", matched)}
            if not scores:
                return []
            slugs = list(scores)
            ph2 = ",".join("?" * len(slugs))
            out: List[Dict] = []
            for slug, name, kind, desc, body, status, match_json in con.execute(
                f"SELECT slug, name, kind, description, body, status, match_json FROM units WHERE slug IN ({ph2})", slugs):
                if status == "archived":
                    continue
                resolved_kind = kind or "semantic"
                if kinds and resolved_kind not in kinds:
                    continue
                out.append({
                    "slug": slug, "path": unit_path(slug), "name": name, "kind": resolved_kind,
                    "description": desc or "", "body": (body or "").strip(),
                    "match_terms": json.loads(match_json or "[]"), "score": scores[slug],
                })
            out.sort(key=lambda d: -d["score"])
            return out[:n_best]
        finally:
            con.close()

    def dependency_closure(self, slugs) -> set:
        """All units reachable from `slugs` via depends_on edges (the prerequisite
        closure), cycle-safe; includes the inputs."""
        seen: set = set()
        frontier = list(slugs)
        while frontier:
            slug = frontier.pop()
            if slug in seen:
                continue
            seen.add(slug)
            frontier.extend(d for d in self.depends_on(slug) if d not in seen)
        return seen

    def fetch_units(self, slugs: List[str]) -> List[Dict]:
        """Full unit dicts for the given slugs (existing, non-archived)."""
        if not slugs or not self.db_path.exists():
            return []
        from aigg_memory.memory import unit_path  # lazy
        con = self._connect()
        try:
            ph = ",".join("?" * len(slugs))
            out = []
            for slug, name, kind, desc, body, status, match_json in con.execute(
                f"SELECT slug, name, kind, description, body, status, match_json FROM units WHERE slug IN ({ph})", slugs):
                if status == "archived":
                    continue
                out.append({
                    "slug": slug, "path": unit_path(slug), "name": name, "kind": kind or "semantic",
                    "description": desc or "", "body": (body or "").strip(),
                    "match_terms": json.loads(match_json or "[]"),
                })
            return out
        finally:
            con.close()

    # --- dependency graph (MemoryMakefile data) ---------------------------

    def _edges(self, where: str, value: str, rels) -> List[str]:
        if not self.db_path.exists():
            return []
        con = self._connect()
        try:
            ph = ",".join("?" * len(rels))
            rows = con.execute(
                f"SELECT DISTINCT {('target' if where == 'slug' else 'slug')} FROM deps "
                f"WHERE {where}=? AND rel IN ({ph})", (value, *rels))
            return sorted(r[0] for r in rows)
        finally:
            con.close()

    def depends_on(self, slug: str) -> List[str]:
        """What this unit needs (forward edges: deps + references)."""
        return self._edges("slug", slug, ("deps", "references"))

    def depended_by(self, slug: str) -> List[str]:
        """The blast radius: who needs this unit (reverse edges)."""
        return self._edges("target", slug, ("deps", "references"))

    def supersedes(self, slug: str) -> List[str]:
        return self._edges("slug", slug, ("supersedes",))

    # --- semantic recall (vectors) ---------------------------------------

    @staticmethod
    def _routing_text(name, description, match_json) -> str:
        terms = " ".join(json.loads(match_json or "[]"))
        return f"{name or ''} {description or ''} {terms}".strip()

    def embed(self, embedder) -> None:
        """Embed (build-time) any unit missing a vector for this embedder's model;
        idempotent and incremental (changed units have their vectors cleared on sync)."""
        self.sync()
        if not self.db_path.exists():
            return
        from aigg_memory.embed import pack_vector
        con = self._connect()
        try:
            have = {s for (s,) in con.execute("SELECT slug FROM vectors WHERE model=?", (embedder.name,))}
            todo = [(slug, self._routing_text(name, desc, match_json))
                    for slug, name, desc, match_json in con.execute(
                        "SELECT slug, name, description, match_json FROM units")
                    if slug not in have]
            if not todo:
                return
            vectors = embedder.embed([text for _slug, text in todo])
            con.executemany(
                "INSERT OR REPLACE INTO vectors(slug, model, vec) VALUES(?, ?, ?)",
                [(slug, embedder.name, pack_vector(vec)) for (slug, _t), vec in zip(todo, vectors)])
            con.commit()
        finally:
            con.close()

    def query_semantic(self, request: str, embedder, kinds: Optional[List[str]] = None, n_best: int = 5) -> List[Dict]:
        """Cosine recall over stored vectors (brute force). Embeds missing units
        first (build-time), then ranks (run-time)."""
        self.embed(embedder)
        if not self.db_path.exists():
            return []
        from aigg_memory.embed import cosine, unpack_vector
        from aigg_memory.memory import unit_path
        qvec = embedder.embed([request or ""])[0]
        con = self._connect()
        try:
            scored = []
            for slug, name, kind, desc, body, status, match_json, blob in con.execute(
                "SELECT u.slug, u.name, u.kind, u.description, u.body, u.status, u.match_json, v.vec "
                "FROM units u JOIN vectors v ON u.slug=v.slug AND v.model=?", (embedder.name,)):
                if status == "archived":
                    continue
                resolved_kind = kind or "semantic"
                if kinds and resolved_kind not in kinds:
                    continue
                sim = cosine(qvec, unpack_vector(blob))
                if sim <= 0:
                    continue
                scored.append((sim, {
                    "slug": slug, "path": unit_path(slug), "name": name, "kind": resolved_kind,
                    "description": desc or "", "body": (body or "").strip(),
                    "match_terms": json.loads(match_json or "[]"), "score": round(sim, 4),
                }))
            scored.sort(key=lambda item: -item[0])
            return [unit for _s, unit in scored[:n_best]]
        finally:
            con.close()

    def vectors_with_meta(self, model: str):
        """[(slug, kind, status, vec)] for every embedded unit of the given model."""
        if not self.db_path.exists():
            return []
        from aigg_memory.embed import unpack_vector
        con = self._connect()
        try:
            return [(slug, kind or "semantic", status, unpack_vector(blob))
                    for slug, kind, status, blob in con.execute(
                        "SELECT u.slug, u.kind, u.status, v.vec FROM units u "
                        "JOIN vectors v ON u.slug=v.slug AND v.model=?", (model,))]
        finally:
            con.close()

    def graph(self) -> Dict[str, Dict]:
        """Per-unit dependency view: depends_on / depended_by / supersedes."""
        self.sync()
        if not self.db_path.exists():
            return {}
        con = self._connect()
        try:
            nodes = {slug: {"kind": kind or "semantic", "description": desc or ""}
                     for slug, kind, desc in con.execute("SELECT slug, kind, description FROM units")}
        finally:
            con.close()
        for slug, node in nodes.items():
            node["depends_on"] = self.depends_on(slug)
            node["depended_by"] = self.depended_by(slug)
            node["supersedes"] = self.supersedes(slug)
        return dict(sorted(nodes.items()))


def _scan_select(workspace: Dict[str, str], request: str, n_best: int, kinds: Optional[List[str]]) -> List[Dict]:
    """Index-free fallback (read-only filesystem, or no index): scan the loaded
    workspace directly. Same semantics as the index query."""
    from aigg_memory.memory import MemoryUnit

    req = (request or "").lower()
    scored: List[Tuple[int, Dict]] = []
    for path, content in workspace.items():
        if not path.endswith(_UNIT_SUFFIX):
            continue
        unit = MemoryUnit.from_text(content)
        if not unit.name or unit.frontmatter.get("status") == "archived":
            continue
        resolved_kind = unit.kind or "semantic"
        if kinds and resolved_kind not in kinds:
            continue
        score = sum(1 for t in unit.match_terms if t.lower() in req)
        if score > 0:
            scored.append((score, {
                "path": path, "name": unit.name, "kind": resolved_kind,
                "description": unit.frontmatter.get("description", ""), "body": unit.body.strip(),
                "match_terms": unit.match_terms, "score": score,
            }))
    scored.sort(key=lambda item: -item[0])
    return [d for _s, d in scored[:n_best]]


def _merge_hybrid(keyword: List[Dict], semantic: List[Dict], n_best: int) -> List[Dict]:
    """Union keyword + semantic, scoring each by its normalized rank in both."""
    def ranks(units):
        return {u["slug"]: 1.0 - i / max(len(units), 1) for i, u in enumerate(units)}
    kr, sr = ranks(keyword), ranks(semantic)
    by_slug = {u["slug"]: u for u in (*keyword, *semantic)}
    for slug, unit in by_slug.items():
        unit["score"] = round(kr.get(slug, 0.0) + sr.get(slug, 0.0), 4)
    return sorted(by_slug.values(), key=lambda u: -u["score"])[:n_best]


def select_and_count(root: Union[str, Path], corpus: str, request: str, n_best: int = 5,
                     kinds: Optional[List[str]] = None, include_deps: bool = False,
                     retriever: str = "keyword", embedder=None) -> Tuple[List[Dict], int]:
    """Indexed recall + corpus size. `retriever` ∈ {keyword, semantic, hybrid}
    (semantic/hybrid use a pluggable embedder, defaulting to the zero-dep
    HashEmbedder). With `include_deps`, a recalled unit's prerequisite closure (its
    `depends_on` units) is appended as `relation: dependency`. Falls back to a
    direct keyword scan if the index is unavailable (e.g. a read-only corpus)."""
    try:
        index = CorpusIndex(root, corpus)
        if retriever in ("semantic", "hybrid"):
            from aigg_memory.embed import get_embedder
            emb = embedder or get_embedder()
            semantic = index.query_semantic(request, emb, kinds=kinds, n_best=n_best * (2 if retriever == "hybrid" else 1))
            if retriever == "semantic":
                units = semantic[:n_best]
            else:
                keyword = index.query(request, kinds=kinds, n_best=n_best * 2)
                units = _merge_hybrid(keyword, semantic, n_best)
        else:
            units = index.query(request, kinds=kinds, n_best=n_best)
        if include_deps and units:
            matched = {u["slug"] for u in units}
            extra = sorted(index.dependency_closure(matched) - matched)
            for dep in index.fetch_units(extra):
                dep["score"] = 0
                dep["relation"] = "dependency"
                units.append(dep)
        return units, index.size()
    except Exception:
        from aigg_memory.memory import load_corpus
        workspace = load_corpus(root, corpus)
        units = _scan_select(workspace, request, n_best, kinds)
        return units, sum(1 for p in workspace if p.endswith(_UNIT_SUFFIX))


def update_index(root: Union[str, Path], corpus: str = "memory") -> None:
    """Best-effort index refresh (called after a write); never raises."""
    try:
        CorpusIndex(root, corpus).sync()
    except Exception:
        pass
