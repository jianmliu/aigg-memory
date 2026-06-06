"""The typed `memory` domain — SKILL.md-shaped units over the Workspace.

A memory unit is `memory/<slug>/SKILL.md` with YAML frontmatter (name, description,
kind, match, provenance/lifecycle metadata) + a markdown body. A unit's `kind`
(procedural | semantic | episodic) makes consolidation kind-aware: procedural
units land as `candidate` (needs review), declarative ones auto-activate.

Multi-file by nature, so it runs on the kernel's Workspace API
(`generate_workspace_patch` / `evaluate_workspace`). No agentmf import; depends on
PyYAML for frontmatter (a memory store reading SKILL.md legitimately needs YAML).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml

from aigg_memory._util import fingerprint
from aigg_memory.kernel import evaluate_workspace, generate_workspace_patch, run_dream
from aigg_memory.models import Domain, GateResult, Proposal, WorkspacePatch

VALID_KINDS = {"procedural", "semantic", "episodic", "working"}
_UNIT_SUFFIX = "/SKILL.md"


@dataclass
class MemoryUnit:
    frontmatter: Dict
    body: str

    @property
    def name(self) -> Optional[str]:
        return self.frontmatter.get("name")

    @property
    def kind(self) -> Optional[str]:
        return self.frontmatter.get("kind")

    @property
    def match_terms(self) -> List[str]:
        return list((self.frontmatter.get("match") or {}).get("user_intent") or [])

    def to_text(self) -> str:
        fm = yaml.safe_dump(self.frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
        return f"---\n{fm}\n---\n\n{self.body.rstrip(chr(10))}\n"

    @classmethod
    def from_text(cls, text: str) -> "MemoryUnit":
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for index in range(1, len(lines)):
                if lines[index].strip() == "---":
                    fm = yaml.safe_load("\n".join(lines[1:index])) or {}
                    body = "\n".join(lines[index + 1:]).lstrip("\n")
                    return cls(fm if isinstance(fm, dict) else {}, body)
        return cls({}, text)


def validate_corpus(corpus: str) -> str:
    """Guard the one untrusted path component a request controls. A corpus is used
    as `root/<corpus>/<slug>/SKILL.md`; nested corpora (`npcs/<id>/memory`) are
    supported, so slashes are fine — but a `..` segment, an absolute path, or a
    Windows drive would escape `root`. Allow nesting, reject traversal. Raises
    ValueError on anything unsafe (the server turns that into a 400)."""
    if not isinstance(corpus, str) or not corpus.strip():
        raise ValueError("corpus must be a non-empty string")
    segments = corpus.replace("\\", "/").split("/")
    for seg in segments:
        if seg in ("", ".", "..") or ":" in seg:
            raise ValueError(f"unsafe corpus path: {corpus!r}")
    return corpus


def unit_path(slug: str) -> str:
    return f"memory/{slug}{_UNIT_SUFFIX}"


def _is_unit(path: str) -> bool:
    return path.endswith(_UNIT_SUFFIX)


# --- appliers (workspace -> workspace) ------------------------------------

def _apply_add_unit(workspace: Dict[str, str], change: dict) -> Dict[str, str]:
    slug = change["slug"]
    path = unit_path(slug)
    if path in workspace:
        return workspace  # idempotent
    frontmatter = {
        "name": change.get("name", slug),
        "description": change.get("description", ""),
        "kind": change.get("kind", "semantic"),
        "match": {"user_intent": list(change.get("match", []))},
        "id": slug,
        "confidence": change.get("confidence", "medium"),
        "observations": change.get("observations", 1),
        "source_events": sorted(set(change.get("source_events", []))),
        "status": change.get("status", "active"),
    }
    for relation in ("deps", "references"):  # carry declared relations into the unit
        if change.get(relation):
            frontmatter[relation] = list(change[relation])
    ws = dict(workspace)
    ws[path] = MemoryUnit(frontmatter, change.get("body") or change.get("description", "")).to_text()
    return ws


def _apply_update_unit(workspace: Dict[str, str], change: dict) -> Dict[str, str]:
    path = unit_path(change["slug"])
    if path not in workspace:
        return workspace
    unit = MemoryUnit.from_text(workspace[path])
    if change.get("body") is not None:
        unit.body = change["body"]
    if change.get("description"):
        unit.frontmatter["description"] = change["description"]
    if change.get("source_events"):
        merged = set(unit.frontmatter.get("source_events") or []) | set(change["source_events"])
        unit.frontmatter["source_events"] = sorted(merged)
    if change.get("updated"):
        unit.frontmatter["updated"] = change["updated"]
    ws = dict(workspace)
    ws[path] = unit.to_text()
    return ws


def _apply_archive_unit(workspace: Dict[str, str], change: dict) -> Dict[str, str]:
    path = unit_path(change["slug"])
    if path not in workspace:
        return workspace
    unit = MemoryUnit.from_text(workspace[path])
    unit.frontmatter["status"] = "archived"
    if change.get("source_events"):  # the obsolete signal is part of the unit's provenance
        merged = set(unit.frontmatter.get("source_events") or []) | set(change["source_events"])
        unit.frontmatter["source_events"] = sorted(merged)
    ws = dict(workspace)
    ws[path] = unit.to_text()
    return ws


def _apply_merge_units(workspace: Dict[str, str], change: dict) -> Dict[str, str]:
    into = change["into"]
    ws = dict(workspace)
    for slug in change["slugs"]:
        ws.pop(unit_path(slug), None)
    frontmatter = {
        "name": into.get("name", into["slug"]),
        "description": into.get("description", ""),
        "kind": into.get("kind", "semantic"),
        "match": {"user_intent": list(into.get("match", []))},
        "id": into["slug"],
        "supersedes": list(into.get("supersedes", [])),
        "status": into.get("status", "active"),
    }
    ws[unit_path(into["slug"])] = MemoryUnit(frontmatter, into.get("body", "")).to_text()
    return ws


# --- detectors (evidence -> proposals), kind-aware ------------------------

def _detect_promote_repeated(records: List, min_count: int = 2) -> List[Proposal]:
    groups: dict = {}
    for record in records:
        if record.source != "observation" or record.outcome:
            continue
        summary = record.summary or {}
        slug = summary.get("slug")
        if not slug:
            continue
        group = groups.setdefault(slug, {
            "slug": slug, "name": summary.get("name") or slug,
            "description": summary.get("description", ""), "kind": summary.get("kind", "semantic"),
            "match": summary.get("match", []), "body": summary.get("body", ""),
            "deps": summary.get("deps", []), "references": summary.get("references", []),
            "events": [], "n": 0,
        })
        group["n"] += 1
        group["events"].append(record.event_id)
        for field in ("description", "body", "match", "name", "deps", "references"):
            if summary.get(field):
                group[field] = summary[field]
    proposals = []
    for slug, group in sorted(groups.items()):
        if group["n"] >= min_count:
            # kind-aware policy: procedural memory needs review; declarative auto-activates.
            status = "candidate" if group["kind"] == "procedural" else "active"
            proposals.append(Proposal(
                proposal_id=fingerprint(("add", slug))[:12],
                title=f"remember: {group['name']}",
                changes=[{
                    "type": "add_unit", "slug": slug, "name": group["name"],
                    "description": group["description"], "kind": group["kind"], "match": group["match"],
                    "body": group["body"] or group["description"], "source_events": group["events"],
                    "observations": group["n"], "confidence": "high", "status": status,
                    "deps": group["deps"], "references": group["references"],
                }],
                scope={"corpus": "memory/"},
            ))
    return proposals


def _detect_corrections(records: List) -> List[Proposal]:
    proposals = []
    for record in records:
        if record.source == "observation" and record.outcome == "correction":
            summary = record.summary or {}
            slug = summary.get("slug")
            if slug and (summary.get("description") or summary.get("body")):
                proposals.append(Proposal(
                    proposal_id=fingerprint(("update", slug, record.event_id))[:12],
                    title=f"update: {slug}",
                    changes=[{
                        "type": "update_unit", "slug": slug,
                        "description": summary.get("description"), "body": summary.get("body"),
                        "source_events": [record.event_id], "updated": record.timestamp,
                    }],
                    scope={"corpus": "memory/"},
                ))
    return proposals


def _detect_obsolete(records: List) -> List[Proposal]:
    proposals = []
    for record in records:
        if record.source == "observation" and record.outcome == "obsolete":
            slug = (record.summary or {}).get("slug")
            if slug:
                proposals.append(Proposal(
                    proposal_id=fingerprint(("archive", slug))[:12],
                    title=f"archive: {slug}",
                    changes=[{"type": "archive_unit", "slug": slug, "source_events": [record.event_id]}],
                    scope={"corpus": "memory/"},
                ))
    return proposals


# --- gates (workspace) ----------------------------------------------------

def _units(workspace: Dict[str, str]):
    for path, content in workspace.items():
        if _is_unit(path):
            yield path, MemoryUnit.from_text(content)


def _gate_units_parse(before, after, proposal) -> GateResult:
    bad = [p for p, u in _units(after) if not (u.name and u.frontmatter.get("description") and u.kind)]
    return GateResult("units_parse", len(bad) == 0, detail=f"{len(bad)} malformed unit(s)")


def _gate_unique_ids(before, after, proposal) -> GateResult:
    ids = [u.frontmatter.get("id") for _p, u in _units(after)]
    return GateResult("unique_ids", len(ids) == len(set(ids)), detail=f"{len(ids) - len(set(ids))} duplicate id(s)")


def _gate_has_match(before, after, proposal) -> GateResult:
    missing = [p for p, u in _units(after) if not u.match_terms]
    return GateResult("has_match_terms", len(missing) == 0, detail=f"{len(missing)} unit(s) without match terms")


def _gate_kind_valid(before, after, proposal) -> GateResult:
    bad = [p for p, u in _units(after) if u.kind not in VALID_KINDS]
    return GateResult("kind_valid", len(bad) == 0, detail=f"{len(bad)} unit(s) with invalid kind")


def memory_domain(min_promote_count: int = 2) -> Domain:
    return Domain(
        name="memory",
        summarizers={"observation": lambda p: {
            k: p.get(k) for k in ("name", "slug", "kind", "description", "match", "body", "deps", "references")
            if p.get(k) is not None
        }},
        appliers={
            "add_unit": _apply_add_unit,
            "update_unit": _apply_update_unit,
            "merge_units": _apply_merge_units,
            "archive_unit": _apply_archive_unit,
        },
        gates=[_gate_units_parse, _gate_unique_ids, _gate_has_match, _gate_kind_valid],
        detectors=[partial(_detect_promote_repeated, min_count=min_promote_count), _detect_corrections, _detect_obsolete],
    )


# --- orchestrator ---------------------------------------------------------

@dataclass
class MemoryConsolidationResult:
    proposals: List[Proposal]
    patch: WorkspacePatch
    gates: List[GateResult]
    new_workspace: Dict[str, str]

    @property
    def gates_ok(self) -> bool:
        return all(g.passed for g in self.gates)


def consolidate(workspace: Dict[str, str], records: List, domain: Optional[Domain] = None) -> MemoryConsolidationResult:
    """Run the full loop over a memory corpus (workspace of unit files): evidence
    -> proposals (run_dream) -> multi-file patch -> gates. Pure: no file IO."""
    domain = domain or memory_domain()
    proposals = run_dream(domain, records)
    all_changes = [change for proposal in proposals for change in proposal.changes]
    combined = Proposal("consolidation", "memory consolidation", all_changes, scope={"corpus": "memory/"})
    patch = generate_workspace_patch(domain, combined, workspace)
    gates = evaluate_workspace(domain, workspace, patch.new_workspace, combined)
    return MemoryConsolidationResult(proposals=proposals, patch=patch, gates=gates, new_workspace=patch.new_workspace)


# --- file-backed corpus (the on-disk memory/ directory) -------------------

def _remove_unit(root: Path, corpus: str, key: str) -> None:
    """Delete a unit's SKILL.md and its now-empty `<slug>/` directory (defrag)."""
    path = _disk_path(Path(root), corpus, key)
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def _disk_path(root: Path, corpus: str, key: str) -> Path:
    """A workspace key is always domain-normalised (`memory/<slug>/SKILL.md`); on
    disk the unit lives under `root/<corpus>/<slug>/SKILL.md`."""
    slug = Path(key).parent.name
    return root / corpus / slug / "SKILL.md"


