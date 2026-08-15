# family_camp2

A from-scratch rewrite of the Family Camp **scheduling engine only** —
consuming camper/activity/session data and producing a timetable, plus
validating any timetable against the rules that define a correct schedule.

This is *not* a full replacement for the rest of the `family_camp`
package: this package has its own PDF reports (`pdf_reports.py`, below)
and its own hand-editing/re-validation workflow (`revalidate`, below),
but the old package's other tooling (packs, the booking-site automation)
is untouched. It does include its own way to fetch input data from
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

`python -m family_camp2` has two subcommands (OQ-15): `solve` generates
a schedule with a solver; `revalidate` takes a previously exported
schedule (optionally hand-edited) and runs it through the same
validation/reporting pipeline *without* running a solver - see "Manual
editing and re-validation" below. Both share the `--data`/`--legacy-cache`
data-source flags and the `--out`/`--export-schedule`/`--report-dir`/
`--pdf-dir` output flags.

```sh
# Constraint programming (Design A) against a JSON camp file
python -m family_camp2 solve --solver cp_sat --data tests/fixtures/small_camp.json

# Simulated annealing (Design B), tuned, with a reproducible seed
python -m family_camp2 solve --solver annealing --data tests/fixtures/small_camp.json \
    --num-chains 8 --iterations-per-chain 2000 --seed 1

# Against a real camp's existing .cache.pickle (produced by the unmodified
# family_camp/schedule/fetch_data.py - see io/legacy_cache_loader.py)
python -m family_camp2 solve --solver cp_sat --legacy-cache ../.cache.pickle

# Write the full structured report to a file as well as stdout
python -m family_camp2 solve --solver cp_sat --data tests/fixtures/small_camp.json --out report.json

# A long CP-SAT run: progress every 60s to a log file, plus the actual
# schedule (not just the validation report) and human-readable reports
python -m family_camp2 solve --solver cp_sat --data data.json --time-limit 5400 \
    --progress-output run.log --export-schedule schedule --report-dir reports/
```

`solve`-only flags: `--solver {cp_sat,annealing}` (required),
`--time-limit SECONDS` (both solvers), `--seed INT` (both solvers),
`--num-chains`/`--iterations-per-chain` (annealing only),
`--progress-output`/`--progress-interval`. Shared with `revalidate`:
`--data`/`--legacy-cache` (mutually exclusive, required), `--config
PATH` (an `EngineConfig` JSON file, see below), `--export-schedule`,
`--report-dir`, `--pdf-dir`/`--pdf-paper`/`--pdf-orientation` (all
documented in the next section).

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
  Campers whose family also appears in `unfeasible_families_report.txt`
  are marked `[over demand]`.
- `unfeasible_families_report.txt` (FR-77) - families whose members
  collectively requested more distinct activities than the family could
  ever fit into non-overlapping session slots across the whole camp,
  regardless of capacity. This is computed per-*family*, not per-camper:
  Class 2's family-time-conflict rule means no two members can be in
  overlapping sessions, so the family - not the individual - is the unit
  that can only occupy one slot at a time (see
  `validation/feasibility.py`'s module docstring for exactly what this
  ceiling does and doesn't prove - it's a necessary-infeasibility check,
  not a full solver). Useful for telling "not enough capacity" apart from
  "not enough time" as the reason an optional request went unmet.

Not implemented: exporting more than one candidate schedule when a solver
has several (e.g. annealing's other restart chains) - REQUIREMENTS.md
FR-75 is a *should*, and OQ-12 confirmed a single best answer is
sufficient for this rewrite.

**PDF reports** (`--pdf-dir PATH`, `--pdf-paper {a4,a3}` default a4,
`--pdf-orientation {portrait,landscape}` default portrait): writes
`activities.pdf`, `campers.pdf`, `available_adults.pdf`, and
`available_families.pdf` into `PATH` (created if needed) -
FR-80/81/82/84/85, added at the user's request after reviewing the old
system's PDF output. Uses `reportlab` (a pure-Python PDF library, no
external binaries/subprocesses) - a core dependency, installed
automatically alongside `family_camp2` itself, since the status report
below (§4.11) needs it unconditionally on every run regardless of
`--pdf-dir`. Examples of all four (both A4 portrait and A3 landscape)
generated from real 2026 camp data are in `fetched_data/pdfs/`.

