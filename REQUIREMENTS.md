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
  info packs).
- **Manual editing workflow** (hand-tweaking a generated schedule in a
  spreadsheet/CSV and re-importing it, diffing against a previous run, etc.).
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