def load_corpus(root: Union[str, Path], corpus: str = "memory") -> Dict[str, str]:
    """Read all `<corpus>/<slug>/SKILL.md` under `root` into a workspace keyed by
    the domain path convention (`memory/<slug>/SKILL.md`), regardless of the
    on-disk corpus directory."""
    root = Path(root)
    workspace: Dict[str, str] = {}
    for path in sorted((root / corpus).glob("*/SKILL.md")):
        workspace[unit_path(path.parent.name)] = path.read_text(encoding="utf-8")
    return workspace


def write_corpus(root: Union[str, Path], workspace: Dict[str, str], corpus: str = "memory",
                 only: Optional[List[str]] = None) -> List[str]:
    root = Path(root)
    written: List[str] = []
    for key in (only if only is not None else list(workspace)):
        disk = _disk_path(root, corpus, key)
        disk.parent.mkdir(parents=True, exist_ok=True)
        disk.write_text(workspace[key], encoding="utf-8")
        written.append(key)
    return written


@dataclass
class CorpusConsolidationResult:
    consolidation: MemoryConsolidationResult
    written: List[str]
    removed: List[str]

    @property
    def gates_ok(self) -> bool:
        return self.consolidation.gates_ok


def consolidate_corpus(root: Union[str, Path], records: List, write: bool = False,
                       corpus: str = "memory", domain: Optional[Domain] = None,
                       min_promote_count: int = 2) -> CorpusConsolidationResult:
    """Load the on-disk `<corpus>/` corpus, consolidate from evidence, and (when
    `write` and every gate passes) write changed unit files back, deleting any
    merged-away units. Returns the changed/removed paths. `min_promote_count` is the
    repetition gate: ambient capture keeps the default (2) so one-off chatter isn't
    promoted; an explicit 'remember X' passes 1 to land immediately."""
    root = Path(root)
    if domain is None:
        domain = memory_domain(min_promote_count=min_promote_count)
    before = load_corpus(root, corpus)
    result = consolidate(before, records, domain=domain)
    written: List[str] = []
    removed: List[str] = []
    if write and result.gates_ok:
        after = result.new_workspace
        changed = sorted(key for key, content in after.items() if before.get(key) != content)
        written = write_corpus(root, after, corpus=corpus, only=changed)
        removed = sorted(key for key in before if key not in after)
        for key in removed:
            _remove_unit(root, corpus, key)
        # refresh the derived index (cache) to match the new on-disk corpus
        from aigg_memory.index import update_index  # lazy to avoid an import cycle
        update_index(root, corpus)
    return CorpusConsolidationResult(consolidation=result, written=written, removed=removed)


