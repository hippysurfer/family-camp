import os
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from .utils import get_overlapping_sessions

DATEFORMAT = "%a %H:%M"


def extract_schedule_data(individual, campers):
    """Extracts loops from schedule. Returns unified structured entities."""
    data = {
        "status": {
            "fitness": individual.fitness(debug=True),
            "goodness": individual.goodness(campers, debug=True)
        },
        "inactive_adults": [],   
        "inactive_groups": [],   
        "by_family": [],         
        "by_activity": {}        
    }

    start_days = sorted(set([_.start.date() for _ in individual.sessions]))
    
    @dataclass
    class _Session:
        start: datetime
        end: datetime

    for day in start_days:
        earliest_start = min([_.start for _ in individual.sessions if _.start.date() == day])
        latest_end = max([_.end for _ in individual.sessions if _.end.date() == day])

        hours = []
        hour = earliest_start
        while hour < latest_end:
            over_lapping_sessions = get_overlapping_sessions(
                _Session(hour, hour + timedelta(minutes=59)), individual.sessions
            )
            if len(over_lapping_sessions):
                hours.append(hour)
            hour += timedelta(hours=1)

        for hour in hours:
            time_str = hour.strftime(DATEFORMAT)
            active_sessions = get_overlapping_sessions(
                _Session(hour, hour + timedelta(minutes=59)), individual.sessions
            )
            
            active_campers = []
            for active_session in active_sessions:
                active_campers += individual.session_inst_map[active_session].campers

            active_groups = sorted(set([_.group for _ in active_campers]))
            inactive_c = [_ for _ in campers if _ not in active_campers]
            
            inactive_adults = sorted([_.name for _ in inactive_c if _.age_group == "Adult (over 18 years)"])
            if inactive_adults:
                data["inactive_adults"].append({"time": time_str, "names": inactive_adults})

            inactive_groups = sorted(set([_.group for _ in campers if _.group not in active_groups]))
            inactive_groups = [_ for _ in inactive_groups if _ != ""]
            if inactive_groups:
                data["inactive_groups"].append({"time": time_str, "groups": inactive_groups})

    for f, s in sorted(individual.export_by_family().items(),
                        key=lambda _: '' if _[0] == '' else _[0].split('/')[1].lower()):
        for i, f_campers in sorted(s.items(), key=lambda s: s[0].session.start):
            for c in f_campers:
                data["by_family"].append({
                    "family": f,
                    "time": i.session.start.strftime(DATEFORMAT),
                    "label": i.session.label,
                    "camper": c.name
                })

    for a, s in sorted(individual.export_by_activity().items(), key=lambda _: _):
        data["by_activity"][a] = []
        limit = s[0].session.activity.limit if (s and hasattr(s[0].session.activity, 'limit')) else "N/A"
        for i in s:
            data["by_activity"][a].append({
                "time": i.session.start.strftime(DATEFORMAT),
                "campers": [c.name for c in i.campers],
                "limit": limit
            })

    return data

