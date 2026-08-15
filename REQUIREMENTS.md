# Family Camp Scheduling Engine — Requirements

## 0. Purpose of this document

This document specifies requirements for the **core scheduling engine**
for Family Camp: the component that takes camper registration/preference
data and produces a timetable assigning campers to activity sessions.

It is intentionally **solver-agnostic** — it describes *what* a correct and
good schedule is, and what the system must do, without assuming a
genetic algorithm, constraint solver, MILP, heuristic, or any other
technique. Two solver implementations are built to it — see
[`DESIGN_OPTIONS.md`](DESIGN_OPTIONS.md).

Requirements are numbered (`FR-n` functional, `NFR-n` non-functional) so
code comments and other documents can reference them directly.

## 1. Scope

### 1.1 In scope

- Consuming camper, family, activity, and session data (see §3) and
  producing a timetable: an assignment of campers to specific activity
  sessions.
- Determining whether the input data (or any candidate timetable, however
  produced) satisfies the rules that define a correct schedule (§4.1), and
  scoring how *good* it is against the softer goals (§4.2).
- Reporting, clearly and specifically, where a schedule falls short — both
  during generation and when evaluating an arbitrary candidate timetable.
- Producing a structured, unambiguous output that other tools (printing,
  per-family exports, manual review) can consume.
- Fetching camper/activity/session data from Google Sheets, and a unified
  command-line interface tying fetching, generation, and re-validation
  together (§4.11–§4.13).

### 1.2 Explicitly out of scope

- **Printing/rendering beyond the specific reports in §4.7/§4.8/§4.11.**
  No general printing/layout framework, no interactive editing, no
  per-family "packs" beyond the itinerary PDF.
- **Manual editing workflow.** §4.9 covers taking a hand-edited schedule
  back through validation and reporting; there is no interactive editor,
  no edit-time constraint enforcement, and no diff summary against a
  prior run.
- Camp registration, payment, or booking-form automation.

These exclusions are about this engine's scope, not a judgement that they
are unimportant — they are separate concerns with their own requirements,
and coupling them to the scheduling engine's design would narrow the
solver options unnecessarily.

## 2. Glossary

| Term | Meaning |
|---|---|
| **Camper** | An individual attending camp (child or adult) who may be assigned to sessions. |
| **Family / Group** | A set of campers (typically a household) who registered together. Membership is given in the input data, not inferred. |
| **Activity** | A named thing campers can do (e.g. "Archery"), with a duration and an occupancy range. An activity may run multiple times across the weekend. |
| **Session** | A single scheduled occurrence of an activity: one activity, one start time, one (derived) end time. Distinct sessions of the same activity are independent — filling one does not fill another. |
| **Priority activity** | An activity a camper has stated they must/most want to do. |
| **Optional activity** | An activity a camper has stated they'd like to do if possible, but is not essential. |
| **Compulsory activity** | An activity that, if designated as such, every camper must attend one session of (e.g. a camp-wide meal). Distinct from a camper's own priority list. |
| **Assignment** | A single (camper, session) pairing. |
| **Timetable / Schedule** | The complete set of assignments for all campers across the weekend. |
| **Clash / overlap** | Two sessions whose time ranges intersect. |
| **Feasible schedule** | A timetable satisfying every hard constraint in §4.1. |
| **Class 1 / Class 2** | Class 1 constraints (§4.1) are structurally always satisfiable by simply not making an assignment, so a solver never has a legitimate reason to violate one. Class 2 constraints (§4.3) are demand-driven — real input data can make them jointly infeasible, so violations are tracked and reported rather than assumed impossible. |

## 3. Input data contract

The engine consumes three required collections and one optional one,
fetched from Google Sheets (§4.13) or supplied as hand-written JSON.

### 3.1 Activity

| Field | Meaning |
|---|---|
| Identifier/name | Unique name of the activity. |
| Duration | Length of one session of this activity. |
| Minimum occupancy | Fewest campers required for a session of this activity to be considered valid, if it runs at all. |
| Maximum occupancy (capacity) | Most campers a single session of this activity can hold. |
| Minimum age (optional) | If set, the youngest age eligible for this activity (FR-18). |

### 3.2 Session