@dataclass
class ConsolidationStatus:
    corpus: str
    total_evidence: int
    consolidated_events: int       # distinct event_ids already folded into units
    pending: int                   # evidence not yet absorbed into any unit
    oldest_pending_timestamp: Optional[str]
    recommended: bool              # advisory: pending >= min_new (the app owns the policy)

    def to_dict(self) -> Dict[str, object]:
        return {
            "corpus": self.corpus,
            "total_evidence": self.total_evidence,
            "consolidated_events": self.consolidated_events,
            "pending": self.pending,
            "oldest_pending_timestamp": self.oldest_pending_timestamp,
            "recommended": self.recommended,
        }


def consolidation_status(root: Union[str, Path], records: List, corpus: str = "memory",
                         min_new: int = 1) -> ConsolidationStatus:
    """A cheap readiness signal so an application can decide *when* to consolidate
    (the trigger is app policy — an NPC sleeping, a session ending, a chain epoch).
    Stateless: an evidence record is 'pending' when its event_id is not yet folded
    into any unit's source_events. The engine reports; the app decides."""
    consolidated: set = set()
    for content in load_corpus(root, corpus).values():
        for event in MemoryUnit.from_text(content).frontmatter.get("source_events") or []:
            consolidated.add(event)
    pending = [r for r in records if r.event_id not in consolidated]
    oldest = min((r.timestamp for r in pending), default=None)
    return ConsolidationStatus(
        corpus=corpus,
        total_evidence=len(records),
        consolidated_events=len(consolidated),
        pending=len(pending),
        oldest_pending_timestamp=oldest,
        recommended=len(pending) >= min_new,
    )


