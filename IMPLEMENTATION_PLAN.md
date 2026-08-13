# Family Camp Scheduling Engine — Implementation Plan

This plan turns [DESIGN_OPTIONS.md](DESIGN_OPTIONS.md) into an ordered
sequence of small, independently-committable steps for building **both**
Design A (OR-Tools CP-SAT) and Design B (simulated annealing) behind a
single CLI, in a new top-level directory: **`family_camp2/`**.

It is written to be executed by a coding agent one step at a time, in
order, with a git commit after every step whose tests pass.

## 0. Ground rules (read before starting)

- **Clean start.** `family_camp2/` does not exist yet. Step 1 creates it.
  Nothing under the existing `family_camp/` package, or root-level files
  (`schedule.py`, `refresh_data.py`, `Pipfile`, etc.), is read, imported, or
  modified by any step in this plan — `family_camp2` is fully additive and
  self-contained. The one intentional exception is Step 10, which reads the
  **file format** already produced by `family_camp/schedule/fetch_data.py`
  (`.cache.pickle`) — as a data contract, not a code dependency.
- **One step at a time.** Do not combine steps into one commit, and do not
  start step *N+1* until step *N* is committed. If a step's tests reveal a
  problem in an earlier module, fix that module as part of the *current*
  step (don't rewrite history) and note the deviation in the commit
  message.
- **Every step ends with a green test suite, then a commit.** The protocol
  for each step is always:
  1. Implement the changes described.
  2. Add/update the pytest tests described.
  3. Run the **entire** `family_camp2` test suite (not just the new tests)
     and confirm it's green.
  4. Check off this step's box below (`- [ ]` → `- [x]`) in this file.
  5. `git add family_camp2 IMPLEMENTATION_PLAN.md` and commit with message
     `family_camp2 step NN: <short summary>` (see each step's suggested
     message).
  6. Only then move to the next step.
- **Environment**: Python ≥3.11, a dedicated virtual environment inside
  `family_camp2/` (`family_camp2/.venv/`, gitignored), installed editable:
  `cd family_camp2 && python -m venv .venv && source .venv/bin/activate &&
  pip install -e ".[dev]"`. Every step after Step 1 assumes this
  environment is active and tests are run with `pytest` from inside
  `family_camp2/`. Use /usr/local/opt/python3/bin/python3 to make the virtual env.
- **No solver-specific dependency until it's needed.** `ortools` is only
  added to `pyproject.toml` in Step 12; nothing before that needs it.
  Everything else uses only the standard library plus `pytest` (and
  `hypothesis` from Step 21 on).
- **Requirement traceability.** Steps reference `FR-n`/`NFR-n`/`OQ-n` from
  REQUIREMENTS.md and the Class 1/Class 2/Tier framework from
  DESIGN_OPTIONS.md §2 throughout — that section is required reading before
  Step 3.

## 1. Target layout (end state after Step 22)

```
family_camp2/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/family_camp2/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── domain.py
│   ├── io/
│   │   ├── __init__.py
│   │   ├── json_loader.py
│   │   └── legacy_cache_loader.py
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── class1.py
│   │   ├── class2.py
│   │   ├── tiers.py
│   │   ├── idle.py
│   │   ├── report.py
│   │   └── validator.py
│   └── solvers/
│       ├── __init__.py
│       ├── base.py
│       ├── registry.py
│       ├── cp_sat.py
│       └── annealing/
│           ├── __init__.py
│           ├── moves.py
│           ├── scoring.py
│           ├── seed.py
│           └── solver.py
└── tests/
    ├── conftest.py
    ├── fixtures.py
    └── test_*.py   (one or more per step, named below)
```

## 2. Step list

### - [x] Step 1: Project scaffold

**Goal**: A pip-installable, empty-but-real package with a working test
runner and a CLI stub that already exposes the `--solver` argument shape
(with no solvers registered yet).

**Add**:
- `family_camp2/pyproject.toml` — project metadata, `requires-python = ">=3.11"`,
  build backend (`setuptools` + `src` layout is fine), a `[project.optional-dependencies] dev = ["pytest"]`.
- `family_camp2/.gitignore` — `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`.
- `family_camp2/src/family_camp2/__init__.py` — package version constant only.
- `family_camp2/src/family_camp2/cli.py` — `build_parser()` returning an
  `argparse.ArgumentParser` with a **required** `--solver` argument,
  `choices=["cp_sat", "annealing"]`, and `main(argv=None)` that parses args
  and currently just prints the resolved solver choice (real dispatch
  arrives in Step 11).
- `family_camp2/src/family_camp2/__main__.py` — `if __name__ == "__main__":
  raise SystemExit(cli.main())`.
- `family_camp2/tests/conftest.py` — empty for now (placeholder for shared
  fixtures added later).
- `family_camp2/tests/test_cli_smoke.py` — asserts `build_parser()` accepts
  `--solver cp_sat` and `--solver annealing`, rejects `--solver bogus`
  (via `SystemExit`/`argparse.ArgumentError`), and rejects missing
  `--solver` entirely.

**Commit message**: `family_camp2 step 01: project scaffold and CLI argument stub`

---

### - [x] Step 2: Domain model

**Goal**: The core data types every later step builds on.

**Add** `src/family_camp2/domain.py`:
- `Activity` (frozen dataclass): `name: str`, `duration: timedelta`,
  `min_occupancy: int`, `max_occupancy: int`, `min_age: int | None = None`
  (OQ-8).
- `Session` (frozen dataclass): `activity: Activity`, `label: str`,
  `start: datetime`; `end` as a computed `@property` (`start + activity.duration`).
  Needs a stable identity for use in sets/dicts — derive equality/hash from
  `(activity.name, label, start)`, not object identity.
- `Camper` (frozen dataclass): `name: str`, `family_id: str`, `age: int`,
  `age_group: str`, `priorities: tuple[Activity, ...]`, `optional: tuple[Activity, ...]`;
  `is_adult` as a computed `@property` (`age >= 18`).
- `Assignment` — `NamedTuple` or frozen dataclass of `(camper: Camper, session: Session)`.
- `Timetable` — wraps a `frozenset[Assignment]` plus indexes built once at
  construction: `sessions_for_camper: dict[Camper, set[Session]]`,
  `campers_for_session: dict[Session, set[Camper]]`. Provide `with_assignment`
  /`without_assignment` methods returning a **new** `Timetable` (keep it
  immutable — later steps, especially Step 16's move primitives, benefit
  from not having to reason about shared mutable state accidentally
  leaking between candidate solutions).

**Tests** (`tests/test_domain.py`):
- `Session.end` derives correctly from `start + activity.duration`.
- `Camper.is_adult` is correct at the 18-year boundary (17 → False, 18 → True).
- Two `Session` instances with the same `(activity, label, start)` compare
  equal and hash equal even if constructed separately (needed so sessions
  loaded twice — e.g. once in the model, once in a test fixture — behave
  as the same key).
- `Timetable.with_assignment` / `without_assignment` return a new object,
  leave the original unchanged, and keep both indexes consistent with the
  assignment set.

**Commit message**: `family_camp2 step 02: domain model (Activity, Session, Camper, Timetable)`

---

### - [x] Step 3: Class 1 structural validators

**Goal**: Pure functions that detect the constraints DESIGN_OPTIONS.md §2.2
classifies as "Class 1" — never supposed to occur in *any* output, from
either solver. These exist as an independent safety net, not as something
either solver "tries" to satisfy.

**Add** `src/family_camp2/validation/class1.py`:
- `sessions_overlap(a: Session, b: Session) -> bool`.
- `find_double_bookings(timetable) -> list[...]` — FR-10.
- `find_capacity_overflows(timetable) -> list[...]` — FR-12 (max side only; min side is Class 2, Step 4).
- `find_unrequested_assignments(timetable) -> list[...]` — FR-14.
- `find_duplicate_activity_assignments(timetable) -> list[...]` — FR-15.
- `find_age_ineligible_assignments(timetable) -> list[...]` — OQ-8.
- `check_class1(timetable) -> Class1Report` — aggregates all of the above
  into one structured, named result (empty lists = clean).

**Tests** (`tests/test_class1.py`): one deliberately-broken fixture per
rule (e.g. two overlapping sessions assigned to the same camper) asserting
the corresponding `find_*` function reports it with the right identifying
detail (camper/session), and a clean fixture asserting `check_class1`
returns all-empty.

**Commit message**: `family_camp2 step 03: Class 1 structural constraint checks`

---

### - [x] Step 4: Class 2 violation detection + Tier 0 scoring

**Goal**: The demand-driven rules that *can* conflict, plus the weighted
Tier 0 score used for best-effort ranking (FR-30/31).

**Add** `src/family_camp2/validation/class2.py`:
- `find_missing_priorities(timetable, campers) -> list[...]` — FR-13.
- `find_family_time_conflicts(timetable) -> list[...]` — FR-11 core rule
  (two members of a family in different, overlapping sessions).
- `find_unsupervised_family_splits(timetable) -> list[...]` — OQ-7
  refinement: for every family/activity where the family's assigned
  sessions of that activity are non-overlapping (i.e. not already flagged
  by the rule above), each such session must contain at least one adult
  from that family; report the ones that don't.
- `find_under_minimum_sessions(timetable, activities) -> list[...]` — FR-12
  (min side).
- `find_unmet_compulsory_activities(timetable, campers, compulsory: set[Activity]) -> list[...]` — FR-16 (empty `compulsory` set by default, per OQ-5).
- `Tier0Weights` (dataclass with a default severity ordering: priority-unmet
  > family-conflict/unsupervised-split > under-minimum > compulsory-unmet —
  documented as configurable, wired to real config in Step 7).
- `score_tier0(report, weights) -> int` — weighted sum.

**Tests** (`tests/test_class2.py`): one fixture per rule showing it fires
correctly; specifically include the OQ-7 case (a family split across two
non-overlapping sessions of the same priority activity, one with an adult
and one without — assert only the unsupervised one is flagged); a
capacity-vs-demand fixture where `score_tier0` is computed by hand and
compared against the function's output.

**Commit message**: `family_camp2 step 04: Class 2 violation detection and Tier 0 scoring`

---

### - [x] Step 5: Tier 1 & Tier 2 scoring, idle-time report

**Goal**: The remaining objective tiers (FR-20/21/22) and the FR-23
reporting-only idle-time feature (per OQ-3: report, don't optimise).

**Add** `src/family_camp2/validation/tiers.py`:
- `score_tier1(timetable, campers) -> float` — sum over campers of
  `|optional ∩ assigned| / |optional|` (0 if `optional` is empty, contributes
  1 by convention so a camper with no optional requests doesn't drag the
  score down) — satisfies FR-21 by construction per DESIGN_OPTIONS.md §2.3.
- `score_tier2(timetable, activities) -> float` — population variance of
  occupancy across sessions sharing an activity, summed/averaged across
  activities that have more than one session (activities with only one
  session contribute 0 — there's nothing to spread).

**Add** `src/family_camp2/validation/idle.py`:
- `find_idle_slots(timetable, campers, sessions, granularity: timedelta) -> IdleReport`
  — for each time bucket where at least one session runs, list campers/
  families with no assignment overlapping that bucket. Pure port of the
  *intent* of the current system's idle-time report (DESIGN.md §2.8), not
  its 2-day-hardcoded implementation (FR-3/NFR-5: no fixed camp-length
  assumption).

**Tests** (`tests/test_tiers.py`, `tests/test_idle.py`): hand-computed
expected scores on small fixtures (including the zero-optional-requests
edge case for Tier 1, and the single-session-activity edge case for Tier
2); an idle-report fixture with a known idle camper at a known time bucket.

**Commit message**: `family_camp2 step 05: Tier 1/Tier 2 scoring and idle-time reporting`

---

### - [x] Step 6: Unified validator façade + human-readable report

**Goal**: The single entry point required by FR-40/41 — works on *any*
`Timetable`, generated by either solver or hand-built in a test.

**Add** `src/family_camp2/validation/report.py`:
- `ValidationReport` dataclass bundling: `class1: Class1Report`,
  `class2: Class2Report`, `tier0_score`, `tier1_score`, `tier2_score`,
  `idle: IdleReport`.
- `render_text(report: ValidationReport) -> str` — human-readable rendering
  naming specific campers/families/activities/sessions per FR-41.

**Add** `src/family_camp2/validation/validator.py`:
- `validate(timetable, activities, sessions, campers, tier0_weights, compulsory) -> ValidationReport`
  — calls everything from Steps 3–5 and assembles the result. This is the
  function both solvers (and any future tool) call — no solver-specific
  code appears in this module.

**Tests** (`tests/test_validator.py`): one full end-to-end fixture (a
handful of campers/activities/sessions with at least one Class 2 violation
and a known Tier 1/2 score) asserting the full `ValidationReport` matches
expectations, and that `render_text` mentions the specific camper/activity
involved in the violation (not just a count).

**Commit message**: `family_camp2 step 06: unified validator façade (FR-40/FR-41)`

---

### - [x] Step 7: Configuration schema

**Goal**: NFR-4's "adjustable without code changes" — objective tier order,
Tier 0 severity weights, and (later) solver parameters, all in one loaded
config object.

**Add** `src/family_camp2/config.py`:
- `EngineConfig` dataclass: `tier0_weights: Tier0Weights`, `objective_order:
  tuple[str, ...]` (default `("tier0", "tier1", "tier2")` — fixed content,
  order is what's configurable per OQ-4), `compulsory_activities: tuple[str, ...]`
  (default empty, per OQ-5).
- `load_config(path: Path | None) -> EngineConfig` — loads from JSON if a
  path is given (schema documented in a docstring/README snippet), else
  returns defaults. Invalid/unknown keys raise a clear error (don't
  silently ignore typos in a config file).

**Tests** (`tests/test_config.py`): default config loads with no path;
loading a valid JSON file overrides specific fields; loading a JSON file
with an unknown key raises with a message naming the bad key; loading a
JSON file with `objective_order` containing a duplicate or unknown tier
name raises.

**Commit message**: `family_camp2 step 07: engine configuration (NFR-4)`

---

### - [x] Step 8: Solver interface

**Goal**: A common shape both real solvers will implement, proven with a
fake solver before either real one exists — de-risks the CLI wiring in
Step 11 independently of CP-SAT/annealing being ready.

**Add** `src/family_camp2/solvers/base.py`:
- `SolveResult` dataclass: `timetable: Timetable`, `report: ValidationReport`,
  `diagnostics: dict` (free-form — e.g. CP-SAT's optimality gap, or
  annealing's chain count; deliberately solver-specific and not part of the
  common contract beyond "exists").
- `Solver` — `typing.Protocol` with one method:
  `solve(activities, sessions, campers, config: EngineConfig) -> SolveResult`.

**Add** `src/family_camp2/solvers/registry.py`:
- `SOLVERS: dict[str, type[Solver]]` and `register(name)` decorator /
  `get_solver(name) -> Solver`.

**Add** (test-only) a `FakeSolver` in `tests/fixtures.py` implementing
`Solver` by returning a trivially empty `Timetable` run through the real
`validate()` — proves the interface is usable end-to-end without needing
either real solver.

**Tests** (`tests/test_solver_interface.py`): registering and retrieving a
solver by name works; retrieving an unregistered name raises a clear
error; `FakeSolver.solve(...)` returns a `SolveResult` whose `report` is a
real `ValidationReport`.

**Commit message**: `family_camp2 step 08: solver interface and registry`

---

### - [x] Step 9: JSON input loader

**Goal**: A documented, minimal file format for describing a camp instance
— used by every test fixture from here on, and usable standalone for
manual runs without needing real Google Sheets data.

**Add** `src/family_camp2/io/json_loader.py`:
- Documented schema (docstring + example): top-level `activities`,
  `sessions`, `campers` arrays with the fields from REQUIREMENTS.md §3 (plus
  `min_age` on activities, per OQ-8).
- `load_json(path: Path) -> tuple[list[Activity], list[Session], list[Camper]]`.
- Implements **FR-1**: if a camper's priority/optional list or a session
  references an activity name not present in `activities`, raise a clear
  error naming the camper/session and the bad reference — never silently
  drop it.

**Add** `tests/fixtures/small_camp.json` — a hand-built ~5-camper,
2-family, 3-activity, 4-session instance, small enough to reason about by
hand; this becomes the fixture most later tests build on (via a
`load_small_camp()` helper in `tests/fixtures.py`).

**Tests** (`tests/test_json_loader.py`): loading `small_camp.json` produces
the expected counts and a couple of spot-checked field values; a
malformed copy with a bad activity reference raises with the camper's name
in the message; a malformed copy with a bad session→activity reference
raises similarly.

**Commit message**: `family_camp2 step 09: JSON input loader and small_camp fixture`

---

### - [x] Step 10: Legacy `.cache.pickle` loader

**Goal**: A path to run against **real** historical camp data without
waiting on any new data-fetch work — reads the file format the existing,
unmodified `family_camp/schedule/fetch_data.py` already produces (a data
contract, per REQUIREMENTS.md's "Google Sheets is a prerequisite" framing
— this step depends on that *file format*, not on any code in the old
package).

**Add** `src/family_camp2/io/legacy_cache_loader.py`:
- `load_legacy_cache(path: Path) -> tuple[list[Activity], list[Session], list[Camper]]`
  — unpickles the `(acts_wks, session_wks, campers_wks)` tuple and parses
  it into `family_camp2` domain objects using fresh, from-scratch parsing
  logic (column indices documented in a comment, mirroring the layout
  described in DESIGN.md §"Data loading/caching" — but written independently,
  not imported from `family_camp.schedule.deep`). Applies the same FR-1
  validation as Step 9's loader.

**Tests** (`tests/test_legacy_cache_loader.py`): build a small pickle
**in-memory** in the test (via `pickle.dumps` on a hand-constructed tuple
matching the known raw-row shape — no binary fixture file committed to the
repo) and assert it parses into the expected domain objects; a row with a
bad activity reference raises per FR-1.

**Commit message**: `family_camp2 step 10: legacy .cache.pickle loader adapter`

---

### - [x] Step 11: CLI end-to-end wiring (with the fake solver)

**Goal**: Prove the full pipeline — load → solve → validate → report —
works end to end, before either real solver exists.

**Update** `src/family_camp2/cli.py`:
- Arguments: `--solver {cp_sat,annealing}` (required), `--data PATH` (JSON,
  Step 9) or `--legacy-cache PATH` (Step 10) — mutually exclusive, one
  required; `--config PATH` (optional, Step 7); `--out PATH` (optional;
  default prints `render_text(report)` to stdout; if given, also writes a
  JSON dump of the report).
- `main(argv)`: parse → load activities/sessions/campers → `load_config` →
  `get_solver(args.solver).solve(...)` → print/write the report.
- Temporarily register `FakeSolver` (moved from test-only to
  `solvers/registry.py` under **both** names) so the CLI is fully
  exercisable now; Steps 15 and 19 replace these registrations with the
  real solvers one at a time.

**Tests** (`tests/test_cli.py`): running `main` with `--solver cp_sat
--data tests/fixtures/small_camp.json` (still the fake solver under the
hood at this point) exits 0 and prints a report; missing/invalid `--solver`
or providing both/neither of `--data`/`--legacy-cache` exits non-zero with
a clear message; `--out` writes a JSON file that round-trips.

**Commit message**: `family_camp2 step 11: CLI wired end-to-end (fake solver, real loaders)`

---

### - [x] Step 12: CP-SAT — model builder with Class 1 structural constraints

**Goal**: The start of Design A. Add the `ortools` dependency; build (but
don't yet solve) a CP-SAT model whose *shape* already guarantees Class 1.

**Update** `pyproject.toml`: add `ortools` to `[project.dependencies]`.

**Add** `src/family_camp2/solvers/cp_sat.py`:
- `build_model(activities, sessions, campers, config) -> tuple[cp_model.CpModel, VarIndex]`
  where `VarIndex` maps `(camper, session)` → `BoolVar`, created **only**
  for pairs where the camper requested the session's activity (priority or
  optional) and is age-eligible (OQ-8) — per DESIGN_OPTIONS.md §3.1, this
  is what makes Class 1's request/age rules structural rather than
  enforced-by-penalty.
- No-overlap constraint per camper (using `NewOptionalIntervalVar` /
  `AddNoOverlap` over each camper's candidate sessions) — FR-10.
- Capacity constraint per session (`sum(...) <= activity.max_occupancy`) — FR-12 max side.
- (Unrequested-activity (FR-14) is excluded by construction via
  `VarIndex`'s restricted domain. **Correction found during
  implementation**: duplicate-activity (FR-15) is *not* excluded by
  construction — a camper can be eligible for two different session
  instances of the *same* activity (e.g. a morning and an afternoon slot),
  so an explicit `sum(...) <= 1` constraint per camper per activity is
  required. Added in Step 12 alongside the other structural constraints.)

**Tests** (`tests/test_cp_sat_model.py`): building a model for
`small_camp.json` succeeds; assert no `VarIndex` entry exists for a
camper/session pair the camper never requested, and none for an
under-age camper against an age-restricted activity (construct a small
case with an `min_age` activity for this); solving the bare model (any
feasible solution, no objective yet) and running the result through
Step 3's `check_class1` confirms zero violations.

**Commit message**: `family_camp2 step 12: CP-SAT model builder with structural Class 1 constraints`

---

### - [x] Step 13: CP-SAT — Class 2 indicators, Tier 0 objective, Phase 1 solve

**Goal**: The best-effort core of Design A.

**Update** `src/family_camp2/solvers/cp_sat.py`:
- Violation indicator `BoolVar`s for each Class 2 rule from Step 4:
  `missing_priority[c, a]`, `family_conflict[...]`,
  `unsupervised_split[...]`, `under_minimum[s]`, `unmet_compulsory[c, a]` —
  each linked to the assignment variables via reification
  (`OnlyEnforceIf`) so it's forced to 1 exactly when the corresponding
  violation genuinely occurs, and free to be 0 otherwise (the solver isn't
  required to set it — that's what lets it minimise them).
- `tier0_expr` — weighted linear sum of the indicators using `config.tier0_weights`.
- `solve_phase1(model, tier0_expr, ...) -> tuple[CpSolver, int]` — minimise
  `tier0_expr`, return the solver (for variable inspection) and the
  achieved optimum `V0`.

**Tests** (`tests/test_cp_sat_tier0.py`): a deliberately over-subscribed
fixture (more priority demand for one activity than total capacity across
its sessions) where the true minimum Tier 0 score is small enough to
verify by hand; assert `solve_phase1` finds exactly that value; **cross-check**
by converting the solved assignment into a `Timetable` and running it
through Step 6's `validate()` — assert the validator's own `tier0_score`
agrees with the solver's `V0` (this is the "two independent layers agree"
property from DESIGN_OPTIONS.md §2.4/§3.6, made into an actual test).

**Commit message**: `family_camp2 step 13: CP-SAT Class 2 indicators and Phase 1 (Tier 0) solve`

---

### - [x] Step 14: CP-SAT — Phase 2/3 and the full solver

**Goal**: Complete the three-phase lexicographic solve from
DESIGN_OPTIONS.md §3.1 and wrap it as a `Solver`.

**Update** `src/family_camp2/solvers/cp_sat.py`:
- `solve_phase2(model, ..., v0)` — add `tier0_expr == v0`, maximise an
  integer-scaled Tier 1 expression (sum of per-camper optional-satisfaction
  fractions, scaled by e.g. `10_000` and rounded, since CP-SAT works in
  integers) → `O1`.
- `solve_phase3(model, ..., v0, o1)` — add `tier0_expr == v0` and
  `tier1_expr == o1`, minimise the Tier 2 (spread) expression.
- `class CpSatSolver` implementing the `Solver` protocol: runs all three
  phases, converts the final assignment into a `Timetable`, calls
  `validate()` for the returned `report`, and populates `diagnostics` with
  each phase's objective value and solve status (optimal/feasible/timeout).

**Tests** (`tests/test_cp_sat_solver.py`): a fixture with multiple
Tier-0-optimal solutions that differ in Tier 1/2 (constructed so that a
*naive weighted sum* would pick the wrong one but strict lexicographic
ordering must pick a specific, hand-identified one) — assert
`CpSatSolver().solve(...)` returns that solution, proving the phases are
genuinely sequential and not accidentally equivalent to a single weighted
objective.

**Deviations found during implementation:**
- Tier 2 inside the CP-SAT model is minimised via an exact-integer proxy
  (sum, per multi-session activity, of max-occupancy minus min-occupancy
  across its sessions) rather than true population variance, which would
  need quadratic terms and per-group rational scaling to normalise across
  differently-sized activity groups. The validator's true
  `tiers.score_tier2` (population variance) remains the authoritative,
  reported score regardless of this internal proxy.
- The installed `ortools` build's `CpSolver.StatusName()` is broken when
  called with no arguments on this Python version (calls
  `self._checked_response.status()` on a non-callable enum). Worked around
  by stashing the `Solve()` return value as `solver._resolved_status` and
  always calling `StatusName(status)` with an explicit argument.

**Commit message**: `family_camp2 step 14: CP-SAT three-phase lexicographic solver`

---

### - [x] Step 15: CP-SAT — register in CLI, solver parameters, integration test

**Goal**: `--solver cp_sat` now runs the real thing.

**Update**:
- `solvers/cp_sat.py`: accept `time_limit_seconds` and `random_seed`
  parameters (threaded through `EngineConfig` — extend it with a
  `cp_sat: CpSatParams` field, Step 7's config gains an optional section)
  for NFR-2/NFR-3.
- `solvers/registry.py` / CLI: replace the fake registration for
  `"cp_sat"` with `CpSatSolver`.

**Tests** (`tests/test_cp_sat_cli.py`): `cli.main(["--solver", "cp_sat",
"--data", "tests/fixtures/small_camp.json"])` exits 0 and the printed
report shows a Tier 0 score of 0 (this fixture should be feasible); a
larger generated fixture (a helper that synthesises ~30 campers/6
activities/10 sessions, still small enough to keep the test fast) solves
within a test-appropriate timeout (a few seconds) and produces a
`ValidationReport` with zero Class 1 violations.

**Deviation found during implementation:** the plan called for adding a
`cp_sat: CpSatParams` field to `EngineConfig`, but `EngineConfig` lives in
`config.py` and `CpSatParams`/`CpSatSolver` live in `solvers/cp_sat.py`,
which already imports `EngineConfig` - adding the reverse import would
create a circular import. Instead, `CpSatSolver.__init__` takes
`time_limit_seconds`/`random_seed` directly as constructor kwargs (not
routed through `EngineConfig`, which stays scoped to "what does a good
schedule look like" per NFR-4, not solver runtime parameters), and
`registry.get_solver(name, **kwargs)` was generalised to pass arbitrary
kwargs through to the solver's constructor so the CLI's new `--time-limit`/
`--seed` flags reach it uniformly regardless of which solver is chosen.

**Commit message**: `family_camp2 step 15: wire CP-SAT into the CLI (--solver cp_sat)`

---

### - [x] Step 16: Annealing — move primitives

**Goal**: The start of Design B — moves that can never produce a Class 1
violation, by construction (DESIGN_OPTIONS.md §4.1).

**Add** `src/family_camp2/solvers/annealing/moves.py`:
- `assign_family(state, family_id, session) -> State | None` — returns
  `None` (move rejected) if it would violate Class 1 (age, request,
  capacity, double-booking), otherwise the new state with the eligible
  family members added.
- `move_family(state, family_id, from_session, to_session) -> State | None`.
- `swap_families(state, family_a, session_a, family_b, session_b) -> State | None`.
- `remove_family(state, family_id, session) -> State`.
- `fix_unsupervised_split(state, family_id, session) -> State | None` —
  tries to move an adult from the family into `session` if it's short one.
- A `State` wrapper (mutable, unlike `Timetable`) with O(1)-ish incremental
  occupancy/assignment lookups, plus `to_timetable() -> Timetable` for
  handing off to the validator.

**Tests** (`tests/test_annealing_moves.py`): one test per move type on
`small_camp.json`-derived state, including a rejection case per move
(e.g. `assign_family` returns `None` when it would exceed capacity, or
when a family member is under the activity's `min_age`); after every
successful move, run `to_timetable()` through `check_class1()` (Step 3)
and assert it's still clean.

**Commit message**: `family_camp2 step 16: annealing move primitives with Class 1 preconditions`

---

### - [x] Step 17: Annealing — lexicographic scorer and single-chain SA loop

**Goal**: The comparator and core loop from DESIGN_OPTIONS.md §4.1.

**Add** `src/family_camp2/solvers/annealing/scoring.py`:
- `score(state, ...) -> tuple` — `(tier0_score, -tier1_score, tier2_score)`
  using Step 4/5's scoring functions against `state.to_timetable()`.
- `compare(score_a, score_b) -> int` — lexicographic tuple comparison.
- `acceptance_probability(delta, temperature) -> float` — standard SA
  acceptance function, applied to how much *worse* a candidate is under
  `compare`, not a scalarised delta (avoids the sign-convention bug class
  flagged in DESIGN.md §3.1).

**Add** `src/family_camp2/solvers/annealing/solver.py` (core loop only for
now — restarts arrive in Step 18):
- `run_chain(initial_state, moves, cooling_schedule, seed, iterations) -> State`
  — repeatedly proposes a random move from `moves.py`, accepts/rejects per
  `compare` + `acceptance_probability`, cools the temperature, returns the
  best state seen.

**Tests** (`tests/test_annealing_core.py`): running `run_chain` on a fixed
seed twice produces identical results (NFR-3 reproducibility); running on
`small_camp.json` for a modest fixed iteration count produces a final
state whose Tier 0 score is no worse than the score of the empty starting
state (sanity: the search isn't actively making things worse net of its
own best-tracking); final state passes `check_class1` cleanly (moves
preserved it throughout, per Step 16).

**Commit message**: `family_camp2 step 17: lexicographic scorer and single-chain simulated annealing`

---

### - [x] Step 18: Annealing — constructive seed, multi-chain restarts, full solver

**Goal**: Complete Design B per DESIGN_OPTIONS.md §4.1's restart strategy.

**Add** `src/family_camp2/solvers/annealing/seed.py`:
- `greedy_seed(activities, sessions, campers, rng) -> State` — constructive
  starting point (family-grouped, weighted-random admission), the spirit of
  the current system's `gen_seed_individual` rewritten from scratch against
  the new `State`/move primitives.

**Update** `src/family_camp2/solvers/annealing/solver.py`:
- `run_restarts(..., num_chains, seeds) -> State` — runs `num_chains`
  independent `run_chain` calls (via `multiprocessing.Pool`) from
  independently-seeded `greedy_seed` starts, returns the best result
  across all chains per `compare`.
- `class AnnealingSolver` implementing `Solver`: builds a `State`,
  calls `run_restarts`, converts to `Timetable`, calls `validate()`,
  populates `diagnostics` with per-chain scores and the winning chain's
  seed (for reproducibility of that specific result).

**Tests** (`tests/test_annealing_solver.py`): `AnnealingSolver().solve(...)`
on `small_camp.json` returns a `SolveResult` whose report has zero Class 1
violations; running with a fixed list of chain seeds twice produces
identical results (NFR-3); result's Tier 0 score is `<=` the best single
chain's score among the diagnostics (aggregation correctness).

**Addition beyond the plan:** `run_chain` gained an optional `deadline`
parameter (a `time.monotonic()` timestamp, checked every 100 iterations to
keep overhead negligible) so `time_limit_seconds` - accepted by
`AnnealingSolver` for CLI-uniformity with `CpSatSolver` - actually bounds
wall-clock time per NFR-2, rather than being an accepted-but-ignored
parameter.

**Commit message**: `family_camp2 step 18: greedy seed, multi-chain restarts, full AnnealingSolver`

---

### - [x] Step 19: Annealing — register in CLI, solver parameters, integration test

**Goal**: `--solver annealing` now runs the real thing.

**Update**:
- `EngineConfig` gains an `annealing: AnnealingParams` section (chain
  count, iterations per chain, cooling schedule parameters, seed list) —
  NFR-4.
- `solvers/registry.py` / CLI: replace the fake registration for
  `"annealing"` with `AnnealingSolver`.

**Tests** (`tests/test_annealing_cli.py`): `cli.main(["--solver",
"annealing", "--data", "tests/fixtures/small_camp.json"])` exits 0 with a
zero Tier 0 score; the same ~30-camper synthetic fixture used in Step 15
solves within a test-appropriate time budget.

**Bug found and fixed during implementation:** the medium-synthetic-instance
test (this step's own integration test) caught a real Class 1 violation -
`swap_families` (Step 16) computed the room freed up in `session_a` using
`len(members_b)` (the incoming group) instead of `len(members_a)` (the
group actually vacating `session_a`), which meant the check was
effectively a no-op whenever `session_a` wasn't already over capacity -
allowing swaps that overflowed `session_a` whenever the incoming family
was larger than the outgoing one. Fixed in `moves.py`, with a
hand-verified regression test added to `test_annealing_moves.py`
(`test_swap_families_rejected_when_asymmetric_group_sizes_would_overflow_capacity`).
Also updated `EngineConfig`-adjacent CLI wiring: as in Step 15, annealing's
tuning knobs (`--num-chains`, `--iterations-per-chain`) are separate CLI
flags passed conditionally as constructor kwargs (only when `--solver
annealing`), not routed through `EngineConfig`, for the same
circular-import reason. `_stub.py` and its import in `solvers/__init__.py`
were removed now that both real solvers exist, per its own docstring.

**Commit message**: `family_camp2 step 19: wire annealing into the CLI (--solver annealing)`

---

### - [x] Step 20: Cross-solver consistency tests

**Goal**: Empirically validate the comparative claim in DESIGN_OPTIONS.md
§5 — CP-SAT's Tier 0 result is optimal, so annealing should never beat it,
only match or trail it.

**Add** `tests/test_cross_solver_consistency.py`:
- Run both `CpSatSolver` and `AnnealingSolver` against several small,
  hand-built fixtures (including at least one deliberately infeasible
  one), and assert:
  - Both reports show zero Class 1 violations (trivially true by
    construction in both, but worth asserting explicitly here as a
    regression guard).
  - `annealing.tier0_score >= cp_sat.tier0_score` (CP-SAT is provably
    optimal; annealing can only tie or trail it) — this is the concrete,
    automated version of the "provable vs. best-found" gap discussed in
    DESIGN_OPTIONS.md §4.6.
  - On the feasible fixtures, both report `tier0_score == 0`.

**Commit message**: `family_camp2 step 20: cross-solver consistency regression tests`

---

### - [x] Step 21: Property-based hardening for the validator

**Goal**: Strengthen confidence in Step 3's Class 1 checkers and Step 16's
move preconditions beyond example-based tests, per DESIGN_OPTIONS.md
§4.5's recommendation.

**Update** `pyproject.toml`: add `hypothesis` to the `dev` extra.

**Add** `tests/test_class1_properties.py`:
- A Hypothesis strategy generating small random valid camps (bounded
  camper/activity/session counts) and small random subsets of
  `(camper, session)` pairs as candidate assignments.
- Property: for any assignment set built **only** from moves in
  `solvers/annealing/moves.py` (i.e. never bypassing the move layer),
  `check_class1` always reports zero violations.
- Property: for any assignment set built **only** through
  `CpSatSolver`'s `VarIndex`-restricted variables (a small solved model),
  `check_class1` always reports zero violations.

**Commit message**: `family_camp2 step 21: property-based tests for Class 1 invariants`

---

### - [x] Step 22: Documentation and polish

**Goal**: Make the package approachable to the next person (or agent) who
opens it cold.

**Add** `family_camp2/README.md`:
- What this is, how it relates to `family_camp/` (a from-scratch rewrite of
  the scheduling engine only — see `../DESIGN.md`, `../REQUIREMENTS.md`,
  `../DESIGN_OPTIONS.md`, `../IMPLEMENTATION_PLAN.md` at the repo root).
- Install/test instructions (the venv + `pip install -e ".[dev]"` + `pytest`
  commands from §0).
- CLI usage examples for both `--solver cp_sat` and `--solver annealing`,
  against both `--data` (JSON) and `--legacy-cache` (pickle) inputs.
- The JSON input schema (from Step 9), documented plainly with the example
  fixture.
- A short "how to add a third solver" note pointing at `solvers/base.py`'s
  `Solver` protocol and `solvers/registry.py`.

**Final check**: run the complete test suite one more time from a fresh
`pip install -e ".[dev]"` in a brand-new venv (catches any accidental
reliance on leftover local state) before the final commit.

**Commit message**: `family_camp2 step 22: README and final polish`

---

## 3. Progress reporting and final report generation (Steps 23–32)

### Context

Reverse-engineered from two sources: the old GA-based system's actual
behaviour (`family_camp/schedule/generate_schedule.py`,
`family_camp/schedule/deep.py`'s `MyHallOfFame.dump_to_dir`, and
`family_camp/schedule/check_schedule.py`), and direct, first-hand
experience running family_camp2's own CP-SAT solver for a real ~3-hour
job against real 2026 camp data: there was no way to tell what stage the
run was in, whether it was making progress, or to get anything useful out
of it without waiting for the whole thing to finish — external `ps`/log
polling was the only option. Separately, that same session surfaced a
concrete functional gap: the CLI's `--out` only ever wrote the
*validation report* (scores and violations), never the actual generated
*timetable* — there was no way to get the schedule itself back out in a
reusable form.

This phase implements REQUIREMENTS.md §4.6 (FR-60–FR-64, progress
reporting) and §4.7 (FR-70–FR-75, schedule export and human-readable
reporting), plus NFR-9/NFR-10. It follows the same ground rules as §0
above (one step at a time, tests before commit, commit per step).

REQUIREMENTS.md OQ-9–OQ-12 are now answered; each affected step
implements that answer directly (no longer provisional):

- **OQ-9 (cadence)**: wall-clock-time based, **default 60 seconds** - not
  event-based. This matters for design, not just the default number:
  reporting must keep happening on a timer even during a long stretch
  where the search finds nothing better (exactly the silent stretches
  experienced during the real 3-hour run) - see Step 24's design note on
  why a plain "report on every improving solution" callback isn't enough
  on its own to satisfy this.
- **OQ-10 (channel)**: a command-line option to send progress to a file;
  **default `-` for stdout**. There's deliberately no separate on/off
  switch (matching the old system's always-on `verbose=True`) - redirecting
  to a file the operator doesn't look at (or `/dev/null`) is how it's
  silenced if unwanted, which NFR-9 (progress reporting stays cheap) makes
  safe to leave on by default.
- **OQ-11 (export format)**: **both CSV and JSON**. `--export-schedule
  PATH` writes both `PATH.csv` and `PATH.json` (any extension typed on
  `PATH` is stripped first) rather than needing two separate flags.
- **OQ-12 (multiple candidates)**: a single best answer is sufficient -
  FR-75 is explicitly not implemented by this plan. Step 31 is retained
  below only as a record of that decision.

### Step list

### - [x] Step 23: Progress-reporting abstraction

**Goal**: A solver-agnostic way to report progress (FR-60/FR-61) on a
wall-clock cadence (OQ-9), usable by any current or future solver, cheap
enough to leave on by default (NFR-9, OQ-10).

**Add** `src/family_camp2/progress.py`:
- `ProgressEvent` (frozen dataclass): `stage: str` (e.g. `"phase1"`,
  `"restarts"`), `message: str`, `elapsed_seconds: float`,
  `tier0_score: int | None`, `tier1_score: float | None`,
  `tier2_score: float | None` — reusing the same tier vocabulary as the
  rest of the engine (FR-61, NFR-10), not a separate ad-hoc metric.
- `ProgressReporter` — a `Protocol` with one method, `report(event:
  ProgressEvent) -> None`.
- `NullProgressReporter` — a no-op implementation, used internally by
  anything that doesn't need reporting (e.g. existing tests that don't
  pass a reporter explicitly).
- `PrintProgressReporter` — writes a formatted line to a given stream.
  Takes a `destination: str` constructor argument resolved once, up
  front: `"-"` → `sys.stdout`, anything else → that path opened for
  writing (OQ-10) - resolving eagerly at construction, not per-call,
  keeps the hot path (NFR-9) to a single write.
- `PeriodicHeartbeat` — a small helper that owns a background daemon
  thread: constructed with a `ProgressReporter`, an `interval_seconds`
  (OQ-9 default 60), and a zero-argument `get_event: Callable[[],
  ProgressEvent | None]` callback; every `interval_seconds` it calls
  `get_event()` and, if not `None`, reports it. Used as a context manager
  (`__enter__` starts the thread, `__exit__` stops and joins it). This is
  what makes the cadence genuinely wall-clock-based rather than tied to
  how often a solver happens to find something new to report (see Step
  24).

**Deviation found during implementation**: the plan originally called for
an injectable `sleep` hook so tests could drive the loop without a fake
clock. Building it that way first surfaced a real deadlock: if `__exit__`
sets the stop flag while the background thread is blocked inside a
same-signature-but-uninterruptible fake `sleep`, `thread.join()` hangs
forever, since nothing wakes that `sleep` up early. Fixed by using
`threading.Event.wait(interval_seconds)` as the timer instead of a plain
`sleep` call - `Event.wait` doubles as the shutdown signal, so it returns
immediately once `__exit__` sets the stop event, rather than only after a
full interval (or never). This is also simpler to test: no fake clock
needed, just a short real `interval_seconds` (tests use ~0.02s).

**Tests** (`tests/test_progress.py`): `PrintProgressReporter("-")` writes
to the given stdout-like stream; `PrintProgressReporter(path)` writes to
that file. `PeriodicHeartbeat` reports repeatedly on a short real
interval while active, produces nothing when `get_event` returns `None`,
and - the regression test for the deadlock above - `__exit__` returns
promptly even with a very long `interval_seconds` (999s), not blocking
until that interval elapses. `NullProgressReporter.report()` is a no-op.

**Commit message**: `family_camp2 step 23: progress-reporting abstraction (FR-60/FR-61/NFR-9)`

---

### - [x] Step 24: CP-SAT progress integration

**Goal**: Surface phase transitions and search progress from the
three-phase solve (FR-61/FR-62) on a genuine wall-clock cadence (OQ-9) -
the exact gap felt during the real 3-hour run, where Phase 2/3 went long,
silent stretches with no signal at all.

**Design note**: `cp_model.CpSolverSolutionCallback` only fires when the
solver finds a *new, improving* solution - during a long stall (observed
for real on the 283-camper run) it fires rarely or not at all, so relying
on it alone cannot satisfy "reports on a timer" (OQ-9). Instead: the
callback's only job is to cheaply record the latest solution's info
(objective value, elapsed time) into a small lock-protected holder
(`solver.Solve()` may run CP-SAT's own internal worker threads, so the
callback can fire from a thread other than the caller's - a `threading.Lock`
around the holder is required, not optional). A `PeriodicHeartbeat`
(Step 23) runs alongside the blocking `solver.Solve(...)` call for that
phase's duration, reading the holder every `interval_seconds` and
reporting whatever it finds (even if unchanged since the last report -
that repetition *is* the "still alive" signal) regardless of whether the
callback has fired recently.

**Update** `src/family_camp2/solvers/cp_sat.py`:
- Add a `_ProgressCallback(cp_model.CpSolverSolutionCallback)` that
  updates a shared, lock-protected "latest known solution" holder on
  every new solution (elapsed time + objective value); no reporting
  happens inside the callback itself.
- Thread `progress_reporter: ProgressReporter = NullProgressReporter()`
  and `progress_interval_seconds: float = 60` through `solve_phase1`/
  `solve_phase2`/`solve_phase3`: report a "phase started" event, wrap the
  `solver.Solve(model, callback)` call in a `PeriodicHeartbeat` reading
  the callback's holder (tagging events with the right tier field for
  that phase), then report a "phase finished" event with the final
  status.
- `CpSatSolver.__init__`/`.solve()` gain the same two parameters, passed
  through to all three phases.

**Tests** (`tests/test_cp_sat_progress.py`): a fake, list-collecting
`ProgressReporter` passed into `CpSatSolver().solve(...)` on a small
instance; assert phase-start/finish events appear in order (1 before 2
before 3).

**Deviation found during implementation**: the plan called for a test
that solves a real (if tiny) instance with a short `progress_interval_seconds`
and asserts a mid-phase heartbeat actually lands - this turned out to be
inherently flaky, not just slow: `small_camp` solves each phase in
single-digit *milliseconds*, so even a 20ms interval frequently beats the
heartbeat thread to the finish line, and there's no larger fixture that
reliably takes "a bit longer" without either risking the same flakiness
on a fast machine or making the suite noticeably slower on every run.
Racing a real solve's wall-clock duration against a timer is the wrong
way to test this. Replaced with deterministic unit tests of `_make_get_event`/
`_ProgressCallback` directly (no real solve involved): one confirms the
"no solution yet" event shape before any incumbent is recorded, one
manually sets `callback._latest` (simulating `on_solution_callback` having
fired) and confirms the value lands in the correct tier field
(`tier0_score`/`tier1_score`/`tier2_score`) for each phase. This tests the
actual logic that matters precisely and instantly, instead of hoping a
real solve is slow enough to observe it happening. Confirmed omitting the
new parameters doesn't change existing behaviour - the existing
`test_cp_sat_solver.py` suite passes unchanged.

**Commit message**: `family_camp2 step 24: CP-SAT progress reporting (phase transitions + wall-clock heartbeat)`

---

### - [x] Step 25: Annealing progress integration

**Goal**: Surface restart progress (FR-61/FR-62) for the multi-restart
search, on the same wall-clock cadence.

**Design note (scope)**: annealing's chains run in separate *worker
processes* (`multiprocessing.Pool`), not threads in the caller's process -
a `ProgressReporter` (potentially wrapping an open file handle) isn't
safely shareable across that boundary the way it is for CP-SAT's
in-process callback. Rather than building a cross-process progress queue,
this step reports at **chain-completion** boundaries in the *main*
process, using `pool.imap_unordered` (which yields each chain's result as
soon as it's ready) in place of the current `pool.starmap` (which blocks
until *all* chains finish). This is a deliberate scope decision, not an
oversight: measured on real ~283-camper data, a full 8-chain ×
5000-iteration run completes in about 2.5 minutes total, i.e. individual
chains are seconds, not the tens-of-minutes-plus that motivated Step 24's
in-phase heartbeat for CP-SAT - per-chain-completion events already land
well inside the 60-second default cadence in practice. If a future,
much-larger-scale run made individual chains themselves run for a long
time, intra-chain reporting could be added the same way as Step 24 (a
progress queue drained by a `PeriodicHeartbeat` in the main process) -
worth a one-line note in the code, not implementing pre-emptively now.

**Update** `src/family_camp2/solvers/annealing/solver.py`:
- `run_restarts` gains `progress_reporter: ProgressReporter =
  NullProgressReporter()`; switch its pool usage from `pool.starmap` to
  `pool.imap_unordered` over a small single-argument adapter (since
  `imap_unordered` doesn't support multiple positional args the way
  `starmap` does), and report an event each time a chain's result arrives
  (`stage="restarts"`, message noting which chain of how many just
  finished and its resulting Tier 0/1/2 scores).
- `AnnealingSolver.__init__`/`.solve()` gain the same parameter.

**Tests** (`tests/test_annealing_progress.py`): fake reporter passed into
`AnnealingSolver(...).solve(...)` with a handful of chains on a small
instance; assert one completion event arrives per chain (order not
guaranteed, per `imap_unordered`'s nature - assert the *set* of chains
reported matches, not a fixed order). Confirm omitting the parameter
doesn't change existing behaviour - existing annealing tests pass
unchanged.

**Commit message**: `family_camp2 step 25: annealing progress reporting (per-chain completion via imap_unordered)`

---

### - [x] Step 26: CLI progress wiring

**Goal**: Make progress reporting usable from the command line, on by
default (FR-60, OQ-10).

**Update**:
- `src/family_camp2/cli.py`: add `--progress-output PATH` (default `"-"`
  for stdout, per OQ-10) and `--progress-interval SECONDS` (default `60`,
  per OQ-9, CP-SAT only - passed as `progress_interval_seconds` only when
  `--solver cp_sat`, since annealing has no such parameter, per Step 25).
  Always construct a `PrintProgressReporter` from `--progress-output` (no
  separate on/off flag - redirect to a file or `/dev/null` to silence, per
  the Context note above), pass it as `progress_reporter=` alongside
  `time_limit_seconds`/`random_seed` in `_solver_kwargs`, and `.close()`
  it in a `finally` after solving.

**Deviation from the plan**: didn't touch `solvers/base.py`'s `Solver`
protocol at all. Both `CpSatSolver` and `AnnealingSolver` already accept
`progress_reporter` as a **constructor** kwarg (Steps 24/25), exactly like
the existing `time_limit_seconds`/`random_seed` pattern - `get_solver(name,
**kwargs)` already passes constructor kwargs through uniformly, so there
was nothing left for the `Solver.solve()` method signature to do. Simpler
than planned, not a redesign.

**Tests** (`tests/test_cli.py` additions): CLI run with `--progress-output`
pointed at a temp file produces a progress line in that file, not on
stdout, while the final validation report still prints to stdout; the
default `--progress-output -` produces progress lines interleaved with
(not replacing) that same final report on stdout.

**Commit message**: `family_camp2 step 26: wire --progress-output/--progress-interval into the CLI`

---

### - [ ] Step 27: Schedule CSV + JSON export/import

**Goal**: Make the actual generated timetable - not just the validation
report - durably exportable and re-importable (FR-70/FR-71), in both
formats (OQ-11), closing the gap found during the real 3-hour run where
the only way to get the schedule out was an ad-hoc one-off script.

**Add** `src/family_camp2/io/schedule_export.py`:
- `ScheduleExportError` (new exception type, matching the project's
  established "fail loud and specific" convention from FR-1).
- A shared internal helper building one row/record per assignment
  (`family_id`, `camper_name`, `activity_name`, `session_label`,
  `session_start` as ISO 8601) - used by both formats below, so the
  "what does an exported assignment look like" logic exists exactly once.
- `dump_schedule_csv(timetable: Timetable, path: Path | str) -> None` and
  `dump_schedule_json(timetable: Timetable, path: Path | str) -> None`.
- `load_schedule_csv(path, activities, sessions, campers) -> Timetable`
  and `load_schedule_json(path, activities, sessions, campers) -> Timetable`
  - the import side (FR-71), resolving each row/record back to the
  matching `Camper`/`Session` from the given reference collections;
  raises `ScheduleExportError` naming the specific row and the
  unresolvable camper/session if it can't, rather than crashing or
  silently skipping it.

**Update** `src/family_camp2/cli.py`: add `--export-schedule PATH`. Strip
any extension from `PATH` and always write both `<stem>.csv` and
`<stem>.json` (OQ-11) after solving - independent of `--out`, which
continues to write the validation report only.

**Tests** (`tests/test_schedule_export.py`): round-trip a small
`Timetable` through both `dump_schedule_csv`/`load_schedule_csv` and
`dump_schedule_json`/`load_schedule_json`, asserting equality in each
case; an unresolvable row/record raises `ScheduleExportError` naming it,
for both formats. CLI test: `--export-schedule PATH` produces both
`PATH.csv` and `PATH.json`, each independently re-loadable to the same
assignments.

**Commit message**: `family_camp2 step 27: schedule CSV + JSON export/import (FR-70/FR-71)`

---

### - [ ] Step 28: Per-family and per-activity reports

**Goal**: Human-readable operational reports from a timetable (FR-72/FR-73),
matching the *content* of the old system's `campers_out`/`activites_out`
reports (not their exact formatting).

**Add** `src/family_camp2/reporting.py`:
- `render_family_itinerary(timetable: Timetable, campers: list[Camper]) -> str`
  - for each family (sorted alphabetically, matching the old system's
  human-friendly ordering), its members' sessions in time order.
- `render_activity_roster(timetable: Timetable, sessions: list[Session]) -> str`
  - for each activity's sessions, who's assigned plus an occupancy-vs-limit
  summary line.

Both functions read only `Timetable`/domain objects - per NFR-10, no new
validation/scoring logic, only presentation of what `validation/` already
computes.

**Tests** (`tests/test_reporting.py`): small fixture; assert expected
campers/sessions appear under the right family/activity grouping, and
occupancy-vs-limit figures are correct.

**Commit message**: `family_camp2 step 28: per-family itinerary and per-activity roster reports (FR-72/FR-73)`

---

### - [ ] Step 29: Family-group and adult-specific idle reporting

**Goal**: Extend idle-time reporting to the family/group level and flag
idle adults specifically (FR-74), matching the old system's two distinct
staffing-relevant views (a whole idle family vs. specifically which
adults are free) rather than one undifferentiated camper-level list.

**Update** `src/family_camp2/validation/idle.py`: extend `IdleBucket` (or
add a parallel structure - exact shape is an implementation decision, the
requirement is the two distinct views) with `idle_families: tuple[str,
...]` and `idle_adults: tuple[Camper, ...]`, computed from the same
active-session scan `find_idle_slots` already does (no second full pass,
per NFR-9).

**Tests** (`tests/test_idle.py` additions): a family with every member
idle at a bucket is reported as an idle family; an idle adult is named
specifically; a family with at least one active member is not reported as
idle even if others are.

**Commit message**: `family_camp2 step 29: family-group and adult-specific idle reporting (FR-74)`

---

### - [ ] Step 30: CLI wiring for reports

**Goal**: Let an operator actually get Steps 28/29's reports out of a run,
mirroring the old system's per-run output-directory convention
(`MyHallOfFame.dump_to_dir`/`check_schedule.py`).

**Update** `src/family_camp2/cli.py`: add `--report-dir PATH` - if given,
after solving, write `family_itinerary.txt`, `activity_roster.txt`, and
`idle_report.txt` into that directory.

**Tests**: CLI run with `--report-dir` produces the three expected files
with correct, non-empty content on a small fixture.

**Commit message**: `family_camp2 step 30: wire report generation into the CLI (--report-dir)`

---

### - [x] Step 31: Multi-candidate export for annealing (FR-75) — SKIPPED

**Not implemented.** FR-75 is explicitly a *should*, not a *must*, and
REQUIREMENTS.md OQ-12 answered that a single best answer is sufficient for
this rewrite. Recorded here (checked off, with this note) rather than
silently deleted, so the decision and its reasoning stay visible: if a
future need arises to compare annealing's per-chain candidates rather than
only using them internally to pick the overall winner, `run_restarts`
(Step 25) already has every chain's result available in-process before
picking the winner - exposing them would be additive, not a redesign.

---

### - [ ] Step 32: Documentation

**Goal**: `family_camp2/README.md` documents everything this phase added.

**Update** `README.md`: document `--progress-output`/`--progress-interval`,
`--export-schedule` (now writing both `.csv` and `.json`), `--report-dir`,
and the new report/export file formats, alongside the existing CLI usage
examples. Note FR-75/OQ-12's outcome (single-candidate export only) so a
future reader doesn't wonder why annealing's other chains aren't surfaced.

**Final check**: full test suite green from a fresh `pip install -e
".[dev]"` in a new venv, same as Step 22.

**Commit message**: `family_camp2 step 32: document progress reporting and report generation`

---

## 4. After this plan

Not part of this plan, but worth flagging for a follow-up plan once this
one is complete and in real use:

- Wiring `family_camp2`'s output back into the existing printing/export
  code (`family_camp/schedule/schedule_printer.py`, `family_camp/pack/`),
  which DESIGN_OPTIONS.md §1.2 deliberately scoped out.
- The CP-SAT warm-start hybrid mentioned in DESIGN_OPTIONS.md §5 (seed the
  CP-SAT solve with `annealing.seed.greedy_seed`'s output as a hint) —
  not needed at current scale (§3.2), but cheap to add later if a much
  larger camp changes that calculus.
- Retiring `family_camp/schedule/{deep,generate_schedule,check_schedule}.py`
  and `timetable_cps.py` once `family_camp2` is validated against a real
  camp's data and trusted as a replacement.
