# coding: utf-8
"""Generate Family Camp Timetable.


Usage:
  test_schedule_csp.py [-d|--debug] [-r|--refresh]
  test_schedule_csp.py (-h | --help)
  test_schedule_csp.py --version

Options:
  -r,--refresh   Refresh cache from Google Docs
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

import logging
from docopt import docopt
from deep import *
import constraint as con

log = logging.getLogger(__name__)


DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"

from datetime import timedelta
from datetime import datetime

acts = [Activity('Archery', timedelta(minutes=30), 2),
        Activity('BMX', timedelta(minutes=30), 3),
        Activity('Caving', timedelta(minutes=30), 10),
        Activity('Maze', timedelta(minutes=30), 10)]

Archery, BMX, Caving, Maze = acts

campers = [Camper('camper1', 'group1', [BMX, Archery], [Caving]),
           Camper('camper2', 'group1', [BMX, Archery], [Maze, Caving]),
           Camper('camper3', 'group2', [Caving, Archery], [BMX]), ]


s = [(Archery, "Archery Indoor", datetime(2014, 7, 5, 9, 0)),
     (Archery, "Archery Outdoor", datetime(2014, 7, 5, 9, 0)),
     (BMX, "BMX", datetime(2014, 7, 5, 11, 0)),
     (BMX, "BMX", datetime(2014, 7, 5, 12, 0)),
     (Caving, "Caving", datetime(2014, 7, 5, 9, 0)),
     (Caving, "Caving", datetime(2014, 7, 5, 10, 0)),
     (Maze, "Maze", datetime(2014, 7, 5, 9, 0)),
     (Maze, "Maze", datetime(2014, 7, 5, 10, 0)),
     (Maze, "Maze", datetime(2014, 7, 5, 11, 0))]

sessions = [Session(_[0], _[1], _[2]) for _ in s]

timetable = [False
             for _ in range(0, len(campers)*len(sessions))]


if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    solver = con.BacktrackingSolver()
    p = con.Problem(solver)

    cols = range(0, len(sessions) * len(campers))

    p.addVariables(cols, [False, True])

    min_count = len(cols)
    
    def check(*args):
        global min_count
        new_count = args.count(True)
        if new_count < min_count:
            print(new_count)
            min_count = min(min_count, new_count)
        return new_count == 4

    p.addConstraint(check)
    s = p.getSolution()
    print (s)
