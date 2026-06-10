# aigg-skill Design: a skill-ecosystem manager on the memory kernel

**Status:** design + **V1 landed in the kernel** — `memory.verify_skill()` (invocation-outcome
tally; episodes reference the skill via `source_events`; witness gate blocks review-stuffing;
locked/curated scored-not-written), `record_episode(source_events=)`, and `/memory/verify` now
dispatches by kind (procedural → V1, belief → outcome tally); under `tests/test_verification.py`.
V2 admission, the importer, `route()`/`report()`, and the corpus validation plan remain. Incubate
as a thin layer over aigg-memory (the same path
aigg-memory itself took inside AgentMakefile: incubate, extract when mature). Companion to
`verification_design.md` (the trust axis it consumes), the kernel paper §11, and AgentMakefile's
`docs/skill_memory_relationship.md` (the bridge spec) + `agentmf_openclaw_importer_spec.md` (the
build-time sibling, boundary below).

## Why

Large skill ecosystems (OpenClaw-scale: ~5,127 community skills) have four named pain points —
**routing, deduplication, trust, maintenance** — and these are exactly four operations the memory
kernel already has (`select`+closure, `compact`, provenance+`verify`, stale/`valid_to`/`reconcile`/
`curate`). Since a skill *is* a `kind=procedural` memory unit, skill-ecosystem management is memory
management plus a thin skill-specific layer (~20%): an importer, an invocation loop, a security-tier
policy, and the procedural verification signal.

**A real validation corpus exists**: `/Volumes/T7-Data/skill-corpus` — 248 quality-tiered tier1+2
skills plus the 5,127-entry OpenClaw community manifest (security-gated pilot). Every design claim
below can be tested against it.

## Design constraints pinned by the two reference papers

From **SkillsBench** (Li et al., 2026, arXiv:2602.12670 — 86 tasks / 11 domains / 7,308 trajectories):

- **S1 — import ≠ trust.** Self-generated skills provide *no average benefit*; curated ones add
  +16.2pp. ⇒ Everything entering the pool — imported, synthesized, community — starts
  `status=candidate` and climbs the verification axis; only curation or verification grants
  routability at high trust.
- **S2 — route few, focused skills.** Focused skills (2–3 modules) beat comprehensive documentation.
  ⇒ `route()` returns a *capped dependency closure* (default ≤3 units), never a registry dump; the
  flat "all skills in context" mode is the degraded fallback.
- **S3 — benefit is domain-variable** (+4.5pp SWE … +51.9pp Healthcare). ⇒ Track marginal benefit
  *per domain*; the pruning criterion for `curate` is SkillsBench's own three-arm protocol
  (no-skill / curated / learned) run on the host's task distribution — a skill that shows no
  marginal benefit in its domain is archived, not kept on vibes.
- **S4 — small model + skills ≈ big model without.** ⇒ Routing must stay *runtime-cheap*:
  `select`+closure is deterministic (no LLM), consistent with the project's cost principle (big
  model at build/import time, cheap or no model at runtime).

From **OpenSkill** (Yan et al., 2026, arXiv:2606.06741 — self-evolution with self-built verification):

- **O1 — verification without ground truth.** Their virtual tests anchor to *independently
  verifiable facts* (documented API parameters, dataset invariants, expected output formats), and the
  verifier is **isolated** from the skill author (never sees its reasoning — no supervision leakage).
  ⇒ Our pre-deployment signal (V2 below) generates checks from the skill's *grounding*, run by an
  op/model independent of the synthesis.
- **O2 — failure diagnostics fork.** Their diagnostics separate *knowledge gaps* (→ targeted
  retrieval) from *implementation bugs* (→ code fix). ⇒ A failed verify emits a typed diagnostic:
  grounding-missing → `stale` + targeted re-ingest; procedure-broken → `needs_review`.
