# Verification Design: a third trust axis for learned memory

**Status:** design + **prototype landed for the belief case** — `memory.verify_belief()` and
`agent.record_episode(outcome=, predicts=)`, with `tests/test_verification.py` proving E1's two burns
→ confidence 0.75 (and refute→stale, out-of-scope ignored, predicts inferred, neutral ignored). Still
open: the endpoint / Dream-stage wiring, and the procedural/fact signals (see Open decisions). The
evaluative complement to `reflect` (backward synthesis) and `plan` (forward synthesis). Companion to
`reflection_design.md`, `planning_design.md`, and the kernel paper §11. Frames how a *learned* unit accrues trust from whether its prediction pays
off — the axis SkillsBench (arXiv:2602.12670) and OpenSkill (arXiv:2606.06741) show matters most for
self-generated knowledge.

## Why

aigg-memory grounds trust three ways — **provenance** (who/from-what), **repetition** (the
consolidation gate), and **valid-time** (when it holds) — but never *verifies* a unit against an
independent payoff signal. Generation without evaluation does not help: a synthesized belief, fact, or
skill is self-generated knowledge, and the kernel currently substitutes *frequency* (repetition) and
*lineage* (provenance) for *correctness*. Verification is the missing axis. Because a skill is just a
`procedural` unit, this is kind-general; this doc develops the **belief** case (the most concrete, and
the one E1 already has data for), then generalizes.

## Two signals — keep them separate

| | (A) policy / outcome-level | (B) belief / prediction-level |
|---|---|---|
| question | does *using memory* pay off in aggregate? | is *this belief's prediction* correct? |
| E1 | burns 8→2 (vs OFF 8) | per-belief hit/miss tally |
| granularity | aggregate, not attributable to a unit | one unit, accruing |
| computed by | comparing ON vs OFF outcomes | counting in-scope outcome-tagged episodes |

(A) validates the *system*; (B) validates a *unit*. This doc is about (B) — the accruing,
per-unit confidence. **The hits for E1's trap-belief are the burn *episodes* it was derived from**, not
the aggregate burn count (a correction to an earlier conflation in paper §11).

## Data model

**Episodes carry an outcome** (set by the host at record time — the host knows what happened):

```yaml
kind: episodic
match: { user_intent: [pump, trap] }
outcome: loss          # loss | gain | neutral   (the verifiable result of acting)
asserted_by: self      # or a peer id — peer episodes are low-risk tests (see §social)
```

**Beliefs carry a prediction + a verification record:**

```yaml
kind: belief
predicts: loss                      # the valence this belief predicts for its scope
                                    # (inferred from the outcomes of its derived_from episodes)
derived_from: [burn_pump_0, burn_pump_1]
verification:
  hits: 2                           # in-scope episodes whose outcome matches `predicts`
  misses: 0                         # in-scope episodes whose outcome contradicts it
  last_tested: 2026-06-09T20:00     # valid-time of the most recent test
  confidence: 0.75                  # derived, not stored authoritatively (see below)
```

`confidence` is derived by **Laplace-smoothed** hit-rate so a small sample is honest:
`confidence = (hits + 1) / (hits + misses + 2)` → 2/0 = **0.75**, 5/0 ≈ 0.86, 2/2 = 0.5.

## The operation: `verify(belief)` is a deterministic tally (no LLM)

```
scope  = episodes whose match/topic overlaps the belief (and optionally postdate it)
for each scoped episode with an `outcome`:
    outcome == belief.predicts  → hit
    outcome contradicts         → miss            (neutral → ignored)
write verification{hits, misses, last_tested}; derive confidence
if confidence < θ_refute:                          # the belief is being refuted
    mark belief stale / needs_review               # → triggers re-reflect (existing machinery)
```

