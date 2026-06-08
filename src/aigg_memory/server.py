"""aigg-memory serve — a standalone local JSON API for typed agent memory.

The HTTP/UI surface for the memory domain, owned by aigg-memory itself (no host
framework needed). An agent or app — a MUD, an inference gateway — can drive the
full online→offline→online memory cycle over HTTP:

  POST /memory/observe               record one observation (online, cheap)
  POST /memory/consolidation-status  readiness signal (app owns the trigger)
  POST /memory/consolidate           Dream consolidation → typed units (offline)
  POST /memory/select                kind-filtered recall + kind-aware bundle
  POST /memory/units                 list a corpus

`dispatch(method, path, body, root)` is the pure, unit-tested core; the
`http.server` shell only calls it. A corpus is `<corpus>/<slug>/SKILL.md`
(relative to `root`); evidence is its append-only JSONL store.
"""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from aigg_memory.index import select_and_count as index_select_and_count
from aigg_memory.memory import (
    MemoryUnit,
    compact_corpus,
    consolidate_corpus,
    consolidation_status,
    curate,
    dream,
    reflect,
    infer_temporal,
    reconcile,
    validate_corpus,
    detect_contradictions,
    infer_dependencies,
    load_corpus,
    memory_domain,
)
from aigg_memory.store import EvidenceStore

SERVE_API_VERSION = 1
_DEFAULT_CORPUS = "memory"
_UNIT_SUFFIX = "/SKILL.md"

Envelope = Dict[str, Any]


def _ok(data: Any, status: int = 200) -> Tuple[int, Envelope]:
    return status, {"ok": True, "diagnostics": [], "data": data}


def _err(code: str, message: str, status: int = 400) -> Tuple[int, Envelope]:
    return status, {"ok": False, "diagnostics": [{"severity": "error", "code": code, "message": message}], "data": None}


# --- helpers --------------------------------------------------------------

