"""PDF report generation - native Python via reportlab (a pure-Python
library; no external binaries or subprocesses involved), not part of the
original scope (REQUIREMENTS.md §1.2 explicitly excluded printing), added
at the user's explicit request after reviewing the old system's PDF
output (see fetched_data/old_reports/ for the originals this design
reacts against).

Two separate documents, matching how they're actually used on the day:
``render_activities_pdf`` for staff running each session, ``render_campers_pdf``
for a family to find their own itinerary at a glance. Both deliberately
depart from the old system's layout (`family_camp/schedule/schedule_printer.py`)
in two ways that drove its page count up (41 pages at A4 for one camp):

1. The old layout gave every camper attending a session their own
   Paragraph line. Here, a session's attendees are one wrapped Paragraph
   in one table cell/row - a session of 19 people takes a handful of
   wrapped lines, not 19.
2. The old layout forced a page break before every single activity/family,
   regardless of how much room was left on the current page. Here,
   nothing is force-broken: entries flow through an adaptive multi-column
   frame (the number of columns is computed from the page's actual
   width, not hardcoded to 2 or 4 like the old system), so short entries
   pack in next to each other instead of each claiming a fresh page.

The campers document also uses a different shape entirely: one small
attendance-matrix table per family (rows = distinct sessions anyone in
the family attends, columns = the family's members, an "X" marks who's
where) instead of one row per (member, session) pair - a family that's
mostly together produces mostly-full rows in a handful of lines, rather
than repeating the same time/activity text once per attending member.

A third document, ``render_available_adults_pdf``, answers a different
question: not "who's doing what", but "who's free right now" - one row
per active time bucket listing which adult campers have nothing
scheduled (reusing ``validation.idle.find_idle_slots``'s existing
computation, filtered to ``idle_adults`` - children aren't volunteer
candidates), for an organiser trying to find a spare pair of hands.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Table, TableStyle

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.idle import IdleReport

__all__ = ["PageSpec", "render_activities_pdf", "render_campers_pdf", "render_available_adults_pdf"]

_PAGE_SIZES = {"a4": A4, "a3": A3}
_TIME_FORMAT = "%a %H:%M"

_MARGIN = 14 * mm
_TOP_MARGIN = 20 * mm
_COLUMN_GAP = 8 * mm
_TARGET_COLUMN_WIDTH = 62 * mm  # narrow enough to fit several per page, wide enough to stay readable

_HEADER_COLOR = "#2C5282"
_TITLE_COLOR = "#1A365D"
_MUTED_COLOR = "#718096"
_GRID_COLOR = "#E2E8F0"
_STRIPE_COLOR = "#F7FAFC"


@dataclass(frozen=True)
class PageSpec:
    """Paper size (``"a4"``/``"a3"``) and orientation (``"portrait"``/
    ``"landscape"``) for a generated PDF."""

    paper_size: str = "a4"
    orientation: str = "portrait"

    def __post_init__(self) -> None:
        if self.paper_size not in _PAGE_SIZES:
            raise ValueError(f"Unknown paper_size {self.paper_size!r}, expected one of {sorted(_PAGE_SIZES)}")
        if self.orientation not in ("portrait", "landscape"):
            raise ValueError(f"Unknown orientation {self.orientation!r}, expected 'portrait' or 'landscape'")

    @property
    def pagesize(self) -> tuple[float, float]:
        base = _PAGE_SIZES[self.paper_size]
        return landscape(base) if self.orientation == "landscape" else base


_styles = {
    "section_title": ParagraphStyle(
        "SectionTitle", fontName="Helvetica-Bold", fontSize=10, leading=12,
        textColor=colors.HexColor(_TITLE_COLOR), spaceBefore=8, spaceAfter=3, keepWithNext=True,
    ),
    "table_header": ParagraphStyle(
        "TableHeader", fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=colors.white
    ),
    "table_cell": ParagraphStyle(
        "TableCell", fontName="Helvetica", fontSize=7, leading=8.5, textColor=colors.HexColor("#2D3748")
    ),
    "table_cell_center": ParagraphStyle(
        "TableCellCenter", fontName="Helvetica", fontSize=7, leading=8.5,
        textColor=colors.HexColor("#2D3748"), alignment=TA_CENTER,
    ),
    "note": ParagraphStyle(
        "Note", fontName="Helvetica-Oblique", fontSize=7.5, leading=9,
        textColor=colors.HexColor(_MUTED_COLOR), spaceAfter=6,
    ),
}


class _NumberedCanvas(canvas.Canvas):
    """Draws a running title/rule and "Page N of TOTAL" footer - a single,
    non-duplicated version of the old system's ``NumberedCanvas`` (which
    had two drifted copies pasted into the same file)."""

    def __init__(self, *args, title: str, pagesize: tuple[float, float], **kwargs):
        super().__init__(*args, **kwargs)
        self._title = title
        self._doc_pagesize = pagesize
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_decorations(total_pages)
            super().showPage()
        super().save()

    def _draw_decorations(self, total_pages: int) -> None:
        width, height = self._doc_pagesize
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor(_MUTED_COLOR))
        self.drawString(_MARGIN, height - 12 * mm, self._title)
        self.setStrokeColor(colors.HexColor(_GRID_COLOR))
        self.setLineWidth(0.5)
        self.line(_MARGIN, height - 14 * mm, width - _MARGIN, height - 14 * mm)
        self.setFont("Helvetica", 8)
        self.drawRightString(width - _MARGIN, 10 * mm, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def _build_doc(output_path: Path, page_spec: PageSpec) -> tuple[BaseDocTemplate, float]:
    """A document whose page template has as many equal-width columns as
    comfortably fit the page - unlike the old system's hardcoded 2/4
    column count, this adapts to whatever paper size/orientation was
    asked for. Returns the doc and the resulting column width (needed by
    callers to size their tables)."""

    pagesize = page_spec.pagesize
    doc = BaseDocTemplate(
        str(output_path), pagesize=pagesize,
        leftMargin=_MARGIN, rightMargin=_MARGIN, topMargin=_TOP_MARGIN, bottomMargin=_MARGIN,
    )
    available_width = pagesize[0] - 2 * _MARGIN
    num_columns = max(1, int((available_width + _COLUMN_GAP) // (_TARGET_COLUMN_WIDTH + _COLUMN_GAP)))
    column_width = (available_width - (num_columns - 1) * _COLUMN_GAP) / num_columns
    frame_height = pagesize[1] - _MARGIN - _TOP_MARGIN

    frames = [
        Frame(
            _MARGIN + i * (column_width + _COLUMN_GAP), _MARGIN, column_width, frame_height,
            id=f"col{i}", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        for i in range(num_columns)
    ]
    doc.addPageTemplates([PageTemplate(id="columns", frames=frames)])
    return doc, column_width


_MIN_MEMBER_COLUMN_WIDTH = 15 * mm


def _activity_label(session: Session) -> str:
    """The session's label, unless it's identical to its own activity's
    name (common in this camp's real data, e.g. a single-label activity
    whose only label repeats the activity name) - shown alongside the
    activity name would just repeat it."""
    if session.label.strip().lower() == session.activity.name.strip().lower():
        return ""
    return f" ({escape(session.label)})"


def _short_name(camper: Camper, family_surname: str | None) -> str:
    """Drops a trailing surname that matches the family's own (inferred
    from ``family_id``, e.g. ``"012/Winwood"`` -> ``"Winwood"``) - it's
    already in the family's heading, so repeating it in every matrix
    column header just narrows the room left for the first name. Left
    alone for a member whose surname differs (e.g. a step-family)."""
    if not family_surname:
        return camper.name
    prefix, _, surname = camper.name.rpartition(" ")
    if prefix and surname.lower() == family_surname.lower():
        return prefix
    return camper.name


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_HEADER_COLOR)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(_HEADER_COLOR)),
        ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor(_GRID_COLOR)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_STRIPE_COLOR)]),
    ])


def render_activities_pdf(
    timetable: Timetable, sessions: list[Session], output_path: Path, page_spec: PageSpec = PageSpec()
) -> None:
    """One table per activity: each row is a session (not a camper), with
    its attendees wrapped into a single cell - see the module docstring
    for why this is dramatically more compact than the old system."""

    doc, column_width = _build_doc(output_path, page_spec)
    time_w = column_width * 0.30
    occ_w = column_width * 0.14
    names_w = column_width - time_w - occ_w

    by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        by_activity[s.activity].append(s)

    story = []
    for activity in sorted(by_activity, key=lambda a: a.name):
        activity_sessions = sorted(by_activity[activity], key=lambda s: s.start)
        story.append(Paragraph(
            f"{escape(activity.name)} "
            f"<font color='{_MUTED_COLOR}' size='7'>(cap {activity.min_occupancy}-{activity.max_occupancy})</font>",
            _styles["section_title"],
        ))

        rows = [[
            Paragraph("Session", _styles["table_header"]),
            Paragraph("#", _styles["table_header"]),
            Paragraph("Attendees", _styles["table_header"]),
        ]]
        for session in activity_sessions:
            occupants = sorted(timetable.campers_in(session), key=lambda c: c.name)
            names = ", ".join(escape(c.name) for c in occupants) if occupants else "—"
            rows.append([
                Paragraph(
                    f"{escape(session.start.strftime(_TIME_FORMAT))}{_activity_label(session)}",
                    _styles["table_cell"],
                ),
                Paragraph(f"{len(occupants)}/{activity.max_occupancy}", _styles["table_cell_center"]),
                Paragraph(names, _styles["table_cell"]),
            ])

        table = Table(rows, colWidths=[time_w, occ_w, names_w], repeatRows=1)
        table.setStyle(_table_style())
        story.append(table)

    doc.build(story, canvasmaker=partial(_NumberedCanvas, title="ACTIVITY SCHEDULE", pagesize=doc.pagesize))


def _session_row_label(session: Session) -> str:
    return f"{escape(session.start.strftime(_TIME_FORMAT))}<br/>{escape(session.activity.name)}{_activity_label(session)}"


def render_campers_pdf(
    timetable: Timetable, campers: list[Camper], output_path: Path, page_spec: PageSpec = PageSpec()
) -> None:
    """One attendance-matrix table per family: rows are the distinct
    sessions anyone in the family attends (in time order), columns are
    the family's members, an "X" marks who's in which session - see the
    module docstring for why this is more compact than one row per
    (member, session) pair. Each family's table is kept together
    (``KeepTogether``) so it never splits across a column/page boundary -
    unlike the activities table, a family's whole block is small enough
    that this is safe rather than wasteful.

    A family with enough members that its matrix columns would drop below
    ``_MIN_MEMBER_COLUMN_WIDTH`` (long names would then wrap mid-word to
    fit) falls back to a plain [session, attendees] list instead - still
    one row per session, not per member, so it's no less compact, just
    less immediately "at a glance" than the matrix."""

    doc, column_width = _build_doc(output_path, page_spec)

    campers_by_family: dict[str, list[Camper]] = defaultdict(list)
    for c in campers:
        campers_by_family[c.family_id].append(c)

    story = []
    for family_id in sorted(campers_by_family):
        members = sorted(campers_by_family[family_id], key=lambda c: c.name)
        block = [Paragraph(escape(family_id), _styles["section_title"])]
        family_surname = family_id.split("/", 1)[1] if "/" in family_id else None

        sessions_attended = sorted(
            {s for m in members for s in timetable.sessions_of(m)}, key=lambda s: (s.start, s.label)
        )
        if not sessions_attended:
            block.append(Paragraph("(no assigned sessions)", _styles["note"]))
            story.append(KeepTogether(block))
            continue

        time_w = column_width * 0.34
        member_w = (column_width - time_w) / len(members)

        if member_w >= _MIN_MEMBER_COLUMN_WIDTH:
            header = [Paragraph("Session", _styles["table_header"])] + [
                Paragraph(escape(_short_name(m, family_surname)), _styles["table_header"]) for m in members
            ]
            rows = [header]
            for session in sessions_attended:
                attendees = timetable.campers_in(session)
                row = [Paragraph(_session_row_label(session), _styles["table_cell"])]
                for m in members:
                    row.append(Paragraph("X" if m in attendees else "", _styles["table_cell_center"]))
                rows.append(row)
            col_widths = [time_w] + [member_w] * len(members)
        else:
            rows = [[
                Paragraph("Session", _styles["table_header"]),
                Paragraph("Attendees", _styles["table_header"]),
            ]]
            for session in sessions_attended:
                attendees = sorted(timetable.campers_in(session) & set(members), key=lambda c: c.name)
                names = ", ".join(escape(_short_name(m, family_surname)) for m in attendees)
                rows.append([
                    Paragraph(_session_row_label(session), _styles["table_cell"]),
                    Paragraph(names, _styles["table_cell"]),
                ])
            col_widths = [column_width * 0.42, column_width * 0.58]

        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(_table_style())
        block.append(table)
        story.append(KeepTogether(block))

    doc.build(story, canvasmaker=partial(_NumberedCanvas, title="FAMILY ITINERARIES", pagesize=doc.pagesize))


def render_available_adults_pdf(idle_report: IdleReport, output_path: Path, page_spec: PageSpec = PageSpec()) -> None:
    """One table, one row per active time bucket, listing which adult
    campers have nothing scheduled at that time - for finding a volunteer
    who's free right now. Only adults (``IdleBucket.idle_adults`` is
    already filtered to ``is_adult`` by ``find_idle_slots`` - idle
    children aren't volunteer candidates); buckets with nobody idle at
    all are shown with an explicit "—" rather than being dropped, so a
    fully-staffed hour is still visible as "checked, nobody free" rather
    than looking like a gap in the document.

    Unlike the activities/campers documents there's only one dimension
    here, so this is a single continuous table rather than one per group
    - ``Table`` already splits itself across the multi-column frame's
    columns/pages on its own, repeating the header each time
    (``repeatRows=1``)."""

    doc, column_width = _build_doc(output_path, page_spec)
    time_w = column_width * 0.28
    count_w = column_width * 0.10
    names_w = column_width - time_w - count_w

    rows = [[
        Paragraph("Time", _styles["table_header"]),
        Paragraph("#", _styles["table_header"]),
        Paragraph("Available adults", _styles["table_header"]),
    ]]
    for bucket in idle_report.buckets:
        names = ", ".join(escape(c.name) for c in sorted(bucket.idle_adults, key=lambda c: c.name))
        time_label = f"{escape(bucket.start.strftime(_TIME_FORMAT))}&#8211;{escape(bucket.end.strftime('%H:%M'))}"
        rows.append([
            Paragraph(time_label, _styles["table_cell"]),
            Paragraph(str(len(bucket.idle_adults)), _styles["table_cell_center"]),
            Paragraph(names if names else "—", _styles["table_cell"]),
        ])

    table = Table(rows, colWidths=[time_w, count_w, names_w], repeatRows=1)
    table.setStyle(_table_style())

    doc.build([table], canvasmaker=partial(_NumberedCanvas, title="AVAILABLE ADULTS", pagesize=doc.pagesize))
