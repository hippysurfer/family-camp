# Family Camp Scheduling Engine — Solver Architectures

This document describes the two solver implementations built to
[REQUIREMENTS.md](REQUIREMENTS.md): Design A (OR-Tools CP-SAT) and
Design B (simulated annealing). Both are fully implemented and
selectable at runtime via `--solver`; CP-SAT is the default. It closes
with guidance on when each is the better choice.

Requirement IDs (`FR-n`, `NFR-n`) refer to REQUIREMENTS.md throughout.

## 1. Scale and the objective-ranking requirement

Two facts shape both designs:

- **Scale and budget (NFR-1/NFR-2)**: up to 500 campers, 30 activities,
  50 sessions, with up to 24 hours wall-clock available. A boolean
  camper×session assignment matrix at this scale is at most 25,000
  variables — small-to-medium by the standards of modern
  constraint/optimisation solvers, the kind that typically solves to
  optimality or a tight, provable bound in seconds to low minutes, not
  hours.
- **Strict objective ranking (§4.2)**: the soft objectives must be
  *lexicographically* ranked, not combined into a single weighted score
  with an arbitrary trade-off — fully satisfy the first-ranked
  objective, then, among solutions tying on that, do as well as possible
  on the second, and so on.

At this scale, an exact method can afford to *prove* it has found the
lexicographically best (or best-effort) schedule, whereas a search
heuristic can only ever report "the best I happened to find." That
tension runs through both designs below.

## 2. Shared foundations (used by both designs)

Both designs sit on top of the same solver-independent core: building it
once is what makes FR-40/FR-41 (validate *any* candidate timetable,
generated or not) and NFR-6/NFR-7 (testable in isolation) hold
regardless of which solver produced the timetable, and keeps each
solver's own code limited to "how do I search for a good assignment"
rather than also re-deriving "what does a good assignment mean."

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
                     │  - Idle-slot reporting (FR-74)   │
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
input contract in REQUIREMENTS.md §3:

- `Activity.min_age: int | None` — lower age bound (FR-18). `None` means
  no restriction.
- `Camper.is_adult: bool` (derived from age) — used by the
  family-split supervision rule below.

### 2.2 Constraint classification

Not all hard constraints behave the same way under capacity pressure,
and telling them apart cleanly is what makes the best-effort behaviour
in FR-30/FR-31 tractable and explainable, in *either* design:

**Class 1 — structurally always satisfiable.** These can always be met by
simply *not* making an assignment, so there is never a capacity-driven
reason to break them. They are treated as absolute invariants in both
designs — never relaxed, never reported as "violated," full stop:

- FR-10 no double-booking
- FR-12 (max side) session over capacity
- FR-14 no unrequested activities
- FR-15 no duplicate activity per camper
- FR-18 age eligibility

**Class 2 — demand-driven, can genuinely conflict.** Whether these can all
be satisfied depends on how registration demand compares to capacity, so
real inputs may make them jointly infeasible. These are the ones FR-31
requires a best-effort account of:

- FR-13 every priority activity honoured
- FR-11 no family time-conflict
- FR-17 family-split supervision: when a family is split across sessions
  of the same activity, each session needs at least one adult and one
  child present, with an idle-adult exception for children-only sessions