# --- compaction: automatic merge + defrag + redundancy removal -------------

@dataclass
class CompactionResult:
    clusters: List[List[str]]   # similarity clusters found (incl. singletons)
    merged: List[Dict]          # [{into: slug, folded: [slugs]}]
    written: List[str]
    removed: List[str]
    gates_ok: bool = True


def _cluster_by_similarity(items, threshold: float) -> List[List[str]]:
    """Connected components of (slug, kind, vec) where same-kind cosine >= threshold."""
    from aigg_memory.embed import cosine

    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if items[i][1] == items[j][1] and cosine(items[i][2], items[j][2]) >= threshold:
                parent[find(i)] = find(j)
    groups: Dict[int, List[str]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i][0])
    return list(groups.values())


def compact_corpus(root: Union[str, Path], corpus: str = "memory", *, threshold: float = 0.85,
                   write: bool = False, embedder=None, min_cluster: int = 2) -> CompactionResult:
    """Cluster near-duplicate units (semantic similarity, same kind), fold each
    cluster into one canonical unit (union of match + provenance; `supersedes`
    records the fold), and remove the redundant files. Conservative by a high
    `threshold`; dry-run unless `write`. App-triggered, like Dream."""
    from aigg_memory.index import CorpusIndex, update_index

    root = Path(root)
    if embedder is None:
        from aigg_memory.embed import get_embedder
        embedder = get_embedder()
    index = CorpusIndex(root, corpus)
    index.embed(embedder)

    active = [(slug, kind, vec) for slug, kind, status, vec in index.vectors_with_meta(embedder.name)
              if status != "archived"]
    clusters = _cluster_by_similarity(active, threshold)
    merge_clusters = [c for c in clusters if len(c) >= min_cluster]

    merged: List[Dict] = []
    written: List[str] = []
    removed: List[str] = []
    for cluster in merge_clusters:
        units = {slug: MemoryUnit.from_text(_disk_path(root, corpus, unit_path(slug)).read_text(encoding="utf-8"))
                 for slug in cluster}
        canonical = max(cluster, key=lambda s: (units[s].frontmatter.get("observations", 1), len(units[s].body)))
        folded = sorted(s for s in cluster if s != canonical)
        canon = units[canonical]

        match_terms: List[str] = []
        for slug in [canonical, *folded]:
            for term in units[slug].match_terms:
                if term not in match_terms:
                    match_terms.append(term)
        canon.frontmatter["match"] = {"user_intent": match_terms}
        source_events = set(canon.frontmatter.get("source_events") or [])
        supersedes = set(canon.frontmatter.get("supersedes") or [])
        for slug in folded:
            source_events |= set(units[slug].frontmatter.get("source_events") or [])
            supersedes |= set(units[slug].frontmatter.get("supersedes") or []) | {slug}
        canon.frontmatter["source_events"] = sorted(source_events)
        canon.frontmatter["supersedes"] = sorted(supersedes)

        merged.append({"into": canonical, "folded": folded})
        if write:
            _disk_path(root, corpus, unit_path(canonical)).write_text(canon.to_text(), encoding="utf-8")
            written.append(unit_path(canonical))
            for slug in folded:
                _remove_unit(root, corpus, unit_path(slug))
                removed.append(unit_path(slug))

    if write and (written or removed):
        update_index(root, corpus)
    return CompactionResult(clusters=clusters, merged=merged, written=written, removed=removed)


