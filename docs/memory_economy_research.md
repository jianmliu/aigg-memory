# Memory and the economics of luck — a research design

> Does memory change the verdict that luck beats talent? This composes three lines —
> **Effort-Luck-Choice** (a strict superset of Pluchino et al.'s Talent-vs-Luck, in
> `aigg-mud-demo/src/experiments/effort-luck-choice.ts`), the **Generative-Agents emergences**
> (reproduced in [`examples/eval/`](../examples/eval/)), and **aigg-memory** — into one claim:
> the slot where cognition decides success is the *quality of choice*, and aigg-memory turns
> that slot from a static scalar into a **learned, socially-shared, auditable** faculty.
> Status: design. Date: 2026-06-08. **Simulation only — see §10 (ethics & boundaries).**

## 1. Thesis

Pluchino's Talent-vs-Luck shows success tracks **luck more than talent**, because talent is
*passive* (a fixed multiplier) while luck *compounds* (early breaks snowball through a
rich-get-richer dynamic). The Effort-Luck-Choice (ELC) refinement isolates the exact slot
where this can be reversed: **choice** — whether you seize the good draw and skip the trap,
gated by **discernment** `q = clamp(talent + faculty)`.

**Claim:** discernment is not a constant. With memory it is *learned* (you remember the trap
that burned you), *socially shared* (a friend warns you), and *auditable* (your track record
makes your skill legible to those allocating capital). aigg-memory is the substrate for all
three. So the research question sharpens from "does talent matter?" to **"does a memory that
makes choice better let talent reclaim success from luck — and through which channels?"**

## 2. The three composed models (grounded)

- **ELC** (`effort-luck-choice.ts`): three channels on a pure STF (`applyTx`) with
  per-agent **independent** seeded PRNGs *outside* the STF (counterfactual-clean — the luck
  hand dealt to an agent is identical across conditions, so a treatment's causal effect is
  readable):
  - **effort** — a flat, faculty-independent grind (`effortEarn` per turn).
  - **luck** — exogenous multiplicative events *dealt* to you (good ×`goodF` / trap ×`badF`).
  - **choice** — good draws are seized; a trap hits unless avoided (`avoidRoll < q`), with
    discernment `q = clamp01(talent + faculty)`. `faculty=0` reproduces TvL (luck dominates).
    Metrics: `ρ(wealth,talent)`, `ρ(wealth,skill)`, `ρ(wealth,luck)`, `Gini`. A **patron**
    allocates a budget by policy (`meritocratic` = reward current winners = reward luck;
    `egalitarian`; `talent` = oracle upper bound; `random`).
- **Generative-Agents emergences** (in `examples/eval/`, all reproduced + ablated):
  information **diffusion**, relationship **formation**, **coordination** — measured directly
  from the git-versioned store.
- **aigg-memory**: observe → reflect (facts→beliefs) → plan (+ stale-replan) → recall; with
  reconcile (correction/temporal, **no-guess → `needs_review`**), provenance
  (`asserted_by`/`source_events`), valid-time, and a git-versioned, auditable history.

## 3. The unified model — a four-channel decomposition of success

ELC decomposes wealth into effort + luck + choice. We split **choice** into an *individual*
and a *social* term, yielding four channels:

```
wealth ~ effort            # the slope: flat grind (given)
       + luck              # the deal: exogenous, dealt independently (given)
       + faculty_individual# learned discernment: q rises as memory accrues  (aigg-memory)
       + social_capital    # shared discernment + reach: network centrality  (the emergences)
```

The decisive change to ELC: `faculty` is no longer a static per-agent constant. It becomes

```
q_t(agent, opp_type) = clamp( talent
                            + facultyFromMemory(agent, opp_type, t)   # H-mem
                            + socialWarning(agent, opp_type, t) )      # H-social
```

`facultyFromMemory` rises when the agent has reflected "opp_type X is a trap" from past
episodes; `socialWarning` is non-zero when a relationship-neighbour holds such a belief and it
has diffused to the agent. **Effort and luck are fate; the two choice terms are built — and
memory is what builds them.**

## 4. How the three emergences map to economic channels

The emergences are not decoration; each feeds a specific channel, and together they form the
`social_capital` axis — the only success channel besides effort that is *constructible*.

