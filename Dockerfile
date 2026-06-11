# aigg-memory serve — the typed agent-memory HTTP API (:8092).
# Tiny: the kernel core has no third-party deps; only PyYAML (SKILL.md
# frontmatter) + the pure-Python HashEmbedder. No numpy/torch (the embedding
# extra is intentionally NOT installed). Reproducible replacement for the old
# agentmf-pinned image, which shipped aigg-memory v0.2.0 and so lacked the
# /memory/remember route the game's SharedWorld uses.
#
#   docker build -t aigg-memory:latest .
#
# Runtime: bind to 0.0.0.0 for the compose network; --token from env.
FROM python:3.11-slim

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

WORKDIR /data
EXPOSE 8092
CMD ["python", "-m", "aigg_memory", "serve", "--root", "/data", "--port", "8092", "--host", "0.0.0.0"]
