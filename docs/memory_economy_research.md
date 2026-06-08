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
  independent explanatory power for wealth beyond talent and luck. **(E2: ρ(wealth,centrality)
  = +0.995 with the warning network, +0.28 without — social capital is real but purely
  instrumental.)** *Refinement — `social_capital` has a **sign**:* the same network channel
  carries warnings (E2, positive-sum, welfare↑) **or** a pump cabal's "buy + recruit" (E6,
  negative-sum, welfare↓). The identical `ρ(wealth, centrality/earliness)` appears in both, so
  social capital "paying" is welfare-ambiguous — *earned* (you help others) vs *extracted* (you
  recruit marks) is legible only from the recipients' sign, not the correlation.
- **H-immunity (memory is herd-level, not only individual).** A pump needs marks (memoryless
  followers); a memory-equipped agent (E5) refuses and won't relay, so the pump percolates only
  through the susceptible sub-network. Prediction: above a memory-penetration threshold (≈ the
  site-percolation threshold `1 − 1/⟨k⟩` of the peer graph) the cascade shatters and the pump
  dies. **(E6: a society's manipulator-profit collapses from 535 marks to ~0 as memory crosses
  ~80% on a ⟨k⟩=6 network — a society that remembers can't be pumped, because there are no
  marks.)** Pyramid/MLM recruitment (single-path) is far more fragile — a memory minority
  suffices.
- **H-coord (collective seize) — unified with the pump.** Coordination unlocks coalition-only
  returns a lone agent can't reach. But the machinery (plan→invite→assemble) is *identical* to a
  pump cabal's; the only difference is the **value source**: an external beneficiary paid for
  value the coalition produced (a venture, counterparty welfare +) vs a transfer from recruited
  marks (a pump, counterparty welfare −). **(E3: ρ(wealth, coordination) = +1.0 for both, so
  wealth cannot tell them apart; the discriminator is the counterparty-welfare sign.)** Memory
  is what reads it: with `track_record`, members refuse leaders whose history harmed
  counterparties → pumps starve, total welfare flips from −1 to +273, and coordination pays
  *only if it creates value* (ρ → +0.64). So "coalition-only opportunity" is not a separate
  thing from the pump — it is the *same* act with the value-source knob turned to production, and
  only memory makes the two legible.
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
     memory immunizes against manipulation — the ethical inverse of a pump tool. **Herd-level
     (E6/H-immunity):** because the same relationship network is a *neutral* channel — warnings
     in E2, a pump cabal's "buy + recruit" here — the pump is a percolation on the *memoryless*
     sub-network; past a memory-penetration threshold (≈ `1 − 1/⟨k⟩`) it cannot recruit enough
     marks and dies. Memory's immunity is collective, not just personal. We model the cabal only
     to measure that immunity (the build target is the immune system, not the pathogen).

## 8. Canonical scenario — the compute-price (GCC) rumor

One scenario threads every channel, hypothesis, and instrument above, and it is native to a
metered-cognition world: **a rumor that "the price of compute (GCC) is about to rise."** Its
power is that the rumour's *referent is the fuel agents burn to think* — so it is reflexive,
self-referential, and differentially attacks the cognition-poor.

**Mechanics.** Make `gccCost` endogenous: `gccCost_{t+1}` rises with aggregate GCC
hoarding/demand. Seed the rumour in one agent; it spreads by co-located conversation (the
diffusion rails). An agent who *believes* it hoards GCC now (to lock in cheap thinking) →
demand spikes → `gccCost` actually rises → the rumour is validated → more believe → cascade.
**The rumour does not predict the price; it causes it** (Soros reflexivity, self-fulfilling).
A **manipulator** variant: a pump agent pre-hoards, plants the rumour, and dumps into the
spike — the rug.

**Three sharp properties this concrete case exposes:**

1. **Discernment becomes a beauty contest.** Since enough believers *make it true*, `q` is no
   longer "is the rumour true?" but **"will enough others believe it?"** — a Keynesian
   coordination game. Predicting others' beliefs is exactly what memory of past cascades +
   the social signal informs; raw single-shot talent cannot.
