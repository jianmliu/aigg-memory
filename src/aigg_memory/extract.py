"""Encoding: extract structured observations from raw chat transcripts.

This is the front of the memory cycle — where memory comes from. The core stays
**model-free**: `HeuristicExtractor` is a deterministic, zero-dependency baseline;
`AIGGExtractor` routes the real extraction through an external AIGG inference
service (OpenAI-compatible) using only stdlib `urllib` — no new dependency. The
app supplies AIGG's auth + per-task token-budget headers, so extraction is a
cost-controlled inference call.

Output observations feed the existing `observe → consolidate` pipeline.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Union

Transcript = Union[str, List[Dict[str, Any]]]
Observation = Dict[str, Any]

_EXTRACTION_SYSTEM = (
    "You extract durable memories from a conversation transcript. Capture only valuable "
    "information THE USER provided about themselves — their facts, preferences, decisions, "
    "goals, and context. Do NOT extract the assistant's own statements, explanations, or "
    "output; the memory is about the user, not what the assistant said. Return ONLY a JSON "
    "array; each item is {slug, name, kind, description, match, body, apply}. "
    "kind is one of procedural|semantic|episodic. slug is a stable, readable snake_case "
    "id for the fact (e.g. prefers_dark_mode), NOT a hash. match is a few short trigger "
    "phrases. apply is one sentence of actionable guidance — HOW the assistant should "
    "use this fact in future turns (e.g. 'default to dark mode when a UI choice is open'). "
    "Keep only durable, reusable "
    "facts / preferences / decisions — skip chit-chat. Return [] if nothing is worth keeping."
)

_STOP = {"the", "a", "an", "is", "are", "that", "remember", "note", "i", "my", "we", "to", "of", "and", "记住"}


def _as_text(transcript: Transcript) -> str:
    if isinstance(transcript, str):
        return transcript
    return "\n".join(f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in transcript)


def _keywords(sentence: str) -> List[str]:
    words = re.findall(r"\w+", sentence.lower())
    return [w for w in dict.fromkeys(words) if w not in _STOP and len(w) > 2][:5]


def _normalize_observation(item: Dict[str, Any]) -> Optional[Observation]:
    slug = item.get("slug")
    if not slug:
        return None
    description = item.get("description", "")
    obs = {
        "slug": str(slug), "name": item.get("name", slug), "kind": item.get("kind", "semantic"),
        "description": description, "match": item.get("match", []) or [], "body": item.get("body", description),
    }
    if item.get("apply"):  # actionable guidance — how to use this fact
        obs["apply"] = str(item["apply"])
    return obs


def _loads_json(content: str):
    """Parse the first JSON value in a model reply, tolerant of small-model output (e.g. Ollama):
    a ```json fenced block ANYWHERE (not only wrapping the whole reply), surrounding prose, and
    trailing text after the value. Returns the parsed value, or None (callers degrade safely). A
    bare JSON reply — what cloud models emit — parses identically, so the strict path is unchanged."""
    s = (content or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.DOTALL)   # a fenced code block, anywhere
    if m:
        s = m.group(1).strip()
    i = next((k for k, ch in enumerate(s) if ch in "[{"), -1)     # the first array/object
    if i < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(s, i)           # parse it; ignore trailing prose
        return obj
    except Exception:
        return None


def parse_observations(content: str) -> List[Observation]:
    """Parse an LLM response (a JSON array, possibly fenced + wrapped in prose) into observations."""
    data = _loads_json(content)
    if isinstance(data, dict):
        data = data.get("memories") or data.get("observations") or [data]
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict):
            obs = _normalize_observation(item)
            if obs:
                out.append(obs)
    return out


class HeuristicExtractor:
    """Deterministic, zero-dependency baseline: pull sentences with memory cues.
    Crude — real extraction wants a model (use AIGGExtractor)."""

    name = "heuristic"
    _CUE = re.compile(r"(?:remember(?: that)?|note that|i prefer|prefers?|my .+ is|we decided|记住|偏好)", re.I)

    def extract(self, transcript: Transcript) -> List[Observation]:
        from aigg_memory._util import fingerprint

        out: List[Observation] = []
        for sentence in re.split(r"(?<=[.!?。！？\n])\s+", _as_text(transcript)):
            sentence = sentence.strip()
            # drop a leading "role:" prefix from transcript turns
            sentence = re.sub(r"^\w+:\s*", "", sentence)
            if len(sentence) < 4 or not self._CUE.search(sentence):
                continue
            terms = _keywords(sentence)
            # a readable slug derived from the content (prefer_dark_mode), so units stay
            # hand-editable / navigable; fall back to a hash only when no keywords survive.
            slug = "_".join(terms[:4]) or ("fact_" + fingerprint(sentence.lower())[:10])
            out.append({
                "slug": slug, "name": sentence[:60], "kind": "semantic",
                "description": sentence, "match": terms, "body": sentence,
            })
        return out


class _AIGGClient:
    """Shared OpenAI-compatible chat call to an external AIGG service (stdlib
    urllib). `extra_headers` carries the app's AIGG auth + per-task token-budget
    headers, which AIGG enforces server-side. `transport(user_text) -> content`
    is injectable for testing."""

    def __init__(self, base_url: str, system: str, api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini", extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.system = system
        self.api_key = api_key
        self.model = model
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout
        if transport is not None:
            self._transport = transport
        elif backend == "claude-cli":
            self._transport = self._claude_cli
        else:
            self._transport = self._http

    def complete(self, user_text: str) -> str:
        return self._transport(user_text)

    def _claude_cli(self, text: str) -> str:
        """Backend that shells out to `claude -p` (headless) instead of HTTP — reuses the
        user's Claude Code login (subscription, no API key). The extraction prompt is set with
        `--system-prompt` (an OVERRIDE, not `--append-...`) + `--exclude-dynamic-system-prompt-
        sections`, so `claude -p` behaves as a clean structured extractor rather than its default
        agentic persona — which otherwise replies conversationally and ignores "return only JSON".
        The user text rides on stdin; the answer comes back on stdout (the parse_* helpers tolerate
        fenced JSON). Config via env:
          AIGG_MEMORY_CLAUDE_CMD   the CLI (default "claude")
          AIGG_MEMORY_CLAUDE_ARGS  extra args (e.g. "--allowedTools Read")
          AIGG_MEMORY_CLAUDE_TIMEOUT  seconds (default 180 — process start + inference)."""
        cmd = shlex.split(os.environ.get("AIGG_MEMORY_CLAUDE_CMD", "claude"))
        args = [*cmd, "-p", "--system-prompt", self.system, "--exclude-dynamic-system-prompt-sections"]
        if self.model and not self.model.startswith("gpt-"):  # gpt-* default == "unset" for claude
            args += ["--model", self.model]
        extra = os.environ.get("AIGG_MEMORY_CLAUDE_ARGS")
        if extra:
            args += shlex.split(extra)
        timeout = float(os.environ.get("AIGG_MEMORY_CLAUDE_TIMEOUT", "180"))
        result = subprocess.run(args, input=text, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"claude -p failed (rc={result.returncode}): {result.stderr.strip()[:300]}")
        return result.stdout

    def _http(self, text: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": text},
            ],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read())
        return data["choices"][0]["message"]["content"]


class AIGGExtractor:
    """Extract observations from a transcript via an external AIGG service."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg:{model}"
        self._client = _AIGGClient(base_url, _EXTRACTION_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def extract(self, transcript: Transcript) -> List[Observation]:
        return parse_observations(self._client.complete(_as_text(transcript)))


_DEP_SYSTEM = (
    "You are given memory units, one per line as 'id: description'. Identify DIRECTED "
    "dependency edges between them. Return ONLY a JSON array of {from, to, rel}; rel is "
    "one of depends_on|references|supersedes. Use ONLY the given ids — never invent one. "
    "'from depends_on to' means 'from' needs the concept in 'to' to be understood; "
    "'from supersedes to' means 'from' replaces 'to'. Return [] if there are none."
)


def parse_edges(content: str) -> List[Dict[str, str]]:
    """Parse an LLM response into directed dependency edges {from, to, rel}."""
    data = _loads_json(content)
    out = []
    for item in data if isinstance(data, list) else []:
        if (isinstance(item, dict) and item.get("from") and item.get("to")
                and item.get("rel") in ("depends_on", "references", "supersedes", "precedes")):
            out.append({"from": str(item["from"]), "to": str(item["to"]), "rel": item["rel"]})
    return out


_CONTRADICTION_SYSTEM = (
    "You are given memory units, one per line as 'id: description'. Identify PAIRS "
    "that CONTRADICT — assert incompatible facts about the same thing. Return ONLY a "
    "JSON array of {a, b, winner, reason}; a and b are ids that contradict, winner is "
    "the id to keep (more correct / specific / recent), the other is superseded. Use "
    "ONLY the given ids. Similarity is NOT contradiction — flag only genuine "
    "incompatibility. If two units genuinely contradict but you CANNOT confidently "
    "tell which is correct, still report the pair but set winner to \"uncertain\" — "
    "do NOT guess; an uncertain pair is escalated to a human. Return [] if none."
)


def parse_contradictions(content: str) -> List[Dict[str, str]]:
    data = _loads_json(content)
    out = []
    for item in data if isinstance(data, list) else []:
        # a pair needs both ids; the winner is OPTIONAL — a model that can't decide
        # says so (winner: "uncertain" or omitted) and the pair defers to a human.
        if isinstance(item, dict) and item.get("a") and item.get("b"):
            out.append({"a": str(item["a"]), "b": str(item["b"]),
                        "winner": str(item.get("winner") or "uncertain"),
                        "reason": str(item.get("reason", ""))})
    return out


class AIGGContradictionDetector:
    """Ask an external AIGG model which candidate units genuinely CONTRADICT — the
    judgment embeddings can't make. The caller pre-filters to same-topic candidates
    (cheap) and validates the output against real slugs."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-contra:{model}"
        self._client = _AIGGClient(base_url, _CONTRADICTION_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def detect(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_contradictions(self._client.complete(listing))


_TEMPORAL_SYSTEM = (
    "You are given memory units, one per line as 'id: description'. Identify DIRECTED "
    "temporal-ordering edges: which event/fact happened BEFORE which. Return ONLY a "
    "JSON array of {from, to, rel} with rel always \"precedes\" — 'from precedes to' "
    "means 'from' happened before 'to'. Use ONLY the given ids — never invent one. "
    "Order by real-world time, NOT by topic similarity. Return [] if there is no clear "
    "ordering."
)


class AIGGTemporalInferrer:
    """Ask an external AIGG model for DIRECTED temporal-ordering edges (`precedes`) —
    'A happened before B'. World-time ordering is content semantics, not commit
    metadata, so (like dependency edges) it needs a model. Reuses the same edge
    machinery as AIGGDependencyInferrer; the caller validates against real slugs."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-temporal:{model}"
        self._client = _AIGGClient(base_url, _TEMPORAL_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def infer(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_edges(self._client.complete(listing))


_RECONCILE_SYSTEM = (
    "You are given two memory units about a user, as 'id: description'. Decide how the "
    "SECOND relates to the FIRST and which is true NOW. Return ONLY a JSON object "
    "{relation, current, reason}. relation is one of: "
    "\"none\" (they don't conflict — both can be true), "
    "\"correction\" (one says the other was WRONG / a mistake), "
    "\"temporal\" (one was true BEFORE and the other is true NOW — the fact changed over time), "
    "\"uncertain\" (they conflict but you can't tell which is current, or correction vs change). "
    "current is the id that holds NOW (for correction/temporal); omit or empty if none/uncertain. "
    "Use ONLY the two given ids. Do NOT guess — prefer \"uncertain\" when unsure."
)

_RECONCILE_RELATIONS = ("none", "correction", "temporal", "uncertain")


def parse_reconciliation(content: str) -> Dict[str, str]:
    """Parse the judge's verdict into {relation, current, reason}; an unknown or
    missing relation degrades to 'uncertain' (defer, don't guess)."""
    data = _loads_json(content)
    if not isinstance(data, dict):
        data = {}
    relation = data.get("relation")
    if relation not in _RECONCILE_RELATIONS:
        relation = "uncertain"
    return {"relation": relation, "current": str(data.get("current") or ""),
            "reason": str(data.get("reason", ""))}


class AIGGReconciler:
    """Judge how a candidate pair of user-facts relates — none / correction / temporal
    / uncertain — and which holds now. The directed, semantic call embeddings can't
    make (similarity only narrows the candidates). The caller validates `current`
    against the real pair and routes; uncertain defers to a human."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-reconcile:{model}"
        self._client = _AIGGClient(base_url, _RECONCILE_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def judge(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, str]:
        listing = f"{a['slug']}: {a.get('description', '')}\n{b['slug']}: {b.get('description', '')}"
        return parse_reconciliation(self._client.complete(listing))


_CURATION_SYSTEM = (
    "You are given memory units about a user, one per line as 'id: description'. The value "
    "of a unit is whether it preserves something VALUABLE THE USER provided — a durable "
    "fact, preference, decision, goal, or context about them. For each, return a verdict: "
    "\"keep\" if it captures such valuable user-provided information; \"trivial\" if it is "
    "ephemeral small-talk / a passing mood / not worth keeping, OR if it merely records the "
    "assistant's own output rather than information the user contributed; \"uncertain\" if "
    "unsure. Return ONLY a JSON array of {id, verdict, reason}. Mark \"trivial\" ONLY when "
    "clearly not worth keeping — when in any doubt return \"keep\" or \"uncertain\". NEVER "
    "delete valuable user information. Use ONLY the given ids."
)

_CURATION_VERDICTS = ("keep", "trivial", "uncertain")


def parse_curation(content: str) -> List[Dict[str, str]]:
    """Parse the curator's verdicts into [{slug, verdict, reason}]. An unknown or missing
    verdict degrades to 'keep' — a parse ambiguity must never cause a deletion."""
    data = _loads_json(content)
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        slug = item.get("id") or item.get("slug")
        if not slug:
            continue
        verdict = item.get("verdict")
        if verdict not in _CURATION_VERDICTS:
            verdict = "keep"
        out.append({"slug": str(slug), "verdict": verdict, "reason": str(item.get("reason", ""))})
    return out


class AIGGCurator:
    """Ask an external AIGG model whether each UNIQUE unit is durable/useful or transient
    chatter — the value judgment statistics can't make (recency/similarity measure access
    or structure, not worth). The caller cheaply pre-filters candidates and only archives
    high-confidence 'trivial', non-destructively; uncertain/keep are left alone."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-curate:{model}"
        self._client = _AIGGClient(base_url, _CURATION_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def judge(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_curation(self._client.complete(listing))


_REFLECTION_SYSTEM = (
    "You are given memory units about a user/world, one per line as 'id: description'. "
    "Synthesize higher-level BELIEFS — interpretations that follow from combining several "
    "units but are stated in NO single one (patterns, characterizations, inferred goals or "
    "intent). Return ONLY a JSON array of {slug, name, description, body, apply, derived_from}. "
    "slug is a stable readable snake_case id for the belief; derived_from is the list of the "
    "GIVEN ids the belief is synthesized from (cite ONLY given ids, at least one — never invent "
    "an id). apply is one line on how to act on the belief. These are INTERPRETATIONS, not "
    "recorded facts — assert only what the evidence supports. Return [] if nothing meaningful "
    "can be synthesized."
)


def parse_reflections(content: str) -> List[Dict[str, Any]]:
    """Parse the reflector's output into belief dicts. Tolerant of fenced JSON; an item
    is DROPPED unless it has both a `slug` and a non-empty `derived_from` list — a belief
    with no cited sources is not a reflection (no inventing evidence)."""
    data = _loads_json(content)
    out: List[Dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug") or item.get("id")
        df = item.get("derived_from")
        if not slug or not isinstance(df, list) or not df:
            continue
        out.append({
            "slug": str(slug),
            "name": str(item.get("name") or slug),
            "description": str(item.get("description", "")),
            "body": str(item.get("body", "")),
            "apply": str(item.get("apply", "")),
            "derived_from": [str(x) for x in df],
            "confidence": str(item.get("confidence") or "medium"),
        })
    return out


class AIGGReflector:
    """The GENERATIVE pass: read a cluster of units and synthesize higher-level beliefs
    (interpretations) with `derived_from` provenance. Unlike reconcile/curate (which JUDGE
    existing units), the reflector PRODUCES new units. The caller validates every
    `derived_from` slug against the real corpus (no hallucinated evidence) and writes the
    beliefs as `kind=belief`, status `candidate` — never ground truth."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-reflect:{model}"
        self._client = _AIGGClient(base_url, _REFLECTION_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def reflect(self, units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_reflections(self._client.complete(listing))


_PLANNING_SYSTEM = (
    "You are given an agent's GOALS and relevant beliefs/facts about itself and its world, "
    "one per line as 'id: description', plus a 'now:' line (and maybe a 'horizon:'). Propose "
    "forward-looking PLANS — concrete intentions for what the agent should do next to advance "
    "its goals, that follow from the given units but are stated in none of them. Return ONLY a "
    "JSON array of {slug, name, description, body, apply, valid_from, derived_from}. slug is a "
    "stable readable snake_case id; derived_from is the list of GIVEN ids the plan rests on "
    "(its rationale — goals + beliefs; cite ONLY given ids, at least one, never invent one); "
    "valid_from is an ISO date/time AT OR AFTER 'now' when the plan begins. apply is one line on "
    "how to act on the plan. These are revisable INTENTIONS — not facts, and not yet actions. "
    "Return [] if nothing meaningful can be planned."
)


def parse_plans(content: str) -> List[Dict[str, Any]]:
    """Parse the planner's output into plan dicts. Tolerant of fenced JSON; an item is
    DROPPED unless it has both a `slug` and a non-empty `derived_from` list — a plan with no
    rationale is not a plan (no inventing justification). `valid_from` is carried as given
    (may be empty); the caller enforces it is at/after `now`."""
    data = _loads_json(content)
    out: List[Dict[str, Any]] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug") or item.get("id")
        df = item.get("derived_from")
        if not slug or not isinstance(df, list) or not df:
            continue
        out.append({
            "slug": str(slug),
            "name": str(item.get("name") or slug),
            "description": str(item.get("description", "")),
            "body": str(item.get("body", "")),
            "apply": str(item.get("apply", "")),
            "valid_from": str(item.get("valid_from") or ""),
            "derived_from": [str(x) for x in df],
            "confidence": str(item.get("confidence") or "medium"),
        })
    return out


class AIGGPlanner:
    """The forward GENERATIVE pass: read an agent's goals + beliefs and synthesize forward
    INTENTIONS (`kind=plan`) with `derived_from` rationale and a future `valid_from`. The
    mirror of `AIGGReflector` (backward → beliefs); here backward+present → forward. The
    caller validates every `derived_from` slug against the real corpus (no hallucinated
    rationale) and clamps `valid_from` to `now`; plans are written `candidate`, never acted on
    by the kernel."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-plan:{model}"
        self._client = _AIGGClient(base_url, _PLANNING_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def plan(self, units: List[Dict[str, Any]], *, now: str, horizon: Optional[str] = None) -> List[Dict[str, Any]]:
        header = f"now: {now}\n"
        if horizon:
            header += f"horizon: {horizon}\n"
        listing = header + "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_plans(self._client.complete(listing))


class AIGGDependencyInferrer:
    """Ask an external AIGG model for the DIRECTED dependency edges between units —
    the relations embeddings can't infer. The caller validates the edges against
    real slugs before writing them (no hallucinated nodes)."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0,
                 backend: str = "http") -> None:
        self.name = f"aigg-deps:{model}"
        self._client = _AIGGClient(base_url, _DEP_SYSTEM, api_key, model, extra_headers,
                                   transport, timeout, backend)
        self.extra_headers = self._client.extra_headers

    def infer(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_edges(self._client.complete(listing))


def ingest_transcript(transcript: Transcript, extractor, evidence_path,
                      source: str = "observation", asserted_by: Optional[str] = None,
                      origin_session: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract memories from a transcript and record each as evidence — closing the
    encoding loop (raw chat → extract → observe). The usual consolidate/Dream pass
    then promotes repeated observations into typed units. `asserted_by` stamps every
    extracted observation with who asserted it (the session's principal / EOA) — the
    whole transcript is one speaker — so authority/provenance flows to the units."""
    from aigg_memory.memory import memory_domain
    from aigg_memory.store import EvidenceStore

    store = EvidenceStore(evidence_path, domain=memory_domain())
    out = []
    for obs in extractor.extract(transcript):
        stamp = {}
        if asserted_by is not None:
            stamp["asserted_by"] = asserted_by
        if origin_session is not None:
            stamp["origin_session"] = origin_session   # which conversation produced this
        if stamp:
            obs = {**obs, **stamp}
        out.append(store.record(source, obs).to_dict())
    return out
