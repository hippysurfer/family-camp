# Family Camp Scheduling Engine — Requirements

## 0. Purpose of this document

This document specifies requirements for a ground-up rewrite of the **core
scheduling engine** for Family Camp: the component that takes camper
registration/preference data and produces a timetable assigning campers to
activity sessions.

It is intentionally **solver-agnostic** — it describes *what* a correct and
good schedule is, and what the system must do, without assuming a
genetic algorithm, constraint solver, MILP, heuristic, or any other
technique. It is meant to be used as the basis for generating and comparing
several candidate design/solver approaches.

Requirements are numbered (`FR-n` functional, `NFR-n` non-functional) so
later design documents can reference them directly.

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

### 1.2 Explicitly out of scope (for this document)

- **Fetching/authenticating against Google Sheets.** The existence of
  camper/activity/session data conforming to the contract in §3 is treated
  as a **prerequisite** — a solved problem supplied by an existing or future
  upstream process. This document does not specify how that data arrives.
- **Printing/rendering** (PDF/text output, pagination, page layout, per-family
  info packs). *Partially reopened by §4.8 and §4.11*: four
  audience-specific PDF reports (activity roster, per-family itinerary,
  available adults, available families) were added at the user's
  explicit request after reviewing the old system's PDF output — a
  narrow, presentation-only addition over the same data §4.7's text
  reports already produce, not a general printing/layout framework (no
  manual editing, no per-family "packs" beyond the itinerary PDF). §4.11
  adds one further, distinct document — a single overview/analysis PDF
  aimed at the organiser rather than any one audience, generated
  unconditionally rather than opt-in — still not a general
  printing/layout framework.
- **Manual editing workflow** (hand-tweaking a generated schedule in a
  spreadsheet/CSV and re-importing it, diffing against a previous run, etc.).
  *Partially reopened by §4.9*: re-validating and re-reporting a hand-edited
  schedule through the existing pipeline, at the user's explicit request —
  not an interactive editor, not edit-time constraint enforcement, and
  diffing against a previous run remains excluded pending OQ-17.
- Camp registration, payment, or booking-form automation.

These exclusions are about this rewrite's scope, not a judgement that they
are unimportant — they are separate concerns with their own requirements to
be defined later, and coupling them to the scheduling engine's design would
narrow the solver options unnecessarily.

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

## 3. Input data contract (prerequisite)

The engine consumes three collections, already extracted from whatever
upstream source (currently Google Sheets) into this shape. This document
takes their availability as given; the exact serialisation (files, API,
in-memory objects) is a design decision, not a requirement.

### 3.1 Activity

| Field | Meaning |
|---|---|
| Identifier/name | Unique name of the activity. |
| Duration | Length of one session of this activity. |
| Minimum occupancy | Fewest campers required for a session of this activity to be considered valid, if it runs at all. |
| Maximum occupancy (capacity) | Most campers a single session of this activity can hold. |

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
  long, has exactly N activities, etc.).

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
  session of the same activity, unless the activity is explicitly marked as
  repeatable (see open question OQ-6 — not currently supported).
- **FR-16 (Compulsory activities)**: If any activities are designated
  compulsory, every camper is assigned to exactly one session of each.
  (Currently no activities are so designated, but the engine must support
  the concept.)
- **FR-17 (Supervised family splits)**: This tightens and supersedes
  OQ-7's original answer. When a family is split across more than one
  session of the *same* activity (whether it's a priority or an optional
  request for whoever's attending — OQ-7's answer only covered
  priorities), every one of those sessions must be jointly attended by at
  least one adult (18+) AND at least one non-adult member of the family —
  no session may contain only adults, and no session may contain only
  children, WITH ONE exception: a children-only session is still
  acceptable if at least one adult member of the family has no assignment
  overlapping that session's time (they are then free to informally
  accompany/supervise even though not formally taking part in the
  activity themselves). There is no equivalent exception for an
  adults-only session — the family being split is popular, so this is
  meant to be a real constraint, not one either side can route around.

### 4.2 Soft objectives — a good schedule SHOULD optimise for these

Exact relative weighting between these is a design/tuning decision, not
fixed by this document, but the engine must have *some* way to express and
adjust the trade-off (see NFR-4).

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
- **FR-23 (Engagement / idle time — optional, see OQ-3)**: Prefer schedules
  that minimise stretches where a camper (or family) has no assigned
  activity, where this doesn't conflict with higher-priority objectives.
- **FR-24 (Minimise family splits)**: Splitting a family across several
  sessions of the same activity (FR-17) is unpopular with families and
  should be a last resort. The engine SHOULD first attempt a schedule that
  keeps every family together in a single session per activity, and only
  split a family when there is no way to accommodate its members'
  requested activities otherwise (e.g. session capacity forces it). This
  ranks above FR-20/21/22/23 — the engine should prefer keeping a family
  together over satisfying an extra optional request — but below the
  hard/demand-driven constraints in §4.1 (including FR-17's supervision
  requirement, which is never traded away to reduce a split).

### 4.3 Feasibility and best-effort behaviour

- **FR-30**: Real inputs may be infeasible (e.g. total demand for an
  activity's priority slots exceeds its total capacity across all
  sessions). The engine MUST detect this and MUST NOT report a schedule as
  fully valid if it isn't.