- **O3 — bounded refinement** (≤3 rounds). ⇒ Re-verify/re-synthesize loops are bounded; no unbounded
  self-repair (consistent with the Dream's defer-to-next-pass stance).
- **O4 — skills transfer across models** (model-agnostic SKILL.md). ⇒ Already our unit format; record
  *which model/verifier verified* in the verification metadata, and re-verify (cheap) on model change.
- **O5 — verifier quality is itself measurable.** OpenSkill reports 60.7% agreement with ground
  truth (precision 56.9 / recall 80.5, OR=2.97). ⇒ Our V2 is a *proxy* signal and must be calibrated
  the same way (two-tier eval: deterministic V1 is the anchor; LLM-built V2 needs an agreement
  measurement before its verdicts gate anything important).

## The two verification signals for `kind=procedural`

This fills `verification_design.md`'s open "procedural signal":

**V1 — deployment (deterministic, primary).** Every invocation the host reports becomes an
outcome-tagged episode that *references the skill directly* (`source_events=[<skill-slug>]`) — no
match-term fuzz, cleaner scope than the belief case. `verify_skill` = the existing tally shape with
`predicts=success`: confidence = Laplace hit-rate of invocations; the **witness gate applies
unchanged** (only self/host-trusted agents' invocations count — review-stuffing a registry skill is
the same attack as the pump-poisoning case, and the same guard stops it). The skill's confidence *is*
its track record, and routing prefers it.

**V2 — pre-deployment (OpenSkill-style, admission).** Before a candidate has any usage: generate
checks anchored to independently verifiable facts in the skill's own grounding (its cited docs,
declared parameters, expected formats), run them in isolation from the author, bounded rounds (O3).
V2 *admits* a candidate to routability; V1 *governs* its ongoing trust. V2 verdicts are proxy-grade
(O5) and never outrank accumulated V1 evidence.

## The four mappings, skill-flavored

| pain | kernel op | skill-specific note |
|---|---|---|
| **routing** | `select` + `dependency_closure` | capped ≤3 (S2); deterministic (S4); confidence-weighted (V1) |
| **dedup** | `compact` | community registries are near-duplicate-rich; uncertain merges → `needs_review` (never silent) |
| **trust** | provenance + verify + guards | `asserted_by`=author/registry; import → `candidate` (S1); security tier → policy (tier3 → `needs_review` until vetted); V2 admits, V1 governs |
| **maintenance** | stale + `valid_to` + `reconcile` + `curate` | grounding changed → stale → re-verify (incremental rebuild); deprecation = temporal supersede; pruning = S3's marginal-benefit criterion |

## Lifecycle

```
import(manifest) → candidate (tier-tagged, provenance-stamped)
  → vet: tier policy + V2 admission → active (routable)
  → route(task) → invoked → host report(outcome) → episode
  → V1 sweep: confidence accrues | refuted → stale (O2 fork: re-ingest vs needs_review)
  → curate: no marginal benefit in its domain (S3) → archived (non-destructive)
```

## Host API (sketch)

- `import_skills(manifest, *, tier_policy)` — registry → corpus units (`kind=procedural`,
  `status=candidate`, `asserted_by`, tier metadata).
- `route(task, *, k=3, min_confidence=None)` — select + closure, capped, confidence-gated; returns
  unit bundles for the prompt.
- `report(skill, outcome, *, witness=None)` — one invocation result → an episode referencing the
  skill; feeds V1.
- `sweep()` — verify (V1) + compact + curate + stale handling; the skill-pool's Dream.

## Boundary vs. AgentMakefile

Same graph, two write-paths (the bridge spec): **AgentMakefile's OpenClaw importer** selects and
compiles a *curated subset* at build time (high trust, authored intent); **aigg-skill** manages the
*full ecosystem at runtime* (low-trust admission, verification-climbed promotion). A skill that earns
high V1 confidence is a natural candidate for the Skill Workshop's human review → curated tier.

## Validation plan (against the real corpus)

1. **Dedup rate**: `compact` over the 248 tier1+2 skills, then the 5,127 manifest — how many true
   near-duplicate groups? (a concrete, publishable number)
2. **Routing quality**: `select`+closure vs. a keyword baseline on sampled task descriptions; measure
   where match-term routing strains at 5k (the kernel paper §11 scale boundary, quantified).
3. **V1 loop**: simulate invocation outcomes (deterministic harness, tier-1) — confidence ladders,
   refute→stale, witness-gate poisoning resistance.
4. **V2 calibration**: build OpenSkill-style checks for a sample; measure agreement against known
   tier labels (their O5 discipline applied to us).

## Open decisions

- **V2 weight**: admission-only (proposed) vs. contributing to the same confidence tally at a
  discount; how V2 verdicts are recorded (verification events vs. a separate field).
- **Domain accounting** for S3: how a "domain" is keyed (corpus partition? match-term cluster?).
- **Embedder at 5k**: hash match-term routing vs. opt-in real embedding — decide from validation #2,
  not in advance.
- **Security tiers**: exact tier → {status, locked, needs_review} mapping for the gated pilot.
- **Packaging**: incubate as `aigg_memory.skill` or `examples/skill-manager` first; extract to an
  `aigg-skill` repo when the validation plan passes.
