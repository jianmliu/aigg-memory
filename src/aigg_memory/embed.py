"""Pluggable embedders for semantic recall.

The default `HashEmbedder` is deterministic and **zero-dependency** (pure Python):
feature hashing over word tokens + character bigrams. It catches lexical /
morphological / CJK overlap that exact-substring keyword matching misses — but it
is NOT true semantics. For real semantic embeddings install the optional extra
(`pip install aigg-memory[embedding]`) and pass a model name.

Vectors are stored in the index's `vectors` table (BLOB, float32) keyed by
`(slug, model)`, so changing the embedder model just re-embeds.
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
from typing import List

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _features(text: str) -> List[str]:
    text = text.lower()
    feats = _TOKEN.findall(text)
    compact = re.sub(r"\s+", "", text)
    feats.extend(compact[i:i + 2] for i in range(len(compact) - 1))  # char bigrams (CJK + fuzzy)
    return feats


def _hash(feature: str) -> int:
    return int.from_bytes(hashlib.md5(feature.encode("utf-8")).digest()[:8], "big")


class HashEmbedder:
    """Deterministic feature-hashing embedder (no third-party deps)."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feature in _features(text):
                h = _hash(feature)
                vec[h % self.dim] += 1.0 if (h >> 20) & 1 == 0 else -1.0  # signed hashing
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


class _SentenceTransformerEmbedder:
    """Real semantic embeddings — needs the `embedding` extra."""

    def __init__(self, model: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model)
        self.name = f"st-{model}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [[float(x) for x in v] for v in vectors]


def get_embedder(name: str = "hash", dim: int = 256):
    """`hash` (default, zero-dep) or a sentence-transformers model name (opt-in extra)."""
    if name in (None, "hash") or str(name).startswith("hash-"):
        return HashEmbedder(dim=dim)
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            f"semantic embedder {name!r} needs the optional dependency: "
            "pip install aigg-memory[embedding]") from exc
    return _SentenceTransformerEmbedder(name)


def pack_vector(vec: List[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> List[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def cosine(a: List[float], b: List[float]) -> float:
    """Dot product — assumes both vectors are L2-normalized."""
    return sum(x * y for x, y in zip(a, b))