- **FR-31**: When no fully feasible schedule exists, the engine MUST still
  produce a best-effort schedule, and MUST report exactly which hard
  constraints remain violated and for whom (e.g. "camper X did not get
  priority activity Y — no session had capacity"), so an organiser can act
  on it. Which violations to prefer leaving unresolved (if trade-offs are
  required) is a design decision, but the trade-off actually made must be
  visible in the report, not hidden inside an aggregate score.

### 4.4 Validation / explainability

- **FR-40**: The engine MUST be able to evaluate an arbitrary candidate
  timetable — not just one it generated itself — against every hard
  constraint in §4.1 and every objective in §4.2, and produce a structured
  report (not just a single pass/fail flag). This is what lets any future
  tool (manual review, regression tests, a different generator entirely)
  check a schedule's validity without re-implementing the rules.
- **FR-41**: Violation reports MUST identify the specific camper(s),
  family/group, activity, and session(s) involved — enough detail to act
  on without cross-referencing the raw input data by hand.

### 4.5 Output contract

- **FR-50**: The engine MUST produce a structured result describing, for
  every session, which campers are assigned to it (equivalently, for every
  camper, which sessions they're assigned to). This is the sole interface
  downstream consumers (printing, exports, future manual-editing tools) rely
  on — they must not need to know how the assignment was computed.
- **FR-51**: The output MUST unambiguously identify *which* session
  (specific activity occurrence/time) each assignment refers to — no
  ambiguity between two sessions of the same activity.

### 4.6 Progress reporting during generation

Reverse-engineered from the current GA-based system's behaviour
(`family_camp/schedule/generate_schedule.py`) and from direct experience
running a real, hours-long generation with the family_camp2 rewrite (no
progress reporting exists yet, so the only way to check on it was
externally polling process/CPU state). The old system: prints a per-generation
stats line (min/avg/max/std of the fitness tuple) automatically throughout
the run; lets an operator press Enter on stdin at any time to dump the
current best-known results to disk *without* stopping the run; and always
writes out its best-known results on exit, including on a crash or
Ctrl-C (a `try/finally` around the whole run). These requirements
generalise that behaviour without assuming a GA, generations, or any
particular solver's internal structure.

- **FR-60**: The engine MUST periodically report progress during a
  generation run long enough for it to matter (order of seconds to
  hours), so an operator can tell the run is alive and making progress
  without inspecting external process state.
- **FR-61**: Each progress report MUST include, at minimum, elapsed time
  and the best schedule quality found so far, expressed using the same
  measures used everywhere else (the hard-constraint/best-effort picture
  of FR-30/FR-31, and the soft objectives of FR-20–FR-22) — not a
  separate, solver-specific metric an operator has to learn to interpret.
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

Reverse-engineered from the current system's `MyHallOfFame.dump_to_dir()`
and `check_schedule.py` (`family_camp/schedule/deep.py`,
`family_camp/schedule/check_schedule.py`), which together produce, for a
given timetable: a CSV of the actual assignments; a per-family itinerary
listing; a per-activity/session roster with occupancy totals against each
activity's limit; and two separate idle-time views (whole family/groups
with nothing scheduled, and individually named idle *adults*, for
staffing/supervision purposes). None of this is the same thing as the
FR-40/41 validation report, which describes how *good* a schedule is, not
what it *is* or how to act on it day-to-day. Producing the underlying
report *content* here is in scope even though rendering it to PDF/print
layout is not (§1.2) — the distinction is between generating the
information and laying it out on a page.

- **FR-70**: The engine MUST be able to export a timetable (generated, or
  hand-supplied and already validated) to a durable, machine-readable
  format that captures every assignment (camper, activity, session). This
  is the actual deliverable schedule, distinct from the scoring/violation
  report of FR-40/41.
- **FR-71**: An exported schedule (FR-70) MUST be re-importable by the
  engine, so a previously generated (or manually adjusted, per the
  manual-editing workflow excluded in §1.2) schedule can be re-validated
  (FR-40) without needing to regenerate it from the original
  activities/sessions/campers input. This requirement is only about the
  import/export mechanism; building an editing workflow around it remains
  out of scope.
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
  named idle adults — the old system treated these as two distinct views
  because they serve different purposes, and this rewrite should too, not
  collapse them into one undifferentiated camper-level list. This extends
  the idle-time reporting already required by FR-23.
- **FR-75** (should, not must): Where a solver's search naturally produces
  more than one good candidate schedule (e.g. independent restarts), the
  engine SHOULD be able to export/report on more than just the single
  best one, so an organiser can compare alternatives — the old system
  surfaced its top 10 results for this reason. A solver that only ever
  has one canonical best answer (e.g. a provably lexicographically
  optimal one) is not deficient for not manufacturing artificial
  alternatives.
- **FR-76**: The engine MUST be able to produce a human-readable report of
  unmet optional (non-priority) activity requests from a given timetable:
  for each optional activity that was requested but not obtained, which
  campers missed out. This is the per-request breakdown behind the
  aggregate Tier 1 score (FR-21) — useful to an organiser deciding where
  to add capacity or sessions.
- **FR-77**: The engine MUST be able to produce a human-readable report,
  derived from the input activities/sessions/campers alone (not from any
  particular timetable), of families whose members have collectively
  requested more distinct activities than the maximum number of
  non-overlapping session slots the *family* could ever occupy across the
  whole camp — i.e. a structural, time-based ceiling that no solver could
  work around regardless of available capacity. This is computed at
  family, not individual, granularity: since no two members of a family
  may be in overlapping sessions (the family-time-conflict rule), the
  family as a whole — not each member separately — is the unit that can
  only occupy one slot at a time. This is a necessary-infeasibility
  check only (requesting fewer activities than this ceiling does not
  guarantee everything fits — sessions of the specific requested
  activities may still clash with each other even when the camp overall
  has plenty of free time elsewhere), and exists to help an organiser
  distinguish "not enough capacity" from "not enough time" as the reason
  an optional request went unmet.

### 4.8 PDF reports

Added after the user shared the old system's PDF output
(`family_camp/schedule/schedule_printer.py`, examples in
`fetched_data/old_reports/`) and asked for a deliberately different,
more compact design, not a like-for-like port — see IMPLEMENTATION_PLAN.md's
corresponding step for the specific layout decisions this reacted
against (one Paragraph per camper name driving page count up to 41
pages at A4; a forced page break before every activity/family regardless
of how much room was left).

- **FR-80**: The engine MUST be able to produce a PDF activity roster:
  for each activity, its sessions with attendees and occupancy against
  capacity — the same information as the existing text report (FR-73),
  laid out for printing rather than terminal/file reading.
- **FR-81**: The engine MUST be able to produce a PDF per-family
  itinerary, distinct from FR-80's document (a different audience: staff
  running a session vs. a family finding their own day) — the same
  information as the existing text report (FR-72), laid out for
  printing.