# --- unit-aware merge (deterministic structural conflict resolution) --------

_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass
class MergeResult:
    merged: Dict[str, str]
    conflicts: List[Dict]       # [{slug, reason, ours, theirs}] — genuine value conflicts
    auto_resolved: List[str]    # slugs field-merged automatically


def _merge_frontmatter(a: Dict, b: Dict) -> Dict:
    newer = b if b.get("updated", "") > a.get("updated", "") else a
    out = dict(a)
    for field in ("name", "description", "kind"):
        out[field] = newer.get(field, out.get(field))
    out["match"] = {"user_intent": list(dict.fromkeys(
        [*(a.get("match") or {}).get("user_intent", []), *(b.get("match") or {}).get("user_intent", [])]))}
    for field in ("source_events", "deps", "references", "supersedes", "precedes"):
        if a.get(field) or b.get(field):
            out[field] = sorted(set(a.get(field) or []) | set(b.get(field) or []))
    # valid/world time: carry whichever side has it (newer wins a genuine conflict)
    for field in ("valid_from", "valid_to", "event_time"):
        value = newer.get(field) if newer.get(field) is not None else (a.get(field) or b.get(field))
        if value is not None:
            out[field] = value
    # profile pin is sticky: keep it if either side pinned (don't silently unpin on merge)
    if a.get("pinned") or b.get("pinned"):
        out["pinned"] = True
    # owner lock (persona card) is sticky too: a merge must never quietly unlock it
    if a.get("locked") or b.get("locked"):
        out["locked"] = True
    out["observations"] = max(a.get("observations", 1), b.get("observations", 1))
    out["confidence"] = max([a.get("confidence", "medium"), b.get("confidence", "medium")],
                            key=lambda c: _CONFIDENCE_RANK.get(c, 2))
    created = [x for x in (a.get("created"), b.get("created")) if x]
    if created:
        out["created"] = min(created)
    if a.get("updated") or b.get("updated"):
        out["updated"] = max(a.get("updated", ""), b.get("updated", ""))
    # status: keep active over archived (don't silently forget on merge)
    out["status"] = "active" if "active" in (a.get("status"), b.get("status")) else newer.get("status", "active")
    return out


def _merge_unit(slug: str, ours: MemoryUnit, theirs: MemoryUnit):
    frontmatter = _merge_frontmatter(ours.frontmatter, theirs.frontmatter)
    conflicts = []
    ob, tb = ours.body.strip(), theirs.body.strip()
    if ob == tb or (tb and tb in ob):
        body = ours.body
    elif ob and ob in tb:
        body = theirs.body
    else:
        body = ours.body  # ours wins on a genuine divergence; record it (nothing lost — theirs is reported)
        conflicts.append({"slug": slug, "reason": "body", "ours": ob, "theirs": tb})
    if ours.frontmatter.get("status") != theirs.frontmatter.get("status"):
        conflicts.append({"slug": slug, "reason": "status",
                          "ours": ours.frontmatter.get("status"), "theirs": theirs.frontmatter.get("status")})
    return MemoryUnit(frontmatter, body), conflicts


