# coding: utf-8

import os
import os.path
import csv
import threading
from functools import partial

from deap import base, creator, tools, algorithms
import numpy
from deap.tools import Statistics

# Work around a Python3.10 depreciation issue. Scoop has not caught up yet.
try:
    from scoop import futures
except ImportError:
    import collections.abc
    #hyper needs the four following aliases to be done manually.
    collections.Iterable = collections.abc.Iterable
    collections.Mapping = collections.abc.Mapping
    collections.MutableSet = collections.abc.MutableSet
    collections.MutableMapping = collections.abc.MutableMapping
    from scoop import futures


from .deep import *

import logging

log = logging.getLogger(__name__)

DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"

try:
    (acts, sessions, campers, data_cache) = get_source_data(use_cache=True)
except FileNotFoundError:
    (acts, sessions, campers, data_cache) = get_source_data(use_cache=False)

toolbox = base.Toolbox()

creator.create("FitnessMin", base.Fitness, weights=(5.0, -2.0, -1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)


def mycopy(old):
    new = old.__class__(old[:])
    new.fitness = deepcopy(old.fitness)
    return new


toolbox.register("clone", mycopy)
toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions, data_cache,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=2000)
toolbox.register("mate", partial(mate, campers=campers,
                                 sessions=sessions))
toolbox.register("mutate", partial(mutate, campers=campers,
                                   sessions=sessions,
                                   data_cache=data_cache, toolbox=toolbox))
toolbox.register("select", tools.selTournament, tournsize=20)
toolbox.register("evaluate", partial(evaluate, campers=campers,
                                     sessions=sessions))
toolbox.register("map", futures.map)


def run(refresh, args):
    if refresh:
        log.info('Fetching fresh data.')
        get_source_data(use_cache=False)
        log.info('Done. Now run "generate".')
        sys.exit(0)

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

    (timetables, log_) = algorithms.eaSimple(
        toolbox.population(),
        toolbox, cxpb=0.2, mutpb=0.5, ngen=30000,
        stats=stats,
        halloffame=hof,
        verbose=True)

    hof.dump_to_dir()
