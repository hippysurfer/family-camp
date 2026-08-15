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

from functools import partial

from docopt import docopt
from deap import base, creator, tools
from deap.algorithms import varAnd, varOr

from scoop import futures
import numpy
from deap.tools import Statistics

from family_camp.schedule.deep import *

log = logging.getLogger(__name__)

DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"


def eaSimple(population, toolbox, cxpb, mutpb, ngen, stats=None,
             halloffame=None, verbose=__debug__):
    """This algorithm reproduce the simplest evolutionary algorithm as
    presented in chapter 7 of [Back2000]_.

    :param population: A list of individuals.
    :param toolbox: A :class:`~deap.base.Toolbox` that contains the evolution
                    operators.
    :param cxpb: The probability of mating two individuals.
    :param mutpb: The probability of mutating an individual.
    :param ngen: The number of generation.
    :param stats: A :class:`~deap.tools.Statistics` object that is updated
                  inplace, optional.
    :param halloffame: A :class:`~deap.tools.HallOfFame` object that will
                       contain the best individuals, optional.
    :param verbose: Whether or not to log the statistics.
    :returns: The final population
    :returns: A class:`~deap.tools.Logbook` with the statistics of the
              evolution

    The algorithm takes in a population and evolves it in place using the
    :meth:`varAnd` method. It returns the optimized population and a
    :class:`~deap.tools.Logbook` with the statistics of the evolution. The
    logbook will contain the generation number, the number of evaluations for
    each generation and the statistics if a :class:`~deap.tools.Statistics` is
    given as argument. The *cxpb* and *mutpb* arguments are passed to the
    :func:`varAnd` function. The pseudocode goes as follow ::

        evaluate(population)
        for g in range(ngen):
            population = select(population, len(population))
            offspring = varAnd(population, toolbox, cxpb, mutpb)
            evaluate(offspring)
            population = offspring

    As stated in the pseudocode above, the algorithm goes as follow. First, it
    evaluates the individuals with an invalid fitness. Second, it enters the
    generational loop where the selection procedure is applied to entirely
    replace the parental population. The 1:1 replacement ratio of this
    algorithm **requires** the selection procedure to be stochastic and to
    select multiple times the same individual, for example,
    :func:`~deap.tools.selTournament` and :func:`~deap.tools.selRoulette`.
    Third, it applies the :func:`varAnd` function to produce the next
    generation population. Fourth, it evaluates the new individuals and
    compute the statistics on this population. Finally, when *ngen*
    generations are done, the algorithm returns a tuple with the final
    population and a :class:`~deap.tools.Logbook` of the evolution.

    .. note::

        Using a non-stochastic selection method will result in no selection as
        the operator selects *n* individuals from a pool of *n*.

    This function expects the :meth:`toolbox.mate`, :meth:`toolbox.mutate`,
    :meth:`toolbox.select` and :meth:`toolbox.evaluate` aliases to be
    registered in the toolbox.

    .. [Back2000] Back, Fogel and Michalewicz, "Evolutionary Computation 1 :
       Basic Algorithms and Operators", 2000.
    """
    logbook = tools.Logbook()
    logbook.header = ['gen', 'nevals'] + (stats.fields if stats else [])

    # Evaluate the individuals with an invalid fitness
    invalid_ind = [ind for ind in population if not ind.fitness.valid]
    fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
    for ind, fit in zip(invalid_ind, fitnesses):
        ind.fitness.values = fit

    if halloffame is not None:
        halloffame.update(population)

    record = stats.compile(population) if stats else {}
    logbook.record(gen=0, nevals=len(invalid_ind), **record)
    if verbose:
        print(logbook.stream)

    # Extracting all the fitnesses of
    fits = [ind.fitness.values[0] for ind in population]
    goodness = [ind.fitness.values[1] for ind in population]

    found = False

    # Begin the generational process
    for gen in range(1, ngen + 1):
        for fit, good in zip(fits, goodness):
            if fit == 1 and good == 1/100.0:
                found = True
                break
        if found:
            break

        # Select the next generation individuals
        offspring = toolbox.select(population, len(population))

        # Vary the pool of individuals
        offspring = varAnd(offspring, toolbox, cxpb, mutpb)

        # Evaluate the individuals with an invalid fitness
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        # Update the hall of fame with the generated individuals
        if halloffame is not None:
            halloffame.update(offspring)

        # Replace the current population by the offspring
        population[:] = offspring

        # Append the current generation statistics to the logbook
        record = stats.compile(population) if stats else {}
        logbook.record(gen=gen, nevals=len(invalid_ind), **record)
        if verbose:
            print(logbook.stream)

        # Extracting all the fitnesses of
        fits = [ind.fitness.values[0] for ind in population]
        goodness = [ind.fitness.values[1] for ind in population]

    return population, logbook



acts = [Activity('Archery', timedelta(minutes=30), 1, 5),
        Activity('BMX', timedelta(minutes=30), 1, 10),
        Activity('Caving', timedelta(minutes=30), 1, 10),
        Activity('Maze', timedelta(minutes=30), 1, 10)]

Archery, BMX, Caving, Maze = acts


campers = [
    Camper('camper1', '001/group1', [BMX, Archery], [Caving], 10,"Child"),
    Camper('camper2', '001/group1', [BMX, Archery], [Maze, Caving], None,"Adult (over 18 years)"),
    Camper('camper3', '002/group2', [Caving, Archery], [BMX],None,"Adult (over 18 years)"),
    Camper('camper4', '002/group3', [Caving, Archery], [BMX, Maze],None,"Adult (over 18 years)"),
    Camper('camper5', '002/group4', [Caving], [BMX, Maze],None,"Adult (over 18 years)"),
    Camper('camper6', '001/group5', [BMX, Archery], [Caving], 10,"Child"),
    Camper('camper7', '001/group5', [BMX, Archery], [Maze, Caving], None,"Adult (over 18 years)"),
    Camper('camper8', '002/group6', [Caving, Archery], [BMX],None,"Adult (over 18 years)"),
    Camper('camper9', '002/group7', [Caving, Archery], [BMX, Maze],None,"Adult (over 18 years)"),
    Camper('camper10', '002/group8', [Caving], [BMX, Maze],None,"Adult (over 18 years)"),
    ]


s = [(Archery, "Archery Indoor", datetime(2014, 7, 5, 9, 0)),
     (Archery, "Archery Outdoor", datetime(2014, 7, 6, 9, 0)),
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

data_cache.overlapping_sessions = {
    session: get_overlapping_sessions(session, sessions) for session in sessions
}

timetable = [numpy.random.choice([True, False])
             for _ in range(0, len(campers) * len(sessions))]

toolbox = base.Toolbox()

creator.create("FitnessMin", base.Fitness, weights=(5.0, -2.0, 1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)
toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions,
                                     data_cache=data_cache,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=100)
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

    hof = MyHallOfFame(campers, sessions, outdir, 10)
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


    # t = threading.Thread(target=responder)
    # t.daemon = True
    # t.start()

    # CXPB  is the probability with which two individuals
    #       are crossed
    #
    # MUTPB is the probability for mutating an individual
    (timetables, log) = eaSimple(
        toolbox.population(),
        toolbox, cxpb=0.2, mutpb=0.5, ngen=100,
        stats=stats,
        halloffame=hof,
        verbose=True)

    #print(hof)
    hof.dump_to_dir()
