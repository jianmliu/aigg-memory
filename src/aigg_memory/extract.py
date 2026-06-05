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
import re
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Union

Transcript = Union[str, List[Dict[str, Any]]]
Observation = Dict[str, Any]

_EXTRACTION_SYSTEM = (
    "You extract durable memories from a conversation transcript. Return ONLY a JSON "
    "array; each item is {slug, name, kind, description, match, body}. "
    "kind is one of procedural|semantic|episodic. slug is a stable snake_case id for "
    "the fact. match is a few short trigger phrases. Keep only durable, reusable "
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
    return {
        "slug": str(slug), "name": item.get("name", slug), "kind": item.get("kind", "semantic"),
        "description": description, "match": item.get("match", []) or [], "body": item.get("body", description),
    }


def parse_observations(content: str) -> List[Observation]:
    """Parse an LLM response (a JSON array, possibly fenced) into observations."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()).strip()
    try:
        data = json.loads(text)
    except Exception:
        return []
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
            out.append({
                "slug": "fact_" + fingerprint(sentence.lower())[:10],
                "name": sentence[:60], "kind": "semantic",
                "description": sentence, "match": _keywords(sentence), "body": sentence,
            })
        return out


class _AIGGClient:
    """Shared OpenAI-compatible chat call to an external AIGG service (stdlib
    urllib). `extra_headers` carries the app's AIGG auth + per-task token-budget
    headers, which AIGG enforces server-side. `transport(user_text) -> content`
    is injectable for testing."""

    def __init__(self, base_url: str, system: str, api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini", extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.system = system
        self.api_key = api_key
        self.model = model
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout
        self._transport = transport or self._http

    def complete(self, user_text: str) -> str:
        return self._transport(user_text)

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
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0) -> None:
        self.name = f"aigg:{model}"
        self._client = _AIGGClient(base_url, _EXTRACTION_SYSTEM, api_key, model, extra_headers, transport, timeout)
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
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()).strip()
    try:
        data = json.loads(text)
    except Exception:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if (isinstance(item, dict) and item.get("from") and item.get("to")
                and item.get("rel") in ("depends_on", "references", "supersedes")):
            out.append({"from": str(item["from"]), "to": str(item["to"]), "rel": item["rel"]})
    return out


_CONTRADICTION_SYSTEM = (
    "You are given memory units, one per line as 'id: description'. Identify PAIRS "
    "that CONTRADICT — assert incompatible facts about the same thing. Return ONLY a "
    "JSON array of {a, b, winner, reason}; a and b are ids that contradict, winner is "
    "the id to keep (more correct / specific / recent), the other is superseded. Use "
    "ONLY the given ids. Similarity is NOT contradiction — flag only genuine "
    "incompatibility. Return [] if none."
)


def parse_contradictions(content: str) -> List[Dict[str, str]]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()).strip()
    try:
        data = json.loads(text)
    except Exception:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("a") and item.get("b") and item.get("winner"):
            out.append({"a": str(item["a"]), "b": str(item["b"]),
                        "winner": str(item["winner"]), "reason": str(item.get("reason", ""))})
    return out


class AIGGContradictionDetector:
    """Ask an external AIGG model which candidate units genuinely CONTRADICT — the
    judgment embeddings can't make. The caller pre-filters to same-topic candidates
    (cheap) and validates the output against real slugs."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0) -> None:
        self.name = f"aigg-contra:{model}"
        self._client = _AIGGClient(base_url, _CONTRADICTION_SYSTEM, api_key, model, extra_headers, transport, timeout)
        self.extra_headers = self._client.extra_headers

    def detect(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_contradictions(self._client.complete(listing))


class AIGGDependencyInferrer:
    """Ask an external AIGG model for the DIRECTED dependency edges between units —
    the relations embeddings can't infer. The caller validates the edges against
    real slugs before writing them (no hallucinated nodes)."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0) -> None:
        self.name = f"aigg-deps:{model}"
        self._client = _AIGGClient(base_url, _DEP_SYSTEM, api_key, model, extra_headers, transport, timeout)
        self.extra_headers = self._client.extra_headers

    def infer(self, units: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        listing = "\n".join(f"{u['slug']}: {u.get('description', '')}" for u in units)
        return parse_edges(self._client.complete(listing))


def ingest_transcript(transcript: Transcript, extractor, evidence_path,
                      source: str = "observation") -> List[Dict[str, Any]]:
    """Extract memories from a transcript and record each as evidence — closing the
    encoding loop (raw chat → extract → observe). The usual consolidate/Dream pass
    then promotes repeated observations into typed units."""
    from aigg_memory.memory import memory_domain
    from aigg_memory.store import EvidenceStore

    store = EvidenceStore(evidence_path, domain=memory_domain())
    return [store.record(source, obs).to_dict() for obs in extractor.extract(transcript)]