| Emergence | Channel it feeds | Economic mechanism | aigg-memory primitive |
| --- | --- | --- | --- |
| Information **diffusion** | **choice** (social discernment) | hear "type X is a trap" / "good opp" from others → effective `q` rises **without paying the cost** | observe / recall + provenance |
| Relationship **formation** | **conduit + capital + legibility** | the network diffusion travels on; compounding affinity (returning-visitor continuity); the *reputation* that makes skill visible to a patron | `person_<id>` units, reflect, the auditable store |
| **Coordination** | **choice multiplier** (collective seize) | assemble a group to seize an opportunity a lone agent can't (a class of high-`bigF` events that fire only for an attending coalition); reliability gates it | goal→plan→invite→attend + stale-replan |

The three form a **value chain**, each stage memory-powered: build the network (relationships)
→ the network carries warnings/tips (diffusion) → the network + trust enables joint seizing
(coordination). Social ability is itself a compounding pipeline.

## 5. aigg-memory's role — the bridge

The ELC substrate is untouched; aigg-memory enters at exactly one line — the discernment `q` —
and (optionally) the patron's information set:

- **Decision time:** the agent `observe`s the current opportunity's type; `recall` returns
  whether it (or a co-located, relationship-connected neighbour) holds a "type=trap" belief →
  the `facultyFromMemory` + `socialWarning` terms of `q_t`.
- **Sleep:** `reflect` consolidates repeated trap-encounters into a "type X is a trap" belief
  (private learning); `plan` provides metabolic foresight (don't act into the poverty trap).
- **Patron:** an optional `track-record` policy reads each agent's **auditable** avoidance
  history (provenance-stamped, versioned) to allocate by demonstrated skill — see H-legibility.

The interface contract is one function and one optional policy:

```
facultyFromMemory(agentCorpus, oppType, t) -> number   # via /memory/select over aigg-memory
trackRecord(agentCorpus) -> skillEstimate              # via the versioned store / timeline
```

## 6. Hypotheses

- **H-mem (learned discernment).** Replace static `faculty` with `q_t = clamp(talent +
  f(memory_t))`. Prediction: discernment **rises over turns** (a learning curve); `ρ(wealth,
  skill)` grows *more* the longer the run, where static-faculty is flat. Ablation: reflect
  on/off → with memory, late-game trap-avoidance ≫ early; without, flat. *Static faculty
  cannot show a learning curve — the curve is aigg-memory's signature.*
- **H-social (shared discernment).** Add `socialWarning` from diffused trap-beliefs.
  Prediction: high relationship-centrality agents eat fewer traps; `social_capital` gains
  independent explanatory power for wealth beyond talent and luck.
- **H-coord (collective seize).** Add opportunities that fire only for a coordinated coalition
  (×`bigF`). Prediction: coordination ability (plan→invite→attend reliability) unlocks a class
  of returns unavailable to lone agents — social ability's *offensive* contribution (diffusion
  is only defensive).
- **H-legibility (memory makes skill bankable).** A `track-record` patron policy (allocate by
  audited avoidance history) **beats `meritocratic`** (allocate by current wealth = reward
  luck), approaching the `talent` upper bound. *`meritocratic` fails because no one can tell
  "won" from "got lucky"; aigg-memory supplies the record that can.*
- **H-equity (the open question).** Does the social layer **democratize** luck (warnings
  protect the low-talent → `Gini` ↓) or **concentrate** it (the well-connected hear and seize
  first → Matthew effect → `Gini` ↑)? And does the `track-record` patron correct it?

## 7. The market / reflexivity extension

Markets are the natural limit of this model, with one structural change and one bright line.

- **Endogenous (reflexive) price.** Unlike ELC's *exogenous* luck, a market price is the
  aggregate of everyone's choices. "Social ability to rally buying" no longer just *finds* an
  opportunity — it *manufactures* one by moving the price (Soros reflexivity): a call → price
  up → the call looks validated → more buyers → cascade → pop.
- **The prosocial→antisocial duality.** The *same* social ability that is prosocial in
  Smallville (warn a friend off a trap) becomes antisocial in a money market (lure a friend
  into a trap you set, then sell into the rally). Structurally that is a **pump-and-dump**.
  This duality is itself a finding: in a reflexive market, how much of social capital's return
  is **information** (legitimate edge) vs **manipulation**?
