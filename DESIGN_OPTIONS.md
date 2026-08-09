# Family Camp Scheduling Engine — Design Options

This document presents two detailed designs for the scheduling engine
specified in [REQUIREMENTS.md](REQUIREMENTS.md), built only from open-source
Python tools. It closes with a comparative analysis and a recommendation.

Requirement IDs (`FR-n`, `NFR-n`, `OQ-n`) refer to REQUIREMENTS.md
throughout.

## 1. What the OQ answers decide before we design anything

The answers recorded in REQUIREMENTS.md §7 aren't just clarifications — two
of them largely determine which class of solution is competitive:

- **OQ-1/OQ-2 (scale + budget)**: upper bounds of **500 campers, 30
  activities, 50 sessions**, with up to **24 hours** wall-clock available.
  A boolean camper×session assignment matrix at this scale is at most
  25,000 variables. This is a small-to-medium combinatorial problem by the
  standards of modern constraint/optimisation solvers — the kind that
  typically solves to optimality or to a tight, provable bound in seconds
  to low minutes, not hours. The 24-hour budget is generous even for an
  exact method run several times over.
- **OQ-4 (objective ranking)**: the soft objectives must be **strictly
  ranked**, not combined into a single weighted score with an arbitrary
  trade-off. This is a *lexicographic* optimisation requirement: fully
  satisfy the first-ranked objective, then, among solutions tying on that,
  do as well as possible on the second, and so on.

Taken together, these two answers matter a great deal: at this scale, an
exact method can afford to *prove* it has found the lexicographically best
(or best-effort) schedule, whereas a search heuristic can only ever report
"the best I happened to find." That tension runs through both designs
below and drives the recommendation in §5.

The remaining answers refine the rules rather than the choice of approach
(§2).

## 2. Shared foundations (used by both designs)

Both designs sit on top of the same solver-independent core. This isn't
optional shared infrastructure bolted on afterwards — building it first is
what makes FR-40/FR-41 (validate *any* candidate timetable, generated or
not) and NFR-6/NFR-7 (testable in isolation) achievable regardless of which
design is chosen, and it's what keeps each design's own code limited to
"how do I search for a good assignment" rather than also re-deriving "what
does a good assignment mean."

```
                     ┌───────────────────────────────┐
                     │   Domain model (dataclasses)   │
                     │ Activity / Session / Camper /  │
                     │   Timetable (assignment set)   │
                     └───────────────┬─────────────────┘
                                      │
                     ┌────────────────▼────────────────┐
                     │   Validator / scorer (pure fns)  │
                     │  - Class 1 invariant checks      │
                     │  - Class 2 violation counting     │
                     │  - Objective tiers (FR-20/21/22) │
                     │  - Idle-slot reporting (FR-23)   │
                     │  - Human-readable violation report│
                     └──────┬──────────────────┬─────────┘
                             │                  │
                ┌────────────▼───────┐  ┌────────▼──────────────┐
                │      Design A      │  │       Design B         │
                │  OR-Tools CP-SAT   │  │  Simulated annealing / │
                │   solver adapter   │  │  local-search adapter  │
                └────────────────────┘  └────────────────────────┘
```

### 2.1 Domain model

Plain, dependency-free `dataclasses` for `Activity`, `Session`, `Camper`,
and `Timetable` (a set of `(camper, session)` assignments), matching the
input contract in REQUIREMENTS.md §3, plus two additions driven by the OQ
answers:

- `Activity.min_age: Optional[int]` — lower age bound (OQ-8). `None` means
  no restriction.
- `Camper.is_adult: bool` (derived from age/age-group) — used by the
  adult-supervision rule below.

### 2.2 Constraint classification — the key design decision shared by both approaches

Not all hard constraints behave the same way under capacity pressure, and
telling them apart cleanly is what makes the "best-effort" behaviour in
FR-30/FR-31 tractable and explainable, in *either* design:

**Class 1 — structurally always satisfiable.** These can always be met by
simply *not* making an assignment, so there is never a capacity-driven
reason to break them. They are treated as absolute invariants in both
designs — never relaxed, never reported as "violated," full stop:

- FR-10 no double-booking
- FR-12 (max side) session over capacity
- FR-14 no unrequested activities
- FR-15 no duplicate activity per camper
- Age eligibility (OQ-8): camper below an activity's minimum age is never assigned to it