def render_to_text(data):
    """Renders data back into original plain text layout."""
    status_out = [
        f"Fitness = {data['status']['fitness']}",
        f"Goodness = {data['status']['goodness']}\n\n"
    ]

    inactive_groups_out = []
    for item in data["inactive_groups"]:
        inactive_groups_out.append(f"{item['time']:<20}")
        for indx in range(0, len(item['groups']), 2):
            g1 = item['groups'][indx]
            g2 = item['groups'][indx+1] if len(item['groups']) > indx+1 else ""
            inactive_groups_out.append(f"          {g1:<20} {g2:<20}")
        inactive_groups_out.append("\n")

    campers_out = []
    prev_f, prev_t, prev_l, prev_c = None, None, None, None
    for entry in data["by_family"]:
        f_val = entry['family'] if entry['family'] != prev_f else ''
        t_val = entry['time'] if entry['time'] != prev_t else ''
        l_val = entry['label'] if entry['label'] != prev_l else ''
        c_val = entry['camper'] if entry['camper'] != prev_c else ''
        campers_out.append(f"{f_val:<20} {t_val:<20} {l_val:<20} {c_val:<20}")
        prev_f, prev_t, prev_l, prev_c = entry['family'], entry['time'], entry['label'], entry['camper']
    campers_out.append('\n')

    activities_out = []
    limits_summary = []
    for act, sessions in data["by_activity"].items():
        act_total = 0
        prev_act = None
        for sess in sessions:
            prev_t = None
            for camper in sess['campers']:
                a_val = act if act != prev_act else ''
                t_val = sess['time'] if sess['time'] != prev_t else ''
                activities_out.append(f"{a_val:<20} {t_val:<20} {camper:<20}")
                prev_act, prev_t = act, sess['time']
            
            activities_out.append(f"{'':<20} {'Total in session':<20}: {len(sess['campers'])}\n")
            act_total += len(sess['campers'])
        
        activities_out.append(f"Total in activity:{act_total}\n\n")
        
        limit_val = sessions[0]['limit'] if sessions else "N/A"
        limits_summary.append(f"\n{act}: Session Limit: {limit_val}")
        for sess in sessions:
            limits_summary.append(f"{sess['time']:>20}, {len(sess['campers'])}")

    combined_activities = activities_out + ["##################################################################\n"] + limits_summary

    inactive_adults_out = []
    for item in data["inactive_adults"]:
        inactive_adults_out.append(f"{item['time']:<20}")
        for indx in range(0, len(item['names']), 4):
            n1 = item['names'][indx]
            n2 = item['names'][indx+1] if len(item['names']) > indx+1 else ""
            n3 = item['names'][indx+2] if len(item['names']) > indx+2 else ""
            n4 = item['names'][indx+3] if len(item['names']) > indx+3 else ""
            inactive_adults_out.append(f"          {n1:<20} {n2:<20} {n3:<20} {n4:<20}")
        inactive_adults_out.append("\n")

    return ["\n".join(_) for _ in [status_out, inactive_groups_out, campers_out, combined_activities, inactive_adults_out]]

from reportlab.platypus import BaseDocTemplate, Paragraph, Spacer, Frame, PageTemplate
# Keep your other imports (letter, getSampleStyleSheet, ParagraphStyle, colors) the same

from reportlab.platypus import BaseDocTemplate, Paragraph, Spacer, Frame, PageTemplate
from reportlab.pdfgen import canvas
# Keep your other imports (letter, getSampleStyleSheet, ParagraphStyle, colors) the same

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically calculate and print total page counts."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # 1. Header String & Top Accent Rule (0.5 in / 36 pt margin offsets)
        self.drawString(36, 762, "CAMP PROGRAMME SCHEDULE")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(36, 755, 576, 755) # Top decorative bar line
        
        # 2. Footer Running Page Number
        self.setFont("Helvetica", 8)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(576, 24, page_text)
        self.restoreState()


import os
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from reportlab.lib.pagesizes import letter, A3, landscape
from reportlab.platypus import (
    BaseDocTemplate, Paragraph, Spacer, Frame, 
    PageTemplate, Table, TableStyle, PageBreak
)
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DATEFORMAT = "%a %H:%M"

# --- PART 1: COMPACT VISUAL ANCHOR CANVAS ---

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that handles page counts and draws clean structural lines."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            
            doc = getattr(self, '_doctemplate', None)
            page_w = doc.pagesize[0] if doc else 612
            page_h = doc.pagesize[1] if doc else 792
            cols_count = getattr(doc, 'cols_count', 2)
            
            # 1. Top Decorative Boundary Bar
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.5)
            self.line(36, page_h - 37, page_w - 36, page_h - 37) 
            
            # 2. Dynamic Columns Dividing Lines Placement
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            available_width = page_w - 72  
            gap = 18
            
            col_width = (available_width - (gap * (cols_count - 1))) / cols_count
            for i in range(1, cols_count):
                divider_x = 36 + (i * col_width) + ((i - 1) * gap) + (gap / 2.0)
                self.line(divider_x, 36, divider_x, page_h - 54)
            
            # 3. Dynamic Footer Running Page Number
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#718096"))
            self.drawRightString(page_w - 36, 24, f"Page {self._pageNumber} of {num_pages}")
            
            super().showPage()
        super().save()