def merge_corpora(ours: Dict[str, str], theirs: Dict[str, str]) -> MergeResult:
    """Field-level merge of two corpora. Units unique to a side are kept; a unit in
    both is merged (union metadata, max counts, newer scalars); only divergent
    bodies / statuses surface as conflicts (ours is kept, theirs is reported)."""
    merged = dict(ours)
    conflicts: List[Dict] = []
    auto: List[str] = []
    for path, content in theirs.items():
        if not path.endswith("/SKILL.md"):
            continue
        if path not in ours:
            merged[path] = content
            continue
        if ours[path] == content:
            continue
        slug = Path(path).parent.name
        unit, unit_conflicts = _merge_unit(slug, MemoryUnit.from_text(ours[path]), MemoryUnit.from_text(content))
        merged[path] = unit.to_text()
        auto.append(slug)
        conflicts.extend(unit_conflicts)
    return MergeResult(merged=merged, conflicts=conflicts, auto_resolved=sorted(auto))


def merge_into(root: Union[str, Path], corpus: str, other_root: Union[str, Path],
               other_corpus: str = "memory", write: bool = False) -> MergeResult:
    """Merge another corpus (another agent / shared lore / a branch checkout) into
    this one. With `write`, the merged units are written to this corpus."""
    ours = load_corpus(root, corpus)
    result = merge_corpora(ours, load_corpus(other_root, other_corpus))
    if write:
        changed = sorted(k for k, v in result.merged.items() if ours.get(k) != v)
        if changed:
            write_corpus(root, result.merged, corpus=corpus, only=changed)
            from aigg_memory.index import update_index
            update_index(root, corpus)
    return result


# --- LLM-built dependency graph (directed relations embeddings can't infer) --

_REL_FIELD = {"depends_on": "deps", "references": "references", "supersedes": "supersedes",
              "precedes": "precedes"}


def infer_dependencies(root: Union[str, Path], corpus: str, inferrer, *, write: bool = False) -> Dict:
    """Use an external model (e.g. AIGGDependencyInferrer) to assert DIRECTED
    dependencies between units. Edges are validated against real slugs (no
    hallucinated nodes, no self-loops) and, with `write`, merged into the source
    units' frontmatter so the MemoryMakefile compiles them. Dry-run by default."""
    root = Path(root)
    workspace = load_corpus(root, corpus)
    units, slugs = [], set()
    for path, content in workspace.items():
        if not path.endswith("/SKILL.md"):
            continue
        slug = Path(path).parent.name
        slugs.add(slug)
        units.append({"slug": slug, "description": MemoryUnit.from_text(content).frontmatter.get("description", "")})

    edges = [e for e in inferrer.infer(units)
             if e["from"] in slugs and e["to"] in slugs and e["from"] != e["to"]]

    applied: List[Dict[str, str]] = []
    if write and edges:
        from aigg_memory.index import update_index
        by_from: Dict[str, List[Dict[str, str]]] = {}
        for edge in edges:
            by_from.setdefault(edge["from"], []).append(edge)
        for from_slug, group in by_from.items():
            disk = _disk_path(root, corpus, unit_path(from_slug))
            unit = MemoryUnit.from_text(disk.read_text(encoding="utf-8"))
            for edge in group:
                field = _REL_FIELD[edge["rel"]]
                values = list(unit.frontmatter.get(field) or [])
                if edge["to"] not in values:
                    values.append(edge["to"])
                unit.frontmatter[field] = values
                applied.append(edge)
            disk.write_text(unit.to_text(), encoding="utf-8")
        update_index(root, corpus)
    return {"edges": edges, "applied": applied, "wrote": bool(applied)}


def infer_temporal(root: Union[str, Path], corpus: str, inferrer, *, write: bool = False) -> Dict:
    """Use an external model (e.g. AIGGTemporalInferrer) to assert DIRECTED temporal
    ordering (`precedes`: 'A happened before B') between units — the world-time
    ordering git's transaction-time history can't express. Same edge machinery as
    `infer_dependencies`: edges are validated against real slugs and merged into the
    source units' frontmatter (`precedes`). Dry-run by default."""
    return infer_dependencies(root, corpus, inferrer, write=write)


# --- contradiction detection (the semantic half of conflict handling) --------