| Field | Meaning |
|---|---|
| Activity reference | Which activity this session is an occurrence of. |
| Label | A human-readable identifier for this occurrence (e.g. distinguishing two parallel Saturday-morning slots). |
| Start time | When this session begins. |
| End time | Derived from start time + the activity's duration. |

### 3.3 Camper

| Field | Meaning |
|---|---|
| Identifier/name | Camper's name (or other unique identifier). |
| Family/group identifier | Links this camper to others in the same family/group. |
| Age / age group | Camper's age and/or an age-band classification. |
| Priority activities | List of activities this camper must be scheduled into. |
| Optional activities | List of activities this camper would like, but does not require. |

### 3.4 Data-integrity requirements on input

- **FR-1**: The engine MUST validate, before scheduling, that every activity
  referenced by a camper's priority or optional list exists in the Activity
  collection, and that every session references a valid activity. Invalid
  references MUST be reported (which camper, which activity/session) rather
  than causing a silent skip or an unhandled crash.
- **FR-2**: The engine MUST treat family/group membership as given —
  it does not need to infer or validate family relationships beyond
  confirming the identifier is present and consistent.
- **FR-3**: The engine MUST NOT assume a fixed number of days, sessions, or
  activities in the input (no requirement that a camp is exactly two days
  long, has exactly N activities, etc.), except where a specific
  visualisation explicitly says otherwise (FR-101).

### 3.5 Custom constraint record (optional, §4.10)

A fourth, optional input collection alongside Activity/Session/Camper —
each record is one organiser-authored, parameterised constraint applying
to a specific camper or family, distinct from a camper's own
priority/optional lists.

| Field | Meaning |
|---|---|
| Target | A family identifier (applies to every member), or a specific camper within a family. |
| Constraint | A named, parameterised rule (e.g. "no activities on day 2") — see §4.10 for the rule vocabulary and expression syntax. |
| Severity | Whether this is a hard requirement or a soft/best-effort preference. |
| Note | Free text for the organiser's own reference; never interpreted by the engine. |

## 4. Functional requirements

### 4.1 Hard constraints — a valid schedule MUST satisfy all of these

- **FR-10 (No double-booking)**: No camper is assigned to two sessions
  whose time ranges overlap.
- **FR-11 (No family time-conflict)**: No two members of the same
  family/group are assigned to two *different* sessions whose time ranges
  overlap. (Family members may be assigned to the exact same session
  together, or to different sessions that do not overlap in time — the
  rule only forbids the family being pulled in two directions at once.)
- **FR-12 (Occupancy limits)**: Any session that is used (has one or more
  campers assigned) has a camper count between the activity's minimum and
  maximum occupancy, inclusive. A session with zero campers assigned is not
  subject to the minimum (it is simply not running).
- **FR-13 (Priorities honoured)**: Every camper is assigned to a session of
  each activity on their priority list.
- **FR-14 (No unrequested activities)**: No camper is assigned to an
  activity that appears on neither their priority nor their optional list.
- **FR-15 (No duplicate activity)**: No camper is assigned to more than one
  session of the same activity. There is no concept of a repeatable
  activity a camper can be validly scheduled into more than once.
- **FR-16 (Compulsory activities)**: If any activities are designated
  compulsory, every camper is assigned to exactly one session of each.
  The mechanism is supported but not currently used by any real camp data.
- **FR-17 (Supervised family splits)**: When a family is split across more
  than one session of the *same* activity (whether a priority or an
  optional request for whoever's attending), every one of those sessions
  must be jointly attended by at least one adult (18+) AND at least one
  non-adult member of the family — no session may contain only adults,
  and no session may contain only children, WITH ONE exception: a
  children-only session is still acceptable if at least one adult member
  of the family has no assignment overlapping that session's time (they
  are then free to informally accompany/supervise even though not
  formally taking part in the activity themselves). There is no
  equivalent exception for an adults-only session.
- **FR-18 (Minimum age)**: If an activity has a minimum age set, no camper
  younger than that age is assigned to it.

### 4.2 Soft objectives — a good schedule optimises for these, in order