# --- PART 2: THE COMPILER ENGINE LAYOUT CONTROLLER ---

def render_to_pdf(data, output_filename, paper_size="a3", orientation="landscape"):
    """Generates an optimized multi-column running layout configuration profile."""
    margin = 36 
    
    if paper_size.lower() == "a3":
        base_size = A3
    else:
        base_size = letter
        
    if orientation.lower() == "landscape":
        pagesize = landscape(base_size)
    else:
        pagesize = base_size
        
    doc = BaseDocTemplate(
        output_filename, 
        pagesize=pagesize, 
        leftMargin=margin, rightMargin=margin, 
        topMargin=54, bottomMargin=margin
    )
    
    if paper_size.lower() == "a3" and orientation.lower() == "landscape":
        cols_count = 4
    else:
        cols_count = 2
        
    doc.cols_count = cols_count  
    
    gap = 18
    available_width = doc.width  
    col_width = (available_width - (gap * (cols_count - 1))) / cols_count
    
    frames = []
    for i in range(cols_count):
        frame_x = doc.leftMargin + (i * (col_width + gap))
        frames.append(
            Frame(frame_x, doc.bottomMargin, col_width, doc.height, id=f'col{i}', leftPadding=0, rightPadding=0)
        )
    
    two_col_template = PageTemplate(id='multi_columns', frames=frames)
    doc.addPageTemplates([two_col_template])
    
    styles = getSampleStyleSheet()
    
    running_header_style = ParagraphStyle('RunHead', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor("#718096"), spaceBefore=-20, spaceAfter=15, keepWithNext=True)
    title_style = ParagraphStyle('ActTitle', fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.HexColor("#1A365D"), spaceBefore=10, spaceAfter=2, keepWithNext=True)
    time_style = ParagraphStyle('SessTime', fontName='Helvetica-BoldOblique', fontSize=9, leading=11, textColor=colors.HexColor("#4A5568"), spaceAfter=3, keepWithNext=True)
    name_style = ParagraphStyle('CamperName', fontName='Helvetica', fontSize=8.5, leading=10, textColor=colors.HexColor("#2D3748"), leftIndent=10)
    meta_style = ParagraphStyle('MetaText', fontName='Helvetica-Oblique', fontSize=8, leading=10, textColor=colors.HexColor("#718096"), leftIndent=10, spaceAfter=6)
    section_heading = ParagraphStyle('SectHead', fontName='Helvetica-Bold', fontSize=13, leading=16, textColor=colors.HexColor("#2C5282"), spaceBefore=14, spaceAfter=6, keepWithNext=True)
    
    table_header_style = ParagraphStyle('TableHeader', fontName='Helvetica-Bold', fontSize=8, leading=9, textColor=colors.HexColor("#1A365D"))
    table_cell_style = ParagraphStyle('TableCell', fontName='Helvetica', fontSize=7.5, leading=9, textColor=colors.HexColor("#2D3748"))
    family_cell_style = ParagraphStyle('FamilyCell', fontName='Helvetica-Bold', fontSize=7.5, leading=9, textColor=colors.HexColor("#1A365D"))

    story = []
    
    # SECTION 1: Activity Session Groupings
    is_first_activity = True
    for act, sessions in data["by_activity"].items():
        if not is_first_activity:
            story.append(PageBreak())
        else:
            is_first_activity = False
            
        story.append(Paragraph(f"ACTIVITY: {act.upper()}", running_header_style))
        story.append(Paragraph(act.upper(), title_style))
        for sess in sessions:
            story.append(Paragraph(f"🕒 {sess['time']} <font color='#718096' size='8'>(Limit: {sess['limit']})</font>", time_style))
            for camper in sess['campers']:
                story.append(Paragraph(camper, name_style))
            story.append(Paragraph(f"Total in Session: {len(sess['campers'])}", meta_style))

    # SECTION 2: Individual Camper / Family Schedules
    if data.get("by_family"):
        story.append(PageBreak())  
        story.append(Paragraph("SCHEDULES: INDIVIDUAL CAMPERS", running_header_style))
        story.append(Paragraph("Individual Camper Schedules", section_heading))
        
        table_data = [[
            Paragraph("<b>Family</b>", table_header_style),
            Paragraph("<b>Time</b>", table_header_style),
            Paragraph("<b>Activity</b>", table_header_style),
            Paragraph("<b>Camper</b>", table_header_style)
        ]]
        
        data_row_indices = []
        line_row_indices = []
        
        prev_f, prev_t, prev_l, prev_c = None, None, None, None
        for entry in data["by_family"]:
            if prev_f is not None and entry['family'] != prev_f:
                table_data.append([Paragraph("", table_cell_style)] * 4)
                line_row_indices.append(len(table_data) - 1) 
                table_data.append([Paragraph("", table_cell_style)] * 4)
                
            f_val = entry['family'] if entry['family'] != prev_f else ''
            t_val = entry['time'] if entry['time'] != prev_t else ''
            l_val = entry['label'] if entry['label'] != prev_l else ''
            c_val = entry['camper'] if entry['camper'] != prev_c else ''
            
            table_data.append([
                Paragraph(f"<b>{f_val}</b>" if f_val else "", family_cell_style),
                Paragraph(t_val, table_cell_style),
                Paragraph(l_val, table_cell_style),
                Paragraph(c_val, table_cell_style)
            ])
            
            data_row_indices.append(len(table_data) - 1)
            prev_f, prev_t, prev_l, prev_c = entry['family'], entry['time'], entry['label'], entry['camper']
        
        t_styles = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor("#CBD5E0")),
        ]
        
        for line_row in line_row_indices:
            t_styles.append(('LINEBELOW', (0, line_row), (-1, line_row), 0.5, colors.HexColor("#E2E8F0")))
        
        for step, row_idx in enumerate(data_row_indices):
            if step % 2 == 1:
                t_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#F7FAFC")))
        
        c_w = col_width / 4.0
        family_table = Table(table_data, colWidths=[c_w, c_w, c_w, c_w])
        family_table.setStyle(TableStyle(t_styles))
        story.append(family_table)
        story.append(Spacer(1, 10))

    # SECTION 3: Inactive Adults
    if data.get("inactive_adults"):
        story.append(PageBreak())  
        story.append(Paragraph("LOGISTICS: INACTIVE ADULTS", running_header_style))
        story.append(Paragraph("Inactive Adults (By Hour)", section_heading))
        for item in data["inactive_adults"]:
            story.append(Paragraph(f"🕒 {item['time']}", time_style))
            names_str = ", ".join(item['names'])
            story.append(Paragraph(names_str, name_style))
            story.append(Spacer(1, 4))

    # SECTION 4: Inactive Groups
    if data.get("inactive_groups"):
        story.append(PageBreak())  
        story.append(Paragraph("LOGISTICS: INACTIVE GROUPS", running_header_style))
        story.append(Paragraph("Inactive Groups (By Hour)", section_heading))
        for item in data["inactive_groups"]:
            story.append(Paragraph(f"🕒 {item['time']}", time_style))
            names_str = ", ".join(item['groups'])
            story.append(Paragraph(names_str, name_style))
            story.append(Spacer(1, 4))

    doc.build(story, canvasmaker=NumberedCanvas)




# --- PART 3: REFACTORED WRAPPER SYSTEM ---
def print_individual(individual, campers, output_type="text", pdf_filename="schedule.pdf"):
    """Unified system router module interface."""
    schedule_data = extract_schedule_data(individual, campers)
    if output_type.lower() == "pdf":
        render_to_pdf(schedule_data, pdf_filename)
        return f"PDF output successfully written to {pdf_filename}"
    else:
        return render_to_text(schedule_data)
