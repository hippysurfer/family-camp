"""REQUIREMENTS.md §4.11 (FR-97-109): the schedule status report - a
single A4 PDF generated unconditionally on every ``solve``/``revalidate``
run (FR-98), distinct from every other report in this codebase: not
audience-specific (a family's itinerary, a session's roster, who's free
right now - ``reporting.py``/``pdf_reports.py``) and not the plain
violation report alone (``validation.report``), but a one-stop overview
for the organiser reviewing a run.

Follows the same split the rest of the validation layer uses (NFR-6):
the ``_*_rows``/``_*_summary``/``_*_blocks`` functions below are plain
data transformations over ``Activity``/``Session``/``Camper``/
``Timetable``/``ValidationReport`` with no ``reportlab`` involvement,
independently unit-testable; the ``_render_*`` functions turn that data
into ``reportlab`` flowables, assembled into one document by
``render_status_report_pdf`` (Step 53). Reuses ``pdf_reports.py``'s
styling/table/canvas helpers rather than duplicating them, for visual
consistency with the other PDFs this engine produces (the same private-
helper cross-module import pattern already used by
``io/google_sheets.py``'s import of ``legacy_cache_loader._parse_duration``).

Camper/family fulfilment data (Steps 51/52) reuses the existing
``find_missing_priorities`` (``validation/class2.py``),
``find_unmet_optional_requests`` (``validation/tiers.py``), and
``find_overdemanding_families`` (``validation/feasibility.py``) - no new
fulfilment computation, only new aggregation/presentation over what the
validator already produces.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Table

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.pdf_reports import _GRID_COLOR, _HEADER_COLOR, _MUTED_COLOR, _styles, _table_style
from family_camp2.validation.class2 import Class2Report

__all__ = [
    "FrontMatterSummary",
    "ActivityTableRow",
    "DayBlock",
    "SessionLoadingRow",
    "SessionLoadingStats",
]

# FR-102: sessions flagged under_minimum are drawn in this colour instead
# of the normal "used capacity" colour, so they're visually distinguished
# rather than only implied by a short bar.
_UNDER_MINIMUM_COLOR = "#C53030"
_SPARE_CAPACITY_COLOR = "#CBD5E0"

_CHART_ROW_HEIGHT = 14
_CHART_LABEL_WIDTH = 160
_SESSION_CHART_ROWS_PER_PAGE = 40


def _camp_date_range(sessions: list[Session]) -> tuple[datetime, datetime]:
    """Earliest session start to latest session end (FR-100) - derived
    from the actual data, never assumed, matching FR-3."""
    return min(s.start for s in sessions), max(s.end for s in sessions)


def _distinct_camp_days(sessions: list[Session]) -> list[date]:
    """Sorted distinct calendar dates present in the session data - the
    same concept ``constraints/rules.py``'s ``_day_number`` uses for
    ``no_activities_on_day``, exposed here as the full list rather than
    one session's position in it."""
    return sorted({s.start.date() for s in sessions})


@dataclass(frozen=True)
class FrontMatterSummary:
    generated_at: datetime
    camp_start: datetime
    camp_end: datetime
    num_activities: int
    num_sessions: int
    num_campers: int
    num_families: int

    @property
    def camp_duration(self) -> timedelta:
        return self.camp_end - self.camp_start


def _front_matter_summary(
    activities: list[Activity], sessions: list[Session], campers: list[Camper], generated_at: datetime
) -> FrontMatterSummary:
    camp_start, camp_end = _camp_date_range(sessions)
    return FrontMatterSummary(
        generated_at=generated_at,
        camp_start=camp_start,
        camp_end=camp_end,
        num_activities=len(activities),
        num_sessions=len(sessions),
        num_campers=len(campers),
        num_families=len({c.family_id for c in campers}),
    )


def _render_front_matter(summary: FrontMatterSummary) -> list:
    duration = summary.camp_duration
    duration_hours = duration.total_seconds() / 3600
    return [
        Paragraph("Schedule Status Report", _styles["section_title"]),
        Paragraph(
            f"Generated {summary.generated_at.strftime('%A %d %B %Y, %H:%M')}",
            _styles["note"],
        ),
        Paragraph(
            f"Camp: {summary.camp_start.strftime('%a %d %b %Y %H:%M')} "
            f"&#8211; {summary.camp_end.strftime('%a %d %b %Y %H:%M')} "
            f"({duration_hours:.1f} hours)",
            _styles["table_cell"],
        ),
        Paragraph(
            f"{summary.num_activities} activities, {summary.num_sessions} sessions, "
            f"{summary.num_campers} campers across {summary.num_families} families",
            _styles["table_cell"],
        ),
    ]


@dataclass(frozen=True)
class ActivityTableRow:
    activity: Activity
    num_sessions: int
    is_compulsory: bool


def _activity_table_rows(
    activities: list[Activity], sessions: list[Session], compulsory: frozenset[Activity]
) -> list[ActivityTableRow]:
    session_counts: dict[Activity, int] = defaultdict(int)
    for s in sessions:
        session_counts[s.activity] += 1
    return [
        ActivityTableRow(
            activity=activity,
            num_sessions=session_counts.get(activity, 0),
            is_compulsory=activity in compulsory,
        )
        for activity in sorted(activities, key=lambda a: a.name)
    ]


