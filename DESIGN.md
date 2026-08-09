# Family Camp Scheduler — Design Document

## 1. Overview

This repository is a scheduling tool built for a UK Scout Group's "Family
Camp" weekend. Given a list of registered campers/families and the
activities they've asked to do, it produces a timetable that assigns every
camper to activity sessions across the weekend, then renders that timetable
into printable outputs for the organisers and for each family.

Note: the package entry point is `family_camp/schedule/__main__.py`, not
`family_camp/__main__.py`. `family_camp/__init__.py` re-exports `main` from
`family_camp.schedule.__main__` (via `family_camp/schedule/__init__.py`), so
`python -m family_camp.schedule` (or the `schedule.py` wrapper at the repo
root) is the actual invocation.

### 1.1 Pipeline

```
Google Sheet (camper registrations + activity preferences)
        │  fetch_data.py (fetch_data.fetch)
        ▼
.cache.pickle (raw worksheet rows, local cache)
        │  deep.get_source_data()
        ▼
generate_schedule.py  ──runs a genetic algorithm──▶  CSV timetable + text reports
        │
        │  (organiser can hand-edit the CSV)
        ▼
check_schedule.py  ──re-validates an edited CSV, regenerates the reports
        │
        ▼
print_schedule.py / schedule_printer.py  ──renders a PDF grid timetable (A3 landscape or letter)
        │
        ▼
family_camp/pack/family2pdf.py  ──renders a per-family PDF from the CSV plus a general info pack
```

### 1.2 CLI

`family_camp/schedule/__main__.py:main()` uses `docopt` to expose three
subcommands:

- `generate <outdir>` / `generate <timetable> <outdir>` — run the scheduler,
  optionally seeded from an existing timetable CSV.
- `check <timetable> <outdir>` — reload and re-validate a (possibly
  hand-edited) timetable CSV, producing the same text reports as `generate`.
- `print <timetable> <pdf_out_file>` — render a timetable CSV to a PDF grid.

### 1.3 Package layout

| File | Purpose |
|---|---|
| `family_camp/schedule/__main__.py` | CLI entry point, dispatches to the three subcommands. |
| `family_camp/schedule/deep.py` | Core domain model, GA operators (seed/mutate/mate/evaluate), fitness/goodness/bestness scoring, text report generation, data loading. |
| `family_camp/schedule/generate_schedule.py` | Wires up the DEAP toolbox and runs `eaSimple` to produce a new timetable. |
| `family_camp/schedule/check_schedule.py` | Loads and re-validates an existing CSV timetable without running the GA. |
| `family_camp/schedule/print_schedule.py` | Loads a CSV timetable and renders it to PDF via `schedule_printer`. |
| `family_camp/schedule/schedule_printer.py` | Extracts structured schedule data and renders it as text or a multi-page ReportLab PDF (A3 landscape / letter). |
| `family_camp/schedule/utils.py` | Shared time-overlap helpers (`sessions_overlap`, `get_overlapping_sessions`). |
| `family_camp/schedule/fetch_data.py` | Pulls the three worksheets from Google Sheets and writes `.cache.pickle`. |
| `family_camp/schedule/google_.py` | Thin `gspread`/`oauth2client` wrapper for Sheets auth (with an effectively disabled retry helper — see §3). |
| `family_camp/schedule/timetable_cps.py` | **Unused** experimental alternative scheduler built on Google OR-Tools CP-SAT — see §4. |
| `family_camp/pack/family2pdf.py`, `gen_info_pack.py`, `pad_pdf.py` | Per-family PDF generation and PDF padding/merging for double-sided printing. |
| `family_camp/test/*` | Not a real test suite — see §3.4. |

## 2. How the schedule is currently generated

### 2.1 Approach: a genetic algorithm, not a constraint solver