**Class 2 — demand-driven, can genuinely conflict.** Whether these can all
be satisfied depends on how registration demand compares to capacity, so
real inputs may make them jointly infeasible. These are the ones FR-31
requires a best-effort account of:

- FR-13 every priority activity honoured
- FR-11 no family time-conflict, refined by **OQ-7**: a family may be split
  across non-overlapping sessions of the same priority activity, but every
  such session must include at least one adult (18+) from that family
- FR-12 (min side) session under minimum occupancy
- FR-16 compulsory activities (currently: the designated set is empty, per
  OQ-5 — supported, unused)

This split matters for *functional correctness*, independent of which
solver is chosen: Class 1 constraints are guaranteed 100% of the time in
both designs, by construction, so "functional correctness" for the whole
engine really only hinges on how well each design handles Class 2 — that's
where the two designs genuinely differ, and where §5's comparison focuses.

### 2.3 Objective tiers (realises OQ-4)

The validator exposes a fixed, ordered list of tiers rather than a single
score. A configuration file supplies the order (satisfying NFR-4 — this is
the "adjustable weighting" mechanism, expressed as an *ordering*, not a
weight):

1. **Tier 0 — Class 2 violation minimisation.** A weighted sum *within* this
   tier only (priority-unmet weighted most heavily, then family/adult-supervision
   violations, then under-minimum sessions, then unmet compulsory activities —
   default severity order, itself config-driven). This tier is what FR-30/31
   report on.
2. **Tier 1 — FR-20/FR-21: optional-request satisfaction.** Scored per
   camper as *fraction of their optional requests met* (0–1) and summed —
   this formula already satisfies FR-21's fairness requirement by
   construction, since each camper contributes a comparable 0–1 value
   regardless of how many optional activities they asked for.
3. **Tier 2 — FR-22: even use of parallel sessions.** Population variance of
   occupancy across sessions of the same activity, minimised.

FR-23 (idle time) is **not** an objective tier per OQ-3 — it's computed by
the validator purely for the post-hoc report (who/when is idle), the same
role it plays in the current system today.

### 2.4 Violation/objective report (FR-40/FR-41)

A single validator function takes any `Timetable` (from either design, or
hand-constructed in a test) and returns a structured report: per-rule
violation lists naming the specific camper/family/activity/session
involved, plus the Tier 1/2 scores. Both designs' output MUST be run
through this same function before being presented as a result — this
gives an independent, solver-agnostic correctness check on whatever a
solver claims to have produced (valuable in either design, but especially
as a safety net against solver-adapter bugs).

## 3. Design A — Constraint Programming (OR-Tools CP-SAT)