2. **Compute = cognition: the meta-loop.** The asset is the fuel for thought. A rising
   compute price *taxes cognition* → the poor are priced out of thinking → can only follow
   rumours blindly → rugged worst. A compute-price pump transfers wealth from the
   cognition-poor to the manipulator **and degrades the poor's future discernment** — a
   cognition-inequality spiral. **The reversal (aigg-memory's killer property): recall is
   cheap, thinking is dear** (the cost principle — expensive build-time, near-free runtime
   recall). When the thinking-tax spikes, a memory-equipped poor agent need not re-think —
   only *remember* "last time this talk was a pump." **Memory democratizes discernment exactly
   when thinking becomes a luxury** — the poor's only affordable defence against a
   cognition-cost attack.
3. **Front-running: centrality × memory.** Who hears first hoards first at the low price and
   sells into the spike — so the diffusion structure decides who profits; **centrality
   concentrates the gain** (social capital concentrating luck). But centrality *without*
   discernment is amplified exposure: the well-connected who buy on a *false* rumour are rugged
   hardest. **centrality × memory is the winner; centrality alone is leverage on risk.**

**It instantiates the whole model:** diffusion (how the rumour spreads), reflexivity (it moves
the price it describes), the four channels (effort to grind GCC, luck = whether the shock is
real, individual faculty = remembering the pump, social capital = hearing first), and every
aigg-memory signature — **provenance** (who called it; their versioned track record),
**reconcile** (called price vs realized price), **reflection** ("this rhetoric + price signal →
pump" belief), **no-guess/`needs_review`** (a claim inconsistent with history → distrust, don't
FOMO), **valid-time** (an expired rumour must stop driving action).

**Decisive readouts.** rug-rate by memory condition (on/off) — the headline; cognition
inequality (`Gini` and the *thinks*-distribution skew after a pump, and whether memory flattens
it); front-running return decomposed into information-edge (legitimate) vs manipulated-bagholding;
and the **self-fulfilling half-life** — how long a *false* rumour holds the price up vs the
collective memory depth that pops it. E1 is the truthful-signal slice of this scenario; E5 is the
manipulated slice — same substrate.

## 9. Methodology

- **Counterfactual-clean ablation.** Reuse ELC's per-agent independent luck PRNGs: hold the
  luck seed fixed and toggle a treatment (memory on/off, social layer on/off, patron policy) →
  read the treatment's pure causal effect, exactly as ELC reads faculty's.
- **Four-way variance decomposition.** Regress / rank-correlate wealth against effort, luck,
  individual faculty, and social centrality; report each channel's share, plus `Gini`.
- **Metrics.** ELC's `ρ(wealth,·)` and `Gini`; the harness's `relationship_density` /
  centrality and `diffusion_traceable`; for the market instruments, Brier/log calibration and
  **rug-rate** (fraction of a manipulator's followers left at a loss) by memory condition.
- **Learning curve.** Track `q_t` (or trap-avoidance rate) over turns — the H-mem signature.

## 10. Architecture (interface integration, not a merge)

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

## 11. Ethics & boundaries

- **Simulation only.** Every experiment runs on the STF / the eval harness with seeded PRNGs
  and play money. No real assets, exchanges, or funds.
- **No trading advice.** This program studies *dynamics*; it does not recommend any asset or
  position.
- **No manipulation tooling.** We do **not** build a system to rally real buyers or move a real
  price. Pump dynamics are modelled only to *study* them, and the defensible aigg-memory result
  is the **inverse** of a pump tool: memory as immunity (§7.2). The prosocial→antisocial duality
  (§7) is the reason the build target is the immune system, not the pathogen.

## 12. Experiment program (staged)

All experiments are slices of the §8 canonical scenario (the compute-price rumour).

- **E1 — H-mem (shipped):** the *truthful-signal* slice — a recurring typed trap;
  `observe→reflect→recall` raises `q`; the discernment **learning curve** (`[0,0,1,1,…]` with
  memory, flat without). The ELC step's `q` reads from aigg-memory via the `agent` client.
- **E2 — H-social (shipped):** `socialWarning` diffuses over the relationship network;
  `ρ(wealth, centrality)` = +0.995 with the network, +0.28 without — independent of talent/luck.
- **E3 — H-coord, unified (shipped):** coordination is identical machinery; a venture vs a pump
  cabal is one knob (the value source), distinguishable only by counterparty-welfare sign —
  ρ(wealth,coord)=+1.0 both, but `track_record` starves the pumps (welfare −1 → +273; coordination
  pays only if it creates value). Resolves "isn't a coalition just a group pump?".
- **E4 — H-legibility:** the `track-record` patron policy vs `meritocratic`/`talent`.
- **E5 — anti-manipulation immunity (shipped):** the *manipulated* slice of §8 — the
  memory-as-anti-manipulation **rug-rate** study (rugged 2/8 vs 8/8; discriminates the
  manipulator from an honest caller by provenance/track record). Next: a play-money
  prediction-market discernment scorer.
- **E6 — herd immunity (shipped):** the pump cabal vs memory penetration — manipulator profit
  collapses at the percolation threshold (535 marks → ~0 as memory crosses ~80% on ⟨k⟩=6); the
  self-fulfilling pump's reach ~ the susceptible cluster. Establishes `social_capital`'s
  earned-vs-extracted sign (with E2) and memory's herd-level immunity.
- **E-equity** runs across all: democratize vs concentrate (`Gini`), and whether legibility
  corrects it.

## 13. The one-line claim

> Effort is the slope, luck is the deal, faculty is the play you learned, and social capital is
> who warns you, who backs you, who sits down to play alongside you. The first two are fate; the
> last two are *built* — and memory is what builds them. Pluchino's world rewards luck because no
> one remembers yesterday. And when the rumour is that *thinking itself* will cost more, the poor
> are crushed not by luck but by **not remembering** — and a cheap recall is the only discernment
> they can still afford. **aigg-memory measures, and supplies, the part of success that is earned:
> the memory that turns a lucky break into a skill, a track record into trust, and — when thought
> becomes a luxury — remembering into the poor's last defence.**