The live scheduling path uses the [DEAP](https://deap.readthedocs.io/)
genetic algorithm library, driven by `deap.algorithms.eaSimple`
(`generate_schedule.py:111-116`). It is *not* a constraint solver — there's
no guarantee of feasibility, only a fitness function that is progressively
improved by mutation and selection over many generations.

### 2.2 Chromosome representation

A candidate timetable ("individual") is a flat `list[bool]` of length
`len(sessions) * len(campers)`: a session-major bitmap where element
`session_idx * len(campers) + camper_idx` is `True` if that camper is
assigned to that session (`deep.py:Individual.__init__`, lines 136–159).
`Individual` wraps this raw list together with derived structures —
`SessionInst` objects (a session bound to its actual assigned campers),
a `session_inst_map`, and a cached map of which sessions overlap in time
(`overlapping_sessions_map`, also stashed as a **class attribute**,
`deep.py:134,152-155` — see §3.1).

### 2.3 GA configuration

`generate_schedule.setup_toolbox()` (`generate_schedule.py:44-67`) registers:

- **Population**: 2000 individuals (`tools.initRepeat(..., n=2000)`, line 54).
- **Selection**: tournament selection, tournament size 20 (`tools.selTournament`, line 60).
- **Crossover probability**: `cxpb=0.2` (`generate_schedule.py:113`) — but see §3.1, the crossover operator is a no-op.
- **Mutation probability**: `mutpb=0.5` (`generate_schedule.py:113`).
- **Generations**: `ngen=30000` (`generate_schedule.py:113`), with no convergence/early-stopping criterion — it always runs the full 30000 generations (or until interrupted).
- **Hall of Fame**: the 100 best individuals seen are tracked (`MyHallOfFame`, size 100, `generate_schedule.py:91`) and written to disk on exit.
- **Fitness weights**: `(5.0, -2.0, -1.0)` applied to the 3-tuple described in §2.6 (`generate_schedule.py:46`).
- Fitness evaluation is parallelised across a `multiprocessing.Pool` (`generate_schedule.py:65-66`); an alternative `scoop`-based distributed map is present but commented out due to a Python 3.10 compatibility issue (`generate_schedule.py:13-23`).

### 2.4 Seeding the initial population

`gen_seed_individual()` (`deep.py:785-856`) builds each starting individual
session-by-session: for each session, campers are considered in order and
admitted with a weighted coin-flip — 3/4 probability if the activity is one
of their stated priorities, 1/4 probability if it's a lower-priority "other"
request. Whenever a camper is admitted, their whole family/group (limited to
members who also want the activity) is pulled in together if there's room,
so the seed already tends to avoid split families. `generate` can
additionally be seeded from an existing timetable CSV via
`individual_from_list()` (`generate_schedule.py:78-87`, `deep.py:432-487`).

### 2.5 Mutation — the actual search driver

`mutate()` (`deep.py:641-782`) is a domain-aware repair operator, not a
generic bit-flip. It runs a random number (0–100) of perturbation steps per
call; each step:

1. Picks a random session and a random camper who wants that session's activity.
2. Moves that camper's whole family/group into the session, first removing them from any other session of the same activity.
3. Finds every session that time-overlaps the newly-assigned session and evicts the family from any of them.
4. For each eviction, tries to re-place the family into another instance of the clashing activity that has room and doesn't itself clash with the family's schedule.

Because crossover is disabled (§2.6), this mutate-and-repair step is the sole
mechanism driving the search — the algorithm behaves as mutation-only
stochastic local search/hill-climbing dressed up in DEAP's GA machinery.

### 2.6 Crossover, fitness, goodness, bestness

- **Crossover** — `mate()` (`deep.py:859-900`) is meant to swap families'
  schedules between two individuals, but the entire body is commented out
  (lines 863–898); it just returns `(ind1, ind2)` unchanged. `cxpb=0.2`
  therefore has no observable effect.
- **Fitness** — `Individual.fitness()` (`deep.py:258-338`) counts constraint
  *violations* (starting from 1, higher is worse): a camper double-booked
  into overlapping sessions, a family split across overlapping sessions, a
  session over its `Activity.limit`, a session under its `Activity.min` once
  non-empty, a camper missing one of their priority activities, a camper
  doing an activity they never requested, and a camper duplicated into the
  same activity twice.
- **Goodness** — `Individual.goodness()` (`deep.py:340-382`) is a soft
  objective: the weighted percentage of each camper's "other" (nice-to-have)
  requests that were satisfied, weighted to favour campers who asked for
  fewer extras.
- **Bestness** — `Individual.bestness()` (`deep.py:384-395`) is the
  population variance of session sizes, favouring an even spread of campers
  across sessions.
- **Evaluate** — `evaluate()` (`deep.py:630-637`) combines these into the
  3-tuple `(1/fitness, 1/goodness, 1/bestness-or-0)` that DEAP scores against
  the `(5.0, -2.0, -1.0)` weights from §2.3.

### 2.7 Constraints enforced

- No camper double-booked across time-overlapping sessions.
- No family/group split across overlapping sessions.
- Session size within `[Activity.min, Activity.limit]`.
- Every camper's priority (must-do) activities are scheduled for them.
- Campers are not scheduled into activities they never requested.
- No camper duplicated into the same activity twice.
- Soft: maximise satisfaction of "other" (nice-to-have) requests.
- Soft: even spread of camper counts across sessions.
- Latent/unused: a `COMPULSARY_ACTIVITIES` list exists for activities every
  camper must attend, but is currently set to `[]` in the live code
  (`deep.py:27`).

### 2.8 Output

On completion, exception, or interruption (a background thread lets an
operator press Enter on stdin to force a dump mid-run,
`generate_schedule.py:101-108`), `MyHallOfFame.dump_to_dir()`
(`deep.py:515-546`) writes, for each of the top individuals, a timestamped
CSV timetable plus text reports: overall fitness/goodness, per-hour
idle-camper/idle-family listings (useful for staffing), per-family
schedules, and per-activity/session rosters against capacity
(`print_individual()`, `deep.py:907-1047`).

## 3. Critical review

### 3.1 Correctness-affecting issues

- **Crossover is a no-op.** `mate()`'s real family-swap logic is entirely
  commented out (`deep.py:863-898`), so despite `cxpb=0.2` being passed to
  `eaSimple`, no recombination between individuals ever happens. This is
  effectively mutation-only local search, not a genetic algorithm — either
  restore/redesign a working crossover, or (better) stop paying DEAP's
  population/crossover overhead and adopt an algorithm that matches what's
  actually running (see §4).
- **Fitness sign conventions are non-obvious and inconsistently applied.**
  `fitness()` returns a violation *count* (lower is better), but `evaluate()`
  inverts it to `1/count` before applying DEAP's `(5.0, -2.0, -1.0)` weights.
  `goodness()` and `bestness()` go through similar inversions. The intent is
  never documented, and the throwaway script `test_schedule.py:265` uses
  different weights, `(5.0, -2.0, 1.0)` — the sign on the third term
  disagrees with the production value in `generate_schedule.py:46`. This
  should be documented explicitly (a short comment or table mapping
  "smaller/bigger is better" to each weight sign), and the inconsistency
  between the two files should be resolved so it's clear which is
  authoritative.
- **Shared mutable class attribute risks cross-instance bugs.**
  `Individual.__overlapping_sessions_map__` is a class attribute
  reassigned (not merged) in every `__init__` (`deep.py:134,152-155`). The
  code relies on the invariant that `sessions` never differs between
  `Individual` instances in the same process; if that invariant is ever
  violated (e.g. by future code that mixes timetables from different
  session sets), individuals would silently use another individual's overlap
  map. Recommend making this a per-instance attribute, or explicitly
  documenting/asserting the invariant.

### 3.2 Robustness

- **Broad exception swallowing at import time.**
  `generate_schedule.py:69-73` wraps data loading and toolbox setup in a
  bare `try/except Exception` that just prints "Can't load data. Probably
  fetching fresh." — any error (missing cache, malformed sheet data, a
  genuine bug) is silently hidden behind the same message, making failures
  hard to diagnose. This should log the actual exception and only swallow
  the specific "cache file missing" case.
