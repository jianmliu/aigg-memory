"""Verb library — the reusable host actions an experiment composes. Two families:

  store-setup (fixtures/seed): write a unit file directly — the store's source of truth, the
    deterministic way to establish initial conditions.
  cognition-under-test: drive the real kernel over HTTP (the LLM steps hit the scripted stub).

A new interaction = one new verb here, instantly reusable by every later manifest.
"""


def _fact(ctx, args, kind):
    slug = args["slug"]
    desc = args.get("description", slug)
    fm = {
        "name": args.get("name", slug),
        "description": desc,
        "kind": kind,
        "match": {"user_intent": args.get("match", [slug])},
        "id": slug,
        "status": args.get("status", "active"),
    }
    for k in ("valid_from", "valid_to", "derived_from", "asserted_by", "locked", "pinned", "confidence"):
        if k in args:
            fm[k] = args[k]
    ctx.write_unit(slug, fm, body=args.get("body", desc))


# --- store-setup verbs (write the store directly) -------------------------

def fact(ctx, args):
    """A semantic fact about the user/world."""
    _fact(ctx, args, kind=args.get("kind", "semantic"))


def goal(ctx, args):
    """A durable goal the agent plans toward (kind=goal)."""
    _fact(ctx, args, kind="goal")


def unit(ctx, args):
    """A unit of any kind (escape hatch — kind comes from args)."""
    _fact(ctx, args, kind=args.get("kind", "semantic"))


# --- cognition-under-test verbs (real kernel over HTTP) -------------------

def plan(ctx, args):
    """Synthesize forward intentions (kind=plan) from goals+beliefs — the real /memory/plan."""
    return ctx.http("/memory/plan", {
        "corpus": ctx.corpus, "aigg_url": ctx.model_url, "write": True,
        "now": args.get("now", ctx.now), "horizon": args.get("horizon"),
        "threshold": args.get("threshold", 0.6), "max_plans": args.get("max_plans", 8),
        "goals": args.get("goals"), "kinds": args.get("kinds"),
    })


def reconcile(ctx, args):
    """Reconcile a new statement vs memory (correction / temporal change) — /memory/reconcile.
    A resolved temporal/correction archives the old fact and propagates `stale` to dependents."""
    return ctx.http("/memory/reconcile", {
        "corpus": ctx.corpus, "aigg_url": ctx.model_url, "write": True,
        "now": args.get("now", ctx.now), "threshold": args.get("threshold", 0.3),
    })


def reflect(ctx, args):
    """Synthesize beliefs from fact clusters (kind=belief) — the real /memory/reflect."""
    return ctx.http("/memory/reflect", {
        "corpus": ctx.corpus, "aigg_url": ctx.model_url, "write": True,
        "threshold": args.get("threshold", 0.3), "max_clusters": args.get("max_clusters", 8),
        "kinds": args.get("kinds"),
    })


VERBS = {
    "fact": fact,
    "goal": goal,
    "unit": unit,
    "plan": plan,
    "reconcile": reconcile,
    "reflect": reflect,
}