- FR-24 minimising family splits (a split is never itself a hard
  violation, but is penalised so it's avoided when avoidable)
- FR-12 (min side) session under minimum occupancy
- FR-16 compulsory activities (supported; no real camp currently
  designates any)
- Per-camper/family custom constraints (§4.10) — hard ones join Class 1
  (structurally enforced via the same eligibility mechanism), soft ones
  join Class 2

This split matters for *functional correctness*, independent of which
solver is chosen: Class 1 constraints are guaranteed 100% of the time in
both designs, by construction, so correctness for the whole engine
really only hinges on how well each design handles Class 2 — that's
where the two designs genuinely differ.

### 2.3 Objective tiers

The validator exposes a fixed, ordered list of tiers rather than a
single score. `EngineConfig` supplies the order and weights (NFR-4 — the
"adjustable weighting" mechanism, expressed primarily as an *ordering*):

1. **Tier 0 — Class 2 violation minimisation.** A weighted sum within
   this tier, severity bands most severe first: soft custom-constraint
   violations, missing priorities, family-safety violations (time
   conflicts / poorly supervised splits), family-split occurrences,
   under-minimum sessions, unmet compulsory activities. Each band's
   default weight is ~1,000x the one below it, sized so no plausible
   number of lower-severity violations can numerically outweigh a
   single higher-severity one at NFR-1's scale. This tier is what
   FR-30/31 report on.
2. **Tier 1 — FR-20/FR-21: optional-request satisfaction.** Scored per
   camper as *fraction of their optional requests met* (0–1) and summed
   — this formula satisfies FR-21's fairness requirement by
   construction, since each camper contributes a comparable 0–1 value
   regardless of how many optional activities they asked for.
3. **Tier 2 — FR-22: even use of parallel sessions.** Population
   variance of occupancy across sessions of the same activity, minimised.

Idle time (§4.2) is not an objective tier — it's computed by the
validator purely for the post-hoc report (FR-74).

### 2.4 Violation/objective report (FR-40/FR-41)

A single validator function takes any `Timetable` (from either solver,
or hand-constructed in a test) and returns a structured report: per-rule
violation lists naming the specific camper/family/activity/session
involved, plus the Tier 1/2 scores. Both solvers' output is run through
this same function before being returned — an independent,
solver-agnostic correctness check on whatever a solver claims to have
produced.

## 3. Design A — Constraint Programming (OR-Tools CP-SAT)

**Library**: [Google OR-Tools](https://developers.google.com/optimization)
(`pip install ortools`), Apache 2.0 licensed. Uses its CP-SAT solver.

### 3.1 Approach

Model the problem declaratively: decision variables plus constraints plus
an objective, handed to a general-purpose solver — no hand-written search
procedure.

- **Decision variables**: `x[c, s]` boolean, camper `c` assigned to
  session `s`, for every `(c, s)` pair where `c` requested `s`'s activity
  (priority or optional) and is age-eligible, and no hard custom
  constraint (§4.10) forbids it. Pairs excluded by Class 1 rules are
  never created as variables at all — the model can't represent an
  invalid assignment, a stronger guarantee than "the objective
  discourages it."
- **Class 1 constraints**: a no-overlap constraint per camper (OR-Tools'
  interval/no-overlap machinery over each camper's assigned sessions),
  and a linear capacity constraint per session
  (`sum(x[c,s] for c) <= activity.limit`). Both are structural — there
  is no slack variable, so they can never appear in a solution.
- **Class 2 constraints**: modelled with **violation indicator
  variables** — e.g. `missing_priority[c, a]` is 1 if camper `c` isn't
  assigned any session of priority activity `a`. The family-split
  supervision rule (FR-17) is a set of reified boolean constraints per
  split session capturing "an adult is present", "a child is present",
  and the idle-adult exception. These indicators are what Tier 0's
  objective minimises — they're allowed to be 1, at a cost.
- **Lexicographic solving**: a **sequence of CP-SAT solves**, one per
  tier, each adding the previous tier's achieved optimum back in as a
  constraint before optimising the next tier:
  1. Solve minimising the Tier 0 weighted violation sum → optimum `V0`.
  2. Re-solve with `tier0_violation_sum == V0` added, now maximising Tier 1
     (sum of per-camper optional-satisfaction fractions, scaled to
     integers for CP-SAT) → optimum `O1`.
  3. Re-solve with both `tier0_violation_sum == V0` and
     `tier1_score == O1` added, minimising Tier 2 (session-occupancy
     spread) → final solution.

  Each phase is optimal *subject to* not giving up anything already won
  in an earlier phase — the most literal, provably-correct realisation
  of the "ranking, not weighting" requirement.
- **Best-effort / infeasibility (FR-30/31)**: there is no separate
  infeasible case to handle — Tier 0's violation-minimising solve *is*
  the best-effort behaviour. If `V0 == 0`, the schedule is fully
  feasible; if not, the same solve already found the fewest
  (severity-weighted) violations possible, and the indicator variables
  that ended up at 1 directly identify what to report per FR-31.
- **Output**: the assigned `x[c,s] == 1` pairs become a `Timetable`,
  passed through the shared validator (§2.4) before being returned —
  both as a correctness check on the model and to produce the
  human-readable report.

### 3.2 Performance against NFR-1/NFR-2

At 500 campers × 50 sessions with fairly sparse eligibility (a camper is
only a candidate for sessions of activities they actually requested and
are age-eligible for, not all 50), the core variable count is well under
the full 25,000 — realistically a few thousand. CP-SAT's model class here
— assignment with side constraints, no-overlap, and a bounded linear
objective — is squarely in its well-optimised territory; problems of this
size typically solve to proven optimality in seconds to a few minutes per
phase, comfortably inside the 24-hour budget with large headroom. If a
future, much larger camp changed that calculus, CP-SAT still degrades
gracefully: run with a time limit, it returns the best solution found so
far plus a provable optimality gap — an "I got this close, provably"
answer, not silence.

### 3.3 Reproducibility, configurability (NFR-3/NFR-4)

CP-SAT is deterministic for a fixed `random_seed` and fixed worker/thread
count — rerunning the same input and config reproduces the same solution
exactly. Tier order and Tier-0 severity weights live in `EngineConfig`,
not in code.

### 3.4 Maintainability and testability

The model *is* the specification — each constraint maps to one rule in
REQUIREMENTS.md, so reading the model-building function is reading a
fairly literal translation of the requirements. There's no custom
search/repair code to maintain. The model-building code is unit tested
the same way as any pure function: build a tiny synthetic instance, solve
it, assert on the returned `Timetable` via the shared validator — no
mocking of the solver needed, CP-SAT solves toy instances in
milliseconds. Class 2 behaviour is directly testable: construct a
deliberately over-subscribed toy instance and assert the solver reports
exactly the expected violations, in the expected severity order — a
precise regression test that reflects the true minimum, not just *a*
result. The three-phase sequential solve is a natural seam for
integration tests: phase 2's solution never regresses phase 1's achieved
`V0`, etc.

## 4. Design B — Simulated annealing with domain-aware moves

**Library**: standard library only (`random`, `math`,
`multiprocessing` for parallel restarts).

### 4.1 Approach

Maintain one evolving candidate `Timetable`, repeatedly propose a small
change, and accept or reject it, gradually reducing how often a
worse-scoring change is accepted (the annealing "temperature" schedule).

- **State**: the candidate `Timetable`, plus incrementally-maintained
  per-session occupancy counts and per-camper assigned-session lists, so
  a proposed move's effect on the score can be computed without
  rescanning the whole state.
- **Move set**: a domain-aware repair operator, not a generic bit-flip
  mutation:
  - Assign a family (filtered to age-eligible, activity-requesting
    members, and not forbidden by a hard custom constraint) into a
    session with room.
  - Move a family from one session instance to a parallel instance of the
    same activity.
  - Swap two families between two sessions.
  - Remove a family from an activity entirely (used when repairing an
    over-subscribed session).
  - A targeted "fix family-split supervision" move: if a split session
    is missing an adult or a child, try to move one in from elsewhere.
  - **Class 1 constraints are enforced as move preconditions, not scored
    outcomes**: a move that would create a double-booking, exceed a
    session's capacity, add an unrequested activity, or violate an age
    floor or hard custom constraint is never generated in the first
    place, rather than being generated and then penalised. This mirrors
    §2.2's classification directly in the algorithm and means Design B,
    like Design A, never needs to search its way back out of a Class 1
    violation — it's structurally excluded from the neighbourhood.
- **Scoring / acceptance**: each candidate move produces a **tuple**
  `(tier0_violation_score, -tier1_score, tier2_score)`, using the same
  severity ordering and tier definitions as §2.3 (the shared validator's
  scoring functions, not a separate reimplementation). Two states are
  compared **lexicographically** — element by element, not combined
  into a single scalar — so a move that improves Tier 0 is always
  preferred over one that only improves Tier 1, regardless of magnitude.
  The simulated-annealing temperature still applies: early on, a move
  that is lexicographically *worse* can be accepted with some
  probability (computed from how much worse, via the same severity
  weights used for reporting) to escape local optima; that probability
  decays to ~0 as the run cools.
- **Restarts**: many independent annealing chains run in parallel
  (`multiprocessing`) from different random seeds/starting
  constructions, keeping the lexicographically-best final state across
  all of them — the main lever Design B has for compensating for the
  fact that any single chain offers no optimality guarantee.
- **Best-effort / infeasibility (FR-30/31)**: whatever Tier 0 vector the
  best chain ends with *is* the best-effort report — the same
  structural shape as Design A, but with no proof that it's the
  *minimum* possible Tier 0 vector, only that it's the best found across
  all chains and restarts.

### 4.2 Performance against NFR-1/NFR-2

At this scale, a single annealing chain (a few thousand moves, each an
O(1)-ish incremental score update) runs in well under a second; running
many chains in parallel across restarts easily fits inside the 24-hour
budget with enormous headroom.

### 4.3 Reproducibility, configurability (NFR-3/NFR-4)

Every chain is seeded explicitly, so a specific chain's run is exactly
reproducible; the *overall* multi-chain result is reproducible as long
as the seed list and chain count are fixed. Tier order and severity
weights live in the same shared `EngineConfig` as Design A and plug
directly into the tuple comparator.

### 4.4 Maintainability and testability

No external solver dependency beyond the standard library. The
algorithm is ordinary imperative Python, steppable with a debugger.
Individual move functions are unit-testable in isolation (given a small
fixed state, assert a move produces the expected new state and that
Class 1 invariants still hold afterwards); the lexicographic comparator
is a pure function and trivially unit tested against hand-built tuples.
What is not cleanly testable is solution *quality* the way Design A's
tests are — there is no way to assert "the solver found the true
best-effort Tier 0 result" for a hand-built adversarial instance, only
"the result is no worse than a previously-recorded baseline for this
fixed seed set" (a regression/benchmark test, not a correctness proof).
Property-based testing (`hypothesis`) is a good fit for the move
functions specifically — generating random small synthetic camps and
asserting every move preserves Class 1 invariants.

## 5. Comparing the two

| | Design A — CP-SAT | Design B — Simulated annealing |
|---|---|---|
| Functional correctness (Class 2 / best-effort) | Provably optimal per tier, or a proven gap | Best found within budget; no optimality guarantee |
| Lexicographic ranking fidelity | Exact, by sequential solves | Exact *comparator*, but search may not reach the true optimum it's ranking towards |
| Feasibility detection (FR-30) | Definitive — Tier 0 optimum is the ground truth | Approximate — "best found," possibly not the true minimum |
| Performance at NFR-1 scale, NFR-2 budget | Seconds–minutes; large headroom | Minutes–low hours across restarts; even larger headroom |
| Reproducibility (NFR-3) | Deterministic given seed/thread config | Deterministic per chain given seed |
| Dependency footprint | `ortools` (large-ish native package, mature, Apache 2.0) | Standard library only |
| Maintainability | Model reads as a translation of the requirements; needs some CP modelling fluency | Ordinary Python, debuggable step-by-step; hand-written move/repair logic needs care to keep correct as it grows |
| Testability | Strong — solver correctness tests are precise and independent of search quality | Weaker on solution-quality claims; strong on move-level unit tests; benchmark/regression style needed for quality |

Both are viable at this scale and budget — the choice mostly comes down
to whether provable optimality matters for a given run.

CP-SAT also accepts solution *hints*: a Design-B-style constructive
heuristic (its own greedy seed construction) could warm-start Design A's
solves if a much larger future camp ever made solve time a concern —
not needed today (§3.2).

## 6. Which to use

`--solver cp_sat` (the default) is the right choice for a real camp's
final schedule: it either proves the result optimal per tier, or proves
how far from optimal it is, which is what an organiser needs to trust an
answer like "camper X couldn't get their priority activity" — genuinely
unavoidable, or just not found. `--solver annealing` is useful when
`ortools` isn't available, or for quick iteration during development
(no native dependency, easy to step through), accepting that its result
carries no optimality guarantee.
