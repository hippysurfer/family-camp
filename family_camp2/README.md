# family_camp2

A from-scratch rewrite of the Family Camp **scheduling engine only** —
consuming camper/activity/session data and producing a timetable, plus
validating any timetable against the rules that define a correct schedule.

This is *not* a replacement for the rest of the `family_camp` package yet:
fetching data from Google Sheets, printing PDFs, and the hand-editing
workflow all still live in `../family_camp/` and are untouched. See:

- [`../DESIGN.md`](../DESIGN.md) — review of the original GA-based scheduler.
- [`../REQUIREMENTS.md`](../REQUIREMENTS.md) — solver-agnostic requirements this rewrite implements (`FR-n`/`NFR-n`/`OQ-n` referenced throughout this codebase).
- [`../DESIGN_OPTIONS.md`](../DESIGN_OPTIONS.md) — the two solver designs (CP-SAT and simulated annealing) implemented here, and why both were built.
- [`../IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) — the step-by-step plan this package was built from.

## Install and test

```sh
cd family_camp2
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## CLI usage

`--solver` is required and selects which of the two designs to run.
Exactly one of `--data` or `--legacy-cache` supplies the input data.

```sh
# Constraint programming (Design A) against a JSON camp file
python -m family_camp2 --solver cp_sat --data tests/fixtures/small_camp.json

# Simulated annealing (Design B), tuned, with a reproducible seed
python -m family_camp2 --solver annealing --data tests/fixtures/small_camp.json \
    --num-chains 8 --iterations-per-chain 2000 --seed 1

# Against a real camp's existing .cache.pickle (produced by the unmodified
# family_camp/schedule/fetch_data.py - see io/legacy_cache_loader.py)
python -m family_camp2 --solver cp_sat --legacy-cache ../.cache.pickle

# Write the full structured report to a file as well as stdout
python -m family_camp2 --solver cp_sat --data tests/fixtures/small_camp.json --out report.json
```

Other flags: `--config PATH` (an `EngineConfig` JSON file, see below),
`--time-limit SECONDS` (both solvers), `--seed INT` (both solvers),
`--num-chains`/`--iterations-per-chain` (annealing only).

## Input data

### JSON format (`--data`)

A hand-writable or generated format, documented in full (with an example)
in the `family_camp2.io.json_loader` module docstring:

```json
{
  "activities": [
    {"name": "Archery", "duration_minutes": 60, "min_occupancy": 1, "max_occupancy": 10, "min_age": null}
  ],
  "sessions": [
    {"activity": "Archery", "label": "Morning", "start": "2026-08-01T09:00:00"}
  ],
  "campers": [
    {"name": "Kid", "family_id": "F1", "age": 10, "age_group": "Cub",
     "priorities": ["Archery"], "optional": ["Craft"]}
  ]
}
```

See `tests/fixtures/small_camp.json` for a complete worked example.

### Legacy cache format (`--legacy-cache`)

Reads the `.cache.pickle` file already produced by the existing,
unmodified `family_camp/schedule/fetch_data.py` — see
`family_camp2.io.legacy_cache_loader` for the exact column layout it
expects. This lets the new engine run against real historical camp data
without needing any new data-fetch work.

### Engine config (`--config`)

Optional JSON file overriding `EngineConfig` (see `family_camp2.config`):
`tier0_weights` (severity weights for the demand-driven Class 2 rules),
`objective_order` (must be a permutation of `["tier0", "tier1", "tier2"]`
— the OQ-4 ranking mechanism), and `compulsory_activities` (activity names
everyone must attend, empty by default per OQ-5).

## Architecture

```
domain.py            Activity / Session / Camper / Timetable
validation/          solver-independent rules (Class 1/2, Tier 1/2, idle-time, the FR-40/41 report)
config.py            EngineConfig (NFR-4)
io/                  JSON and legacy-cache loaders
solvers/
  base.py            the Solver protocol every design implements
  registry.py         name -> Solver lookup, used by the CLI
  cp_sat.py           Design A: OR-Tools CP-SAT, three-phase lexicographic solve
  annealing/          Design B: simulated annealing with domain-aware moves
cli.py                argparse entry point (--solver cp_sat|annealing)
```

The validator (`validation/validator.py`) is the single source of truth
for "is this schedule correct and how good is it" — both solvers produce
a `Timetable` and then hand it to the *same* validator, so scoring logic
is never duplicated per-solver. See DESIGN_OPTIONS.md §2 for the
Class 1 (structurally-guaranteed) vs. Class 2 (demand-driven,
best-effort) distinction this is built around.

## Adding a third solver

Implement the `Solver` protocol (`solvers/base.py`): one method,
`solve(activities, sessions, campers, config) -> SolveResult`. Register it
with `@register("your-name")` (`solvers/registry.py`) on the class, add an
import for your module to `solvers/__init__.py` so the registration runs,
and add `"your-name"` to the CLI's `--solver` choices
(`cli.build_parser`). Your solver only needs to search for a good
`Timetable` — pass it through `validation.validator.validate(...)` before
returning, so its correctness/quality is reported exactly like the other
two.
