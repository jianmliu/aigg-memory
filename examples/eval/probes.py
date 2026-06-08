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
}
