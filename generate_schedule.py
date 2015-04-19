# coding: utf-8
"""Generate Family Camp Timetable.

Example:
  stdbuf -oL -eL python -m scoop -n 8 deep.py | tee timetables/best.txt

Usage:
  deep.py [-d|--debug] [-r|--refresh]
  deep.py (-h | --help)
  deep.py --version


Options:
  -r,--refresh   Refresh cache from Google Docs
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

import sys
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

creator.create("FitnessMin", base.Fitness, weights=(1.0, -1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)

toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=1000)
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

    hof = MyHallOfFame(campers, sessions, 'timetables', 100)
    stats = Statistics(key=lambda ind: ind.fitness.values)
    stats.register("avg", numpy.mean, axis=0)
    stats.register("std", numpy.std, axis=0)
    stats.register("min", numpy.min, axis=0)
    stats.register("max", numpy.max, axis=0)

    (timetables, log) = algorithms.eaSimple(
        toolbox.population(),
        toolbox, cxpb=0.2, mutpb=0.5, ngen=1000,
        stats=stats,
        halloffame=hof,
        verbose=True)

    print(print_individual(Individual(hof[0], campers, sessions), campers))
    print(Individual(hof[0], campers, sessions).export_cvs())