Deliberately not a port of the old layout - see
`family_camp2.pdf_reports`'s module docstring for the two changes that
make these documents dramatically shorter for the same camp (41 pages of
activity roster at A4 down to 6): a session's attendees are one wrapped
table cell, not one line per camper; and nothing is force-broken onto a
new page, so short entries pack into the adaptive multi-column layout
(more/fewer columns depending on paper size and orientation) instead of
each claiming a page. `campers.pdf` also uses a different shape entirely:
one small attendance-matrix table per family (rows = sessions, columns =
members, an "X" marks who's where) rather than one row per
(member, session) pair, falling back to a compact list when a family has
too many members for matrix columns to stay legible at the current paper
size. `available_adults.pdf`/`available_families.pdf` answer a different
question again - not "who's doing what" but "who's free right now": one
row per active time period listing which *adult* campers (children
aren't volunteer candidates) have nothing scheduled, for an organiser
hunting for a spare pair of hands - reusing the existing idle-time
computation (`validation.idle.find_idle_slots`) rather than any new
logic. `available_families.pdf` narrows this further to adults whose
*entire family* also has nothing scheduled at that time (not just the
adult themselves) - a stronger availability signal, since they won't
need to break away to rejoin a family member who's mid-activity.

## Schedule status report

REQUIREMENTS.md §4.11 (FR-97-109): a single A4-portrait PDF bringing
together front matter, activity/session loading, camper/family
fulfilment, and solver diagnostics - a one-stop overview for the
organiser reviewing a run, distinct from the audience-specific reports
above and from the plain violation report (FR-40/41) alone.

Unlike every other output in this document, it's generated
**unconditionally** on every `solve`/`revalidate` run - there's no
opt-in flag to switch it off. Its output location defaults to
`<export-schedule-stem>_status_report.pdf` when `--export-schedule` is
given, else `./status_report.pdf`; `--status-report PATH` overrides
either default:

```sh
python -m family_camp2 solve --solver cp_sat --data data.json
# -> ./status_report.pdf

python -m family_camp2 solve --solver cp_sat --data data.json --export-schedule out/schedule
# -> out/schedule_status_report.pdf

python -m family_camp2 solve --solver cp_sat --data data.json --status-report reports/status.pdf
# -> reports/status.pdf
```

Five sections, in order:

1. **Front matter** - generation timestamp, camp date range/duration
   (derived from the session data, never assumed), headline counts.
2. **Camp activity information** - a per-activity table (sessions,
   min/max occupancy, compulsory flag) and a graphical activity
   timetable. The timetable is a two-day Gantt-style grid when the camp
   spans exactly 2 distinct calendar days (an explicit, narrow exception
   to this engine's usual no-fixed-length rule, scoped to this one
   visualisation); for any other camp length it falls back to a plain
   date/activity/session table instead of guessing at a shape that
   doesn't fit.
3. **Activity session loading** - occupancy vs. capacity per session
   (stacked bar: used vs. spare), with sessions below their activity's
   minimum occupancy visually distinguished, plus mean/spread statistics
   ("ideal" session size is its own `max_occupancy` - a fully-booked
   session is ideal).
4. **Camper/family activity loading** - one stacked bar per camper and
   per family (priorities met/unmet, optional met/unmet), every one
   included and paginated across as many pages as needed rather than
   sampled - sorted so a family's members stay adjacent to its own
   family-level bar. Campers/families with an unmet priority are
   doubly distinguished (their own bar segment and a coloured label).
   Families that could never fit their requests regardless of capacity
   (the same structural check as `unfeasible_families_report.txt` above)
   are called out separately.
5. **Solver information** - which solver ran and how long it took (or
   an explicit "N/A" when the report came from `revalidate`, not a real
   solve), the Tier 0/1/2 score breakdown, every violation category's
   count, and a summary of custom constraints in effect (§4.10 - how
   many hard, how many soft, how many soft ones had a violation).

See `family_camp2.status_report`'s module docstring for the
data/render split (NFR-6) this follows - the same pattern already used
throughout `validation/`.

## Manual editing and re-validation

Implements REQUIREMENTS.md §4.9 (FR-86-89) - partially reopens §1.2's
"manual editing workflow" exclusion, at the user's explicit request. The
scope is narrow and specifically *not* an interactive editor: take a
schedule `solve --export-schedule` already wrote out, hand-edit the CSV
(or JSON) in a spreadsheet, and get it back through the exact same
validation and reporting `solve` would have run, without re-running a
solver.

```sh
python -m family_camp2 solve --solver cp_sat --data data.json --export-schedule schedule
# ...open schedule.csv, tweak who's assigned where, save...
python -m family_camp2 revalidate --data data.json --schedule schedule.csv \
    --report-dir reports/ --pdf-dir pdfs/
```

`--schedule PATH` (required) is dispatched to `io.schedule_export.load_schedule_csv`/
`load_schedule_json` by its extension (OQ-14 - the existing FR-70/71
export format is reused as-is, not a new edit-oriented layout: every
edit is just adding, removing, or changing a row). A row that doesn't
resolve to a known camper/session (most likely a typo) raises - and
(OQ-16) *every* bad row is collected and reported together, not just the
first, since a hand-editing session is likely to contain more than one
mistake.

Unlike a solver's own output, a hand-edited schedule can genuinely fail
Class 1 (structural) checks - double-booking, capacity overflow, a
duplicate activity - since those are only *structurally* impossible when
a solver builds the `Timetable` itself (FR-88). `revalidate` doesn't
special-case this: it calls the exact same `validate(...)` `solve` does,
so a bad edit shows up in `Feasible: False` and the itemised Class 1
section exactly like any other violation would.

`revalidate` accepts every output flag `solve` does (`--out`,
`--export-schedule`, `--report-dir`, `--pdf-dir`/`--pdf-paper`/
`--pdf-orientation`), so a revalidated schedule can itself be
re-exported and edited again for a second round (FR-89). Not built:
a diff summary against the schedule being edited (OQ-17 - deferred).

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
  ],
  "constraints": [
    {"family_id": "F1", "camper_name": "Kid", "constraint": "no_activity_before(time=\"11:00\")",
     "severity": "hard", "note": "sleeps in"}
  ]
}
```

`constraints` is optional (defaults to `[]`) — see
[Custom constraints](#custom-constraints) below.

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

python -m family_camp2 solve --solver cp_sat --data data.json
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

[Custom constraints](#custom-constraints) live on a fourth, optional tab.
Unlike the other three, it's not fetched unless you ask for it —
`--constraints-worksheet` with no value uses the default tab name
("Constraints for schedule"); give it a value to use a different tab name.

See `family_camp2.io.google_sheets` for the fetch/parse logic (it shares
its row-parsing with `io/legacy_cache_loader.py`, since both start from
the same raw worksheet-row shape) and `fetch_cli.py` for the full CLI.

### Engine config (`--config`)

Optional JSON file overriding `EngineConfig` (see `family_camp2.config`):
`tier0_weights` (severity weights for the demand-driven Class 2 rules —
`custom_constraint`, `missing_priority`, `family_safety`, `family_split`,
`under_minimum`, `compulsory`, most severe first), `objective_order` (must
be a permutation of `["tier0", "tier1", "tier2"]` — the OQ-4 ranking
mechanism), and `compulsory_activities` (activity names everyone must
attend, empty by default per OQ-5).

`constraints` (the per-camper/family rules below) is deliberately **not**
one of these fields — it comes from `--data`/`--legacy-cache` alongside
the campers it targets, not this separate camp-independent config file.

### Family splits (FR-17/FR-24)

Splitting a family across several sessions of the same activity is
unpopular, so both solvers treat it as a last resort, not a routine
outcome: a split only happens when there's no way to accommodate the
family's requested activities otherwise (e.g. session capacity forces
it), ranked in the objective above satisfying an extra optional request
but below the hard/demand-driven constraints in REQUIREMENTS.md §4.1. A
split is reported (`Class2Report.family_splits`) but is *not* itself a
violation — it doesn't affect `Feasible: True/False`.

When a split does happen, every one of its sessions must have both an
adult (18+) *and* a child from the family present — no session may be
adults-only or children-only — with one exception: a children-only
session is fine if some adult in the family has no assignment overlapping
that session's time, and so is free to informally accompany them without
formally taking part. There's no equivalent exception for an adults-only
session. This *is* a real violation when unmet
(`Class2Report.unsupervised_splits`, each tagged `reason="lone_adult"` or
`"unaccompanied_child"`) — see `validation/class2.py`'s module docstring
for the exact rule, including why a (family, activity) pair is exempted
entirely when no child in the family ever requested that activity (the
rule would otherwise be permanently unfixable in that case).

## Custom constraints

A fourth, optional input collection (REQUIREMENTS.md §3.5/§4.10) for
per-camper or per-family rules that go beyond a camper's own
priority/optional lists — e.g. "022/Glen must not have any activities on
day 2" or "Emma Glen (022/Glen) must not have any activity before 11:00".
Each record has four fields:

| Field | Meaning |
|---|---|
| Target | A family ID (applies to every member) or a specific camper within one. |
| Constraint | A named, parameterised rule — see below. |
| Severity | `hard` (never violated, in either solver) or `soft` (penalised if unmet, like the other Class 2 rules). |
| Note | Free text for the organiser's own reference; never read by the engine. |

In `--data` JSON this is the top-level `"constraints"` array, one object
per record: `family_id`, `camper_name` (`null`/omitted applies to the
whole family), `constraint`, `severity`, `note`. On a Google Sheet
([see above](#fetching-data-from-google-sheets-fetch_clipy)) it's the
same five fields as spreadsheet columns: `Group Ref`, `Camper Name`,
`Constraint`, `Severity`, `Note`.

### Expression syntax

The `Constraint` field is a function-call-like expression, e.g.
`no_activities_on_day(2)` or `no_activity_before(time="11:00")`. It's
parsed with Python's `ast` module and restricted to a single call with
literal (number/string/list) arguments — **never** `eval()` — so an
unparseable expression or unknown rule name is reported clearly (naming
the row) rather than executed or silently ignored (FR-92/93).

Built-in rules (`family_camp2.constraints.rules`):

| Expression | Forbids |
|---|---|
| `no_activities_on_day(day)` | Any session on the given camp day (1-indexed, derived from the distinct calendar dates actually present in the session data — FR-3, not a fixed date). |
| `no_activity_before(time="HH:MM")` | Any session starting before that time of day. |
| `no_activity_after(time="HH:MM")` | Any session starting after that time of day. |
| `no_activities_between(start="HH:MM", end="HH:MM")` | Any session starting within that time-of-day range (inclusive). |
| `not_on_activity(activity="Name")` | Any session of the named activity, regardless of the camper's own priority/optional lists. |

Each corresponds one-to-one with a `forbids(camper, session, all_sessions)
-> bool` predicate class — the same shape used internally to make Class 1
rules (FR-10-16) structurally guaranteed in both solvers. This is what
lets `hard` constraints be enforced "for free": a camper is simply never
considered eligible for a session their rule forbids, in either solver,
with no rule-specific solver code. If a hard constraint makes one of a
camper's own priorities unreachable, that surfaces as an ordinary
`missing_priority` violation, the same as any other unreachable priority
(FR-94) — not a crash or a silent drop. `soft` constraints instead
contribute to the weighted Tier 0 objective (`Tier0Weights.custom_constraint`,
[see Engine config above](#engine-config---config)) and are reported when
unmet, without making the schedule infeasible.

Only rules expressible as that per-(camper, session) predicate — "Tier
A" — are built in. Rules that depend on a camper's *other* assignments
(e.g. "no more than 2 activities per day", "must always be with camper
X") are "Tier B": the same registry/parser architecture accommodates them,
but each needs bespoke validator (and, if hard, solver) logic, and none
are implemented yet — an acknowledged extension point, not part of this
phase (REQUIREMENTS.md OQ-22).

## Architecture

```
domain.py            Activity / Session / Camper / Timetable
validation/          solver-independent rules (Class 1/2, Tier 1/2, idle-time incl. family/adult views, structural overdemand, the FR-40/41 report)
config.py            EngineConfig (NFR-4)
progress.py          ProgressEvent/ProgressReporter/PeriodicHeartbeat (FR-60/61, NFR-9)
reporting.py         per-family/per-activity/idle/unmet-optional/overdemand text reports, from a Timetable (FR-72/73/74/76/77)
pdf_reports.py       activities.pdf / campers.pdf / available_adults.pdf / available_families.pdf (FR-80/81/82/83/84/85)
status_report.py      the unconditionally-generated schedule status report (FR-97-109, §4.11)
io/                  JSON loader/writer, legacy-cache loader, Google Sheets fetch (OAuth), schedule CSV/JSON export (FR-70/71)
solvers/
  base.py            the Solver protocol every design implements
  registry.py         name -> Solver lookup, used by the CLI
  cp_sat.py           Design A: OR-Tools CP-SAT, three-phase lexicographic solve, wall-clock progress heartbeat
  annealing/          Design B: simulated annealing with domain-aware moves, per-chain progress
cli.py                argparse entry point, subcommands: solve (--solver cp_sat|annealing), revalidate (FR-86-89)
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
