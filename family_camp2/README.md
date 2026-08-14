# family_camp2

A from-scratch rewrite of the Family Camp **scheduling engine only** —
consuming camper/activity/session data and producing a timetable, plus
validating any timetable against the rules that define a correct schedule.

This is *not* a replacement for the rest of the `family_camp` package yet:
printing PDFs and the hand-editing workflow still live in `../family_camp/`
and are untouched. It does include its own way to fetch input data from
Google Sheets (`fetch_cli.py`, below) — independent of the old
`family_camp/schedule/fetch_data.py`, and producing this package's own
JSON format rather than a pickle cache. See:

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

# A long CP-SAT run: progress every 60s to a log file, plus the actual
# schedule (not just the validation report) and human-readable reports
python -m family_camp2 --solver cp_sat --data data.json --time-limit 5400 \
    --progress-output run.log --export-schedule schedule --report-dir reports/
```

Other flags: `--config PATH` (an `EngineConfig` JSON file, see below),
`--time-limit SECONDS` (both solvers), `--seed INT` (both solvers),
`--num-chains`/`--iterations-per-chain` (annealing only),
`--progress-output`/`--progress-interval`, `--export-schedule`,
`--report-dir` (all documented in the next section).

## Progress reporting and report generation

Implements REQUIREMENTS.md §4.6/§4.7 (FR-60–75) - reverse-engineered from
the old system's per-generation progress printing and its
Hall-of-Fame/`check_schedule.py` reports, plus direct experience running a
real multi-hour CP-SAT job with none of this and no way to see what was
happening (see DESIGN_OPTIONS.md-adjacent history in
IMPLEMENTATION_PLAN.md §3).

**Progress** (`--progress-output`, `--progress-interval`): on by default -
there's no separate on/off flag, redirect to a file (or `/dev/null`) to
silence it. `--progress-output -` (the default) writes to stdout,
interleaved with the final report; any other value is a file path.
`--progress-interval SECONDS` (default 60) controls the cadence for
CP-SAT, which reports on a genuine wall-clock timer via a background
heartbeat thread (so it keeps reporting even during a long stretch with no
improving solution - see the module note in `solvers/cp_sat.py`).
Annealing instead reports each time a restart chain finishes (see the
module note in `solvers/annealing/solver.py` for why - at real-world
scale, chains finish in seconds, well inside the default cadence anyway).

**Schedule export** (`--export-schedule PATH`): writes the actual
generated timetable - who's assigned to what, distinct from `--out`'s
scoring/violation report - as **both** `PATH.csv` and `PATH.json` (any
extension typed on `PATH` is stripped first). Re-importable via
`family_camp2.io.schedule_export.load_schedule_csv`/`load_schedule_json`.

**Operational reports** (`--report-dir PATH`): writes five text files
into `PATH` (created if needed):
- `family_itinerary.txt` - each family's assigned sessions, in time order.
- `activity_roster.txt` - each session's assigned campers, with occupancy
  against the activity's limit.
- `idle_report.txt` - per time-bucket, which whole families have nobody
  scheduled and which adults specifically are idle (two distinct views,
  matching the old system - a family with nobody scheduled is a different
  signal from "this specific adult happens to be free to help").
- `unmet_optional_report.txt` (FR-76) - optional (non-priority) activity
  requests that weren't met in the generated timetable, grouped by
  activity - the per-request breakdown behind the aggregate Tier 1 score.
- `unfeasible_families_report.txt` (FR-77) - families with a member who
  requested more distinct activities than the maximum number of
  non-overlapping session slots they could ever occupy across the whole
  camp, regardless of capacity (see `validation/feasibility.py`'s module
  docstring for exactly what this ceiling does and doesn't prove - it's a
  necessary-infeasibility check, not a full solver). Useful for telling
  "not enough capacity" apart from "not enough time" as the reason an
  optional request went unmet.

Not implemented: exporting more than one candidate schedule when a solver
has several (e.g. annealing's other restart chains) - REQUIREMENTS.md
FR-75 is a *should*, and OQ-12 confirmed a single best answer is
sufficient for this rewrite.

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

### Fetching data from Google Sheets (`fetch_cli.py`)

`fetch_cli.py` downloads the same three worksheets the old system reads
("Activities for schedule", "Sessions for schedule", "Activities") and
saves them straight into this package's own JSON format, ready for
`--data`:

```sh
pip install -e ".[google]"   # pulls in gspread, only needed for this tool

