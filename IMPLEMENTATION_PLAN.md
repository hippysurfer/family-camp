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

### - [x] Step 27: Schedule CSV + JSON export/import

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

### - [x] Step 28: Per-family and per-activity reports

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

### - [x] Step 29: Family-group and adult-specific idle reporting

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

### - [x] Step 30: CLI wiring for reports

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

### - [x] Step 32: Documentation

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

### - [x] Step 33: Unmet-optional and structural-overdemand reports (FR-76/77)

**Goal**: two more `--report-dir` reports, added after real use of the
3-hour CP-SAT run surfaced a direct question ("which optional activities
went unmet?") that the existing reports couldn't answer, plus a follow-up
("why, when there's plenty of capacity?") that motivated a second,
input-only diagnostic.

- `validation/tiers.py`: `UnmetOptionalRequest`/`find_unmet_optional_requests`
  - the per-request breakdown behind `score_tier1`, from a `Timetable`.
- `validation/feasibility.py` (new): `FamilyOverdemand`/
  `find_overdemanding_families`/`max_non_overlapping_sessions` - derived
  from `activities`/`sessions`/`campers` alone, not a `Timetable`, since
  it's a property of demand vs. the shape of the schedule, not of any
  particular solve. Uses the standard interval-scheduling-maximisation
  greedy to find the true ceiling on non-overlapping sessions a *family*
  could ever occupy (initially built per-camper, then corrected to
  per-family - see the deviation note below); documented as a necessary-,
  not sufficient-, infeasibility check (module docstring).
- `reporting.py`: `render_unmet_optional_report`/
  `render_unfeasible_families_report`, both pure presentation over the
  above (NFR-10). `render_unmet_optional_report` also marks any camper
  whose family appears in the overdemand list with `[over demand]`.
- `cli.py`: both wired into the existing `--report-dir` block as
  `unmet_optional_report.txt`/`unfeasible_families_report.txt`.
- `REQUIREMENTS.md`: FR-76/FR-77 added to §4.7.

**Deviation found during implementation**: the first version of FR-77
computed the ceiling per-camper (`CamperOverdemand`/
`find_overdemanding_campers`). This undercounted real infeasibility:
Class 2's family-time-conflict rule means no two members of a family may
ever be in overlapping sessions, so the *family* - not each member
separately - is the unit that can only occupy one non-overlapping slot at
a time. Corrected to `FamilyOverdemand`/`find_overdemanding_families`,
comparing the union of every member's distinct requests against a ceiling
computed from the union of sessions any member is age-eligible for.

**Commit message**: `family_camp2 step 33: unmet-optional and structural-overdemand reports (FR-76/77)`

---

### - [x] Step 34: Tighten and minimise family splits (FR-17/FR-24)

**Goal**: after showing the user a real family (022/Glen) split across
two *optional* activities with an unbalanced adult/child mix, the user
asked to (1) tighten the supervision rule so every split session needs
both an adult and a child present (with an idle-adult exception for
children-only sessions - see REQUIREMENTS.md OQ-13 for the verbatim ask)
and (2) make the engine actively prefer not splitting families at all,
only doing so when unavoidable. This touches the shared validator and
*both* solvers, since Design A's exact objective and Design B's fitness
function both need to reflect the new rule.

- `validation/class2.py`: `UnsupervisedFamilySplit` gained a `reason`
  field (`"lone_adult"` / `"unaccompanied_child"`); `find_unsupervised_family_splits`
  now takes `campers` (needed for the idle-adult exception, which must
  see adults with *no* assignments at all, not just ones inferable from
  the timetable) and applies to every requested activity, not just
  priorities - broadened after 022/Glen's actual splits turned out to
  both be on optional activities. New `FamilySplitOccurrence`/
  `find_family_splits` (timetable-only, no violation implied) backs the
  new `Tier0Weights.family_split` band and `Class2Report.family_splits`
  (deliberately excluded from `is_clean` - a well-supervised split is a
  last resort, not a wrong answer).
- `validation/report.py`: reason-aware wording for poorly-supervised
  splits; a new non-violation "Family splits: N" summary line.
- `solvers/cp_sat.py`: `add_class2_indicators` rewritten to build
  `is_split`/`lone_adult`/`unaccompanied_child` BoolVars per
  (family, activity, session) for every requested activity, using a new
  `_idle_during` helper (memoised per (camper, session) - the same pair
  recurs across activities) for the idle-adult exception; `tier0_expr`
  gained the `family_split` weighted term. Mirrors the validator exactly
  (test_cp_sat_family_split.py cross-checks solver objective vs.
  independent validator score, matching test_cp_sat_tier0.py's existing
  pattern).
- `solvers/annealing/moves.py`: new `fix_lone_adult_split` (the symmetric
  repair to the existing `fix_unsupervised_split`, adding a child instead
  of an adult); wired into `solver.py`'s `_MOVE_KINDS`. No change needed
  to `scoring.py` - it already calls the shared `check_class2`/
  `score_tier0` directly, so the tightened rule and the new objective
  term apply automatically.
- `config.py`: `family_split` added to `_TIER0_WEIGHT_FIELDS`.
- `REQUIREMENTS.md`: FR-17 (supervision), FR-24 (minimisation, ranked
  above FR-20-23), OQ-13 (verbatim provenance), OQ-7 marked superseded.

**Deviations found during implementation**:
1. A literal per-member reading of "at least one adult and one child"
   would permanently, unfixably flag any split of an activity that no
   child in the family ever requested (or a family with no children at
   all) - there's no assignment that could ever satisfy it. Both the
   validator and CP-SAT's model exempt a (family, activity) pair from the
   lone-adult check when no non-adult family member requested that
   activity (`test_unsupervised_family_split_not_flagged_when_no_child_ever_requested_the_activity`).
2. The first `Tier0Weights` draft (10,000x ratios, matching the
   pre-existing pattern) pushed `missing_priority` to `10**16`, which made
   CP-SAT reject the model outright as `MODEL_INVALID` against real
   ~283-camper data - the objective's coefficients got large enough to
   risk integer overflow internally. Rescaled to 1,000x ratios
   (`missing_priority` back to its original `10**12`, `family_safety`
   `10**9`, `family_split` `10**6`, `under_minimum` `10**3`,
   `compulsory` `1`) - still comfortably clear of NFR-1's 500-camper
   scale, and verified against real data afterwards.

**Commit message**: `family_camp2 step 34: tighten and minimise family splits (FR-17/FR-24)`

---

### - [x] Step 35: PDF reports (FR-80/81/82/83)

**Goal**: partially reopen §1.2's printing exclusion at the user's
explicit request - they shared the old system's PDF output
(`fetched_data/old_reports/`, generated from
`family_camp/schedule/schedule_printer.py`) and asked for separate
activities/campers PDFs, A4/A3 and portrait/landscape support, using
"only native python tools", but explicitly inviting a better layout
rather than a port.

- Visually reviewed the old PDFs (`Read` renders PDF pages as images via
  `pdftoppm`/poppler - installed via `brew install poppler` for this,
  since it wasn't already present) and the old renderer's source. Found
  two structural causes of its 41-page-at-A4 length: one `Paragraph`
  flowable per camper name (no wrapping/table), and a forced
  `PageBreak()` before every single activity/family regardless of
  remaining room.
- `pyproject.toml`: new `pdf` extra (`reportlab` - pure-Python PDF
  generation, no external binaries/subprocesses, matching "native python
  tools" and the old system's own choice of library).
- `pdf_reports.py` (new): `PageSpec` (paper size x orientation ->
  resolved `reportlab.lib.pagesizes` tuple); `render_activities_pdf` (one
  table per activity, rows are *sessions* with attendees wrapped into one
  cell, not one row per camper); `render_campers_pdf` (one small
  attendance-matrix table per family - rows are sessions, columns are
  members, "X" marks who's where - falling back to a compact
  [session, attendees] list when a family has too many members for
  matrix columns to stay legible, see deviation below). Both use a
  single adaptive multi-column `BaseDocTemplate` (column count computed
  from actual page width, not the old system's hardcoded 2/4) with
  nothing force-broken between entries, and a single non-duplicated
  `_NumberedCanvas` (the old file had two drifted copies pasted in).
- `cli.py`: `--pdf-dir`/`--pdf-paper`/`--pdf-orientation`, lazily
  importing `pdf_reports` only when `--pdf-dir` is given (so `cli.py`
  itself doesn't require the `pdf` extra) with a friendly `ImportError`
  naming the install command if `reportlab` is missing, matching
  `io/google_sheets.py`'s existing pattern for the `google` extra.
- `REQUIREMENTS.md`: FR-80-83 added under a new §4.8, with a note on
  §1.2 marking the printing exclusion partially (narrowly) reopened.

**Deviations found during implementation**:
1. Wrapping a session's attendees into one cell revealed the real data's
   session `label` is usually identical to its own activity's name (e.g.
   a single-label activity), so naively showing both repeated the
   activity name on every row. Added `_activity_label` to suppress the
   label when it duplicates the activity name.
2. The campers matrix broke badly (mid-word wrapping, e.g. "Benjami n
   Winwo od") for families with several long-named members in a narrow
   column - the fundamental issue is that no font-size reduction can
   make an 11-character surname fit an ~28pt column while staying
   legible. Fixed two ways: `_short_name` drops a member's surname from
   their column header when it matches the family's own (inferred from
   `family_id`, e.g. `"012/Winwood"` -> `"Winwood"`) rather than
   repeating it in every column; and `render_campers_pdf` measures the
   resulting per-member column width and falls back to a plain
   [session, attendees] list (still one row per session, not per member)
   whenever it would drop below `_MIN_MEMBER_COLUMN_WIDTH`, which is
   robust regardless of name length or family size.
3. Verified against real data (283 campers): `activities.pdf` went from
   the old system's 41 pages (A4) to 6; `campers.pdf` to 15 (down further
   to 15 from an initial 19 after fixes 1-2 above).

**Commit message**: `family_camp2 step 35: PDF reports (FR-80/81/82/83)`

---

### - [x] Step 36: Available-adults PDF (FR-84)

**Goal**: a third PDF, requested right after Step 35, answering a
different question than the first two - not "who's doing what" but
"who's free right now" - to help an organiser find a spare adult
volunteer at a given point in time.

- `pdf_reports.py`: `render_available_adults_pdf` - one continuous table
  (not grouped, since there's only one dimension), one row per active
  time bucket from `validation.idle.find_idle_slots`, columns
  `[Time, #, Available adults]`. Reuses `IdleBucket.idle_adults` directly
  (already filtered to `Camper.is_adult` by the existing idle-time
  computation) rather than inventing a new "who's idle" concept -
  matches NFR-10's existing "reports reuse validator logic" principle.
  A bucket with nobody free renders as an explicit "—" row rather than
  being silently dropped, so a fully-staffed hour still shows as
  "checked, nobody available" rather than looking like a documentation
  gap.
- `cli.py`: wired into the existing `--pdf-dir` block as
  `available_adults.pdf` (no new CLI flags - reuses `--pdf-paper`/
  `--pdf-orientation`).
- `REQUIREMENTS.md`: FR-84 added to §4.8.

**Commit message**: `family_camp2 step 36: available-adults PDF (FR-84)`

---

### - [x] Step 37: Available-families PDF (FR-85)

**Goal**: a fourth PDF, requested right after Step 36 - the same
"who's free right now" question, but narrowed to adults whose *entire*
family has nothing scheduled at that time, a stronger availability
signal than the adult alone being idle (they won't need to break away to
rejoin a family member mid-activity).

- `pdf_reports.py`: `render_available_adults_pdf` refactored to share a
  new `_render_available_pdf(idle_report, output_path, page_spec, title,
  select)` helper with the new `render_available_families_pdf` - both
  build the identical `[Time, #, Available adults]` table, differing
  only in which adults `select` picks out of each `IdleBucket`. New
  `_family_idle_adults(bucket)` intersects `bucket.idle_adults` with
  `bucket.idle_families` (both already computed by `find_idle_slots` -
  no new validation logic, matching NFR-10) and is unit-tested directly
  (`test_family_idle_adults_excludes_an_adult_whose_family_member_is_busy`)
  rather than only indirectly through PDF output.
- `cli.py`: wired into the existing `--pdf-dir` block as
  `available_families.pdf`.
- `REQUIREMENTS.md`: FR-85 added to §4.8.
- Example PDFs (both A4 portrait and A3 landscape, from real 2026 camp
  data) written to `fetched_data/pdfs/` for all four PDF reports.
  Verified the narrowing has real effect: the busiest available-adults
  bucket lists up to 96 names; the same bucket in available-families
  narrows to a smaller, more genuinely-actionable list.

**Commit message**: `family_camp2 step 37: available-families PDF (FR-85)`

---

## 4. Manual editing and re-validation workflow (Steps 38–40)

### Context

Raised by the user wanting to hand-tweak a generated schedule and feed
it back through validation and reporting, rather than only ever
consuming a solver's own output as-is. Reopens part of §1.2's "Manual
editing workflow" exclusion in REQUIREMENTS.md, narrowly — re-validating
and re-reporting an edited schedule, not an interactive editor or
edit-time constraint enforcement.

Good news going in: most of what this needs already exists, built with
exactly this in mind. `io/schedule_export.py` (Step 27, FR-70/71)
already round-trips a `Timetable` to/from CSV/JSON. `validation/validator.py`'s
`validate()`, `reporting.py`, and `pdf_reports.py` were all already
built solver-agnostic — every one of them takes a `Timetable` plus the
original `activities`/`sessions`/`campers`, never a solver-specific
`SolveResult`. The gap is narrow: `cli.py`'s `main()` always calls a
solver; there is currently no path that skips solving and goes straight
from an edited schedule file to validation/reporting.

**REQUIREMENTS.md OQ-14–OQ-17 are now answered**; each step below
implements that answer directly (no longer provisional):

- **OQ-14 (edit format)**: reuse the existing CSV/JSON export format
  as-is, both supported.
- **OQ-15 (entry point shape)**: **(c) restructure the CLI into
  subcommands** (`family_camp2 solve` / `family_camp2 revalidate`) —
  this plan's original draft assumed (b), a separate
  `family_camp2-revalidate` script; Steps 38/40 below were rewritten for
  (c) once the answer came back. No new console script or
  `pyproject.toml` entry was needed as a result — `revalidate` lives in
  the same `cli.py`, dispatched via `argparse`'s subparsers.
- **OQ-16 (bad-row handling)**: collect and report every bad row before
  raising, not just the first.
- **OQ-17 (diff summary)**: out of scope for now — deferred, noted as a
  follow-on in §5 below.

### Step list

### - [x] Step 38: Restructure `cli.py` into `solve`/`revalidate` subcommands (OQ-15)

**Goal**: `argparse` subparsers (`solve`, `revalidate`), each command's
own flags kept separate (`--solver`/`--time-limit`/etc. only make sense
for `solve`), sharing everything downstream of "I have a Timetable" via
extracted helpers - so this step folds in what the draft plan had as a
separate "extract a shared output-writing helper" step, since the
subcommand restructuring needed that extraction anyway.

**Change** `cli.py`: `build_parser()` now builds a top-level parser with
`add_subparsers(dest="command", required=True)`; `_add_data_source_args`/
`_add_output_args` factor out the flag definitions shared by both
subcommands (`--data`/`--legacy-cache`/`--config` and
`--out`/`--export-schedule`/`--report-dir`/`--pdf-dir`/`--pdf-paper`/
`--pdf-orientation` respectively) so they're defined exactly once, not
duplicated per subcommand. `_write_outputs(timetable, report, campers,
sessions, args)` extracts the "given a timetable, its `ValidationReport`,
and the output flags, write everything `--out`/`--export-schedule`/
`--report-dir`/`--pdf-dir` ask for" logic that used to live inline in
`main()`'s tail - both `_run_solve`/`_run_revalidate` (see Step 40) call
it, so the two commands can never write reports differently. Each
subparser is wired to its handler via `set_defaults(func=...)`; `main()`
is now just `parser.parse_args(argv)` then `args.func(args)`.

**Deviation from the plan's draft**: the draft assumed OQ-15 would land
on a separate `family_camp2-revalidate` console script. The actual
answer was subcommands - no new script, no new `pyproject.toml` entry;
`revalidate` is dispatched from the same `cli.py`/`python -m family_camp2`
entry point `solve` already used (which itself changes shape:
`python -m family_camp2 --solver cp_sat ...` becomes
`python -m family_camp2 solve --solver cp_sat ...` - a breaking change
to the existing invocation, made deliberately rather than shimmed with a
default subcommand, consistent with this project's stance against
backwards-compatibility hacks).

**Tests**: every existing `test_cli.py`/`test_cli_smoke.py`/
`test_cp_sat_cli.py`/`test_annealing_cli.py` invocation updated to
prepend `"solve"` - this is a behaviour-preserving refactor for the
`solve` path (same flags, same outputs), just reached through one extra
positional argument.

**Commit message**: `family_camp2 step 38: restructure cli.py into solve/revalidate subcommands (OQ-15)`

---

### - [x] Step 39: Collect every unresolvable row on schedule re-import (OQ-16)

**Goal**: Change `load_schedule_csv`/`load_schedule_json`
(`io/schedule_export.py`) to report *every* row that can't be resolved
to a known camper/session, not just the first. Strict improvement for
every existing caller too (a solver's own valid export never has any bad
rows, so this only changes behaviour on genuinely invalid input) - no
fork/variant function needed, the existing functions' behaviour changes
in place.

**Add** `_resolve_rows(rows, campers_by_key, sessions_by_key)`: calls
the existing per-row `_resolve_row` for each row, catching
`ScheduleExportError` per row instead of letting the first one propagate,
collecting `f"Row {i}: {message}"` (1-based over data rows, matching what
a spreadsheet's row selector would show once the header row is
accounted for) for each failure, and raising once at the end - one
`ScheduleExportError` whose message lists every failing row - only if
there was at least one. `load_schedule_csv`/`load_schedule_json` now
call this instead of a bare set comprehension over `_resolve_row`.

**Tests** (`tests/test_schedule_export.py`): a CSV with three rows, two
independently bad (an unknown camper, and later an unknown session
label) and one good, raises a single error naming both bad rows and both
their row numbers; a bad row appended after otherwise-valid dumped rows
is still caught; existing round-trip tests (zero bad rows) unaffected.

**Commit message**: `family_camp2 step 39: collect every unresolvable row on schedule re-import (OQ-16)`

---

### - [x] Step 40: `revalidate` subcommand (FR-86/87/88/89)

**Goal**: The actual new capability - skip solving, load a hand-edited
schedule, and run it through the same validation/reporting pipeline a
solve would, using Step 38's subcommand structure and shared output
helper.

**Add** to `cli.py`: `_run_revalidate(args)` - loads the original input
data (`--data`/`--legacy-cache`, same as `solve`), loads `--schedule`
into a `Timetable` via `load_schedule_json`/`load_schedule_csv`
(dispatched on `args.schedule.suffix`), resolves `compulsory` from
`config.compulsory_activities` exactly as each solver already does
internally, then calls `validation.validator.validate(...)` directly -
no `get_solver`/`.solve()` call anywhere in this path (FR-86). Prints
`render_text` of the result exactly like `solve` does, then calls Step
38's `_write_outputs` for the export flags (FR-89). No new check for
FR-88 - `validate()` already reports Class 1 violations regardless of
where the `Timetable` came from; this step only exercises that on a new
kind of input.

**Update** `README.md` with a "Manual editing and re-validation" section
showing the two-command workflow end to end (generate + export,
hand-edit the CSV, re-validate), all CLI usage examples elsewhere in the
file updated for the `solve`/`revalidate` split, and the Architecture
section's `cli.py` line updated.

**Tests** (`tests/test_cli.py`): `revalidate` on a schedule freshly
exported by `solve` (unedited) reproduces the same Tier 0 score printed
by `solve` - confirms no solver involvement changes the outcome;
`.json`-suffixed schedules are also accepted; a schedule hand-built to
duplicate an existing assignment onto a second session of the same
activity (a genuine Class 1 violation no solver output could ever have)
surfaces as `Feasible: False` with a `Duplicate activity` line (FR-88);
a schedule with two independently-unresolvable rows raises one error
naming both (OQ-16, exercised through the CLI as well as directly in
`test_schedule_export.py`); `--out`/`--report-dir` both work from
`revalidate` (FR-89).

**Commit message**: `family_camp2 step 40: revalidate subcommand (FR-86/87/88/89)`

---

## 5. Per-camper/family custom constraints (Steps 41–47)

### Context

Raised by the user wanting to express requirements the engine has no
other way to capture, e.g. "022/Glen must not have any activities on the
2nd day" or "Emma Glen (022/Glen) must not have any activity before
11:00" - parameterised by rows on a new Google Sheet tab, editable by an
organiser without a code change. Implements REQUIREMENTS.md §3.5/§4.10
(FR-90-96).

The central design idea, from the design discussion this phase is based
on: nearly every useful constraint of this kind reduces to a
per-(camper, session) predicate - "is this camper allowed in this
session at all?" - exactly the mechanism that already makes Class 1
structurally guaranteed in both solvers (`_is_eligible` in
`cp_sat.py`/`annealing/moves.py`). A constraint expressible this way
(**Tier A** - covers both worked examples, and everything in FR-96) gets
hard *and* soft enforcement in both solvers essentially for free. A
constraint that isn't (**Tier B** - e.g. "must always be with camper X")
needs bespoke work per rule and is explicitly out of scope for this
phase (FR-90/OQ-22).

**REQUIREMENTS.md OQ-18–OQ-22 are now answered**; each step below
implements that answer directly:

- **OQ-18 (syntax)**: function-call-like expression, parsed via Python's
  `ast` module in restricted/safe mode (never `eval()`).
- **OQ-19 (data flow)**: a new `EngineConfig.constraints` field - no
  change to the `Solver` protocol.
- **OQ-20 (soft weighting)**: one shared `Tier0Weights.custom_constraint`
  band, not a per-record weight.
- **OQ-21 (severity ranking)**: **`custom_constraint` ranks above
  `missing_priority`** - the single most severe band, above even
  priorities. Notably different from this plan's original draft
  assumption (which guessed it would rank below `family_split`). The
  exact weight *value* is still deliberately left to Step 45, which
  re-derives the whole six-band scale from scratch (see that step's
  note on the Step 34 `MODEL_INVALID` lesson) rather than only inserting
  a new top band above the existing five numbers.
- **OQ-22 (Tier B scope)**: Tier A only, per FR-96 - confirmed sufficient
  for this phase.

### Step list

### - [x] Step 41: Constraint domain model + registry

**Goal**: The pure-Python foundation - a rule protocol and a
name-to-class registry, independent of parsing, data loading, or either
solver, mirroring `solvers/registry.py`'s existing pattern exactly
(FR-90).

**Add** `src/family_camp2/constraints/base.py`:
- `ConstraintRule` (`Protocol`): the Tier A contract is one method,
  `forbids(camper: Camper, session: Session) -> bool` - true if this
  session would violate the rule for this camper. (Implementation note:
  a rule like "day 2" needs the full session list to know which
  calendar date *is* day 2 - work out during implementation whether that
  context is resolved once at construction time or passed per-call;
  don't let this detail block Step 41's own tests, which can use small
  fixed session lists either way.)
- `ConstraintInstance` (frozen dataclass): `targets: tuple[Camper, ...]`
  (already resolved - see Step 42), `rule: ConstraintRule`,
  `severity: Literal["hard", "soft"]`, `note: str`.

**Add** `src/family_camp2/constraints/registry.py`: `@register("name")`
class decorator + `get_constraint_class(name) -> type[ConstraintRule]`,
structurally identical to `solvers/registry.py`.

**Add** `src/family_camp2/constraints/rules.py` — the FR-96 Tier A set:
`NoActivitiesOnDay(day: int)`, `NoActivityBefore(time: str)`,
`NoActivityAfter(time: str)`, `NoActivitiesBetween(start: str, end:
str)`, `NotOnActivity(activity: str)`.

**Tests** (`tests/test_constraints_rules.py`): each rule's `forbids()`
against hand-built camper/session fixtures - both a session it should
forbid and one it shouldn't, per rule; the registry round-trips
`register`/`get_constraint_class`, and raises a clear error for an
unknown name.

**Commit message**: `family_camp2 step 41: constraint domain model and registry (FR-90)`

---

### - [x] Step 42: Safe expression parser + target resolution (FR-91/92/93)

**Goal**: Turn one raw constraint record (family_id, camper_name,
constraint expression string, severity, note) into a `ConstraintInstance`
or a clear, collected error - never `eval()` (FR-92), never stop at the
first bad record (FR-93, same shape as OQ-16/Step 39's precedent for
schedule re-import).

**Add** `src/family_camp2/constraints/parser.py`:
- `parse_expression(expr: str) -> tuple[str, list, dict]`: `ast.parse(expr,
  mode="eval")`, walks the tree, accepts *only* a single `Call` node with
  a bare `Name` and `Constant`/`List`/negative-number-`UnaryOp` arguments
  - anything else raises `ConstraintParseError` naming the problem.
- `resolve_target(family_id, camper_name, campers) -> tuple[Camper, ...]`:
  same `(family_id, camper.name)`/`family_id`-only lookup convention
  `io/schedule_export.py` already established (FR-91) - blank
  `camper_name` resolves to every member of the family.
- `build_constraint_instances(records, campers) -> list[ConstraintInstance]`:
  resolves every record, collecting `(record index, error)` pairs for
  anything that fails (unknown target, unparseable expression, unknown
  rule name, wrong argument count/types for that rule) and raising one
  combined error only if there's at least one, mirroring
  `schedule_export._resolve_rows`'s Step 39 shape exactly.

**Tests** (`tests/test_constraints_parser.py`): valid expressions for
each Step 41 rule parse correctly; malformed expressions (not a call,
disallowed node type, e.g. an attribute access or a nested call) are
rejected with a clear message; an unresolvable family/camper is reported;
multiple simultaneously-bad records in one batch are all named in a
single raised error, not just the first.

**Commit message**: `family_camp2 step 42: safe constraint expression parser and target resolution (FR-91/92/93)`

---

### - [ ] Step 43: Data loading and `EngineConfig` wiring (OQ-19)

**Goal**: Get constraints from an input file into `solve()`. Assumes
OQ-19 answered "`EngineConfig` field."

**Change** `io/json_loader.py`: `load_json` gains an optional
`"constraints"` array in the JSON schema (§3.5's fields: `family_id`,
`camper_name` nullable, `constraint`, `severity`, `note` optional),
defaulting to `[]` when absent; returns constraints as a fourth element
alongside `activities`/`sessions`/`campers` (every existing call site -
`cli.py`, `fixtures.py`, tests - updated for the new return shape).

**Change** `config.py`: `EngineConfig` gains
`constraints: tuple[ConstraintInstance, ...] = ()`.

**Change** `cli.py`: after loading data and config separately (as today),
merge the loaded constraints into the `EngineConfig` actually used
(`dataclasses.replace(config, constraints=...)`) before calling
`solver.solve(...)` (in `_run_solve`) or `validate(...)` (in
`_run_revalidate` - a hand-edited schedule should be checked against the
same custom constraints the original solve used).

**Tests**: JSON round-trip with a non-empty `"constraints"` array
produces the expected `ConstraintInstance` list; `EngineConfig` carries
them through; a small end-to-end CLI test with a hand-authored
constraints array (not yet enforced by either solver until Steps 44/45 -
this step only proves the data reaches `config.constraints`).

**Commit message**: `family_camp2 step 43: load custom constraints from --data and wire into EngineConfig (OQ-19)`

---

### - [ ] Step 44: Hard-constraint enforcement in both solvers (FR-94)

**Goal**: A hard constraint becomes structurally impossible to violate,
in both solvers, using only the existing eligibility mechanism - no new
modeling concept.

**Change** `solvers/cp_sat.py`: `_is_eligible(camper, session)` (and
`build_model`'s signature) also checks that no *hard* constraint in
`config.constraints` forbids the pair.

**Change** `solvers/annealing/moves.py`: the equivalent `_is_eligible`
gets the same check; `run_chain`/`run_restarts`/`AnnealingSolver.solve`
thread `constraints` through to it.

**Tests**: a hard `NoActivityBefore` constraint means neither solver ever
assigns that camper to an early session (checked directly against the
resulting `Timetable`, both solvers); when that early session was the
camper's *only* eligible option for a priority activity, confirm this
surfaces as an ordinary `missing_priority` violation (FR-94) rather than
a crash or a silently-dropped priority - mirrors the existing "no
eligible session at all" handling in `_reify_activity_missing`.

**Commit message**: `family_camp2 step 44: hard custom-constraint enforcement via eligibility filtering (FR-94)`

---

### - [ ] Step 45: Soft-constraint scoring (FR-95)

**Goal**: A soft constraint is penalised, not enforced - the same
demand-driven, best-effort treatment Class 2 already gives
`missing_priority`/`family_split`/etc.

**Add** `find_custom_constraint_violations(timetable, config.constraints)`
(new module or folded into `validation/class2.py`), mirroring
`find_missing_priorities`'s shape: for each soft `ConstraintInstance`,
for each target camper actually assigned to a session their rule
forbids, one violation record.

**Change** `validation/class2.py`: `Tier0Weights` gains a
`custom_constraint` field; `Class2Report`/`check_class2`/`score_tier0`
include it. **Re-derive the weight scale carefully here** (OQ-21) -
Step 34's deviation note recorded that naively extending the established
1,000x-ratio pattern by one more band pushed `missing_priority` back
into the range that caused a real `MODEL_INVALID` overflow in CP-SAT
against real ~283-camper data; don't repeat that mistake by just
tacking a sixth band onto the existing five numbers.

**Change** `solvers/cp_sat.py`: `add_class2_indicators`/`tier0_expr`
gain reified indicators for soft-forbidden (camper, session)
assignments, mirroring the existing Class 2 indicator pattern exactly.
No equivalent annealing change needed beyond Step 43's threading of
`constraints` through to `config` - annealing's scoring already calls
the shared validator machinery, so this falls out for free (the design's
core payoff) - verify with a cross-solver-agreement test rather than
assuming it.

**Tests**: a soft constraint's violation is reported and contributes to
`tier0_score` without affecting `Feasible: True`; CP-SAT's own internal
objective value agrees with the independent validator's score on a hand-
verified small instance (mirroring `test_cp_sat_family_split.py`'s
pattern); annealing's best-found score reflects a soft violation too.

**Commit message**: `family_camp2 step 45: soft custom-constraint scoring (FR-95)`

---

### - [ ] Step 46: Google Sheets fetch integration

**Goal**: The real-world input path - a new "Constraints for schedule"
worksheet, fetched the same way the other three already are.

**Change** `io/google_sheets.py`: `DEFAULT_CONSTRAINTS_WORKSHEET`
constant; parse the new sheet via the same header-name-driven
`_extract_table` pattern already used for Activities/Sessions/Campers,
producing raw records fed through Step 42's `build_constraint_instances`.

**Change** `fetch_cli.py`: `--constraints-worksheet` override flag,
matching the existing `--activities-worksheet`/`--sessions-worksheet`/
`--campers-worksheet`; fetched constraints included in the JSON this
tool writes (Step 43's `"constraints"` array).

**Tests** (`tests/test_google_sheets.py`): a raw worksheet-row fixture
for the new tab (preamble/header/blank-row messiness, matching the
existing fixtures' realism) parses to the expected `ConstraintInstance`
list.

**Commit message**: `family_camp2 step 46: fetch custom constraints from a new Google Sheets tab`

---

### - [ ] Step 47: Documentation

**Goal**: Everything this phase added is discoverable without reading
source.

**Update** `README.md`: a new "Custom constraints" section - the §3.5
record schema, the expression syntax with both of the user's original
worked examples, the FR-96 Tier A rule list, hard vs. soft, and an
explicit note that Tier B (relational/aggregate rules) is an
acknowledged extension point for the same architecture, not built by
this phase.

**Final check**: full test suite green from a fresh `pip install -e
".[dev]"` in a new venv, same as previous phases' final steps.

**Commit message**: `family_camp2 step 47: document custom constraints`

---

## 6. After this plan

Not part of this plan, but worth flagging for a follow-up plan once this
one is complete and in real use:

- Tier B custom constraint rules (relational, e.g. "must always be with
  camper X"; aggregate, e.g. "no more than 2 activities per day") -
  the architecture (Step 41's registry) accommodates them, but each one
  needs bespoke validator logic and, if hard, bespoke solver modeling,
  unlike Tier A's uniform eligibility-filtering treatment.
- Per-constraint-record soft weighting (OQ-20, if a single shared band
  turns out to be too coarse in practice).

- OQ-17: a diff summary (assignments added/removed/moved) when
  re-validating an edited schedule against the one it was edited from -
  deferred by this plan; would sit naturally alongside Step 40's entry
  point if wanted later.

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
