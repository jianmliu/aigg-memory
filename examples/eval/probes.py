"""Probe library — read-only measurements over the git-versioned corpora. Decoupled from the
run loop: a probe is a pure function of the *store state*, sampled after the fact. Adding a
metric = one function here; it never touches execution.

Single-corpus probes take an optional `agent`; multi-corpus probes (the social-emergence
metrics) iterate every NPC in the sandbox via ctx.agents().
"""


def _corpus(ctx, args):
    return ctx.corpus_of(args.get("agent"))


def _matches(slug, fm, needle):
    """Is `needle` in a unit's slug / description / match terms (case-insensitive)?"""
    n = needle.lower()
    terms = " ".join((fm.get("match", {}) or {}).get("user_intent", []) or [])
    hay = f"{slug} {fm.get('description', '')} {terms}".lower()
    return n in hay


# --- single-corpus probes -------------------------------------------------

def unit_status(ctx, args):
    fm = ctx.read_unit(_corpus(ctx, args), args["slug"])
    return None if fm is None else fm.get("status")


def unit_field(ctx, args):
    fm = ctx.read_unit(_corpus(ctx, args), args["slug"])
    return None if fm is None else fm.get(args["field"])


def unit_exists(ctx, args):
    return ctx.read_unit(_corpus(ctx, args), args["slug"]) is not None


def derived_from(ctx, args):
    fm = ctx.read_unit(_corpus(ctx, args), args["slug"]) or {}
    return sorted(fm.get("derived_from", []) or [])


# --- multi-corpus probes (the social-emergence metrics) -------------------

def knows_count(ctx, args):
    """How many NPCs hold a non-archived unit matching `matcher` — information diffusion."""
    needle = args["matcher"]
    n = 0
    for agent in ctx.agents():
        units = ctx.read_units(ctx.corpus_of(agent))
        if any(fm.get("status") != "archived" and _matches(slug, fm, needle)
               for slug, fm in units.items()):
            n += 1
    return n


def plan_count(ctx, args):
    """How many NPCs hold an active plan matching `matcher` valid by `at` — formed intentions."""
    needle, at = args["matcher"], args.get("at")
    n = 0
    for agent in ctx.agents():
        for slug, fm in ctx.read_units(ctx.corpus_of(agent)).items():
            if fm.get("kind") != "plan" or fm.get("status") == "archived":
                continue
            if not _matches(slug, fm, needle):
                continue
            vf = fm.get("valid_from")
            if at is None or vf is None or vf <= at:
                n += 1
                break
    return n


def stale_plan_count(ctx, args):
    """How many NPCs hold a plan matching `matcher` flagged stale — pending replan after a change."""
    needle = args["matcher"]
    n = 0
    for agent in ctx.agents():
        for slug, fm in ctx.read_units(ctx.corpus_of(agent)).items():
            if fm.get("kind") == "plan" and fm.get("stale") and _matches(slug, fm, needle):
                n += 1
                break
    return n


def diffusion_traceable(ctx, args):
    """Audit (multi-hop): every NPC that knows `matcher` learned it from someone who also knows
    it — i.e. the knowers form a real transmission tree, no spontaneous/hallucinated knowledge.
    `root` is the origin (exempt). True iff every non-root knower's copy is asserted_by another
    knower."""
    needle, root = args["matcher"], args["root"]
    knowers = set()
    tellers = {}  # agent -> set of asserted_by on its matching units
    for agent in ctx.agents():
        srcs = set()
        knows = False
        for slug, fm in ctx.read_units(ctx.corpus_of(agent)).items():
            if fm.get("status") != "archived" and _matches(slug, fm, needle):
                knows = True
                if fm.get("asserted_by"):
                    srcs.add(fm["asserted_by"])
        if knows:
            knowers.add(agent)
            tellers[agent] = srcs
    for agent in knowers:
        if agent == root:
            continue
        if not (tellers[agent] & knowers):   # told by someone who also knows
            return False
    return True


def relationship_edges(ctx, args):
    """Directed acquaintance edges: how many ordered pairs (A,B) where A holds a non-archived
    person_<B> unit. The numerator of the paper's network density."""
    agents = ctx.agents()
    edges = 0
    for a in agents:
        units = ctx.read_units(ctx.corpus_of(a))
        for b in agents:
            if b != a and (units.get(f"person_{b}") or {}).get("status", "active") != "archived" \
                    and f"person_{b}" in units:
                edges += 1
    return edges


def relationship_density(ctx, args):
    """Network density = acquaintance edges / N*(N-1), rounded — the paper's headline metric."""
    agents = ctx.agents()
    n = len(agents)
    if n < 2:
        return 0.0
    return round(relationship_edges(ctx, args) / (n * (n - 1)), 4)


def provenance_ok(ctx, args):
    """Audit: every NPC's copy of a `matcher` unit is stamped asserted_by=`root` (the info was
    relayed, not hallucinated). Returns True if every copy traces to the source."""
    needle, root = args["matcher"], args["root"]
    for agent in ctx.agents():
        if agent == root:
            continue
        for slug, fm in ctx.read_units(ctx.corpus_of(agent)).items():
            if _matches(slug, fm, needle) and fm.get("asserted_by") != root:
                return False
    return True


PROBES = {
    "unit_status": unit_status,
    "unit_field": unit_field,
    "unit_exists": unit_exists,
    "derived_from": derived_from,
    "knows_count": knows_count,
    "plan_count": plan_count,
    "stale_plan_count": stale_plan_count,
    "provenance_ok": provenance_ok,
    "diffusion_traceable": diffusion_traceable,
    "relationship_edges": relationship_edges,
    "relationship_density": relationship_density,
}