def detect_contradictions(root: Union[str, Path], corpus: str, detector, *, threshold: float = 0.6,
                          write: bool = False, embedder=None) -> Dict:
    """Find units that CONTRADICT. Cheap semantic similarity narrows to same-topic
    candidate pairs; an external model (e.g. AIGGContradictionDetector) judges which
    genuinely contradict. A pair with a CONFIDENT winner is auto-resolved (loser
    ARCHIVED — non-destructive, restorable — and the supersession recorded on the
    winner). A pair the model can't confidently decide (winner "uncertain", or a
    winner that isn't one of the pair) is NOT guessed: it goes to `needs_review` for
    a human to decide, and nothing is touched. Dry-run by default."""
    from aigg_memory.index import CorpusIndex, update_index

    root = Path(root)
    if embedder is None:
        from aigg_memory.embed import get_embedder
        embedder = get_embedder()
    index = CorpusIndex(root, corpus)
    index.embed(embedder)

    pairs = index.similar_pairs(embedder.name, threshold)
    candidate_slugs = {slug for a, b, _s in pairs for slug in (a, b)}
    if not candidate_slugs:
        return {"contradictions": [], "resolved": [], "needs_review": []}

    workspace = load_corpus(root, corpus)
    by_slug = {Path(p).parent.name: MemoryUnit.from_text(c) for p, c in workspace.items() if p.endswith("/SKILL.md")}
    units = [{"slug": s, "description": by_slug[s].frontmatter.get("description", "")}
             for s in candidate_slugs if s in by_slug]

    found, confident, needs_review = [], [], []
    for c in detector.detect(units):
        a, b, winner = c["a"], c["b"], c["winner"]
        # a or b not a real slug => a hallucinated NODE: invalid, drop entirely.
        if a not in by_slug or b not in by_slug or a == b:
            continue
        found.append(c)
        if winner in (a, b):
            loser = a if winner == b else b
            if by_slug[loser].frontmatter.get("locked"):
                # the loser is owner-locked (e.g. a persona card) — never auto-archive it
                needs_review.append({**c, "locked": True})
            else:
                confident.append(c)        # a trustworthy pick -> auto-resolvable
        else:
            needs_review.append(c)         # "uncertain"/invalid winner -> ask a human, don't guess

    resolved = []
    if write and confident:
        for c in confident:
            winner = c["winner"]
            loser = c["a"] if winner == c["b"] else c["b"]
            loser_unit = by_slug[loser]
            loser_unit.frontmatter["status"] = "archived"
            loser_unit.frontmatter["superseded_by"] = winner
            _disk_path(root, corpus, unit_path(loser)).write_text(loser_unit.to_text(), encoding="utf-8")
            winner_unit = by_slug[winner]
            sup = set(winner_unit.frontmatter.get("supersedes") or []) | {loser}
            winner_unit.frontmatter["supersedes"] = sorted(sup)
            _disk_path(root, corpus, unit_path(winner)).write_text(winner_unit.to_text(), encoding="utf-8")
            resolved.append({"winner": winner, "archived": loser})
        update_index(root, corpus)
    return {"contradictions": found, "resolved": resolved, "needs_review": needs_review}


