#!/usr/bin/env python
# coding: utf-8
"""Create PDF for individual family's Timetable.

Usage:
  check_schedule.py [-d|--debug] DIR
  check_schedule.py (-h | --help)
  check_schedule.py --version

Arguments:
  DIR     output directory.

Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

import csv
import logging
from pathlib import Path
from typing import Union

from .deep import (
    get_source_data,
    print_individual,
    individual_from_list,
    Individual)

log = logging.getLogger(__name__)


def run(timetable, out_dir: Union[Path, None]):

    (acts, sessions, campers, data_cache) = get_source_data(use_cache=True)

    with open(timetable) as timetable:
        individual = individual_from_list(
            list(csv.reader(timetable, delimiter=',')),
            campers, acts, sessions)

    status_out, inactive_out, campers_out, activites_out = print_individual(
        Individual(individual, campers, sessions), campers)

    if out_dir is None:
        for section in [status_out, campers_out, activites_out, inactive_out]:
            print(section)
            print("*"*40)

    else:
        out_dir.mkdir(exist_ok=True)
        out_dir.joinpath("status.txt").write_text(status_out)
        out_dir.joinpath("inactive.txt").write_text(inactive_out)
        out_dir.joinpath("campers.txt").write_text(campers_out)
        out_dir.joinpath("activites.txt").write_text(activites_out)