def _unit_summaries(workspace: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path, content in sorted(workspace.items()):
        if not path.endswith(_UNIT_SUFFIX):
            continue
        unit = MemoryUnit.from_text(content)
        if not unit.name:
            continue
        out.append({
            "path": path,
            "name": unit.name,
            "kind": unit.kind or "semantic",
            "description": unit.frontmatter.get("description", ""),
            "status": unit.frontmatter.get("status", "active"),
            "observations": unit.frontmatter.get("observations", 1),
            "confidence": unit.frontmatter.get("confidence", "medium"),
            "match_terms": unit.match_terms,
        })
    return out


def _bundle(units: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for label, kind in [("## Procedures", "procedural"), ("## Facts", "semantic"), ("## History", "episodic")]:
        group = [u for u in units if u["kind"] == kind]
        if not group:
            continue
        lines.append(label)
        for u in group:
            prefix = f"- apply `{u['name']}` — " if kind == "procedural" else "- "
            lines.append(prefix + (u["body"] or u["description"]))
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n") if lines else ""


# --- handlers -------------------------------------------------------------

def _h_healthz(body: dict, root: Path) -> Tuple[int, Envelope]:
    return _ok({"version": SERVE_API_VERSION, "root": str(root),
                "corpus_present": (root / _DEFAULT_CORPUS).exists()})


def _h_observe(body: dict, root: Path) -> Tuple[int, Envelope]:
    evidence_path = body.get("evidence")
    if not evidence_path:
        return _err("AM_MEM_400", "evidence path required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return _err("AM_MEM_400", "payload must be a JSON object")
    store = EvidenceStore(root / evidence_path, domain=memory_domain())
    try:
        record = store.record(body.get("source", "observation"), payload, outcome=body.get("outcome"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(record.to_dict())


def _h_consolidate(body: dict, root: Path) -> Tuple[int, Envelope]:
    evidence_path = body.get("evidence")
    if not evidence_path:
        return _err("AM_MEM_400", "evidence path required")
    corpus = body.get("corpus", _DEFAULT_CORPUS)
    domain = memory_domain()
    store = EvidenceStore(root / evidence_path, domain=domain)
    try:
        records = store.load()
        corpus_result = consolidate_corpus(root, records, write=bool(body.get("write", False)), corpus=corpus, domain=domain)
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    result = corpus_result.consolidation
    data = {
        "proposals": [p.to_dict() for p in result.proposals],
        "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail} for g in result.gates],
        "gates_ok": result.gates_ok,
        "diffs": result.patch.diffs,
        "diagnostics": result.patch.diagnostics.to_list(),
        "written": corpus_result.written,
        "removed": corpus_result.removed,
        "units_after": _unit_summaries(result.new_workspace),
    }
    return (200 if result.gates_ok else 422), {"ok": result.gates_ok, "diagnostics": [], "data": data}


def _h_dream(body: dict, root: Path) -> Tuple[int, Envelope]:
    """The offline maintenance pass for one entity, in one call — so an app (e.g. a MUD
    firing an NPC's sleep) consolidates + reconciles (+ deep: compacts + curates) that
    NPC's own corpus. Body: { evidence, corpus?, write?, deep?, min_count?, now?,
    threshold?, allowed_principals?, aigg_url?/aigg_key?/model?/backend? }. The LLM steps
    run only when a model is configured (aigg_url, or backend=claude-cli)."""
    evidence_path = body.get("evidence")
    if not evidence_path:
        return _err("AM_MEM_400", "evidence path required")
    store = EvidenceStore(root / evidence_path, domain=memory_domain())
    backend = body.get("backend", "http")
    has_model = backend == "claude-cli" or bool(body.get("aigg_url"))
    reconciler = curator = reflector = None
    if has_model:
        from aigg_memory.extract import AIGGCurator, AIGGReconciler
        kw = dict(api_key=body.get("aigg_key"), model=body.get("model", "gpt-4o-mini"),
                  extra_headers=body.get("extra_headers"), backend=backend)
        reconciler = AIGGReconciler(body.get("aigg_url") or "", **kw)
        if body.get("deep"):
            from aigg_memory.extract import AIGGReflector
            curator = AIGGCurator(body.get("aigg_url") or "", **kw)
            reflector = AIGGReflector(body.get("aigg_url") or "", **kw)
    try:
        out = dream(root, body.get("corpus", _DEFAULT_CORPUS), store.load(),
                    write=bool(body.get("write", False)), min_promote_count=int(body.get("min_count", 2)),
                    allowed_principals=body.get("allowed_principals"), reconciler=reconciler, curator=curator,
                    reflector=reflector, deep=bool(body.get("deep", False)),
                    compact_threshold=float(body.get("threshold", 0.85)), now=body.get("now"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_consolidation_status(body: dict, root: Path) -> Tuple[int, Envelope]:
    evidence_path = body.get("evidence")
    if not evidence_path:
        return _err("AM_MEM_400", "evidence path required")
    store = EvidenceStore(root / evidence_path, domain=memory_domain())
    try:
        status = consolidation_status(root, store.load(), corpus=body.get("corpus", _DEFAULT_CORPUS),
                                      min_new=int(body.get("min_new", 1)))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(status.to_dict())


def _h_select(body: dict, root: Path) -> Tuple[int, Envelope]:
    corpus = body.get("corpus", _DEFAULT_CORPUS)
    try:
        units, total = index_select_and_count(
            root, corpus, body.get("request", ""), n_best=int(body.get("n_best", 5)),
            kinds=body.get("kinds"), include_deps=bool(body.get("include_deps", False)),
            retriever=body.get("retriever", "keyword"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok({"units": units, "bundle": _bundle(units), "total_in_corpus": total})


def _h_ingest(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Encoding: extract memories from a raw transcript into the evidence store.
    Body: { transcript, evidence, extractor?, aigg_url?, aigg_key?, model?, extra_headers? }
    Real extraction (extractor='aigg') routes through an external AIGG service."""
    transcript = body.get("transcript")
    evidence_path = body.get("evidence")
    if not transcript or not evidence_path:
        return _err("AM_MEM_400", "transcript and evidence are required")
    from aigg_memory.extract import AIGGExtractor, HeuristicExtractor, ingest_transcript
    if body.get("extractor") == "aigg":
        if not body.get("aigg_url"):
            return _err("AM_MEM_400", "aigg_url is required for extractor=aigg")
        extractor = AIGGExtractor(body["aigg_url"], api_key=body.get("aigg_key"),
                                  model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    else:
        extractor = HeuristicExtractor()
    try:
        records = ingest_transcript(transcript, extractor, root / evidence_path)
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok({"extracted": len(records), "records": records})


def _h_infer_temporal(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Assert temporal-ordering edges (`precedes`) with an external AIGG model — the
    world-time ordering git's transaction-time history can't express.
    Body: { corpus?, aigg_url, aigg_key?, model?, extra_headers?, write? }"""
    if not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGTemporalInferrer
    inferrer = AIGGTemporalInferrer(body["aigg_url"], api_key=body.get("aigg_key"),
                                    model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    try:
        out = infer_temporal(root, body.get("corpus", _DEFAULT_CORPUS), inferrer, write=bool(body.get("write", False)))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_timeline(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Indexed temporal retrieval: units ordered by world-time (valid_from), or — with
    `as_of` — only those whose valid interval contains that time (the world-time
    complement to git's transaction-time restore). Body: { corpus?, as_of?, kinds? }"""
    from aigg_memory.index import CorpusIndex
    idx = CorpusIndex(root, body.get("corpus", _DEFAULT_CORPUS))
    kinds = body.get("kinds")
    rows = idx.as_of(body["as_of"], kinds) if body.get("as_of") else idx.timeline(kinds)
    return _ok({"timeline": rows})


def _h_curate(body: dict, root: Path) -> Tuple[int, Envelope]:
    """LLM value-triage: archive unique trivial chatter (non-destructive), via an AIGG
    model. Body: { corpus?, aigg_url, aigg_key?, model?, kinds?, max_confidence?, write? }"""
    if not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGCurator
    curator = AIGGCurator(body["aigg_url"], api_key=body.get("aigg_key"),
                          model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    try:
        out = curate(root, body.get("corpus", _DEFAULT_CORPUS), curator, write=bool(body.get("write", False)),
                     kinds=body.get("kinds"), max_confidence=body.get("max_confidence"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_reconcile(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Reconcile new statements vs memory (correction / temporal change) with an AIGG
    model. Body: { corpus?, aigg_url, aigg_key?, model?, threshold?, now?, write? }"""
    if not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGReconciler
    judge = AIGGReconciler(body["aigg_url"], api_key=body.get("aigg_key"),
                           model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    try:
        out = reconcile(root, body.get("corpus", _DEFAULT_CORPUS), judge,
                        threshold=float(body.get("threshold", 0.6)), write=bool(body.get("write", False)),
                        now=body.get("now"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_reflect(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Synthesize higher-level beliefs from fact clusters (generative) with an AIGG model —
    the synthesis layer above Dream. Body: { corpus?, aigg_url, aigg_key?, model?, backend?,
    threshold?, max_clusters?, kinds?, write? }. Writes kind=belief, status candidate."""
    backend = body.get("backend", "http")
    if backend != "claude-cli" and not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGReflector
    reflector = AIGGReflector(body.get("aigg_url") or "", api_key=body.get("aigg_key"),
                              model=body.get("model", "gpt-4o-mini"),
                              extra_headers=body.get("extra_headers"), backend=backend)
    try:
        out = reflect(root, body.get("corpus", _DEFAULT_CORPUS), reflector,
                      write=bool(body.get("write", False)), threshold=float(body.get("threshold", 0.6)),
                      max_clusters=int(body.get("max_clusters", 8)), kinds=body.get("kinds"))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_detect_contradictions(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Find + resolve contradicting units with an external AIGG model (similarity
    pre-filters candidates). Body: { corpus?, aigg_url, aigg_key?, model?, threshold?, write? }"""
    if not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGContradictionDetector
    detector = AIGGContradictionDetector(body["aigg_url"], api_key=body.get("aigg_key"),
                                         model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    try:
        out = detect_contradictions(root, body.get("corpus", _DEFAULT_CORPUS), detector,
                                    threshold=float(body.get("threshold", 0.6)), write=bool(body.get("write", False)))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_infer_deps(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Build the dependency graph with an external AIGG model (directed edges that
    embeddings can't infer). Body: { corpus?, aigg_url, aigg_key?, model?, extra_headers?, write? }"""
    if not body.get("aigg_url"):
        return _err("AM_MEM_400", "aigg_url is required")
    from aigg_memory.extract import AIGGDependencyInferrer
    inferrer = AIGGDependencyInferrer(body["aigg_url"], api_key=body.get("aigg_key"),
                                      model=body.get("model", "gpt-4o-mini"), extra_headers=body.get("extra_headers"))
    try:
        out = infer_dependencies(root, body.get("corpus", _DEFAULT_CORPUS), inferrer, write=bool(body.get("write", False)))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok(out)


def _h_compact(body: dict, root: Path) -> Tuple[int, Envelope]:
    """Offline compaction: merge near-duplicate units (defrag / remove redundancy).
    Body: { corpus?, threshold?, write? }"""
    try:
        result = compact_corpus(root, corpus=body.get("corpus", _DEFAULT_CORPUS),
                                threshold=float(body.get("threshold", 0.85)), write=bool(body.get("write", False)))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)
    return _ok({"merged": result.merged, "written": result.written, "removed": result.removed})


def _h_units(body: dict, root: Path) -> Tuple[int, Envelope]:
    corpus = body.get("corpus", _DEFAULT_CORPUS)
    workspace = load_corpus(root, corpus)
    return _ok({"corpus": corpus, "units": _unit_summaries(workspace),
                "total": sum(1 for p in workspace if p.endswith(_UNIT_SUFFIX))})


_ROUTES = {
    ("GET", "/healthz"): _h_healthz,
    ("POST", "/memory/observe"): _h_observe,
    ("POST", "/memory/consolidate"): _h_consolidate,
    ("POST", "/memory/dream"): _h_dream,
    ("POST", "/memory/ingest"): _h_ingest,
    ("POST", "/memory/infer-deps"): _h_infer_deps,
    ("POST", "/memory/infer-temporal"): _h_infer_temporal,
    ("POST", "/memory/timeline"): _h_timeline,
    ("POST", "/memory/detect-contradictions"): _h_detect_contradictions,
    ("POST", "/memory/reconcile"): _h_reconcile,
    ("POST", "/memory/reflect"): _h_reflect,
    ("POST", "/memory/curate"): _h_curate,
    ("POST", "/memory/consolidation-status"): _h_consolidation_status,
    ("POST", "/memory/compact"): _h_compact,
    ("POST", "/memory/select"): _h_select,
    ("POST", "/memory/units"): _h_units,
}


def _authorized(auth_header: str, token: Optional[str]) -> bool:
    """No token configured == open (by design, for localhost). Otherwise require a
    matching bearer, compared in constant time to avoid a timing side channel."""
    if not token:
        return True
    return hmac.compare_digest(auth_header or "", f"Bearer {token}")


def dispatch(method: str, path: str, body: Optional[dict], root: Union[Path, str]) -> Tuple[int, Envelope]:
    """Pure request dispatch — the unit-tested core."""
    handler = _ROUTES.get((method, path))
    if handler is None:
        return _err("AM_MEM_404", f"no route: {method} {path}", status=404)
    body = body or {}
    # the corpus is the one untrusted path component a request controls — validate
    # it before any handler turns it into a filesystem path (reject `..` / absolute).
    if "corpus" in body:
        try:
            validate_corpus(body["corpus"])
        except ValueError as exc:
            return _err("AM_MEM_400", str(exc))
    try:
        return handler(body, Path(root))
    except Exception as exc:
        return _err("AM_MEM_500", f"{type(exc).__name__}: {exc}", status=500)


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>aigg-memory</title>
<style>
  :root { color-scheme: light dark; --b:#3b82f6; --mut:#888; --bd:#8884; }
  * { box-sizing: border-box; }
  body { font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 1.5rem; max-width: 1000px; margin-inline: auto; }
  h1 { font-size: 1.3rem; margin: 0 0 1rem; }
  h1 small { color: var(--mut); font-weight: 400; font-size: .8rem; }
  h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: var(--mut); margin: 1.2rem 0 .4rem; }
  .bar { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
  input, button { font: inherit; padding: .5rem .6rem; border: 1px solid var(--bd); border-radius: 6px; background: transparent; color: inherit; }
  #request { flex: 1 1 320px; }
  button { background: var(--b); color: #fff; border: 0; cursor: pointer; }
  .grid { display: grid; grid-template-columns: 1fr 240px; gap: 1.5rem; margin-top: 1rem; }
  @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
  pre { background: #8881; padding: 1rem; border-radius: 8px; overflow: auto; max-height: 60vh; margin: 0; white-space: pre-wrap; word-break: break-word; }
  ul { margin: 0; padding-left: 1.1rem; } li { margin: .15rem 0; }
  .kind { font-size: .8rem; color: var(--mut); display: inline-flex; align-items: center; gap: .2rem; }
  .tok { margin-top: 1.5rem; } .tok input { width: 280px; }
  .err { color: #ef4444; }
</style>
</head>
<body>
  <h1>aigg-memory <small id="health">connecting…</small></h1>
  <div class="bar">
    <input id="request" placeholder="Recall memory for a task — e.g. 游侠 swordsmanship" autofocus>
    <input id="corpus" value="memory" title="corpus directory" style="width:160px">
    <label class="kind"><input type="checkbox" class="mem-kind" value="procedural" checked> proc</label>
    <label class="kind"><input type="checkbox" class="mem-kind" value="semantic" checked> sem</label>
    <label class="kind"><input type="checkbox" class="mem-kind" value="episodic" checked> epi</label>
    <button id="recall">Recall</button>
    <button id="list">List units</button>
  </div>
  <div class="grid">
    <section>
      <h2>Bundle · POST /memory/select</h2>
      <pre id="bundle">Recall memory for a request, or list the corpus.</pre>
    </section>
    <aside><h2>Units</h2><ul id="units"></ul></aside>
  </div>
  <div class="tok"><input id="token" placeholder="bearer token (only if server set --token)"></div>
<script>
const $ = (id) => document.getElementById(id);
const auth = () => { const t = $("token").value.trim(); return t ? { Authorization: "Bearer " + t } : {}; };
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", ...auth() }, body: JSON.stringify(body) });
  return { status: r.status, env: await r.json() };
}
function bullets(id, items) { $(id).innerHTML = items.map((i) => `<li>${i}</li>`).join(""); }
function kinds() { const c = [...document.querySelectorAll(".mem-kind:checked")].map((x) => x.value); return c.length && c.length < 3 ? c : null; }
async function recall() {
  const body = { request: $("request").value, corpus: $("corpus").value };
  const k = kinds(); if (k) body.kinds = k;
  $("bundle").textContent = "…";
  try {
    const { env } = await api("/memory/select", body); const d = env.data || {};
    $("bundle").textContent = d.bundle || "(no relevant memory)";
    bullets("units", (d.units || []).map((u) => `${u.name} · ${u.kind} · score ${u.score}`));
    $("health").textContent = `· ${d.total_in_corpus || 0} in corpus`;
  } catch (e) { $("bundle").innerHTML = '<span class="err">recall failed: ' + e + "</span>"; }
}
async function list() {
  try {
    const { env } = await api("/memory/units", { corpus: $("corpus").value }); const d = env.data || {};
    bullets("units", (d.units || []).map((u) => `${u.name} · ${u.kind} · ${u.status}`));
    $("bundle").textContent = `${d.total || 0} unit(s) in "${d.corpus}".`;
    $("health").textContent = `· ${d.total || 0} units`;
  } catch (e) { $("bundle").innerHTML = '<span class="err">list failed: ' + e + "</span>"; }
}
$("recall").addEventListener("click", recall);
$("list").addEventListener("click", list);
$("request").addEventListener("keydown", (e) => { if (e.key === "Enter") recall(); });
fetch("/healthz").then((r) => r.json()).then((j) => { $("health").textContent = "· " + (j.data ? j.data.root : ""); }).catch(() => { $("health").innerHTML = '<span class="err">· offline</span>'; });
</script>
</body>
</html>
"""

_STATIC_PATHS = {"/", "/ui", "/index.html"}


def render_index() -> str:
    return _INDEX_HTML


def static_response(path: str) -> Optional[Tuple[str, bytes]]:
    if path in _STATIC_PATHS:
        return "text/html; charset=utf-8", _INDEX_HTML.encode("utf-8")
    return None


_MAX_BODY_BYTES = 8 * 1024 * 1024  # reject oversize request bodies (cheap DoS guard)


def run_server(root: Union[Path, str], port: int = 8788, token: Optional[str] = None,
               host: str = "127.0.0.1") -> None:
    """Start the JSON memory server. Thin shell over dispatch(). Binds localhost by
    default — pass host="0.0.0.0" to expose it on a (trusted) network on purpose."""
    root_path = Path(root)

    class _Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, env: Envelope) -> None:
            payload = json.dumps(env, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle(self, method: str) -> None:
            if not _authorized(self.headers.get("Authorization", ""), token):
                self._send(401, _err("AM_MEM_401", "unauthorized", status=401)[1])
                return
            parsed = {}
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY_BYTES:
                self._send(413, _err("AM_MEM_413", "request body too large", status=413)[1])
                return
            if length:
                try:
                    parsed = json.loads(self.rfile.read(length))
                except Exception:
                    self._send(400, _err("AM_MEM_400", "invalid JSON body")[1])
                    return
            status, env = dispatch(method, self.path, parsed, root_path)
            self._send(status, env)

        def do_GET(self) -> None:  # noqa: N802
            static = static_response(self.path)
            if static is not None:
                content_type, payload = static
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, *args: Any) -> None:
            pass

    ThreadingHTTPServer((host, port), _Handler).serve_forever()
