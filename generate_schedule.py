# coding: utf-8
"""Generate Family Camp Timetable.

Example:
  stdbuf -oL -eL python -m scoop -n 8 generate_schedule.py outdir

Usage:
  generate_schedule.py [-d|--debug] -r|--refresh
  generate_schedule.py [-d|--debug] <outdir>
  generate_schedule.py [-d|--debug] <timetable> <outdir>
  generate_schedule.py (-h | --help)
  generate_schedule.py --version

Arguments:

  outdir         Directory to hold results.
  timetable      A csv of an existing timetable.

Options:

  -r,--refresh   Refresh cache from Google Docs
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

import sys
import os
import os.path
import csv
import threading
from functools import partial
import logging
from docopt import docopt
from deap import base
from deap import creator
from deap import tools
import numpy
from deap import algorithms
from deap.tools import Statistics

from deep import *

log = logging.getLogger(__name__)


DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"

from scoop import futures

(acts, sessions, campers) = get_source_data(use_cache=True)

toolbox = base.Toolbox()

creator.create("FitnessMin", base.Fitness, weights=(5.0, -2.0, -1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)

toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=2000)
toolbox.register("mate", partial(mate, campers=campers,
                                 sessions=sessions))
toolbox.register("mutate", partial(mutate, campers=campers,
                                   sessions=sessions, toolbox=toolbox))
toolbox.register("select", tools.selTournament, tournsize=20)
toolbox.register("evaluate", partial(evaluate, campers=campers,
                                     sessions=sessions))
toolbox.register("map", futures.map)

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    refresh = args['--refresh']

    if refresh:
        log.info('Fetching fresh data.')
        get_source_data(use_cache=False)
        log.info('Done. restart without the --refresh flag.')
        sys.exit(0)

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    if args['<timetable>']:
        log.info('Reading seed individual from {}.'.format(args['<timetable>']))
        with open(args['<timetable>']) as csvfile:
            individual = individual_from_list(
                list(csv.reader(csvfile, delimiter=',')),
                campers, acts, sessions)

        toolbox.register("individual",
                         partial(gen_individual, toolbox=toolbox),
                         Individual(individual, campers, sessions))

    outdir = args['<outdir>']


    hof = MyHallOfFame(campers, sessions, outdir, 100)
    stats = Statistics(key=lambda ind: ind.fitness.values)
    stats.register("avg", numpy.mean, axis=0)
    stats.register("std", numpy.std, axis=0)
    stats.register("min", numpy.min, axis=0)
    stats.register("max", numpy.max, axis=0)

    if not os.path.exists(outdir):
        os.mkdir(outdir)

    def responder():
        while sys.stdin.readline():
            print("Dumping current Hall of Fame to {}".format(outdir))
            hof.dump_to_dir()

    t = threading.Thread(target=responder)
    t.daemon = True
    t.start()

    (timetables, log) = algorithms.eaSimple(
        toolbox.population(),
        toolbox, cxpb=0.2, mutpb=0.5, ngen=30000,
        stats=stats,
        halloffame=hof,
        verbose=True)

    hof.dump_to_dir()