def reconcile(root: Union[str, Path], corpus: str, reconciler, *, threshold: float = 0.6,
              write: bool = False, now: Optional[str] = None, embedder=None) -> Dict:
    """Reconcile new statements against existing memory so the store stays current.
    Cheap similarity narrows same-topic candidate pairs; the reconciler judges how
    each pair relates and which fact holds NOW, and we route:
      - correction (old was WRONG): archive old (superseded_by current).
      - temporal (old was true BEFORE): archive old + stamp its `valid_to`=now, and
        the current fact's `valid_from`=now — non-destructive, history preserved.
      - none: leave both.
      - uncertain / invalid current: don't guess — queue to `needs_review`.
    Dry-run by default. `now` (an ISO string) is supplied by the caller (the engine
    ships no clock); temporal stamping is skipped if it's omitted."""
    from aigg_memory.index import CorpusIndex, update_index

    root = Path(root)
    if embedder is None:
        from aigg_memory.embed import get_embedder
        embedder = get_embedder()
    index = CorpusIndex(root, corpus)
    index.embed(embedder)

    pairs = index.similar_pairs(embedder.name, threshold)
    if not pairs:
        return {"reconciled": [], "needs_review": []}

    workspace = load_corpus(root, corpus)
    by_slug = {Path(p).parent.name: MemoryUnit.from_text(c) for p, c in workspace.items() if p.endswith("/SKILL.md")}

    actions, needs_review = [], []
    for a, b, _score in pairs:
        if a not in by_slug or b not in by_slug or a == b:
            continue
        v = reconciler.judge({"slug": a, "description": by_slug[a].frontmatter.get("description", "")},
                             {"slug": b, "description": by_slug[b].frontmatter.get("description", "")})
        relation, current = v["relation"], v.get("current")
        if relation == "none":
            continue
        if relation in ("correction", "temporal") and current in (a, b):
            old = a if current == b else b
            if by_slug[old].frontmatter.get("locked"):
                # the unit that would be archived is owner-locked (a persona card) —
                # the loop must not overwrite the owner's authored memory; defer.
                needs_review.append({"a": a, "b": b, "relation": relation,
                                     "reason": v.get("reason", ""), "locked": True})
            else:
                actions.append({"current": current, "old": old, "relation": relation, "reason": v.get("reason", "")})
        else:  # uncertain, or a current that isn't one of the pair -> defer, don't guess
            needs_review.append({"a": a, "b": b, "relation": "uncertain", "reason": v.get("reason", "")})

    reconciled = []
    if write and actions:
        for act in actions:
            current, old, relation = act["current"], act["old"], act["relation"]
            old_unit, cur_unit = by_slug[old], by_slug[current]
            old_unit.frontmatter["status"] = "archived"
            old_unit.frontmatter["superseded_by"] = current
            if relation == "temporal" and now:
                old_unit.frontmatter["valid_to"] = now          # old was true until now
                cur_unit.frontmatter.setdefault("valid_from", now)  # current holds as of now
            _disk_path(root, corpus, unit_path(old)).write_text(old_unit.to_text(), encoding="utf-8")
            cur_unit.frontmatter["supersedes"] = sorted(set(cur_unit.frontmatter.get("supersedes") or []) | {old})
            _disk_path(root, corpus, unit_path(current)).write_text(cur_unit.to_text(), encoding="utf-8")
            reconciled.append({"current": current, "old": old, "relation": relation})
        update_index(root, corpus)
    return {"reconciled": reconciled, "needs_review": needs_review}


# --- MemoryMakefile: the compiled dependency graph (human navigation) ------

def build_memorymakefile(root: Union[str, Path], corpus: str = "memory", write: bool = False) -> Dict:
    """Compile the units' declared relations (deps / references / supersedes) into
    a dependency graph — the MemoryMakefile. Each unit lists `depends_on` and the
    reverse `depended_by` (blast radius), so a human knows which unit to edit and
    what an edit touches. Derived from the units (source of truth); regenerable."""
    from aigg_memory.index import CorpusIndex  # lazy to avoid an import cycle

    graph = CorpusIndex(root, corpus).graph()
    makefile = {
        "version": "0.1",
        "metadata": {"corpus": corpus, "module_type": "memory-makefile"},
        "memories": graph,
    }
    if write:
        path = Path(root) / corpus / "MemoryMakefile"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(makefile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return makefile


def edit_unit(root: Union[str, Path], corpus: str, slug: str, *, body: Optional[str] = None,
              description: Optional[str] = None, status: Optional[str] = None,
              deps: Optional[List[str]] = None, references: Optional[List[str]] = None,
              match: Optional[List[str]] = None, valid_from: Optional[str] = None,
              valid_to: Optional[str] = None, pinned: Optional[bool] = None,
              locked: Optional[bool] = None) -> Dict:
    """Navigate to one unit and update it (units are the source of truth — this
    edits the file). Returns the unit's blast radius (`depended_by`) so the caller
    knows what an edit may affect."""
    from aigg_memory.index import CorpusIndex, update_index  # lazy

    path = _disk_path(Path(root), corpus, unit_path(slug))
    if not path.exists():
        return {"slug": slug, "updated": False, "blast_radius": []}
    unit = MemoryUnit.from_text(path.read_text(encoding="utf-8"))
    if body is not None:
        unit.body = body
    if description is not None:
        unit.frontmatter["description"] = description
    if status is not None:
        unit.frontmatter["status"] = status
    if deps is not None:
        unit.frontmatter["deps"] = deps
    if references is not None:
        unit.frontmatter["references"] = references
    if match is not None:
        unit.frontmatter["match"] = {"user_intent": match}
    if valid_from is not None:
        unit.frontmatter["valid_from"] = valid_from
    if valid_to is not None:
        unit.frontmatter["valid_to"] = valid_to
    if pinned is not None:
        unit.frontmatter["pinned"] = pinned
    if locked is not None:
        unit.frontmatter["locked"] = locked
    path.write_text(unit.to_text(), encoding="utf-8")
    update_index(root, corpus)
    return {"slug": slug, "updated": True, "blast_radius": CorpusIndex(root, corpus).depended_by(slug)}
