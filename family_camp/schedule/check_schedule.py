#!/usr/bin/env python
# coding: utf-8

import csv
import logging

from .deep import (
    get_source_data,
    print_individual,
    individual_from_list,
    Individual)

log = logging.getLogger(__name__)


def run(timetable):

    (acts, sessions, campers, data_cache) = get_source_data(use_cache=True)

    with open(timetable) as timetable:
        individual = individual_from_list(
            list(csv.reader(timetable, delimiter=',')),
            campers, acts, sessions)

    print(print_individual(Individual(individual, campers,
                                      sessions), campers))
