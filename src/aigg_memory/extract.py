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


class AIGGExtractor:
    """Extract via an external AIGG inference service (OpenAI-compatible chat
    completions). Zero new dependency (stdlib urllib). `extra_headers` carries the
    app's AIGG auth + per-task token-budget headers, which AIGG enforces server-side."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: str = "gpt-4o-mini",
                 extra_headers: Optional[Dict[str, str]] = None,
                 transport: Optional[Callable[[str], str]] = None, timeout: float = 30.0) -> None:
        self.name = f"aigg:{model}"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout
        self._transport = transport or self._http

    def extract(self, transcript: Transcript) -> List[Observation]:
        return parse_observations(self._transport(_as_text(transcript)))

    def _http(self, text: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": _EXTRACTION_SYSTEM},
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


def ingest_transcript(transcript: Transcript, extractor, evidence_path,
                      source: str = "observation") -> List[Dict[str, Any]]:
    """Extract memories from a transcript and record each as evidence — closing the
    encoding loop (raw chat → extract → observe). The usual consolidate/Dream pass
    then promotes repeated observations into typed units."""
    from aigg_memory.memory import memory_domain
    from aigg_memory.store import EvidenceStore

    store = EvidenceStore(evidence_path, domain=memory_domain())
    return [store.record(source, obs).to_dict() for obs in extractor.extract(transcript)]