python -m family_camp2.fetch_cli --sheet-id <SHEET_ID_OR_URL> --out data.json
# or, via the console script installed by pip:
family_camp2-fetch --sheet-id <SHEET_ID_OR_URL> --out data.json

python -m family_camp2 --solver cp_sat --data data.json
```

Authentication is the interactive **user OAuth flow**, not the old
system's service-account key: the first run opens a browser for you to
sign in to Google and grant *read-only* access
(`gspread.auth.READONLY_SCOPES` — this tool never writes to the sheet);
gspread caches the resulting token afterwards, so you don't repeat the
consent step on later runs. Pass `--credentials PATH` to use your own
Google Cloud OAuth client instead of gspread's shared default one (needed
if you hit its rate limits), and `--authorized-user PATH` to control where
the cached token is stored. If your spreadsheet uses different tab names,
override them with `--activities-worksheet`/`--sessions-worksheet`/`--campers-worksheet`.

See `family_camp2.io.google_sheets` for the fetch/parse logic (it shares
its row-parsing with `io/legacy_cache_loader.py`, since both start from
the same raw worksheet-row shape) and `fetch_cli.py` for the full CLI.

### Engine config (`--config`)

Optional JSON file overriding `EngineConfig` (see `family_camp2.config`):
`tier0_weights` (severity weights for the demand-driven Class 2 rules),
`objective_order` (must be a permutation of `["tier0", "tier1", "tier2"]`
— the OQ-4 ranking mechanism), and `compulsory_activities` (activity names
everyone must attend, empty by default per OQ-5).

## Architecture

```
domain.py            Activity / Session / Camper / Timetable
validation/          solver-independent rules (Class 1/2, Tier 1/2, idle-time incl. family/adult views, structural overdemand, the FR-40/41 report)
config.py            EngineConfig (NFR-4)
progress.py          ProgressEvent/ProgressReporter/PeriodicHeartbeat (FR-60/61, NFR-9)
reporting.py         per-family/per-activity/idle/unmet-optional/overdemand text reports, from a Timetable (FR-72/73/74/76/77)
io/                  JSON loader/writer, legacy-cache loader, Google Sheets fetch (OAuth), schedule CSV/JSON export (FR-70/71)
solvers/
  base.py            the Solver protocol every design implements
  registry.py         name -> Solver lookup, used by the CLI
  cp_sat.py           Design A: OR-Tools CP-SAT, three-phase lexicographic solve, wall-clock progress heartbeat
  annealing/          Design B: simulated annealing with domain-aware moves, per-chain progress
cli.py                argparse entry point (--solver cp_sat|annealing)
fetch_cli.py          argparse entry point to download --data input from Google Sheets
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

Progress reporting is optional but recommended for anything that can run
longer than a few seconds: accept a `progress_reporter: ProgressReporter =
NullProgressReporter()` constructor kwarg (matching `time_limit_seconds`/
`random_seed`'s existing pattern - `registry.get_solver(name, **kwargs)`
already passes constructor kwargs through uniformly, no protocol change
needed) and call `.report(ProgressEvent(...))` on it periodically. See
`progress.py` for `PeriodicHeartbeat` (a wall-clock timer, for a solver
with one long blocking call) and `solvers/annealing/solver.py`'s
`run_restarts` (per-unit-of-work reporting, for a solver that's already a
visible Python loop or naturally chunked across multiple processes).
