#!/usr/bin/env python
# coding: utf-8
"""Print PDF for individual family's Timetable.
"""

import csv
import logging
from pathlib import Path
from typing import Union

from .deep import individual_from_list, get_source_data, Individual
from .schedule_printer import print_individual

log = logging.getLogger(__name__)


def run(timetable="/home/rjt/Devel/Personal/Cubs/family_camp/2026_schedule.csv", out_file="out_2026.pdf"):

    (acts, sessions, campers, data_cache) = get_source_data()
    #print(sessions)

    with open(timetable) as timetable:
        individual = individual_from_list(
            list(csv.reader(timetable, delimiter=',')),
            campers, acts, sessions)

    print_individual(
        Individual(individual, campers, sessions), 
        campers, 
        "pdf", 
        pdf_filename=out_file)
    

if __name__ == "__main__":
    run()
    