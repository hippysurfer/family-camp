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
import csv
import logging

from docopt import docopt
import random
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    Spacer)

log = logging.getLogger(__name__)

from deep import get_source_data, timetable_from_list

import gen_info_pack

W, H = A4
TITLE_FONT = "Helvetica-Bold"
TITLE_SIZE = 16
TH_LOGO = "7thlogo.png"

TITLE = "7th Lichfield Scout Group"
SUBTITLE = "2019 Family Camp"


def pageTemplate(family, bingo_name):
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

        #canvas.setFont(TITLE_FONT, TITLE_SIZE - 2)
        #canvas.setFillColor(colors.purple)
        #canvas.drawRightString(W - 2 * cm, H - 1.3 * cm, "Bingo Name")
        #canvas.drawRightString(W - 2 * cm, H - 2 * cm, bingo_name)

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
        # gen_info_pack.para_small(
        #     "Please note that Saturday Lunch and Sunday Lunch "
        #     "have been included on your timetable to ensure "
        #     "that families with a packed schedule get a slot "
        #     "for lunch. You are, of course, free to take your "
        #     "meals whenever you choose."),
        #Spacer(0*cm, 0.4*cm),
        # gen_info_pack.para_small(
        #     "Please try to arrive at the Saturday BBQ close "
        #     "to your allotted time. By staggering the arrival "
        #     "times, we are trying hard to limit the length of "
        #     "time that you need to queue."),
        Spacer(0*cm, 0.4*cm),
        gen_info_pack.para_small(
            "There are a very few occasions where we have "
            "had to split a group so that members of the  "
            "group are doing different activities at the same "
            "time. This has been necessary to give as many "
            "people as possible the activities that they have "
            "requested.")
    ]))

    return elements


def gen_pdf(filename, family, sat_data, sun_data, bingo_name):
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            topMargin=3.25 * cm, bottomMargin=0)

    info_pack = gen_info_pack.gen_story(doc)
    e = gen_story(doc, family, sat_data, sun_data)

    # write the document to disk
    doc.build(info_pack+e, onFirstPage=pageTemplate(family, bingo_name),
              onLaterPages=pageTemplate(family, bingo_name))


def get_schedule(sessions):
    sat_sessions = sorted(
        [_ for _ in sessions.items() if _[0].session.start.weekday() == 5],
        key=lambda x: x[0].session.start)

    sun_sessions = sorted(
        [_ for _ in sessions.items() if _[0].session.start.weekday() == 6],
        key=lambda x: x[0].session.start)

    sat_table = [[session.session.start.strftime("%H:%M"),
                  (session.session.label if not session.session.label.endswith((' A', ' B', ' C', ' D'))
                   else session.session.label[:-2]),
                  "\n".join([c.name for c in campers])]
                 for session, campers in sat_sessions]

    sun_table = [[session.session.start.strftime("%H:%M"),
                  (session.session.label if not session.session.label.endswith((' A', ' B', ' C', ' D'))
                   else session.session.label[:-2]),
                  "\n".join([c.name for c in campers])]
                 for session, campers in sun_sessions]

    return (sat_table, sun_table)

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    (acts, sessions, campers, data_cache) = get_source_data(use_cache=True)

    csv_file = args['FILE']
    out_dir = args['DIR']

    with open(csv_file) as csvfile:
        individual = timetable_from_list(
            list(csv.reader(csvfile, delimiter=',')),
            campers, acts, sessions)

    BINGO_NAMES = [('Flag Flyer', 5),
                   ('Cliff Hangers', 5),
                   ('River Ripplers', 5),
                   ('Trail Blazers', 5),
                   ("T'rific Troglodytes", 5),
                   ('Naughty Navigators', 5),
                   ('Star gazers', 5),
                   ('Firestarters', 5),
                   ('Rope Wranglers', 5),
                   ('Knot Knitters', 5),
                   ('Lumberjacks', 4),
                   ('Wood Choppers', 4),
                   ('Walking Wanderers', 4),
                   ('Fletch Fettlers', 4),
                   ('Woggle Worriers', 4),
                   ('Peg Pullers', 4),
                   ('Wood Whittlers', 4),
                   ('Clever Climbers', 4),
                   ('Necker Knockers', 4),
                   ('Bewildered Bikers', 4),
                   ('Crazy Canoeists', 4)]

    num_fams = len(individual.export_by_family())
    name_list = []
    for name, repeat in BINGO_NAMES:
        name_list.extend([name,] * repeat)

    # for name in BINGO_NAMES:
    #     name_list.extend([name,] * (num_fams//len(BINGO_NAMES)))
    #
    # if len(name_list) < num_fams:
    #     name_list.extend(random.sample(BINGO_NAMES,num_fams-len(name_list)))

    # total = 0
    # for name in set(name_list):
    #     print("{} = {}".format(name, name_list.count(name)))
    #     total += name_list.count(name)
    # print("total = {}".format(total))

    for name, (f, s) in zip(name_list, individual.export_by_family().items()):

        sat_sessions, sun_sessions = get_schedule(s)
        gen_pdf("{}/{}_timetable.pdf".format(out_dir, f.replace('/', '_')),
                f, sat_sessions, sun_sessions, name)

