# coding: utf-8
"""Generate Family Camp Timetable.

Example:
  stdbuf -oL -eL python -m scoop -n 8 test_schedule.py outdir

Usage:
  test_schedule.py [-d|--debug] [-r|--refresh] <outdir>
  test_schedule.py (-h | --help)
  test_schedule.py --version

Arguments:

  outdir         Directory to hold results.

Options:
  -r,--refresh   Refresh cache from Google Docs
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

from functools import partial
import logging
import threading
from docopt import docopt

from deap import base
from deap import creator
from deap import tools
from scoop import futures
import numpy
from deap import algorithms
from deap.tools import Statistics
from deep import *

log = logging.getLogger(__name__)


DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"


import random
from datetime import timedelta
from datetime import datetime


acts = [Activity('BMX', timedelta(minutes=30), 2),
        Activity('Caving', timedelta(minutes=30), 10),
        Activity('Maze', timedelta(minutes=30), 10)]

BMX, Caving, Maze = acts

campers = [Camper('camper1', 'group1', [BMX, Caving], []),
           Camper('camper2', 'group1', [BMX, ], [Maze, Caving]),
           Camper('camper3', 'group2', [Caving, ], [BMX]), ]


s = [(acts[0], datetime(2014, 7, 5, 9, 0)),
     (acts[0], datetime(2014, 7, 5, 10, 0)),
     (acts[0], datetime(2014, 7, 5, 11, 0)),
     (acts[1], datetime(2014, 7, 5, 9, 0)),
     (acts[1], datetime(2014, 7, 5, 10, 0)),
     (acts[2], datetime(2014, 7, 5, 9, 0)),
     (acts[2], datetime(2014, 7, 5, 10, 0))]

sessions = [Session(_[0], _[1]) for _ in s]

timetable = [random.choice([True, False])
             for _ in range(0, len(campers)*len(sessions))]

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
    outdir = args['<outdir>']

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    # individual = toolbox.individual()
    # toolbox.evaluate(individual)
    # mutant = toolbox.mutate(individual)[0]

    # print(print_individual(Individual(mutant, campers, sessions), campers))

    # print(Individual(individual, campers, sessions).export_cvs())

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

    #t = threading.Thread(target=responder)
    #t.daemon = True
    #t.start()

    (timetables, log) = algorithms.eaSimple(
        toolbox.population(),
        toolbox, cxpb=0.2, mutpb=0.5, ngen=1,
        stats=stats,
        halloffame=hof,
        verbose=True)

    hof.dump_to_dir()
