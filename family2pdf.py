#!/usr/bin/env python
# coding: utf-8
"""Create PDF for individual family's Timetable.

Usage:
  family2pdf.py [-d|--debug] FILE DIR
  family2pdf.py (-h | --help)
  family2pdf.py --version

Arguments:
  FILE    csv file.
  DIR     output directory.

Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Image,
    PageBreak,
    KeepTogether,
    Spacer)
from reportlab.lib.units import mm, cm
from docopt import docopt
import csv
import logging
log = logging.getLogger(__name__)

from deep import get_source_data, timetable_from_list

import gen_info_pack

W, H = A4
TITLE_FONT = "Helvetica-Bold"
TITLE_SIZE = 16
TH_LOGO = "7thlogo.png"

TITLE = "7th Lichfield Scout Group"
SUBTITLE = "2015 Family Camp"


def pageTemplate(family):
    def familyTemplate(canvas, doc):
        canvas.saveState()
        canvas.drawImage(TH_LOGO, 1 * cm, H - 4.5 * cm,
                         width=5 * cm, height=5 * cm, mask=None,
                         preserveAspectRatio=True)

        canvas.setFont(TITLE_FONT, TITLE_SIZE)
        canvas.drawCentredString(W / 2.0, H - 1.3 * cm, TITLE)
        canvas.setFont(TITLE_FONT, TITLE_SIZE)
        canvas.drawCentredString(W / 2.0, H - 2 * cm, SUBTITLE)
        canvas.setFont(TITLE_FONT, TITLE_SIZE - 2)
        canvas.drawCentredString(W / 2.0, H - 3 * cm, "Group: " + family)
        canvas.restoreState()

    return familyTemplate


def gen_story(doc, family, sat_data, sun_data):

    # container for the 'Flowable' objects
    ts = TableStyle([
        ('TOPPADDING', (0, 0), (-1, 0), 1 * cm),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEABOVE', (0, 1), (-1, 1), 1, colors.purple),
        ('LINEABOVE', (1, 2), (-1, -1), 1, colors.purple), ])

    elements = []

    elements.append(PageBreak())

    elements.append(gen_info_pack.title2('Family Timetable'))

    sat = Table([["Saturday", None, None]] +
                [["", ] + s[:] for s in sat_data])
    sat.setStyle(ts)
    elements.append(sat)

    sun = Table([["Sunday", None, None]] +
                [["", ] + s[:] for s in sun_data])
    sun.setStyle(ts)
    
    elements.append(KeepTogether([
        sun,
        Spacer(0*cm, 1*cm),
        gen_info_pack.para("Please note that Saturday Lunch and Sunday Lunch "
                           "have been included on your timetable to ensure "
                           "that families with a packed schedule get a slot "
                           "for lunch. You are, of course, free to take your "
                           "meals whenever you choose."),
        Spacer(0*cm, 0.5*cm),
        gen_info_pack.para("Please try to arrive at the Saturday BBQ close "
                           "to your allotted time. By staggering the arrival "
                           "times, we are trying hard to limit the length of "
                           "time that you need to queue.")
    ]))

    return elements


def gen_pdf(filename, family, sat_data, sun_data):
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            topMargin=3.25 * cm, bottomMargin=0)

    info_pack = gen_info_pack.gen_story(doc)
    e = gen_story(doc, family, sat_data, sun_data)

    # write the document to disk
    doc.build(info_pack+e, onFirstPage=pageTemplate(family),
              onLaterPages=pageTemplate(family))


def get_schedule(sessions):
    sat_sessions = sorted(
        [_ for _ in sessions.items() if _[0].session.start.weekday() == 5],
        key=lambda x: x[0].session.start)

    sun_sessions = sorted(
        [_ for _ in sessions.items() if _[0].session.start.weekday() == 6],
        key=lambda x: x[0].session.start)

    sat_table = [[session.session.start.strftime("%H:%M"),
                  session.session.label,
                  "\n".join([c.name for c in campers])]
                 for session, campers in sat_sessions]

    sun_table = [[session.session.start.strftime("%H:%M"),
                  session.session.label,
                  "\n".join([c.name for c in campers])]
                 for session, campers in sun_sessions]

    return (sat_table, sun_table)

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    (acts, sessions, campers) = get_source_data(use_cache=True)

    csv_file = args['FILE']
    out_dir = args['DIR']

    with open(csv_file) as csvfile:
        individual = timetable_from_list(
            list(csv.reader(csvfile, delimiter=',')),
            campers, acts, sessions)

    for f, s in individual.export_by_family().items():

        sat_sessions, sun_sessions = get_schedule(s)
        gen_pdf("{}/{}_timetable.pdf".format(out_dir, f.replace('/', '_')),
                f, sat_sessions, sun_sessions)