- **Unguarded `IndexError` risk.** `timetable_from_list()` and
  `individual_from_list()` (`deep.py:401-487`) look up campers/sessions by
  filtering a list and indexing `[0]`; `individual_from_list` at least logs
  before this in some branches, but an empty match still raises a raw
  `IndexError` rather than a clear error. Since these functions parse
  hand-edited CSVs (`check`/`generate <timetable>`/`print`), a typo in the
  CSV currently produces a stack trace instead of an actionable message.
- **Retry logic is effectively disabled.** `google_.retry()`
  (`google_.py:24-79`) has its actual retry-on-failure body commented out,
  and `MAX_ATTEMPTS = 1` (`google_.py:13`) means the loop only ever runs
  once regardless. The abstraction exists but does not retry — either
  restore it or remove the dead machinery so the code isn't misleading.
- **Hardcoded 2-day assumption.** `print_individual()` asserts
  `len(start_days) == 2` (`deep.py:919`). Any change to the camp's length
  (e.g. a 3-day event) would hard-crash report generation.

### 3.3 Maintainability

- **Duplicated, drifted domain model.** `timetable_cps.py` (unused, see §4)
  reimplements `Activity`/`Camper`/`Session`/`Group` and the worksheet
  column-index parsing found in `deep.py`, but the two have drifted: e.g.
  `timetable_cps.py:11` still has
  `COMPULSARY_ACTIVITIES = ["Saturday Lunch", "Sunday Lunch", "Saturday BBQ"]`
  while `deep.py:27` has emptied it to `[]`. Since it's dead code, either
  delete it or clearly mark it as an archived prototype (see §4).
