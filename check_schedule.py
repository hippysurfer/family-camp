#!/usr/bin/env python
# coding: utf-8
"""Check Family Camp Timetable.

Usage:
  check_schedule.py [-d|--debug] FILE
  check_schedule.py (-h | --help)
  check_schedule.py --version

Arguments:
  FILE    csv file.

Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

from datetime import datetime
from docopt import docopt
import csv
import logging
log = logging.getLogger(__name__)


from deep import Individual, Activity, Session, Camper, SessionInst
from deep import get_source_data, print_individual

def timetable_from_list(schedule, campers, activities, sessions):
    """Convert list of the form:

       (group, camper, activity, start datetime)

     Timetable object."""

    session_insts = {}

    for (group, camper, activity, start_datetime) in schedule:
        c = [_ for _ in campers if _.group == group and _.name == camper][0]
        a = activities[activity]
        s = [_ for _ in sessions if _.activity == a and
             _.start == datetime.strptime(start_datetime, "%Y-%m-%d %H:%M:%S")][0]
        if s in session_insts:
            session_insts[s].campers.append(c)
        else:
            session_insts[s] = SessionInst(s, [c,], campers)

    return Individual(None, campers, sessions, session_insts.values())

if __name__ == '__main__':
    
    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    (acts, sessions, campers) = get_source_data(use_cache=True)

    csv_file = args['FILE']

    with open(csv_file) as csvfile:
        individual = timetable_from_list(list(csv.reader(csvfile, delimiter=',')),
                                         campers, acts, sessions)

    print(print_individual(individual, campers))