- **FR-82**: Both PDF reports MUST support the organiser choosing paper
  size (A4 or A3) and orientation (portrait or landscape) independently,
  matching the old system's two example outputs.
- **FR-83** (should, not must): Layout SHOULD adapt to the chosen paper
  size/orientation to use space efficiently (e.g. more columns on a
  wider page) rather than a fixed layout scaled to fit, and SHOULD avoid
  forcing a new page/section for every activity or family regardless of
  how much room remains, since it was exactly this combination that made
  the old system's output unnecessarily long.
- **FR-84**: The engine MUST be able to produce a PDF listing, for each
  active time period, which *adult* campers have nothing scheduled — a
  third document, distinct from FR-80/81 (a different question: not
  "who's doing what", but "who's free right now"), for an organiser
  trying to find a spare adult volunteer. Only adults appear (children
  are not volunteer candidates) — reuses the existing idle-time
  computation (FR-23/FR-74) filtered to `is_adult`, not a new concept.
- **FR-85**: The engine MUST be able to produce a PDF, in the same shape
  as FR-84, narrowed to adults whose *entire family* has nothing
  scheduled at that time (not just the adult themselves) — a stronger
  availability signal, since they won't need to break away to rejoin a
  family member who's mid-activity. Reuses the existing idle-family
  computation (FR-74's `idle_families`) intersected with FR-84's idle
  adults, not a new concept.

### 4.9 Manual editing and re-validation workflow

Reopens part of §1.2's "Manual editing workflow" exclusion, at the
user's explicit request. The scope agreed is narrow: taking a
hand-edited schedule back through validation and reporting — not an
interactive editor, not edit-time constraint enforcement, not (yet)
diffing against a prior run. Most of what this needs already exists and
was built with exactly this in mind: `io/schedule_export.py` (FR-70/71)
already round-trips a `Timetable` to/from CSV/JSON, and `validate()`/the
FR-72-74/FR-80-85 reports were already built solver-agnostic — they only
ever need a `Timetable` plus the original `activities`/`sessions`/
`campers`, never a solver-specific result. The one piece that doesn't
exist yet is an entry point that skips solving entirely and goes
straight from an edited schedule file to validation and reporting.

- **FR-86**: The engine MUST support taking a previously exported
  schedule (FR-70/71's format) that has been edited by hand, and
  producing the same validation report (FR-40/41) and human-readable/PDF
  reports (FR-72-74, FR-80-85) it would for a freshly solved schedule,
  without invoking a solver.
- **FR-87**: Re-importing an edited schedule MUST NOT silently accept a
  row that can't be resolved back to a known camper or session from the
  original input data (e.g. a typo'd name). See OQ-16 for whether this
  stops at the first such row or collects all of them.
- **FR-88**: The engine MUST report Class 1 (structural) violations in a
  re-validated schedule exactly as it would for a solver's output. This
  needs no new check — `validate()` already does this — but is worth
  stating explicitly: unlike a solver-built `Timetable` (where a Class 1
  violation is structurally impossible by construction), a hand edit can
  genuinely introduce one (e.g. double-booking, capacity overflow), and
  the engine must not treat re-validated input as inherently trustworthy.
- **FR-89** (should, not must): The re-validation entry point SHOULD
  support the same export flags available for a freshly generated
  schedule (schedule export, the text reports, the PDF reports), so a
  re-validated schedule can itself be re-exported and edited again,
  supporting multiple rounds of hand-tweaking.

### 4.10 Per-camper/family custom constraints

Raised by the user wanting to express requirements the engine has no
other way to capture — e.g. "022/Glen must not have any activities on
the 2nd day" or "Emma Glen (022/Glen) must not have any activity before
11:00" — parameterised per §3.5's new input collection, editable by an
organiser without a code change.

The central design idea: nearly every useful constraint of this kind
reduces to a per-(camper, session) predicate — "is this camper allowed
to be in this session at all?" — which is exactly the mechanism that
already makes Class 1 (FR-10-16) structurally guaranteed in both
solvers (`_is_eligible` in `cp_sat.py`/`annealing/moves.py`). A
constraint expressible this way (called **Tier A** below) gets hard
*and* soft enforcement in both solvers for free, with zero
solver-specific code needed per new rule. A constraint that isn't
expressible this way (**Tier B** — e.g. "no more than 2 activities per
day," which depends on a camper's *other* assignments, not a fixed
session set) needs bespoke validator logic and, if hard, bespoke solver
modeling, case by case. This document only requires Tier A support;
Tier B is an explicitly acknowledged future extension of the same
architecture, not part of this phase (OQ-22).

- **FR-90**: The engine MUST support a general, extensible architecture
  for named, parameterised per-camper/family constraint rules — adding a
  new rule type MUST NOT require changes to the solvers themselves for
  the common (Tier A) case, only a new rule class.
- **FR-91**: Each constraint record (§3.5) MUST resolve its target to one
  or more campers: a family identifier resolves to every member; a
  family+camper pair resolves to that one camper. An unresolvable target
  (unknown family/camper) MUST be reported, not silently skipped —
  consistent with FR-87's requirement for schedule re-import.
- **FR-92**: The constraint expression (§3.5's "Constraint" field) MUST
  be parsed safely — it MUST NOT be evaluated as arbitrary code (this is
  organiser-edited spreadsheet data, not trusted source code). An
  unparseable expression or unknown rule name MUST be reported clearly,
  naming the row and the problem.
- **FR-93**: As with FR-87/OQ-16's precedent for schedule re-import, the
  engine MUST collect and report every invalid constraint record (bad
  target, bad expression, unknown rule) together, not stop at the first.
- **FR-94**: A **hard** constraint MUST be enforced exactly like a Class
  1 rule: the engine must never produce a timetable that violates it, in
  either solver. If a hard constraint makes one of that camper's own
  priorities structurally unreachable, this MUST surface as a normal
  `missing_priority` violation (FR-13/FR-31) — no special-case handling,
  the same graceful behaviour already used for e.g. an age-restricted
  activity a camper can never reach.
- **FR-95**: A **soft** constraint MUST be treated as an optimisation
  target: penalised in the same weighted-severity mechanism Class 2
  already uses (FR-30/31), reported when unmet, but not treated as
  making the schedule infeasible on its own.
- **FR-96**: The engine MUST implement at least the following Tier A
  rules: activities excluded by camp day number (day 1, 2, ... - derived
  from the distinct calendar dates present in the session data, not a
  fixed date, per FR-3); activities excluded before/after a time of day;
  activities excluded within a given date/time range; a specific
  activity excluded outright regardless of the camper's own
  priority/optional lists.

### 4.11 Schedule Status Report

A single-document overview aimed at the organiser, distinct from
everything else in §4.7-§4.9: not "what is the schedule" (FR-70-74/
FR-80-85, audience-specific: staff running a session, a family finding
their day, a volunteer coordinator) and not "is this schedule valid"
alone (FR-40/41's violation report), but a one-stop analysis document
bringing together front matter, activity/session loading, camper/family
fulfilment, and solver diagnostics, so an organiser can sanity-check a
run without cross-referencing several separate outputs. Unlike every
other report in this document, it is generated **unconditionally** —
see FR-98/FR-107 — not behind an opt-in export flag.

The subsections below (FR-100-106) elaborate the five content areas
originally sketched in FR-99, and resolve the design decisions the user
made when this requirement was reviewed (chart library, pagination,
trigger mechanism, output location, and the `reportlab` dependency).

- **FR-97**: The status report MUST be generated as an A4 PDF document,
  portrait orientation, fixed (not organiser-configurable per-run the
  way FR-82's audience-specific PDFs are, since unlike FR-80/81/84/85
  this isn't a per-audience print-out — it's always the same kind of
  read).
- **FR-98**: The status report MUST be generated at the end of every
  `solve` run and every `revalidate` run, unconditionally. See FR-107
  for where it's written. *Superseded in scope by §4.12/FR-110*: this
  requirement originally motivated making just the status report
  unconditional while every other export/report output stayed opt-in;
  the user later asked (§4.12) for that same unconditional treatment to
  extend to every report this engine produces, not only this one.
- **FR-99**: The status report MUST contain, at minimum, five sections:
  front matter (FR-100), camp activity information (FR-101), activity
  session loading (FR-102), camper/family activity loading (FR-103/104),
  and solver information (FR-106).
- **FR-100 (Front matter)**: The report MUST open with: the date/time
  the report was generated; the camp's date range and duration, derived
  from the actual session data (earliest session start to latest session
  end, per FR-3 — never assumed or hardcoded); and headline counts
  (number of activities, sessions, campers, and families).
- **FR-101 (Camp activity information)**: The report MUST include a
  table of every activity (name, number of scheduled sessions, min/max
  occupancy, whether it's a configured compulsory activity per
  FR-16/OQ-5), and a graphical activity timetable showing, per activity,
  when its sessions run. As explicitly scoped by the user, this
  graphical timetable MAY assume the camp spans exactly 2 distinct
  calendar days — narrower than FR-3's general no-fixed-length rule,
  and justified only because it's a single specific visualisation, not a
  computation. If the session data's actual distinct dates don't number
  exactly 2, the graphical timetable MUST degrade to a clearly-labelled
  tabular fallback (session start/end per activity, grouped by actual
  date) rather than crash or mislabel days that don't exist — consistent
  with this document's established "never crash, report clearly" pattern
  (e.g. FR-1, FR-94).
- **FR-102 (Activity session loading)**: The report MUST show, for
  every session, occupancy against its activity's capacity (e.g. a
  stacked bar of filled vs. spare seats), and summary statistics
  including the mean and spread of spare capacity across all sessions.
  "Ideal" session size for this deviation statistic is a session's
  `max_occupancy` (a fully-booked session is ideal; deviation measures
  how far below full each session ran) — chosen over a min/max midpoint
  or a new configurable target because it reuses a concept
  (`max_occupancy`) the engine already has, needing no new config
  surface. Sessions already flagged `under_minimum` (Class 2,
  FR-30/31/§4.10) SHOULD be visually distinguished, not just implied by
  a low bar.
- **FR-103 (Camper activity loading)**: The report MUST show, for every
  camper, a stacked bar comparing requested (priority + optional)
  activities against allocated ones — distinguishing at least priorities
  met, optional activities met, and unmet requests of each kind, so a
  camper with everything satisfied looks visibly different from one who
  didn't. Every camper MUST appear (not a sample or an "anomalies only"
  subset) — with hundreds of campers this needs pagination across
  multiple pages, sorted by family so a family's members stay adjacent
  and easy to cross-check against §4.11's family-level view (FR-104).
- **FR-104 (Family activity loading)**: As FR-103, aggregated to family
  granularity — one stacked bar per family, summing its members'
  requested vs. allocated activities. Every family MUST appear, paginated
  as needed, in a consistent family order with FR-103.
- **FR-105 (Anomaly visibility)**: Campers/families with at least one
  *unmet priority* (the most severe shortfall a camper can have, per
  FR-13) MUST be visually distinguished within FR-103/104's charts (e.g.
  colour), so they don't require reading every bar to find. The report
  MUST also include the existing structural-overdemand finding (FR-77 —
  families who could never fit their requests regardless of capacity,
  a time-based ceiling no solver could work around) as a callout list,
  reusing `find_overdemanding_families` rather than a new computation.
- **FR-106 (Solver information)**: The report MUST state which solver
  produced the schedule and how long it took (wall-clock), the full
  Tier 0/1/2 score breakdown, every Class 2 violation category's count
  (including custom-constraint violations, §4.10), and a summary of
  custom constraints in effect (how many hard, how many soft, and how
  many soft ones had at least one violation). When the report is
  produced via `revalidate` (no solver was run), this section MUST say
  so explicitly (e.g. "N/A — re-validated from an edited schedule") —
  never fabricate solver information that doesn't exist, consistent with
  FR-88's "don't treat re-validated input as inherently trustworthy".
- **FR-107 (Output location)** — *superseded by §4.12/FR-110*: originally,
  with no opt-in flag to hang a path off (FR-98), the default output path
  was alongside `--export-schedule` when given, otherwise
  `./status_report.pdf`, overridable with `--status-report PATH`. §4.12
  replaced this status-report-specific rule with one shared location
  convention for every report this engine produces.
- **FR-108 (`reportlab` dependency)**: Since generation is unconditional
  (FR-98), `reportlab` MUST move from the optional `pdf` extra
  (`pip install -e ".[pdf]"`) into family_camp2's core install
  dependencies — every `solve`/`revalidate` run now needs it, so there's
  no longer a meaningful "optional" case to guard with the existing
  `ImportError`-catching pattern. The four existing audience-specific
  PDFs (FR-80/81/84/85) benefit incidentally — `reportlab` is now
  guaranteed present for them too.
- **FR-109 (Charting approach)**: Charts (FR-102/103/104) MUST be built
  with `reportlab.graphics.charts` (native bar/stacked-bar support), not
  a new charting dependency (e.g. matplotlib) — consistent with NFR-6
  and every other visual element `pdf_reports.py` already produces.

### 4.12 Unified report output location

Raised by the user wanting to "tidy up the cli arguments for generating
reports": by this point, `solve`/`revalidate` had accumulated one opt-in
flag per report (`--out`, `--export-schedule`, `--report-dir`,
`--pdf-dir`/`--pdf-paper`/`--pdf-orientation`) plus the status report's
own unconditional-but-separately-pathed `--status-report` (§4.11/FR-98).
The user asked for every report to be generated unconditionally — no
flag to exclude any of them — consolidated under one `--out-dir` option,
with every file for a run living in one folder named from the camp and
the run's date/time, and nothing ever written outside it except
`fetch_cli.py`'s cached download JSON.

- **FR-110 (Unconditional, consolidated report generation)**: Every
  report `solve`/`revalidate` can produce — the exported schedule
  (FR-70/71), the operational text reports (FR-72-74/76/77), the
  audience-specific PDFs (FR-80/81/84/85), the validation report JSON,
  and the status report (§4.11) — MUST be generated on every run, with
  no per-report flag to exclude any of them. `--pdf-paper`/
  `--pdf-orientation`'s former choice of one paper size/orientation MUST
  become both combinations, generated unconditionally, rather than a
  choice the organiser makes per run.
- **FR-111 (`--out-dir` and folder naming)**: `solve`/`revalidate` MUST
  take a single `--out-dir` option (a folder, default `fetched_data`).
  Every report for one run MUST be written into a subfolder of it named
  `<camp_name>_<run timestamp>` — the run timestamp captured when the
  command starts, so two runs never collide into the same folder. No
  file MUST be created outside that subfolder. *`camp_name`'s source
  refined by §4.13/FR-114*, since this was written before `fetch` became
  a subcommand of the same CLI with a fixed output filename.
- **FR-112 (Fetch tool alignment)** — *fixed filename refined by
  §4.13/FR-115*: the tool that downloads camp data from a Google Sheet
  MUST take the same `--out-dir` option (default `fetched_data`) and
  write its cached download JSON directly into it (not a per-run
  subfolder, per FR-111's exception) — this is a durable cache reused
  across many later `solve` runs, not one run's own report. `camp_name`
  for it MUST be derived from the Google Sheet's own title, so no
  separate `--camp-name` flag is needed, and `solve`/`revalidate`
  (FR-111) recover the same name automatically.

### 4.13 Unified CLI (`fetch` as a subcommand)

Raised by the user wanting "a single unified cli": at the point §4.12
was implemented, fetching (`fetch_cli.py`, a separate script/console
entry point) and scheduling (`cli.py`'s `solve`/`revalidate`) were still
two different command-line tools that happened to agree on a shared
`--out-dir` convention. The user asked for one tool with `fetch` as a
third subcommand, `fetch` taking a Google Sheets URL, and `solve`
automatically using whatever `fetch` most recently downloaded — stopping
with a clear, descriptive error (not a bare stack trace) if nothing has
been fetched yet.

- **FR-113 (Single CLI)**: `fetch` MUST be a subcommand of the same CLI
  as `solve`/`revalidate` (`family_camp2 fetch ...`), not a separate
  script/console entry point.
- **FR-114 (Automatic input discovery)**: `solve`/`revalidate` MUST NOT
  require `--data`/`--legacy-cache` — when neither is given, they MUST
  use the file `fetch` most recently wrote into `--out-dir`
  automatically. Explicit `--data`/`--legacy-cache` MUST still be
  accepted, overriding the automatic choice.
- **FR-115 (Descriptive missing-data error)**: If `solve`/`revalidate`
  is run with no explicit `--data`/`--legacy-cache` and nothing has been
  fetched into `--out-dir` yet, the engine MUST stop with a clear,
  descriptive error explaining that `fetch` needs to be run first
  (naming the command), not an unhandled `FileNotFoundError` or similar.
- **FR-116 (Camp name propagation)**: Since `fetch`'s output filename is
  now fixed (FR-114 needs one predictable path to look for, so it can no
  longer vary by camp name the way §4.12 originally specified), the camp
  name FR-111's output-folder naming needs MUST instead be carried
  inside the cached JSON itself (a `camp_name` field, set by `fetch` from
  the Google Sheet's own title) and read back by `solve`/`revalidate` -
  falling back to the input file's own name when that field is absent
  (a hand-written `--data` file, or `--legacy-cache`, which predates it).

## 5. Non-functional requirements

- **NFR-1 (Scale)**: The engine must handle input sizes consistent with an
  actual Family Camp weekend (see OQ-1 for the need to confirm concrete
  numbers from historical data — order of magnitude is hundreds of
  campers, dozens of activities, on the order of a hundred sessions).
- **NFR-2 (Turnaround time)**: The engine must produce a usable schedule
  within a time budget compatible with iterative use during camp planning
  — an organiser should be able to adjust input data and re-run without it
  becoming a blocker (see OQ-2 for the specific budget to target).
- **NFR-3 (Reproducibility)**: Given the same input and configuration, the
  engine should produce comparable-quality results on repeated runs. If the
  chosen approach involves randomness, there must be a way to reproduce a
  specific run exactly (e.g. a seed) for debugging and regression testing.
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
  MUST NOT materially slow down the underlying search — e.g. no expensive
  full re-validation triggered on every single search step. Reporting
  granularity/cadence is a tunable trade-off, not something that should
  force a choice between "informative" and "fast".
- **NFR-10 (Reports reuse the same rules)**: The human-readable reports of
  §4.7 MUST be derived from the same validator/scoring logic as
  everything else (FR-40, NFR-8) — not a separate, potentially
  inconsistent implementation of "who's idle" or "who's in which
  session".

## 6. Success criteria

The rewrite succeeds if, for a real Family Camp dataset conforming to §3:

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

## 7. Open questions to confirm before/while designing

- **OQ-1 (Scale)**: What are realistic upper bounds for number of campers,
  activities, and sessions, based on historical camps? This materially
  affects which solver approaches are viable.

  [Answer:  number of campers - upper bound: 500
            activities - upper bound: 30
            sessions - upper bound: 50 ]
- **OQ-2 (Turnaround budget)**: What's an acceptable wall-clock time for a
  single generation run — seconds, minutes, or is an overnight batch run
  acceptable?

  [Answer:  24 hours]

- **OQ-3 (Idle-time objective)**: Should minimising camper/family idle time
  (FR-23) be a real optimisation objective, or is it sufficient (as today)
  to just report idle slots for staffing awareness after the fact?

  [Answer: it is sufficient to just report idle slots]

- **OQ-4 (Objective priority)**: Is there an intended ranking between the
  soft objectives (FR-20–FR-23) — e.g. is even spread (FR-22) more or less
  important than optional-request satisfaction (FR-20) — or should this
  simply be an adjustable weight with no fixed default preference?

  [Answer: this need to be a ranking between the soft objectives]

- **OQ-5 (Compulsory activities)**: Should this rewrite activate the
  compulsory-activity concept (FR-16) from day one (e.g. shared meals), or
  keep it supported-but-unused as it is currently?

  [Answer: supported-but-unused]

- **OQ-6 (Repeatable activities)**: Is there a real need for a camper to be
  validly scheduled into the *same* activity more than once (e.g. an
  open-session craft table), or does FR-15's "no duplicates" rule hold
  universally?

  [Answer: the "no duplicates" rule holds universally]

- **OQ-7 (Partial-family scheduling)**: When a family can't all get the
  same priority activity due to capacity, is splitting them across
  non-overlapping sessions of it (rather than an overlapping clash)
  acceptable, or should some activities require the whole family together
  in the same session? Today's rules only forbid *overlapping* conflicts,
  not different-but-non-overlapping sessions — confirm this matches intent.

  [Answer: it is acceptable to split a family across non-overlapping sessions of the same priority activity, only if all sessions have at least one adult (over 18) from the family included.]

  [Superseded/tightened by OQ-13 below — see FR-17/FR-24.]

- **OQ-8 (Age-based constraints)**: Camper age/age-group is captured in the
  input (§3.3) but no age-based eligibility rule exists in the current
  system. Should the rewrite support restricting an activity to an age
  range/group, or is this out of scope?

  [Answer: yes, there should be a way to express a lower bound age for an activity]

- **OQ-9 (Progress update cadence)**: What's a sensible default interval
  for progress updates (FR-60) — wall-clock-time based (e.g. every N
  seconds), event-based (e.g. every time the best-found score improves),
  or both?

  [Answer: wall-clock-time (defaut: 60s)]

- **OQ-10 (Progress reporting channel)**: Should progress (FR-60) be
  written to stdout/a log (as the old system did), to a separate
  pollable status file (useful for exactly the kind of external
  background-run monitoring done by hand this session), or both?

  [Answer: command line option to send to file (default: '-' for stdout)]

- **OQ-11 (Export format)**: Should the machine-readable schedule export
  (FR-70) be CSV (matching the old system, directly inspectable in a
  spreadsheet), the same JSON-based domain format already used for
  `--data` input, or should both be supported?

  [Answer: output both CSV and JSON]

- **OQ-12 (Multiple candidate schedules)**: Given FR-75 is a *should*, not
  a *must* — is presenting multiple candidate schedules actually wanted
  for this rewrite, or is a single best/canonical answer sufficient?
  Directly relevant to whether annealing's per-chain results are worth
  formally exporting, rather than only being used internally to pick the
  overall winner.
  
  [Answer: single best answer is sufficient]

- **OQ-13 (Tightening family-split supervision, FR-17/FR-24)**: Raised
  after reviewing the generated schedule against real 2026 data and
  finding families split across optional (not just priority) activities
  with unbalanced adult/child groupings. The user's verbatim answer:
  "Splitting a family in this way is very unpopular and should be a last
  resort. I would like to tighten the condition in the following ways:
  1 - if a family must be split, at least one adult and at least one
  child must attend each session, i.e. no lone adults or unaccompanied
  children (it is acceptable to have an unaccompanied child if at least
  one adult in the family is not allocated to any activity at the same
  time — this allows the adult to accompany the child, even though they
  are not taking part). 2 - the solver should first attempt to solve the
  schedule without splitting families, it should only attempt to split
  them if absolutely necessary (this could also be expressed as a desire
  to minimise the number [of] split families if this is better for the
  solver)." Implemented as FR-17 (supervision) and FR-24 (minimisation,
  ranked above FR-20-23 but below §4.1's hard/demand-driven constraints).

- **OQ-14 (Edit format, FR-86)**: Should hand-editing reuse the existing
  CSV/JSON export format as-is (FR-70/71 — one row per assignment, every
  edit is just adding/removing/changing a row), or is a different,
  more edit-oriented layout worth building instead — e.g. grouped by
  session or by family, closer to the existing text/PDF reports' shape —
  or a real spreadsheet (`.xlsx`) with data-validation dropdowns on the
  camper/session columns, so an invalid reference is impossible to enter
  rather than just caught at import time?

  [Answer: use existing CSV/JSON, allow both]

- **OQ-15 (Entry point shape, FR-86)**: How should "validate an edited
  schedule" actually be invoked? Options considered: (a) a new
  `--solver none`-style choice on the existing `family_camp2` command,
  paired with a new `--schedule PATH` flag, instead of solving; (b) a
  separate console script, e.g. `family_camp2-revalidate`, mirroring the
  existing `family_camp2-fetch` precedent, sharing an internal
  output-writing helper with `cli.py` so `--out`/`--export-schedule`/
  `--report-dir`/`--pdf-dir` logic isn't duplicated; (c) restructuring
  the CLI into subcommands (`family_camp2 solve` / `family_camp2
  revalidate`).

  [Answer: (c) restructure into subcommands ]

- **OQ-16 (Bad-row handling, FR-87)**: When re-importing a schedule that
  references an unknown camper or session (most likely a hand-editing
  typo), should this stop at the first such row (current
  `load_schedule_csv`/`load_schedule_json` behaviour, unchanged), or
  collect and report every bad row before raising — friendlier for a
  hand-editing session that's likely to contain more than one mistake,
  since it avoids a fix-one/re-run/hit-the-next-one loop?

  [Answer: collect and report every bad row before raising]

- **OQ-17 (Diff summary, FR-89)**: Should re-validation also report a
  summary of what changed versus the schedule being edited (assignments
  added/removed/moved) — a narrower, in-scope version of the "diffing"
  §1.2 still excludes more generally (e.g. diffing across separate
  solver runs, which stays out of scope regardless) — or is even this
  narrower version out of scope for now?

  [Answer: out of scope for now]

- **OQ-18 (Constraint syntax, FR-90)**: Should the "Constraint" field
  (§3.5) be a function-call-like expression (e.g.
  `no_activities_on_day(2)`, parsed via Python's `ast` module in
  restricted/safe mode — never `eval()`), or an English-phrase syntax
  matched against a small fixed vocabulary of sentence templates owned
  per rule class, or something else? Free-form NLP-style parsing is
  explicitly not being considered — too fragile for something that fails
  silently wrong rather than loudly wrong if misparsed.

  [Answer: function-call-like expression]

- **OQ-19 (Data flow into solve(), FR-90)**: Should resolved constraints
  reach the solver via a new field on `EngineConfig` (no change to the
  `Solver` protocol; conceptually similar to the existing
  `compulsory_activities` field), or via a new explicit parameter on
  `Solver.solve(...)` (touches the protocol, both solvers, and
  `validate()`'s signature, but keeps `EngineConfig` purely about
  solver-tuning weights rather than camp-specific per-camper data)?

  [Answer: EngineConfig]

- **OQ-20 (Soft-constraint weighting, FR-95)**: Should every soft custom
  constraint share one `Tier0Weights` severity band (simplest - all
  custom constraints weighted equally against each other), or does each
  constraint record need its own weight/priority (§3.5 would need an
  extra column)?

  [Answer: share one Tier0Weights]

- **OQ-21 (Severity ranking, FR-95)**: Where should the soft
  custom-constraint band rank relative to the existing Tier 0 severity
  order (`missing_priority` > `family_safety` > `family_split` >
  `under_minimum` > `compulsory`)? Note for whoever implements this:
  inserting a sixth band by simply extending the established 1,000x-ratio
  pattern would push the top band back up towards the range that caused
  real `MODEL_INVALID` overflow in CP-SAT (see IMPLEMENTATION_PLAN.md
  Step 34's deviation note) - the actual weight values will need
  re-deriving carefully, not just extending the existing pattern by one
  more step.

  [Answer: `custom-constraint` > `missing_priority` > `family_safety` > `family_split` >
  `under_minimum` > `compulsory`]

- **OQ-22 (Tier B scope, FR-90)**: Is Tier A sufficient for this phase
  (as FR-96 specifies), or is there a specific Tier B rule (e.g.
  "must always be scheduled with camper X") that's actually needed now
  rather than deferred?

  [Answer: Tier A sufficient for this phase]

- **OQ-23 (Charting library, FR-109)**: Should the status report's
  charts use `reportlab.graphics.charts` (no new dependency, stays
  inside the existing `pdf` extra) or `matplotlib` (nicer/easier charts,
  but a new dependency, rendered to an image and embedded)?

  [Answer: reportlab native charts]

- **OQ-24 (Camper/family chart scale, FR-103/104)**: With hundreds of
  campers and around a hundred families, should the per-camper/per-family
  "requested vs. allocated" charts show everyone (paginated across as
  many pages as needed), only anomalies (unmet requests) plus one
  aggregate summary, or an aggregate-only camp-wide view with no
  per-camper/per-family detail at all?

  [Answer: paginate everyone]

- **OQ-25 (Trigger mechanism, FR-98)**: Should the status report be
  generated unconditionally on every `solve`/`revalidate` run (matching
  FR-98's literal wording), or gated behind a new opt-in flag like every
  other export/report output in this document?

  [Answer: generated unconditionally, no opt-in flag]

- **OQ-26 (Ideal session size, FR-102)**: What should "ideal" mean for
  the session-loading deviation statistic — a session's `max_occupancy`
  (fully booked = ideal), the midpoint of `min_occupancy`/`max_occupancy`,
  or a new organiser-configurable target occupancy fraction?

  [Answer: max_occupancy]

- **OQ-27 (Default output location, FR-107)**: With generation
  unconditional (OQ-25) and no guaranteed flag to hang a path off, where
  should the report be written by default — a new flag with its own
  default filename, alongside `--export-schedule` when given, or always
  a fixed filename in the current directory?

  [Answer: alongside `--export-schedule` when given (`<stem>_status_report.pdf`);
  falls back to `./status_report.pdf` when `--export-schedule` isn't given
  — the fallback wasn't asked verbatim but follows directly from OQ-25's
  "unconditional" answer needing *some* location even when
  `--export-schedule` is absent, and was applied as the natural default
  rather than looping back for a third round of questions.]

- **OQ-28 (`reportlab` dependency, FR-108)**: Since generation is now
  unconditional, should the engine skip the report with a warning when
  `reportlab` isn't installed (keeps `reportlab` optional, matches this
  document's "never crash, report clearly" pattern), or should `reportlab`
  become a hard install dependency (simpler code, no optional-import
  path, but a heavier mandatory install)?

  [Answer: reportlab becomes a hard dependency]

- **OQ-29 (Camp name source, FR-111/112)**: Neither the JSON data schema,
  `--legacy-cache`, nor a Google Sheet has an explicit "camp name"
  concept, but both `fetch_cli.py` and `solve`/`revalidate` need one for
  their output naming. Should it come from a new explicit `--camp-name`
  flag (stored in the JSON so downstream commands don't need their own
  copy), from `--camp-name` required on every command separately, or be
  derived automatically (the Google Sheet's own title for `fetch_cli.py`;
  the `--data`/`--legacy-cache` filename's stem for `solve`/`revalidate`)?

  [Answer: derived automatically, no new flag]

- **OQ-30 (`fetch_cli.py` in scope, FR-112)**: Does the `--out-dir`
  restructuring extend to `fetch_cli.py` (writing its cached download
  JSON directly into `--out-dir`), or is it scoped to `solve`/
  `revalidate` only?

  [Answer: yes, fetch_cli.py too]

- **OQ-31 (Run-folder date/time meaning, FR-111)**: Should
  `<camp_name>_<date>_<time>` represent when the `solve`/`revalidate`
  command executed (a run identifier), or the camp's own dates (from the
  session data)?

  [Answer: when the run executed]