The objectives below are organised into a strict, lexicographic
three-tier hierarchy (a schedule is never made worse on a higher tier to
improve a lower one): **Tier 0** is severity-weighted satisfaction of the
demand-driven constraints in §4.3 (a schedule with fewer/less-severe
Class 2 violations always beats one with more); **Tier 1** is FR-20/21;
**Tier 2** is FR-22. This ordering (`tier0`, `tier1`, `tier2`) is the
default and is adjustable without code changes (NFR-4).

- **FR-20 (Optional-request satisfaction)**: Maximise the number/fraction
  of each camper's optional-activity requests that are met.
- **FR-21 (Fairness across campers)**: Avoid a solution that systematically
  favours or disadvantages campers based on how many optional activities
  they requested (e.g. a camper who asked for one thing should not be
  treated as "fully satisfied" any more easily than one who asked for five,
  purely as an artefact of the scoring method).
- **FR-22 (Even use of parallel sessions)**: Where an activity runs as
  several parallel sessions, prefer spreading campers evenly across them
  rather than filling one and leaving others near-empty, to the extent
  this doesn't conflict with other objectives.
- **FR-24 (Minimise family splits)**: Splitting a family across several
  sessions of the same activity (FR-17) is unpopular with families and
  is a last resort. The engine first attempts a schedule that keeps every
  family together in a single session per activity, and only splits a
  family when there is no way to accommodate its members' requested
  activities otherwise (e.g. session capacity forces it). This ranks
  above FR-20/21/22 — the engine prefers keeping a family together over
  satisfying an extra optional request — but below the hard/demand-driven
  constraints in §4.1/§4.3 (including FR-17's supervision requirement,
  which is never traded away to reduce a split).

Camper/family idle time (time with nothing scheduled) is not a search
objective — it is reported for staffing/supervision awareness (FR-74)
rather than minimised, except for the narrow adult-availability check
FR-17's supervision exception depends on.

### 4.3 Feasibility and best-effort behaviour

- **FR-30**: Real inputs may be infeasible (e.g. total demand for an
  activity's priority slots exceeds its total capacity across all
  sessions). The engine MUST detect this and MUST NOT report a schedule as
  fully valid if it isn't.
