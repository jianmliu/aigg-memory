"""Probe library — read-only measurements over the git-versioned corpora. Decoupled from the
run loop: a probe is a pure function of the *store state*, sampled after the fact. Adding a
metric = one function here; it never touches execution. Each returns a plain value the manifest
compares against an `expect`.

The starter set is enough for the memory-correctness family; the social-emergence family adds
`diffusion` / `relationship_density` / `active_plan_fraction` (queries over many corpora) the
same way.
"""


def unit_status(ctx, args):
    """A unit's status ('active' | 'candidate' | 'archived'), or None if the unit is absent."""
    fm = ctx.read_unit(args["slug"])
    return None if fm is None else fm.get("status")


def unit_field(ctx, args):
    """One frontmatter field of a unit (e.g. valid_to, valid_from, stale, superseded_by)."""
    fm = ctx.read_unit(args["slug"])
    return None if fm is None else fm.get(args["field"])


def unit_exists(ctx, args):
    """Whether a unit file exists at all."""
    return ctx.read_unit(args["slug"]) is not None


def derived_from(ctx, args):
    """A unit's rationale list (its derived_from edges), sorted; [] if absent/none."""
    fm = ctx.read_unit(args["slug"]) or {}
    return sorted(fm.get("derived_from", []) or [])


PROBES = {
    "unit_status": unit_status,
    "unit_field": unit_field,
    "unit_exists": unit_exists,
    "derived_from": derived_from,
}