Belief-verification is a **count over outcome-tagged episodes**, not a model call — it fits the kernel's
"deterministic where possible" ethos, and refutation reuses the existing stale-propagation path
(`mark_stale_dependents`) and the `needs_review` holding pen. It is kind-general: only the *signal*
changes (a `procedural` skill verifies by task/replay success, a `semantic` fact by independent
corroboration), the tally-and-gate shape is the same.

## E1 worked example (the data already fits)

- The trap-belief is `derived_from [burn_pump_0, burn_pump_1]`, both `outcome=loss`, matching
  `predicts=loss` → **hits=2, misses=0, confidence=0.75**.
- The genuine opportunity `real` is engaged 8/8 with `outcome=gain`, but `real` is **out of the
  belief's scope** (topic "pump"), so it is **not a test and not a miss** — selectivity is preserved
  by scoping, exactly as discernment already requires.
- A prospective **probe** round (re-engage pump): still a trap → `hits=3`, confidence ↑; pump turned
  legitimate → `miss=1`, confidence ↓ → eventually `stale` → re-reflect. This is how a belief *expires*
  when the world changes, on the verification axis rather than only valid-time.

## Relevance vs. correctness (it sharpens §6)

Two different questions the decision layer must not conflate:

- `believes(X, mode="provenance")` → **is this belief *about* X?** (relevance; §6)
- `verification.confidence` → **is this belief *right* about X?** (correctness; here)

A complete decision is `believes(X, provenance) AND confidence ≥ θ`. Today discernment treats any
matching belief as true; feeding `confidence` in lets a host **weight by it** and require a higher θ for
high-stakes actions — *graded trust* expressed as a number, and the concrete form of "skill is the
highest-trust tier" from `skill_memory_relationship.md`.

## Honest limits

1. **Needs outcome labels.** The host must tag episode outcomes; in domains without clean outcomes,
   (B) is unavailable and trust falls back to provenance + repetition.
2. **Exploit-without-test freezes confidence.** A belief always acted on (always avoid pump) generates
   no new tests, so its confidence is only as fresh as its last test → couple verification with
   valid-time (stale if untested for too long). *When* to re-test is the host's exploration policy, not
   the kernel's (consistent with "the kernel ships no clock and takes no action").
3. **Tests come from exploration or peers.** You only get a test when *something* engages. So hits
   accrue from the agent's own exploration or from **peer episodes** — another agent's `outcome=loss`
   on pump (a `peer`-asserted episode) verifies my belief **without my risk**. Verification therefore
   ties naturally into the social / diffusion layer (E5): observational learning *is* low-cost
   verification.

## Open decisions

- **Scope test.** in-scope = shares match terms? same `derived_from` cluster? embedder similarity ≥ τ?
  (Start with match-term overlap — deterministic, no embedder.)
- **`predicts` inference.** majority outcome of the `derived_from` episodes, or an explicit field the
  reflector emits? (Prefer inference, with an override.)
- **Window.** all-time tally vs. recency-weighted vs. only-postdating-the-belief? (Recency-weighting
  lets a belief recover/decay; start all-time + `last_tested`.)
- **Where it runs.** a standalone `verify` op, or folded into the Dream pass after `reflect`? (Likely a
  Dream stage: reflect → verify → (stale if refuted).)
- **Surfacing.** does `discernment` return `confidence`, and is θ a host parameter or a kernel default?

## Relationship to the other operations

- `reflect` / `plan` **generate**; `verify` **evaluates** — generation needs evaluation (SkillsBench).
- A refuted belief reuses `mark_stale_dependents` → `needs_review` → re-`reflect` (no new revision
  machinery).
- `reconcile` resolves *conflicts between statements*; `verify` scores a *single statement against
  outcomes* — complementary, not overlapping.
- Promotion of a learned unit to high-trust `procedural`/skill status is gated on `confidence`
  (`skill_memory_relationship.md`): one trust axis, two faces.

## See also

`reflection_design.md` · `planning_design.md` · kernel paper `paper_memory_kernel.md` §6/§11 ·
AgentMakefile `docs/skill_memory_relationship.md` (the skill-promotion face of this axis).
