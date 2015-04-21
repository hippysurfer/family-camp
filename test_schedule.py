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

from functools import partial
import logging
from deap import base
from deap import creator
from deap import tools
from scoop import futures
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

individual = toolbox.individual()
toolbox.evaluate(individual)
mutant = toolbox.mutate(individual)[0]

print(print_individual(Individual(mutant, campers, sessions), campers))

print(Individual(individual, campers, sessions).export_cvs())