**Library**: [Google OR-Tools](https://developers.google.com/optimization)
(`pip install ortools`), Apache 2.0 licensed, open source. Uses its CP-SAT
solver.

### 3.1 Approach

Model the problem declaratively: decision variables plus constraints plus
an objective, handed to a general-purpose solver — no hand-written search
procedure.

- **Decision variables**: `x[c, s]` boolean, camper `c` assigned to
  session `s`, for every `(c, s)` pair where `c` requested `s`'s activity
  (priority or optional) and is age-eligible. Pairs that are impossible by
  Class 1 rules (age, non-request) are never created as variables at all —
  the model can't represent an invalid assignment, which is a stronger
  guarantee than "the objective discourages it."
- **Class 1 constraints**: no-overlap constraint per camper (using
  OR-Tools' interval/no-overlap machinery over each camper's assigned
  sessions), and a linear capacity constraint per session
  (`sum(x[c,s] for c) <= activity.limit`). Both are structural — there is
  no slack variable, so they can never appear in a solution.
- **Class 2 constraints**: modelled with **violation indicator
  variables** — e.g. `missing_priority[c, a]` is 1 if camper `c` isn't
  assigned any session of priority activity `a`; `family_conflict[g, s1,
  s2]`-style indicators (or an equivalent reformulation) capture family
  time-conflicts and the OQ-7 adult-supervision condition (`if any minor
  from family g is in session s, an adult from g must also be in s` —
  a direct boolean implication constraint). These indicators are what
  Tier 0's objective minimises — they're allowed to be 1, at a cost.
- **Lexicographic solving**: solved as a **sequence of CP-SAT solves**, one
  per tier, each adding the previous tier's achieved optimum back in as a
  constraint before optimising the next tier:
  1. Solve minimising the Tier 0 weighted violation sum → optimum `V0`.
  2. Re-solve with `tier0_violation_sum == V0` added, now maximising Tier 1
     (sum of per-camper optional-satisfaction fractions, scaled to
     integers for CP-SAT) → optimum `O1`.
  3. Re-solve with both `tier0_violation_sum == V0` and
     `tier1_score == O1` added, minimising Tier 2 (session-occupancy
     spread) → final solution.

  This is the most literal, provably-correct realisation of OQ-4's "must be
  a ranking, not a weighting" requirement: each phase is optimal *subject
  to* not giving up anything already won in an earlier phase. (A single-solve
  alternative using large weight multipliers between tiers, `1e6·Tier0 +
  1e3·Tier1 + Tier2`, is mentioned in §3.5 as a possible later optimisation
  — CP-SAT's integer arithmetic makes that numerically exact, unlike the
  same trick in a floating-point LP — but it trades away the clean,
  independently-checkable optimality-per-tier property in exchange for one
  solve instead of three. Given the 24-hour budget and small scale, three
  solves is not a cost worth paying that price for.)
- **Best-effort / infeasibility (FR-30/31)**: there is no separate
  infeasible case to handle — Tier 0's violation-minimising solve *is* the
  best-effort behaviour. If `V0 == 0`, the schedule is fully feasible; if
  not, the same solve already found the fewest (severity-weighted)
  violations possible, and the indicator variables that ended up at 1
  directly identify what to report per FR-31.
- **Output**: the assigned `x[c,s] == 1` pairs become a `Timetable`,
  passed straight through the shared validator (§2.4) before being
  returned — both as a correctness check on the model and to produce the
  human-readable report.

### 3.2 Performance against NFR-1/NFR-2

At 500 campers × 50 sessions with fairly sparse eligibility (a camper is
only a candidate for sessions of activities they actually requested and
are age-eligible for, not all 50), the core variable count is well under
the full 25,000 — realistically a few thousand. CP-SAT's model class here
— assignment with side constraints, no-overlap, and a bounded linear
objective — is squarely in its well-optimised territory; problems of this
size typically solve to proven optimality in seconds to a few minutes per
phase. Even with three sequential phases and generous safety margin, this
is minutes, not hours, against a 24-hour budget (NFR-2 comfortably met with
large headroom). If a future, much larger camp ever changed that
calculus, CP-SAT still degrades gracefully: it can be run with a time
limit and returns the best solution found so far plus a provable
optimality gap — an "I got this close, provably" answer, not silence.

### 3.3 Reproducibility, configurability (NFR-3/NFR-4)

CP-SAT is deterministic for a fixed `random_seed` and fixed worker/thread
count — rerunning the same input and config reproduces the same solution
exactly, which directly satisfies NFR-3 without extra engineering. Tier
order and Tier-0 severity weights live in a config object passed to the
model-builder, not in code, satisfying NFR-4.

### 3.4 Maintainability assessment

- **Strengths**: the model *is* the specification — each constraint in §3.1
  maps to one rule in REQUIREMENTS.md, so a future maintainer reading the
  model-building function is reading a fairly literal translation of the
  requirements document, not a search procedure whose relationship to the
  rules is indirect. There's no custom search/repair code to maintain (the
  solver's internals are OR-Tools' problem, not ours) — the codebase this
  design needs to own is comparatively small: domain model, constraint
  builder, three-phase solve driver, and the shared validator (§2).
  OR-Tools is a mature (10+ years), heavily used, well-documented library,
  so there's a large body of external reference material for a future
  maintainer to draw on.
- **Risks**: CP modelling has a learning curve if nobody on the team has
  done it before — expressing the OQ-7 adult-supervision implication and
  the sequential-solve driver correctly requires some CP-specific idiom
  (indicator/reified constraints) that isn't obvious from general Python
  experience. `ortools` is a fairly large binary dependency (it ships
  native solver code); that's a heavier install than pure Python, though
  it's a single `pip install` with prebuilt wheels for common platforms,
  not a build-from-source burden.

### 3.5 Testability assessment

- The model-building code can be unit tested the same way as any other pure
  function: build a tiny synthetic instance (a handful of campers/sessions),
  solve it, assert on the returned `Timetable` via the shared validator —
  no mocking of the solver needed, CP-SAT runs in-process and solves toy
  instances in milliseconds.
- Because Class 1 constraints are structural, they can't be tested for
  "does the solver respect this" in the usual sense — they're guaranteed by
  the model shape itself. Tests here are better aimed at "does the model
  correctly *exclude* invalid variables" (e.g. no `x[c,s]` variable exists
  for an activity `c` never requested).
