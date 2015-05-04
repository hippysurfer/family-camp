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


from deep import (
    get_source_data,
    print_individual,
    individual_from_list,
    Individual)

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    (acts, sessions, campers) = get_source_data(use_cache=True)

    csv_file = args['FILE']

    with open(csv_file) as csvfile:
        individual = individual_from_list(
            list(csv.reader(csvfile, delimiter=',')),
            campers, acts, sessions)

    print(print_individual(Individual(individual, campers,
                                      sessions), campers))