- **FR-31**: When no fully feasible schedule exists, the engine MUST still
  produce a best-effort schedule, and MUST report exactly which hard
  constraints remain violated and for whom (e.g. "camper X did not get
  priority activity Y — no session had capacity"), so an organiser can act
  on it. The trade-off actually made must be visible in the report, not
  hidden inside an aggregate score.

### 4.4 Validation / explainability

- **FR-40**: The engine MUST be able to evaluate an arbitrary candidate
  timetable — not just one it generated itself — against every hard
  constraint in §4.1 and every objective in §4.2, and produce a structured
  report (not just a single pass/fail flag). This is what lets any tool
  (manual review, regression tests, a different generator entirely)
  check a schedule's validity without re-implementing the rules.
- **FR-41**: Violation reports MUST identify the specific camper(s),
  family/group, activity, and session(s) involved — enough detail to act
  on without cross-referencing the raw input data by hand.

### 4.5 Output contract

- **FR-50**: The engine MUST produce a structured result describing, for
  every session, which campers are assigned to it (equivalently, for every
  camper, which sessions they're assigned to). This is the sole interface
  downstream consumers (printing, exports, manual-editing) rely on — they
  must not need to know how the assignment was computed.
- **FR-51**: The output MUST unambiguously identify *which* session
  (specific activity occurrence/time) each assignment refers to — no
  ambiguity between two sessions of the same activity.

### 4.6 Progress reporting during generation

- **FR-60**: The engine MUST periodically report progress during a
  generation run long enough for it to matter (order of seconds to
  hours), so an operator can tell the run is alive and making progress
  without inspecting external process state. The default cadence is 60
  wall-clock seconds; progress is written to stdout by default, or a
  file if configured.
- **FR-61**: Each progress report MUST include, at minimum, elapsed time
  and the best schedule quality found so far, expressed using the same
  measures used everywhere else (the hard-constraint/best-effort picture
  of FR-30/FR-31, and the soft objectives of §4.2) — not a separate,
  solver-specific metric an operator has to learn to interpret.
- **FR-62**: For a solver whose search has distinguishable stages (e.g.
  sequential objective phases, or independent restarts/chains), progress
  reports MUST identify which stage is currently active and how it
  relates to the overall run (e.g. "phase 2 of 3", "chain 4 of 8").
- **FR-63**: The engine MUST be able to produce the best schedule found so
  far without waiting for the run to finish, whether by stopping the run
  early or by inspecting it while still running — a long run must not be
  all-or-nothing.
- **FR-64**: If a generation run ends before completing on its own
  (operator-cancelled, crashed, or ran out of its time budget) after
  having found at least one valid or best-effort schedule, that schedule
  MUST NOT be lost — it must already be available or be salvageable,
  rather than forcing the whole run to be repeated from scratch.

### 4.7 Schedule export and human-readable reporting

- **FR-70**: The engine MUST be able to export a timetable (generated, or
  hand-supplied and already validated) to a durable, machine-readable
  format that captures every assignment (camper, activity, session), as
  both CSV and JSON. This is the actual deliverable schedule, distinct
  from the scoring/violation report of FR-40/41.
- **FR-71**: An exported schedule (FR-70) MUST be re-importable by the
  engine, so a previously generated (or manually adjusted, per §4.9)
  schedule can be re-validated (FR-40) without needing to regenerate it
  from the original activities/sessions/campers input.
- **FR-72**: The engine MUST be able to produce a human-readable,
  per-family itinerary report from a given timetable: for each family,
  the sessions its members are assigned to, in time order.
- **FR-73**: The engine MUST be able to produce a human-readable,
  per-activity/session roster report from a given timetable: for each
  session, who is assigned to it, and how that compares to the activity's
  occupancy limits.
- **FR-74**: The engine MUST be able to produce an idle-time report
  suitable for staffing/supervision planning, covering both whole
  family/groups with nothing scheduled at a given time and individually
  named idle adults, as two distinct views.
- **FR-75**: Where a solver's search naturally produces more than one
  good candidate schedule (e.g. independent restarts), only the single
  best one is exported/reported — this is sufficient for the current
  scale and use.
- **FR-76**: The engine MUST be able to produce a human-readable report of
  unmet optional (non-priority) activity requests from a given timetable:
  for each optional activity that was requested but not obtained, which
  campers missed out.
- **FR-77**: The engine MUST be able to produce a human-readable report,
  derived from the input activities/sessions/campers alone (not from any
  particular timetable), of families whose members have collectively
  requested more distinct activities than the maximum number of
  non-overlapping session slots the *family* could ever occupy across the
  whole camp — i.e. a structural, time-based ceiling that no solver could
  work around regardless of available capacity. This is computed at
  family, not individual, granularity: since no two members of a family
  may be in overlapping sessions (FR-11), the family as a whole — not
  each member separately — is the unit that can only occupy one slot at
  a time. This is a necessary-infeasibility check only (requesting fewer
  activities than this ceiling does not guarantee everything fits —
  sessions of the specific requested activities may still clash with
  each other even when the camp overall has plenty of free time
  elsewhere), and exists to help an organiser distinguish "not enough
  capacity" from "not enough time" as the reason an optional request
  went unmet.

### 4.8 PDF reports

- **FR-80**: The engine MUST be able to produce a PDF activity roster:
  for each activity, its sessions with attendees and occupancy against
  capacity — the same information as the text report (FR-73), laid out
  for printing rather than terminal/file reading.
- **FR-81**: The engine MUST be able to produce a PDF per-family
  itinerary, distinct from FR-80's document (a different audience: staff
  running a session vs. a family finding their own day) — the same
  information as the text report (FR-72), laid out for printing.
- **FR-82**: Both PDF reports MUST support the organiser choosing paper
  size (A4 or A3) and orientation (portrait or landscape) independently.
- **FR-83**: Layout adapts to the chosen paper size/orientation to use
  space efficiently (e.g. more columns on a wider page) rather than a
  fixed layout scaled to fit, and avoids forcing a new page/section for
  every activity or family regardless of how much room remains.
- **FR-84**: The engine MUST be able to produce a PDF listing, for each
  active time period, which *adult* campers have nothing scheduled — a
  third document, distinct from FR-80/81 (a different question: not
  "who's doing what", but "who's free right now"), for an organiser
  trying to find a spare adult volunteer. Only adults appear (children
  are not volunteer candidates) — reuses the idle-time computation
  (FR-74) filtered to adults.
- **FR-85**: The engine MUST be able to produce a PDF, in the same shape
  as FR-84, narrowed to adults whose *entire family* has nothing
  scheduled at that time (not just the adult themselves) — a stronger
  availability signal, since they won't need to break away to rejoin a
  family member who's mid-activity.

### 4.9 Manual editing and re-validation workflow

Taking a hand-edited schedule back through validation and reporting —
not an interactive editor, not edit-time constraint enforcement, and no
diff summary against the schedule being edited.

- **FR-86**: The engine MUST support taking a previously exported
  schedule (FR-70/71's format) that has been edited by hand, and
  producing the same validation report (FR-40/41) and human-readable/PDF
  reports (FR-72-74, FR-80-85) it would for a freshly solved schedule,
  without invoking a solver. This is the `revalidate` subcommand (§4.13).
- **FR-87**: Re-importing an edited schedule MUST NOT silently accept a
  row that can't be resolved back to a known camper or session from the
  original input data (e.g. a typo'd name) — every unresolvable row is
  collected and reported together, not just the first.
- **FR-88**: The engine MUST report Class 1 (structural) violations in a
  re-validated schedule exactly as it would for a solver's output.
  Unlike a solver-built timetable (where a Class 1 violation is
  structurally impossible by construction), a hand edit can genuinely
  introduce one (e.g. double-booking, capacity overflow), and the engine
  does not treat re-validated input as inherently trustworthy.
- **FR-89**: The re-validation entry point supports the same reports
  available for a freshly generated schedule, so a re-validated schedule
  can itself be re-exported and edited again, supporting multiple rounds
  of hand-tweaking.

### 4.10 Per-camper/family custom constraints

Organiser-authored, parameterised constraints on individual campers or
families that the built-in rules (§4.1/§4.2) have no other way to
capture — e.g. "family 022/Glen must not have any activities on day 2"
or "Emma Glen must not have any activity before 11:00" — expressed as
rows on an input worksheet (§3.5), editable by an organiser without a
code change.

The central design idea: nearly every useful constraint of this kind
reduces to a per-(camper, session) predicate — "is this camper allowed
to be in this session at all?" — the same shape that makes Class 1
structurally guaranteed. A constraint expressible this way (**Tier A**)
gets hard *and* soft enforcement in both solvers for free, with zero
solver-specific code needed per new rule. A constraint that isn't
expressible this way (**Tier B** — e.g. "no more than 2 activities per
day," which depends on a camper's *other* assignments, not a fixed
session set) needs bespoke validator logic and, if hard, bespoke solver
modelling, case by case. Only Tier A is currently implemented; Tier B is
an acknowledged future extension of the same architecture.

- **FR-90**: The engine MUST support a general, extensible architecture
  for named, parameterised per-camper/family constraint rules — adding a
  new rule type MUST NOT require changes to the solvers themselves for
  the common (Tier A) case, only a new rule class.
- **FR-91**: Each constraint record (§3.5) MUST resolve its target to one
  or more campers: a family identifier resolves to every member; a
  family+camper pair resolves to that one camper. An unresolvable target
  (unknown family/camper) MUST be reported, not silently skipped.
- **FR-92**: The constraint expression (§3.5's "Constraint" field) is a
  function-call-like expression (e.g. `no_activities_on_day(2)`), parsed
  via Python's `ast` module in restricted/safe mode — it MUST NOT be
  evaluated as arbitrary code (this is organiser-edited spreadsheet
  data, not trusted source code). An unparseable expression or unknown
  rule name MUST be reported clearly, naming the row and the problem.
- **FR-93**: The engine MUST collect and report every invalid constraint
  record (bad target, bad expression, unknown rule) together, not stop
  at the first.
- **FR-94**: A **hard** constraint MUST be enforced exactly like a Class
  1 rule: the engine must never produce a timetable that violates it, in
  either solver. If a hard constraint makes one of that camper's own
  priorities structurally unreachable, this MUST surface as a normal
  `missing_priority` violation (FR-13/FR-31) — no special-case handling,
  the same graceful behaviour already used for e.g. an age-restricted
  activity a camper can never reach.
- **FR-95**: A **soft** constraint MUST be treated as an optimisation
  target: penalised in the same weighted-severity mechanism as the other
  demand-driven constraints (§4.3), reported when unmet, but not treated
  as making the schedule infeasible on its own. Every soft custom
  constraint shares one severity weight, ranked above every other
  severity band (`custom-constraint` > `missing_priority` >
  `family_safety` > `family_split` > `under_minimum` > `compulsory`).
- **FR-96**: The engine MUST implement at least the following Tier A
  rules: activities excluded by camp day number (day 1, 2, ... — derived
  from the distinct calendar dates present in the session data, not a
  fixed date, per FR-3); activities excluded before/after a time of day;
  activities excluded within a given time-of-day range; a specific
  activity excluded outright regardless of the camper's own
  priority/optional lists.
- **FR-120 (Automatic constraints-tab detection)**: When fetching from
  Google Sheets (§4.13), the engine MUST fetch the custom-constraints
  worksheet whenever a tab with the expected name (overridable) actually
  exists on the spreadsheet, with no separate flag needed to request it.
  A spreadsheet with no such tab is not an error — it silently yields no
  constraint records.

### 4.11 Schedule status report

A single-document overview aimed at the organiser: front matter,
activity/session loading, camper/family fulfilment, and solver
diagnostics, so an organiser can sanity-check a run without
cross-referencing several separate outputs — distinct from the
audience-specific reports in §4.7/§4.8 and from the plain violation
report (FR-40/41) alone. It is generated unconditionally on every run
(§4.12), not behind an opt-in export flag.

- **FR-97**: The status report MUST be generated as an A4 PDF document,
  portrait orientation, fixed (not organiser-configurable per-run the
  way FR-82's audience-specific PDFs are, since this isn't a
  per-audience print-out — it's always the same kind of read).
- **FR-98**: The status report MUST be generated at the end of every
  `solve` run and every `revalidate` run, unconditionally.
- **FR-99**: The status report MUST contain, at minimum, five sections:
  front matter (FR-100), camp activity information (FR-101), activity
  session loading (FR-102), camper/family activity loading (FR-103/104),
  and solver information (FR-106).
- **FR-100 (Front matter)**: The report MUST open with: the date/time
  the report was generated; the camp's date range and duration, derived
  from the actual session data (earliest session start to latest session
  end, per FR-3); and headline counts (number of activities, sessions,
  campers, and families).
- **FR-101 (Camp activity information)**: The report MUST include a
  table of every activity (name, number of scheduled sessions, min/max
  occupancy, whether it's a configured compulsory activity), and a
  graphical activity timetable showing, per activity, when its sessions
  run. This graphical timetable assumes the camp spans exactly 2
  distinct calendar days — the one exception to FR-3's general
  no-fixed-length rule, scoped to this single visualisation. If the
  session data's actual distinct dates don't number exactly 2, the
  graphical timetable degrades to a clearly-labelled tabular fallback
  (session start/end per activity, grouped by actual date) rather than
  crash or mislabel days that don't exist.
- **FR-102 (Activity session loading)**: The report MUST show, for
  every session, occupancy against its activity's capacity (a stacked
  bar of filled vs. spare seats), and summary statistics including the
  mean and spread of spare capacity across all sessions. "Ideal" session
  size for this deviation statistic is a session's `max_occupancy` (a
  fully-booked session is ideal). Sessions already flagged
  `under_minimum` (§4.3) are visually distinguished, not just implied by
  a low bar.
- **FR-103 (Camper activity loading)**: The report MUST show, for every
  camper, a stacked bar comparing requested (priority + optional)
  activities against allocated ones — distinguishing at least priorities
  met, optional activities met, and unmet requests of each kind, so a
  camper with everything satisfied looks visibly different from one who
  didn't. Every camper MUST appear (not a sample or an "anomalies only"
  subset), paginated across multiple pages, sorted by family so a
  family's members stay adjacent and easy to cross-check against §4.11's
  family-level view (FR-104).
- **FR-104 (Family activity loading)**: As FR-103, aggregated to family
  granularity — one stacked bar per family, summing its members'
  requested vs. allocated activities. Every family MUST appear, paginated
  as needed, in a consistent family order with FR-103.
- **FR-105 (Anomaly visibility)**: Campers/families with at least one
  *unmet priority* (the most severe shortfall a camper can have, per
  FR-13) MUST be visually distinguished within FR-103/104's charts (e.g.
  colour), so they don't require reading every bar to find. The report
  MUST also include the structural-overdemand finding (FR-77) as a
  callout list.
- **FR-106 (Solver information)**: The report MUST state which solver
  produced the schedule and how long it took (wall-clock), the full
  Tier 0/1/2 score breakdown, every Class 2 violation category's count
  (including custom-constraint violations, §4.10), and a summary of
  custom constraints in effect (how many hard, how many soft, and how
  many soft ones had at least one violation). When the report is
  produced via `revalidate` (no solver was run), this section states so
  explicitly (e.g. "N/A — re-validated from an edited schedule") — never
  fabricating solver information that doesn't exist.
- **FR-108 (`reportlab` dependency)**: Since generation is unconditional
  (FR-98), `reportlab` is a core install dependency, not an optional
  extra.
- **FR-109 (Charting approach)**: Charts (FR-102/103/104) are built with
  `reportlab.graphics.charts` (native bar/stacked-bar support), not a
  separate charting library.

### 4.12 Report output location

Every report `solve`/`revalidate` can produce — the exported schedule
(FR-70/71), the operational text reports (FR-72-74/76/77), the
audience-specific PDFs (FR-80/81/84/85), the validation report JSON, and
the status report (§4.11) — is generated on every run, with no
per-report flag to exclude any of them.

- **FR-110 (Unconditional, consolidated report generation)**: Every
  report is generated unconditionally on every `solve`/`revalidate` run.
  Both audience-specific PDF paper size/orientation combinations (A4
  portrait and A3 landscape) are generated together, rather than the
  organiser choosing one per run.
- **FR-111 (`--out-dir` and folder naming)**: `solve`/`revalidate` take a
  single `--out-dir` option (a folder, default `fetched_data`). Every
  report for one run is written into a subfolder of it named
  `<camp_name>_<run timestamp>` — the run timestamp captured when the
  command starts, so two runs never collide into the same folder
  (falling back to a numeric suffix on the rare case two runs start in
  the same second). No file is created outside that subfolder.

### 4.13 Command-line interface

A single unified CLI (`family_camp2`) with three subcommands: `fetch`
downloads camp data from a Google Sheet; `solve` generates a schedule
with a solver; `revalidate` re-validates a previously exported,
optionally hand-edited schedule (§4.9) without invoking a solver.

- **FR-112 (Fetch tool alignment)**: `fetch` takes the same `--out-dir`
  option (default `fetched_data`) as `solve`/`revalidate`, and writes
  its cached download JSON directly into it (not a per-run subfolder,
  per FR-111's exception) — a durable cache reused across many later
  `solve` runs, not one run's own report. The camp name used for FR-111's
  folder naming is derived from the Google Sheet's own title and stored
  in the cached JSON, so no separate `--camp-name` flag is needed
  anywhere, and `solve`/`revalidate` recover it automatically.
- **FR-113 (Single CLI)**: `fetch` is a subcommand of the same CLI as
  `solve`/`revalidate`, not a separate script/console entry point.
- **FR-114 (Automatic input discovery)**: `solve`/`revalidate` do not
  require `--data`/`--legacy-cache` — when neither is given, they use
  the file `fetch` most recently wrote into `--out-dir` automatically.
  Explicit `--data`/`--legacy-cache` are still accepted, overriding the
  automatic choice.
- **FR-115 (Descriptive missing-data error)**: If `solve`/`revalidate`
  is run with no explicit `--data`/`--legacy-cache` and nothing has been
  fetched into `--out-dir` yet, the engine stops with a clear,
  descriptive error explaining that `fetch` needs to be run first
  (naming the command), not an unhandled `FileNotFoundError`.
- **FR-116 (Camp name fallback)**: When the input file carries no
  `camp_name` (a hand-written `--data` file, or `--legacy-cache`, which
  has no such concept), FR-111's folder naming falls back to the input
  file's own name.
- **FR-117 (Positional arguments for defaultless values)**: `fetch`'s
  Google Sheets URL and `revalidate`'s schedule path — the two values in
  this CLI with no sensible default — are positional arguments
  (`family_camp2 fetch <URL>`, `family_camp2 revalidate <SCHEDULE_PATH>`),
  not `--flag VALUE` options.
- **FR-118 (`--solver` default)**: `solve`'s `--solver` defaults to
  `cp_sat`.
- **FR-119 (Every remaining option has a real default)**: Every other
  `solve`/`revalidate`/`fetch` option has an explicit, documented
  default. `--time-limit` defaults to no limit (a solver runs to
  convergence); `--seed` defaults to none (non-deterministic);
  `--num-chains`/`--iterations-per-chain` default to 8/2000.

## 5. Non-functional requirements

- **NFR-1 (Scale)**: The engine must handle input sizes consistent with an
  actual Family Camp weekend: up to 500 campers, 30 activities, and 50
  sessions.
- **NFR-2 (Turnaround time)**: The engine must produce a usable schedule
  within a time budget compatible with iterative use during camp planning
  — up to 24 hours wall-clock is an acceptable upper bound for a full run.
- **NFR-3 (Reproducibility)**: Given the same input and configuration, the
  engine should produce comparable-quality results on repeated runs. Where
  the chosen approach involves randomness, a seed reproduces a specific
  run exactly, for debugging and regression testing.
- **NFR-4 (Configurable trade-offs)**: The relative importance of the soft
  objectives in §4.2 must be adjustable without code changes, since
  organisers may want to retune priorities from year to year (e.g. "even
  spread" mattering more some years than others).
- **NFR-5 (No hardcoded shape assumptions)**: The engine must not assume a
  fixed camp length, fixed activity count, or fixed session count (per
  FR-3) — these vary year to year.
- **NFR-6 (Isolation from I/O and presentation)**: The scheduling and
  validation logic must be usable and testable independently of the
  Google Sheets data-fetch step and of any printing/rendering code, so it
  can be exercised with small synthetic fixtures in automated tests.
- **NFR-7 (Testability)**: Core rules (§4.1–§4.2) must be expressible as
  unit tests against small hand-built scenarios (a handful of campers,
  activities, and sessions) so regressions are caught without needing a
  full-scale run against real data.
- **NFR-8 (Transparency over black-box scoring)**: Wherever the engine
  reduces schedule quality to a score for internal use (e.g. to drive
  search), it must still be able to expand that score back into the
  human-readable violation/objective report required by FR-40 — a single
  opaque number is not sufficient as the *only* output.
- **NFR-9 (Progress reporting stays cheap)**: Progress reporting (§4.6)
  must not materially slow down the underlying search — e.g. no expensive
  full re-validation triggered on every single search step. Reporting
  granularity/cadence is a tunable trade-off, not something that forces a
  choice between "informative" and "fast".
- **NFR-10 (Reports reuse the same rules)**: The human-readable reports of
  §4.7 must be derived from the same validator/scoring logic as
  everything else (FR-40, NFR-8) — not a separate, potentially
  inconsistent implementation of "who's idle" or "who's in which
  session".

## 6. Success criteria

The engine succeeds if, for a real Family Camp dataset conforming to §3:

1. It produces a schedule satisfying every hard constraint in §4.1, or — if
   that's not possible — a best-effort schedule with a precise account of
   what couldn't be satisfied (FR-30/FR-31).
2. The schedule performs well against the soft objectives in §4.2, in a way
   whose trade-offs are visible and tunable, not hidden.
3. Any generated or hand-supplied timetable can be independently validated
   and explained via the same rules (FR-40/FR-41).
4. The scheduling engine has no dependency on Google Sheets access or
   printing code to run or to be tested.
5. A long-running generation reports its own progress and is never
   all-or-nothing (FR-60–FR-64); its result can be exported, re-imported,
   and turned into the operational reports organisers and activity leaders
   actually use day-to-day, without repeating the generation run
   (FR-70–FR-75).