- Class 2 behaviour is directly testable: construct a deliberately
  over-subscribed toy instance (more priority demand than capacity) and
  assert the solver reports exactly the expected violations, in the
  expected severity order — this is a strong, precise regression test that
  a heuristic approach (§4) cannot offer with the same confidence, because
  a heuristic's "expected violations" for a hand-built adversarial case
  aren't guaranteed to be *the minimum possible*, only *a* result.
- The three-phase sequential solve is a natural seam for integration tests:
  assert phase 2's solution never regresses phase 1's achieved `V0`, etc.

### 3.6 Functional correctness assessment

Strongest of the two designs on this axis specifically because of what
"solved" means for CP-SAT: each phase either returns a *proven* optimum for
that tier (not just a good one), or proves the model infeasible (which,
given Class 1's structural satisfiability, only Tier 0 can be — and even
then only if the config'd severity weights make the problem numerically
degenerate, not a real infeasibility). Combined with the shared validator
double-checking the output, there are two independent layers agreeing
before a schedule is reported as final. The main correctness *risk* is
entirely in getting the model right (the reification of OQ-7's conditional
rule is the fiddliest part) — the solving process itself is not a source
of risk once the model is right.

## 4. Design B — Metaheuristic: Simulated Annealing with domain-aware moves

**Library**: no required third-party solver — a self-contained
implementation using only the Python standard library (`random`, `math`,
`multiprocessing` for parallel restarts). Optionally `numpy` (BSD licensed)
for vectorising the assignment state if profiling shows a need. This
intentionally does **not** reuse DEAP or a population/crossover-based GA —
the review in DESIGN.md §3.1 found the existing GA's crossover operator to
be a disabled no-op, meaning the current system is already, in effect, a
single-solution local search wearing GA machinery it isn't using. Design B
makes that explicit and drops the unused population/crossover overhead
rather than repeating it.

### 4.1 Approach

Maintain one evolving candidate `Timetable`, repeatedly propose a small
change, and accept or reject it, gradually reducing how often a
worse-scoring change is accepted (the annealing "temperature" schedule).

- **State**: the candidate `Timetable`, plus incrementally-maintained
  per-session occupancy counts and per-camper assigned-session lists (so a
  proposed move's effect on the score can be computed without rescanning
  the whole state).
- **Move set** (adapted from the current system's `mutate()`, which is
  already a reasonable domain-aware repair operator, per DESIGN.md §2.5):
  - Assign a family (filtered to age-eligible, activity-requesting members)
    into a session with room.
  - Move a family from one session instance to a parallel instance of the
    same activity.
  - Swap two families between two sessions.
  - Remove a family from an activity entirely (used when repairing an
    over-subscribed session).
  - A targeted "fix adult supervision" move: if a family-split session is
    missing an adult, try to move one in from elsewhere.
  - **Class 1 constraints are enforced as move preconditions, not scored
    outcomes**: a move that would create a double-booking, exceed a
    session's capacity, add an unrequested activity, or violate the age
    floor is never generated in the first place, rather than being
    generated and then penalised. This mirrors §2.2's classification
    directly in the algorithm and means Design B, like Design A, never
    needs to search its way back out of a Class 1 violation — it's
    structurally excluded from the neighbourhood.