def _render_activity_table(rows: list[ActivityTableRow]) -> Table:
    header = [
        Paragraph("Activity", _styles["table_header"]),
        Paragraph("Sessions", _styles["table_header"]),
        Paragraph("Min-Max", _styles["table_header"]),
        Paragraph("Compulsory", _styles["table_header"]),
    ]
    table_rows = [header]
    for row in rows:
        table_rows.append([
            Paragraph(row.activity.name, _styles["table_cell"]),
            Paragraph(str(row.num_sessions), _styles["table_cell_center"]),
            Paragraph(f"{row.activity.min_occupancy}-{row.activity.max_occupancy}", _styles["table_cell_center"]),
            Paragraph("Yes" if row.is_compulsory else "", _styles["table_cell_center"]),
        ])
    table = Table(table_rows, repeatRows=1)
    table.setStyle(_table_style())
    return table


@dataclass(frozen=True)
class DayBlock:
    day: date
    activity: Activity
    session: Session
    start_offset_minutes: int
    duration_minutes: int


def _activity_timetable_blocks(activities: list[Activity], sessions: list[Session]) -> list[DayBlock] | None:
    """FR-101: one block per session, positioned by its minutes-since-
    midnight offset on its own calendar day. Returns ``None`` when the
    data doesn't span exactly 2 distinct days - the explicit trigger for
    ``_render_activity_timetable_fallback`` instead, per FR-101's
    graceful-degradation requirement (this graphic, unlike the rest of
    the engine, is allowed to assume exactly 2 days - but only for this
    one visualisation, and only when that assumption actually holds)."""
    if len(_distinct_camp_days(sessions)) != 2:
        return None

    blocks = []
    for s in sessions:
        day = s.start.date()
        midnight = datetime.combine(day, time.min)
        offset_minutes = int((s.start - midnight).total_seconds() // 60)
        duration_minutes = int(s.activity.duration.total_seconds() // 60)
        blocks.append(
            DayBlock(
                day=day,
                activity=s.activity,
                session=s,
                start_offset_minutes=offset_minutes,
                duration_minutes=duration_minutes,
            )
        )
    return blocks


_TIMETABLE_ROW_HEIGHT = 14
_TIMETABLE_LABEL_WIDTH = 90
_TIMETABLE_PANEL_GAP = 10
_TIMETABLE_HEADER_HEIGHT = 16


def _render_activity_timetable_drawing(
    blocks: list[DayBlock], activities: list[Activity], width: float
) -> Drawing:
    """A two-panel (one per camp day) Gantt-style grid: one row per
    activity (shared vertical axis across both panels, so the same
    activity lines up between days), blocks positioned/sized from each
    ``DayBlock``'s time-of-day offset and duration, sharing one time
    scale across both panels so the two days are directly comparable."""

    days = sorted({b.day for b in blocks})
    activity_names = sorted({a.name for a in activities})
    row_index = {name: i for i, name in enumerate(activity_names)}

    min_offset = min(b.start_offset_minutes for b in blocks)
    max_offset = max(b.start_offset_minutes + b.duration_minutes for b in blocks)
    span_minutes = max(max_offset - min_offset, 1)

    chart_height = len(activity_names) * _TIMETABLE_ROW_HEIGHT
    total_height = chart_height + _TIMETABLE_HEADER_HEIGHT

    panel_width = (width - _TIMETABLE_LABEL_WIDTH - _TIMETABLE_PANEL_GAP * (len(days) - 1)) / len(days)

    drawing = Drawing(width, total_height)

    for name, i in row_index.items():
        y = chart_height - (i + 1) * _TIMETABLE_ROW_HEIGHT
        drawing.add(String(0, y + 3, name, fontSize=6, fontName="Helvetica"))
        drawing.add(Line(0, y, width, y, strokeColor=colors.HexColor(_GRID_COLOR), strokeWidth=0.25))

    for day_index, day in enumerate(days):
        panel_x = _TIMETABLE_LABEL_WIDTH + day_index * (panel_width + _TIMETABLE_PANEL_GAP)
        drawing.add(
            String(
                panel_x, chart_height + 4, day.strftime("%a %d %b"),
                fontSize=7, fontName="Helvetica-Bold", fillColor=colors.HexColor(_MUTED_COLOR),
            )
        )
        for block in blocks:
            if block.day != day:
                continue
            row = row_index[block.activity.name]
            y = chart_height - (row + 1) * _TIMETABLE_ROW_HEIGHT
            bx = panel_x + (block.start_offset_minutes - min_offset) / span_minutes * panel_width
            bw = max(block.duration_minutes / span_minutes * panel_width, 1)
            drawing.add(
                Rect(
                    bx, y + 1, bw, _TIMETABLE_ROW_HEIGHT - 2,
                    fillColor=colors.HexColor(_HEADER_COLOR), strokeColor=None,
                )
            )

    return drawing


def _render_activity_timetable_fallback(sessions: list[Session]) -> Table:
    """Used when the data doesn't span exactly 2 distinct days: a plain
    date/activity/session/start/end table instead of the Gantt-style
    graphic, sorted by date then start time - still complete, just not
    the graphical form FR-101 only permits for the 2-day case."""
    header = [
        Paragraph("Date", _styles["table_header"]),
        Paragraph("Activity", _styles["table_header"]),
        Paragraph("Session", _styles["table_header"]),
        Paragraph("Start", _styles["table_header"]),
        Paragraph("End", _styles["table_header"]),
    ]
    rows = [header]
    for s in sorted(sessions, key=lambda s: (s.start.date(), s.start)):
        rows.append([
            Paragraph(s.start.strftime("%a %d %b"), _styles["table_cell"]),
            Paragraph(s.activity.name, _styles["table_cell"]),
            Paragraph(s.label, _styles["table_cell"]),
            Paragraph(s.start.strftime("%H:%M"), _styles["table_cell_center"]),
            Paragraph(s.end.strftime("%H:%M"), _styles["table_cell_center"]),
        ])
    table = Table(rows, repeatRows=1)
    table.setStyle(_table_style())
    return table


# --- FR-102: activity session loading ---


@dataclass(frozen=True)
class SessionLoadingRow:
    session: Session
    capacity: int
    occupancy: int
    spare: int
    under_minimum: bool


def _session_loading_rows(
    timetable: Timetable, sessions: list[Session], class2_report: Class2Report
) -> list[SessionLoadingRow]:
    under_minimum_sessions = {u.session for u in class2_report.under_minimum_sessions}
    rows = [
        SessionLoadingRow(
            session=s,
            capacity=s.activity.max_occupancy,
            occupancy=len(timetable.campers_in(s)),
            spare=s.activity.max_occupancy - len(timetable.campers_in(s)),
            under_minimum=s in under_minimum_sessions,
        )
        for s in sessions
    ]
    return sorted(rows, key=lambda r: (r.session.activity.name, r.session.start))


@dataclass(frozen=True)
class SessionLoadingStats:
    mean_spare: float
    stdev_spare: float
    under_minimum_count: int


def _session_loading_stats(rows: list[SessionLoadingRow]) -> SessionLoadingStats:
    """"Ideal" session size is a session's own capacity (OQ-26) - spare
    capacity *is* the deviation-from-ideal statistic, nothing further to
    compute. Population stdev (``pstdev``, not sample ``stdev``) since
    ``rows`` is the complete set of sessions, not a sample of a larger
    population."""
    spares = [r.spare for r in rows]
    return SessionLoadingStats(
        mean_spare=statistics.mean(spares) if spares else 0.0,
        stdev_spare=statistics.pstdev(spares) if spares else 0.0,
        under_minimum_count=sum(1 for r in rows if r.under_minimum),
    )


def _render_session_loading_stats(stats: SessionLoadingStats) -> Paragraph:
    return Paragraph(
        f"Mean spare capacity: {stats.mean_spare:.1f} seats/session "
        f"(&#963; {stats.stdev_spare:.1f}). "
        f"{stats.under_minimum_count} session(s) below minimum occupancy.",
        _styles["table_cell"],
    )


def _paginate(rows: list, per_page: int) -> list[list]:
    if not rows:
        return []
    return [rows[i : i + per_page] for i in range(0, len(rows), per_page)]


def _session_loading_label(row: SessionLoadingRow) -> str:
    return f"{row.session.activity.name} {row.session.start.strftime('%a %H:%M')}"


def _render_session_loading_page(rows: list[SessionLoadingRow], width: float) -> Drawing:
    """One stacked horizontal bar per session (used vs. spare capacity),
    ``under_minimum`` sessions drawn in a distinct colour rather than only
    implied by a short bar (FR-102)."""
    chart_height = len(rows) * _CHART_ROW_HEIGHT
    chart = HorizontalBarChart()
    chart.x = _CHART_LABEL_WIDTH
    chart.y = 0
    chart.width = width - _CHART_LABEL_WIDTH
    chart.height = chart_height
    chart.data = [tuple(r.occupancy for r in rows), tuple(r.spare for r in rows)]
    chart.categoryAxis.categoryNames = [_session_loading_label(r) for r in rows]
    chart.categoryAxis.style = "stacked"
    chart.categoryAxis.labels.fontSize = 6
    chart.valueAxis.labels.fontSize = 6
    chart.bars[0].fillColor = colors.HexColor(_HEADER_COLOR)
    chart.bars[1].fillColor = colors.HexColor(_SPARE_CAPACITY_COLOR)
    for i, row in enumerate(rows):
        if row.under_minimum:
            chart.bars[(0, i)].fillColor = colors.HexColor(_UNDER_MINIMUM_COLOR)

    drawing = Drawing(width, chart_height)
    drawing.add(chart)
    return drawing


def _render_session_loading_charts(
    rows: list[SessionLoadingRow], width: float, per_page: int = _SESSION_CHART_ROWS_PER_PAGE
) -> list[Drawing]:
    return [_render_session_loading_page(page, width) for page in _paginate(rows, per_page)]