- **Two legitimate, sharper instruments (simulation only):**
  1. **Prediction market as a discernment scorer.** A play-money market with a proper scoring
     rule (Brier / log) is the cleanest possible measurement of `q`. Does memory improve
     forecast *calibration* over rounds (H-mem in its purest form)? Does diffusing a true
     signal yield wisdom-of-crowds or herding (correlated error)?
  2. **Memory as anti-manipulation immunity (the headline aigg-memory result).** In a
     simulated market with a manipulator (pump agent) among a population, do memory-equipped
     agents get rugged *less*? This exercises every aigg-memory signature: **provenance**
     (what is the caller's track record?), **no-guess/`needs_review`** (a "guaranteed 10×"
     claim inconsistent with history → distrust, don't follow), **reflection** ("this rhetoric
     = pump → trap belief"), **reconcile** (the called price vs the realized price). Prediction:
     memory immunizes against manipulation — the ethical inverse of a pump tool.

## 8. Methodology

- **Counterfactual-clean ablation.** Reuse ELC's per-agent independent luck PRNGs: hold the
  luck seed fixed and toggle a treatment (memory on/off, social layer on/off, patron policy) →
  read the treatment's pure causal effect, exactly as ELC reads faculty's.
- **Four-way variance decomposition.** Regress / rank-correlate wealth against effort, luck,
  individual faculty, and social centrality; report each channel's share, plus `Gini`.
- **Metrics.** ELC's `ρ(wealth,·)` and `Gini`; the harness's `relationship_density` /
  centrality and `diffusion_traceable`; for the market instruments, Brier/log calibration and
  **rug-rate** (fraction of a manipulator's followers left at a loss) by memory condition.
- **Learning curve.** Track `q_t` (or trap-avoidance rate) over turns — the H-mem signature.

## 9. Architecture (interface integration, not a merge)

```
ELC economy + luck + metrics      → aigg-mud-demo (TS STF, counterfactual-clean PRNG)  [unchanged]
social substrate (the emergences) → aigg-memory/examples/eval (the rails + probes)
cognition (memory/reflect/plan)   → aigg-memory kernel, over HTTP
bridge                            → q's social/faculty terms <- facultyFromMemory + socialWarning;
                                    patron's track-record <- the versioned store
```

The two `experiments/` directories stay separate (different stacks, different subjects — see
the comparison in chat); they meet only at aigg-memory's public HTTP surface. `smallville.py`
already emits the `centrality` and `diffusion` structures that become the ELC social inputs at
scale.

## 10. Ethics & boundaries

- **Simulation only.** Every experiment runs on the STF / the eval harness with seeded PRNGs
  and play money. No real assets, exchanges, or funds.
- **No trading advice.** This program studies *dynamics*; it does not recommend any asset or
  position.
- **No manipulation tooling.** We do **not** build a system to rally real buyers or move a real
  price. Pump dynamics are modelled only to *study* them, and the defensible aigg-memory result
  is the **inverse** of a pump tool: memory as immunity (§7.2). The prosocial→antisocial duality
  (§7) is the reason the build target is the immune system, not the pathogen.

## 11. Experiment program (staged)

- **E1 — H-mem (headless, first):** typed traps; `observe→reflect→recall` raises `q`; plot the
  discernment **learning curve**; ablation reflect on/off. Reuses the eval harness; the ELC
  step's `q` reads from aigg-memory.
- **E2 — H-social:** add `socialWarning` from diffused trap-beliefs over the relationship
  network; show `ρ(wealth, centrality)` independent of talent/luck.
- **E3 — H-coord:** coalition-only opportunities; coordination reliability unlocks high-`bigF`
  returns.
- **E4 — H-legibility:** the `track-record` patron policy vs `meritocratic`/`talent`.
- **E5 — market instruments:** the play-money prediction-market discernment scorer, then the
  memory-as-anti-manipulation rug-rate study.
- **E-equity** runs across all: democratize vs concentrate (`Gini`), and whether legibility
  corrects it.

## 12. The one-line claim

> Effort is the slope, luck is the deal, faculty is the play you learned, and social capital is
> who warns you, who backs you, who sits down to play alongside you. The first two are fate; the
> last two are *built* — and memory is what builds them. Pluchino's world rewards luck because no
> one remembers yesterday. **aigg-memory measures, and supplies, the part of success that is
> earned: the memory that turns a lucky break into a skill, and a track record into trust.**