- **Scoring / acceptance**: each candidate move produces a **tuple**
  `(tier0_violation_vector, -tier1_score, tier2_score)`, using the same
  severity ordering and tier definitions as §2.3 (the shared validator's
  incremental scoring functions, not a separate reimplementation). Two
  states are compared **lexicographically** — element by element, not
  combined into a single scalar — so a move that improves Tier 0 is always
  preferred over one that only improves Tier 1, regardless of magnitude.
  This is a legitimate way to express OQ-4's "must be a ranking, not a
  weighting" inside a local-search acceptance rule, and avoids the
  weight-tuning fragility that a scalarised fitness function has (the exact
  bug class flagged in DESIGN.md §3.1's fitness-sign-convention finding).
  The simulated-annealing temperature still applies — early on, a move that
  is lexicographically *worse* can be accepted with some probability
  (computed from how much worse, via the same severity weights used for
  reporting) to escape local optima; that probability decays to ~0 as the
  run cools.
- **Restarts**: given the 24-hour budget and small problem size, run many
  independent annealing chains in parallel (`multiprocessing`, as the
  current code already does for fitness evaluation) from different random
  seeds/starting constructions, and keep the lexicographically-best final
  state across all of them. This is the main lever Design B has for
  compensating for the fact that any single chain offers no optimality
  guarantee.
- **Best-effort / infeasibility (FR-30/31)**: whatever Tier 0 vector the
  best chain ends with *is* the best-effort report — there's no separate
  "detect infeasibility" step, same structural shape as Design A, but with
  no proof that it's the *minimum* possible Tier 0 vector, only that it's
  the best found across all chains and restarts.

### 4.2 Performance against NFR-1/NFR-2

At this scale, a single annealing chain (a few thousand moves, each an
O(1)-ish incremental score update) runs in well under a second; running
thousands of chains in parallel across restarts easily fits inside the
24-hour budget with enormous headroom, likely finishing in minutes to low
hours even single-threaded. Performance is not a concern for Design B at
this scale — if anything, it has more spare budget than it can usefully
spend, since more restarts have diminishing returns once the search has
been run long enough to stop finding improvements.

### 4.3 Reproducibility, configurability (NFR-3/NFR-4)

Straightforward: every chain is seeded explicitly, so a specific chain's
run is exactly reproducible; the *overall* multi-chain result is
reproducible as long as the seed list and chain count are fixed and
recorded. Tier order and severity weights live in the same shared config
as Design A (§2.3) and plug directly into the tuple comparator — arguably
even more direct here than the sequential-solve mechanism in Design A,
since there's no need to translate "ranking" into a sequence of
solver invocations, just a tuple field order.

### 4.4 Maintainability assessment

- **Strengths**: no external solver dependency beyond the standard library
  — nothing to install, nothing to version-pin, no native binary. The
  algorithm is ordinary imperative Python, so it can be stepped through
  with a debugger exactly like any other code, which may be more
  approachable to a future maintainer without constraint-programming
  background.
- **Risks**: this is the same shape of system as today's, and the current
  codebase's worst bugs (DESIGN.md §3.1) came from *exactly this kind of
  code* — hand-written mutation/repair logic with subtle invariants (the
  shared class-attribute overlap cache, the inverted fitness-sign
  convention). Design B is less prone to the *sign-convention* class of bug
  specifically, because lexicographic tuple comparison replaces the
  weighted-scalar scoring that caused it — but the move-generation logic
  (correctly filtering by age/request eligibility, correctly enforcing the
  OQ-7 adult-supervision precondition on every relevant move) is bespoke
  code that has to get several interacting details right, and mistakes
  there manifest as *quietly worse* schedules rather than loud errors. This
  is a real, ongoing maintenance cost: every new move type added later
  needs the same care taken to preserve Class 1 invariants and Tier 0
  logic correctly, by hand, with no solver to lean on for that guarantee.

### 4.5 Testability assessment

- Individual move functions are unit-testable in isolation (given a small
  fixed state, assert a move produces the expected new state and that
  Class 1 invariants still hold afterwards).
- The lexicographic comparator is a pure function and trivially unit
  tested against hand-built tuples.
- What is **not** cleanly testable is solution *quality* in the way Design
  A's tests are (§3.5) — there is no way to assert "the solver found the
  true best-effort Tier 0 result" for a hand-built adversarial instance,
  only "the result is no worse than a previously-recorded baseline for this
  fixed seed set" (a regression/benchmark test, not a correctness proof).
  This is a meaningfully weaker testing story for exactly the property
  (§4.1's Class 2 handling) that matters most.
- Property-based testing (e.g. via the open-source `hypothesis` library)
  is a good fit for the move functions specifically — generating random
  small synthetic camps and asserting every move preserves Class 1
  invariants — and is recommended for both designs' shared validator, but
  it strengthens Design B's weaker area (implementation correctness of
  hand-written logic) more than it strengthens Design A's.

### 4.6 Functional correctness assessment

Design B always produces *a* schedule, and Class 1 constraints are
guaranteed with the same confidence as Design A (structural, by move-set
design, not by scoring). The gap is entirely on Class 2 and the objective
tiers: there is no proof that the reported best-effort result is actually
the best achievable, only that it's the best found within the compute
budget spent. In practice, at this scale and with generous restarts, it is
likely to get *close* to optimal — but "likely close" is a materially
weaker correctness statement than Design A's "provably optimal, or a
proven bound," and that gap is exactly what an organiser most needs to
trust when the algorithm reports "camper X couldn't get their priority
activity" — is that truly unavoidable, or did the search just not find the
way to give it to them?

## 5. Comparative analysis

| | Design A — CP-SAT | Design B — Simulated annealing |
|---|---|---|
| Functional correctness (Class 2 / best-effort) | Provably optimal per tier, or a proven gap | Best found within budget; no optimality guarantee |
| Lexicographic ranking (OQ-4) fidelity | Exact, by sequential solves | Exact *comparator*, but search may not reach the true optimum it's ranking towards |
| Feasibility detection (FR-30) | Definitive — Tier 0 optimum is the ground truth | Approximate — "best I found," possibly not the true minimum |
| Performance at NFR-1 scale, NFR-2 budget | Seconds–minutes; large headroom | Minutes–low hours across restarts; even larger headroom |
| Reproducibility (NFR-3) | Deterministic given seed/thread config | Deterministic per chain given seed |
| Configurability (NFR-4) | Config-driven tier order/weights, via solve sequencing | Config-driven tier order/weights, via tuple field order (slightly more direct) |
| Dependency footprint | `ortools` (large-ish native package, mature, Apache 2.0) | Standard library only (+ optional `numpy`) |
| Maintainability | Model reads as a translation of the requirements; needs some CP modelling fluency | Ordinary Python, debuggable step-by-step; repeats the current codebase's riskiest code shape (hand-written repair logic) |
| Testability | Strong — solver correctness tests are precise and solver-independent of search quality | Weaker on solution-quality claims; strong on move-level unit tests; benchmark/regression style needed for quality |
| Risk concentration | Getting the CP model (especially OQ-7's conditional constraint) right | Getting the move set and acceptance logic right, and staying confident it's not silently under-serving campers |

The scale and budget answers (OQ-1/OQ-2) remove what would traditionally be
the strongest argument for a metaheuristic — that an exact solver "won't
scale." At 500 campers and 50 sessions, it will; this is not the regime
where CP-SAT struggles. That leaves the comparison to turn almost entirely
on the OQ-4 ranking requirement and the correctness/testability profile in
§3.6/§4.6/§3.5/§4.5 — both of which favour Design A. Design B's genuine
advantages — a lighter dependency and a more "ordinary Python" debugging
experience — are real but narrower than they'd be at larger scale or under
a tighter time budget, where they might have been decisive instead.

It's also worth noting that the existing repository already contains an
abandoned attempt at something close to Design A
(`family_camp/schedule/timetable_cps.py`, per DESIGN.md §4) — this isn't a
new idea for this codebase, just one that was apparently never finished
rather than one that was tried and found wanting.

### A hybrid worth flagging, not required initially

CP-SAT accepts solution *hints*. A Design-B-style constructive heuristic
(even just the current `gen_seed_individual`-style greedy family-grouping
seed) could be used to warm-start Design A's solves, potentially shortening
solve time further. Given §3.2 shows solve time isn't a problem at this
scale, this isn't needed to meet NFR-2 — but it's a cheap option to keep in
mind if a much larger future camp changed the scale calculus.

## 6. Recommendation

**Build Design A (CP-SAT)**, on top of the shared domain model and
validator in §2 — which should be built first regardless, since it's valid
infrastructure either way and is where most of the direct requirements
traceability (FR-40/41, NFR-6/7) lives.

Rationale, in order of weight:

1. **OQ-4 essentially decides this analytically.** A strict objective
   ranking is far better served by a method that can prove it hasn't traded
   away a higher tier's optimum for a lower one, which is precisely what
   the sequential-solve design in §3.1 gives for free and §4.1's comparator
   can only approximate.
2. **The scale/budget answers remove the traditional counter-argument.**
   There is no realistic performance risk in choosing the exact method here
   (§3.2) — the usual reason to reach for a metaheuristic (an exact solve
   would take too long) doesn't apply at 500 campers / 50 sessions with a
   24-hour budget.
3. **Correctness and testability both favour it** (§3.5/§3.6 vs. §4.5/§4.6),
   specifically on the axis that matters most to organisers: being able to
   say, with proof rather than confidence, whether a camper's unmet
   priority activity was truly unavoidable.

Keep Design B's design in reserve as a documented alternative — its
move-set and lexicographic-comparator ideas remain useful either as a
CP-SAT warm-start heuristic (§5) or as a fallback if a future, much larger
camp ever pushes Design A outside its comfortable range — but there's no
reason to build it as the primary engine given the current requirements.