- **Literal duplicate code in `schedule_printer.py`.** The file defines
  `class NumberedCanvas` twice (once around line 166, again around line 219)
  with duplicated imports interleaved between them (`schedule_printer.py:1-9`,
  `159-163`, `202-213`) — evidence of the A3-landscape feature being pasted
  in alongside the original letter-format code rather than merged. This
  should be consolidated into a single implementation parameterised by page
  size.
- **Hardcoded absolute developer paths.** `timetable_cps.py:302`
  (`/home/rjt/Devel/Personal/Cubs/family_camp/profile.txt`),
  `print_schedule.py:17` (default `timetable`/`out_file` arguments point at
  `/home/rjt/Devel/Personal/Cubs/family_camp/2026_schedule.csv`), and
  `re_process.sh:5` (`root="/home/rjt/Devel/Personal/Cubs/family_camp/family_camp"`)
  all bake in one developer's machine layout. These should be CLI arguments
  or environment-derived, with no hardcoded default.
- **No `pyproject.toml`/`setup.py`.** The package isn't pip-installable; it
  relies on `PYTHONPATH` and being run from the repo root. `Pipfile`/
  `requirements.txt` are also incomplete — `numpy`, `PyPDF2`, and `splinter`
  are imported but not listed as dependencies, and `ortools` (used only by
  the unused `timetable_cps.py`) is similarly absent.
- **Stale Python version pin.** `Pipfile` pins `python_version = "3.7"`,
  but `generate_schedule.py:13` carries a workaround comment for a Python
  3.10-specific deprecation — the pin should be updated to reflect what's
  actually being run.
- **Magic numbers everywhere.** Population size (2000), generation count
  (30000), crossover/mutation probabilities (0.2/0.5), tournament size (20),
  Hall of Fame size (100), and the mutation step count (`randrange(0, 100)`,
  `deep.py:660`) are all hardcoded in the source rather than exposed via CLI
  flags or a config file, making it slow to experiment with tuning.

### 3.4 Testing and CI

There is no automated test coverage for the scheduling algorithm itself.
`family_camp/test/deap_test.py` is a DEAP tutorial script with no
assertions; `family_camp/test/test_schedule.py` is a runnable copy of
production code with hardcoded toy data and no test framework; `
test_register_family.py`/`test_pay_for_camp.py` are Selenium/`splinter`
browser scripts against the live public booking form and PayPal checkout —
unrelated to the scheduler. There's no `pytest` configuration and no CI
workflow. Given the core logic here (fitness scoring, mutation repair,
CSV round-tripping) is exactly the kind of thing unit tests are good at —
pure functions over small synthetic activity/camper/session fixtures —
this is a meaningful gap; a focused test suite around `Individual.fitness()`,
`mutate()`, and the CSV round-trip functions would catch regressions like
the sign-convention issue in §3.1 automatically.

### 3.5 Security/hygiene

`family_camp/test/test_pay_for_camp.py:21` hardcodes a plaintext PayPal
account password (`PP_PASSWD = "ZdIcQM9L2Qfl"`). Even if this targets a
sandbox/test PayPal account, committing credentials in source is bad
practice and should move to an environment variable or local secrets file
excluded from version control.

## 4. Alternative approaches

The underlying problem is a constrained assignment problem: assign each
camper to a subset of activity sessions such that no camper/family has
overlapping sessions, session capacities are respected, and preference
satisfaction is maximised. Several approaches were or could be used to
solve this instead of the current GA:

- **Constraint Programming (Google OR-Tools CP-SAT).** The repository
  already contains an abandoned prototype of this,
  `family_camp/schedule/timetable_cps.py`. It builds a boolean CP model over
  `activity × session × group` and calls `find_timetable()`
  (`timetable_cps.py:272`+) to solve for a feasible/maximal assignment,
  using `possible_family_arrangements_for_activity()`
  (`timetable_cps.py:159`) to precompute valid family/session combinations
  under capacity limits. It's not wired into the CLI, has its own duplicated
  and drifted data model (§3.3), hardcodes a developer's absolute path
  (`timetable_cps.py:302`), and runs against synthetic test data at import
  time rather than the real Google Sheet (`gen_test_data()`,
  `timetable_cps.py:509-510`). Pros of this approach: CP-SAT gives exact
  feasibility guarantees and typically converges far faster than a GA for a
  problem of this size (one weekend, a few hundred campers, a few dozen
  activities); hard constraints like capacity and no-overlap map directly
  onto CP-SAT's native constraint types instead of being expressed as
  fitness penalties. Cons: expressing *soft*, weighted preferences (the
  "goodness"/"bestness" objectives) is less natural in CP-SAT than in a
  fitness function — it requires an explicit multi-objective or weighted-sum
  formulation, and the model needs to be re-derived if constraints change
  shape.
- **Integer/Mixed-Integer Linear Programming (MILP).** Model as a 0/1
  assignment problem: one binary variable per (camper, session), linear
  inequalities for capacity (`sum over campers in session <= limit`) and
  no-overlap (mutually exclusive overlapping sessions per camper), and a
  linear objective combining priority satisfaction and "other" preference
  satisfaction. Solvable with open tools like PuLP + CBC, or OR-Tools' own
  MILP interface. Similar tradeoffs to CP-SAT — exact and fast for this
  problem size, but soft objectives and the "keep families together" rule
  need explicit linear encoding (e.g. auxiliary variables tying family
  members' assignments together).
- **Greedy/heuristic construction plus local repair.** Sort campers by how
  constrained they are (fewest viable session options, or highest number of
  priority requests) and greedily assign each to the best available session,
  then run a bounded local-repair pass to fix any residual clashes/capacity
  violations. This is essentially what `gen_seed_individual()` already does
  as a *seed* for the GA — it could stand alone as the whole algorithm. Much
  simpler to reason about, debug, and unit test than a population-based GA;
  the tradeoff is that pure greedy construction is more prone to getting
  stuck in a poor local optimum without the (currently disabled) exploration
  crossover was meant to provide.
- **Simulated annealing / hill-climbing on a single solution.** Since
  crossover is a no-op (§3.1), the current algorithm is already,
  functionally, mutation-only local search wrapped in DEAP's population/
  generation machinery. Making that explicit — dropping the 2000-individual
  population and `eaSimple` in favour of a single evolving solution with an
  annealing acceptance criterion (accept worsening moves with a probability
  that decreases over time) — would likely be simpler to implement, easier
  to reason about, and cheaper to run, while keeping the existing
  domain-aware `mutate()` repair operator largely as-is.
- **Keep the genetic algorithm, but fix it.** If population-based search is
  still wanted (e.g. because it's easier to parallelise across many
  candidate solutions, or historically was chosen deliberately), the
  concrete fixes are: implement a real crossover operator (the commented-out
  family-swap logic in `mate()` is a reasonable starting point), make
  population size/generation count/rates configurable, and replace the fixed
  `ngen=30000` with a convergence-based stopping criterion (e.g. stop after
  N generations with no Hall-of-Fame improvement).

**Recommendation:** given the problem size (one weekend, a bounded number of
campers and activities) and that a CP-SAT prototype already exists in this
repository, reviving and finishing `timetable_cps.py` — merging its data
model back into `deep.py` rather than maintaining a duplicate, and adding an
explicit weighted-preference objective — is likely to produce a scheduler
that is both faster and easier to reason about ("did it fail because it's
genuinely infeasible, or because search didn't converge?") than the current
GA. The main factor weighing against a full CP/MILP rewrite is how much the
camp organisers value being able to hand-tweak the fitness weighting
intuitively (the current `fitness`/`goodness`/`bestness` split, however
confusingly signed, is at least conceptually simple); any replacement should
preserve an equally accessible way to express "priority activities must be
met, nice-to-haves are best-effort."
