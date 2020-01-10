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


acts = [Activity('Archery', timedelta(minutes=30), 1, 2),
        Activity('BMX', timedelta(minutes=30), 2, 3),
        Activity('Caving', timedelta(minutes=30), 5, 10),
        Activity('Maze', timedelta(minutes=30), 5, 10)]

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


class Cache:
    pass


data_cache = Cache()
data_cache.activities = set([s.activity for s in sessions])
data_cache.campers_per_activity = {}

# Build a map of the list of campers that wish to do
# each activity.
data_cache.priority_campers_per_activity = {a: [] for a in data_cache.activities}
data_cache.other_campers_per_activity = {a: [] for a in data_cache.activities}

for c in campers:
    for activity in data_cache.activities:
        if activity in c.priorities:
            data_cache.priority_campers_per_activity[activity].append(c)

for c in campers:
    for activity in data_cache.activities:
        if activity in c.others:
            data_cache.other_campers_per_activity[activity].append(c)

data_cache.campers_per_activity = {
    act: data_cache.priority_campers_per_activity[act] + data_cache.other_campers_per_activity[act]
    for act in data_cache.activities
}

data_cache.sessions_per_activity = {
    act: [_ for _ in sessions if _.activity == act] for act in data_cache.activities}

all_groups = set([_.group for _ in campers])
data_cache.campers_per_group = {
    group: [_ for _ in campers if _.group == group] for group in all_groups}

data_cache.campers_per_activity_per_group = {
    act: {
        group: [_ for _ in data_cache.campers_per_activity[act] if _.group == group]
        for group in all_groups
    } for act in data_cache.activities}

timetable = [random.choice([True, False])
             for _ in range(0, len(campers)*len(sessions))]


toolbox = base.Toolbox()

creator.create("FitnessMin", base.Fitness, weights=(5.0, -2.0, 1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)
toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions,
                                     data_cache=data_cache,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=1000)
toolbox.register("mate", partial(mate, campers=campers,
                                 sessions=sessions))
toolbox.register("mutate", partial(mutate, campers=campers,
                                   sessions=sessions,
                                   data_cache=data_cache,
                                   toolbox=toolbox))
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
        toolbox, cxpb=0.2, mutpb=0.5, ngen=100,
        stats=stats,
        halloffame=hof,
        verbose=True)

    hof.dump_to_dir()
