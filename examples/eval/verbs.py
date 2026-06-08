"""Verb library — the reusable host actions (rails) an experiment composes. Three families:

  store-setup (fixtures/seed): write a unit file — the store's source of truth, the
    deterministic way to establish initial conditions (per agent).
  social rails (mud): converse/relay/invite/announce_change — info passing between NPCs,
    each modelled as a provenance-stamped write into the recipient's corpus (in live mode the
    host LLM speaks and the kernel ingests via observe; here it is deterministic).
  cognition-under-test: drive the real kernel over HTTP (the LLM steps hit the scripted stub).

Every verb takes an optional `agent` -> corpus npcs/<agent>/memory (else the default corpus).
A new mechanic = one new verb here, reusable by every later manifest.
"""


def _corpus(ctx, args):
    return ctx.corpus_of(args.get("agent"))


def _write_fact(ctx, corpus, slug, args, kind):
    desc = args.get("description", slug)
    fm = {
        "name": args.get("name", slug),
        "description": desc,
        "kind": kind,
        "match": {"user_intent": args.get("match", [slug])},
        "id": slug,
        "status": args.get("status", "active"),
    }
    for k in ("valid_from", "valid_to", "derived_from", "asserted_by", "source_events",
              "locked", "pinned", "confidence"):
        if k in args:
            fm[k] = args[k]
    ctx.write_unit(corpus, slug, fm, body=args.get("body", desc))


# --- store-setup verbs ----------------------------------------------------

def fact(ctx, args):
    """A semantic fact in an agent's memory."""
    _write_fact(ctx, _corpus(ctx, args), args["slug"], args, kind=args.get("kind", "semantic"))


def goal(ctx, args):
    """A durable goal the agent plans toward (kind=goal)."""
    _write_fact(ctx, _corpus(ctx, args), args["slug"], args, kind="goal")


def unit(ctx, args):
    """A unit of any kind (kind from args)."""
    _write_fact(ctx, _corpus(ctx, args), args["slug"], args, kind=args.get("kind", "semantic"))


# --- social rails (mud) ---------------------------------------------------

def relay(ctx, args):
    """`from` tells `to` a fact: write it into the recipient's corpus, stamped with provenance
    (asserted_by=from, source_events=[source]). The atom of information diffusion."""
    frm, src = args["from"], args.get("source", args["slug"])
    a = dict(args, asserted_by=frm, source_events=[src])
    _write_fact(ctx, ctx.corpus_of(args["to"]), args["slug"], a, kind=args.get("kind", "semantic"))


def invite(ctx, args):
    """`from` invites each of `to` to an event: a provenance-stamped relay into every guest."""
    for guest in args["to"]:
        relay(ctx, dict(args, to=guest))


def announce_change(ctx, args):
    """Broadcast a corrected/updated fact to each of `to` (a new unit, so reconcile supersedes
    the old one and stale-propagation reaches the plans built on it). The perturbation rail."""
    frm = args.get("from")
    for guest in args["to"]:
        a = dict(args, to=guest)
        if frm:
            a.update(asserted_by=frm, source_events=[args.get("source", args["slug"])])
        _write_fact(ctx, ctx.corpus_of(guest), args["slug"], a, kind=args.get("kind", "semantic"))


# --- cognition-under-test verbs (real kernel over HTTP) -------------------

def plan(ctx, args):
    return ctx.http("/memory/plan", {
        "corpus": _corpus(ctx, args), "aigg_url": ctx.model_url, "write": True,
        "now": args.get("now", ctx.now), "horizon": args.get("horizon"),
        "threshold": args.get("threshold", 0.6), "max_plans": args.get("max_plans", 8),
        "goals": args.get("goals"), "kinds": args.get("kinds"),
    })


def reconcile(ctx, args):
    return ctx.http("/memory/reconcile", {
        "corpus": _corpus(ctx, args), "aigg_url": ctx.model_url, "write": True,
        "now": args.get("now", ctx.now), "threshold": args.get("threshold", 0.3),
    })


def reflect(ctx, args):
    return ctx.http("/memory/reflect", {
        "corpus": _corpus(ctx, args), "aigg_url": ctx.model_url, "write": True,
        "threshold": args.get("threshold", 0.3), "max_clusters": args.get("max_clusters", 8),
        "kinds": args.get("kinds"),
    })


VERBS = {
    "fact": fact, "goal": goal, "unit": unit,
    "relay": relay, "invite": invite, "announce_change": announce_change,
    "plan": plan, "reconcile": reconcile, "reflect": reflect,
}
