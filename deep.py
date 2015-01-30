# coding: utf-8
"""Generate Family Camp Timetable.

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

import os.path
import sys
import random
from functools import partial
import itertools as it
from datetime import timedelta
from datetime import datetime
import logging
from docopt import docopt
import pickle
import google
from deap import base
from deap import creator
from deap import tools
import scoop

import numpy
from deap import algorithms
from deap.tools import HallOfFame
from deap.tools import Statistics

log = logging.getLogger(__name__)


DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"


class Activity:

    def __init__(self, name, duration, limit):
        self.name = name
        self.duration = duration
        self.limit = int(limit)

    def __str__(self):
        return "Activity: {} {} {}".format(
            self.name, self.duration, self.limit)

    __repr__ = __str__


class Camper:

    def __init__(self, name, group, priorities, others):
        self.name = name
        self.group = group
        self.priorities = priorities
        self.others = others

    def __str__(self):
        return "{}/{}".format(self.group, self.name)

    __repr__ = __str__


class Session:

    def __init__(self, activity, start):
        self.activity = activity
        self.start = start
        self.end = start + activity.duration

    def __str__(self):
        return "Session:{} {}".format(self.activity.name,
                                      self.start.strftime(DATEFORMAT))

    __repr__ = __str__


class SessionInst:

    def __init__(self, session, all_campers, campers):
        self.session = session
        self.all_campers = all_campers
        self.set_campers(campers)

    def set_campers(self, campers):
        self.campers = list(it.compress(self.all_campers,
                                        campers))
        # self.campers = []
        # for i in range(0, len(campers)):
        #     if campers[i]:
        #         self.campers.append(self.all_campers[i])

    def __str__(self):
        return "Session: {} {} / Campers: {}".format(
            self.session.activity.name,
            self.session.start.strftime(DATEFORMAT),
            ", ".join([str(_) for _ in self.campers]))

    __repr__ = __str__


def overlapping_sessions(session_inst, session_insts):
    """Return a list of sessions from sessions that overlap
    with session."""
    return [_ for _ in session_insts
            if (_ != session_inst and sessions_overlap(
                _.session, session_inst.session))]


class Individual:

    def __init__(self, timetable, campers, sessions):
        self.campers = campers
        self.sessions = sessions
        self.session_inst = [
            SessionInst(session,
                        campers,
                        timetable[session_idx:session_idx + len(campers)])
            for session, session_idx in
            zip(sessions,
                range(0, len(campers) * len(sessions), len(campers)))
        ]
        # self.session_inst = []
        # for (session_name, session_idx) in zip(
        #         range(0, len(sessions)),
        #         range(0, len(campers) * len(sessions), len(campers))):
        #     self.session_inst.append(
        #         SessionInst(sessions[session_name],
        #                     campers,
        #                     timetable[session_idx:session_idx + len(campers)]))

        self.overlapping_sessions_map = \
            {session_inst: overlapping_sessions(session_inst,
                                                self.session_inst)
             for session_inst in self.session_inst}

    def export_map(self):
        """Returns a row for each interval. A column for each activity.
        Each cell is the percentage of the slots for that activity/session
        that are used by the timetable."""
        acts = set([s.activity for s in self.sessions])
        # For each 15 period from the start to the end of each day.

        # Get list of days
        days = set([s.start.day for s in self.sessions])

        header = ['Time']
        header.extend([act.name for act in acts])

        out = [header, ]
        for day in days:
            # Get first and last time.
            start = sorted([s.start for s in self.sessions
                            if s.start.day == day])[0]
            end = sorted([s.start for s in self.sessions
                          if s.start.day == day])[-1]

            t = start
            while t < end:
                row = [t.strftime(DATEFORMAT), ]
                for a in acts:
                    active_session = [s for s in self.session_inst
                                      if s.session.activity == a and
                                      (s.session.start <= t and
                                       s.session.end > t)]
                    row.append(
                        str(len(active_session[0].campers) /
                            active_session[0].session.activity.limit)
                        if active_session else '')
                out.append(row)
                t = t + timedelta(minutes=15)

        return out

    def export_by_family(self):
        """Return a dictionary of the following form:

           family => {session_inst => [campers,]}
        """

        ret = {}
        for f in set(c.group for c in self.campers):
            ret[f] = {}
            for s in sorted([s for s in self.session_inst if f in
                             [camper.group for camper in s.campers]],
                            key=lambda s: s.session.start):
                ret[f][s] = [c for c in s.campers if c.group == f]

        return ret

    def export_by_activity(self):
        """Return a dictionary of the following form:

           activity => [session_inst,]
        """

        ret = {}
        for a in set([s.session.activity for s in self.session_inst]):
            ret[a] = sorted(
                [s for s in self.session_inst
                 if s.session.activity == a],
                key=lambda s: s.session.start)

        return ret

    def fitness(self, debug=False):
        count = 1

        for s in self.session_inst:
            # Count the number of times we have the same camper in two sessions
            # that overlap.
            for c in s.campers:
                for other_s in self.overlapping_sessions_map[s]:
                    if c in other_s.campers:
                        count += 1

            # Count the number of times we have a family split accross two
            # sessions that overlap
            for g in set([c.group for c in s.campers]):
                for other_s in self.overlapping_sessions_map[s]:
                    if g in set([c.group for c in other_s.campers]):
                        if debug:
                            print(
                                "{} Found in other session: {}".format(
                                    str(g), str(s)))
                        count += 1

            # How badly have we exceeded session limits?
            if len(s.campers) - s.session.activity.limit > 0:
                if debug:
                    print("{} Exceeded limit: {} > {}".format(
                        str(s), len(s.campers), s.session.activity.limit))
                count += len(s.campers) - s.session.activity.limit

        # How many campers are missing their priorities?
        for c in self.campers:
            activities = []
            for s in self.session_inst:
                if c in s.campers:
                    activities.append(s.session.activity)

            # How many campers are missing their priorities?
            missing = set(c.priorities) - set(activities)
            if len(missing):
                if debug:
                    print("{} missing {}\n".format(
                        str(c), " ".join([str(_) for _ in missing])))
            count += len(missing)

            # How many campers are doing activities they did not request?
            unwanted = set(activities) - (set(c.priorities) | set(c.others))
            if len(unwanted):
                if debug:
                    print("{} unwanted {}\n".format(
                        str(c), " ".join([str(_) for _ in unwanted])))
            count += len(unwanted)

            # How many times are campers doing the same activity more than
            # once?
            duplicates = len(activities) - len(set(activities))
            if duplicates:
                if debug:
                    print("{} duplicated {}".format(str(c), duplicates))
            count += duplicates

        return count

    def goodness(self, debug=False):
        # What percentage of the other activities have been met?

        # Total number of other activities requested.
        other_total = sum([len(c.others) for c in self.campers])
        met = 0
        for c in self.campers:
            activities = []
            for s in self.session_inst:
                if c in s.campers:
                    activities.append(s.session.activity)
            # The intersection is the list of activities that have been met.
            met += len(set(c.others) & set(activities))
            if len(set(c.others)) > len(set(c.others) & set(activities)):
                if debug:
                    print("Others not met: {} missing - {}".format(
                        str(c), " ".join(str(_) for _ in
                                         set(c.others) - set(activities))))

        percentage_met = ((met / other_total) * 100)
        if debug and percentage_met != 100:
            print("Percentation met: {} {} {}\n".format(
                percentage_met, other_total, met))

        return percentage_met if percentage_met != 0 else 1

    def __str__(self):
        return "{}".format("\n".join([str(_) for _ in self.session_inst]))


def sessions_overlap(first, second):
    "If the start of the first sesssion is between the start "
    "and end of the second or the end of the first session is "
    "between the start and end of the second or the start of "
    "the second session is between the start and end of the first or"
    "the end of the second session is between the start and end of the first"

    if first.start >= second.start and first.start <= second.end:
        return True

    if first.end >= second.start and first.start <= second.end:
        return True

    if second.start >= first.start and second.start <= first.end:
        return True

    if second.end >= first.start and second.start <= first.end:
        return True

    return False


class MyHallOfFame(HallOfFame):

    def __init__(self, campers, sessions, dest, *args, **kwargs):
        HallOfFame.__init__(self, *args, **kwargs)
        self.campers = campers
        self.sessions = sessions
        self.count = 0
        self.dest = dest

    def insert(self, item):
        HallOfFame.insert(self, item)

        ind = Individual(item, self.campers, self.sessions)
        scoop.logger.info("fitness = {}, goodness = {}".format(ind.fitness(),
                                                               ind.goodness()))
        if ind.fitness() == 1 and ind.goodness() == 100:
            path = os.path.join(self.dest, str(self.count))
            with open(path, 'w') as f:
                f.write(print_individual(ind))
                scoop.logger.info("Written {}\n".format(path))
            self.count += 1

# import random
# from datetime import timedelta
# from datetime import datetime


# BMX = Activity('BMX',timedelta(minutes=30),2)
# Caving = Activity('Caving',timedelta(minutes=30),10)
# Maze = Activity('Maze',timedelta(minutes=30),10)

# campers = [Camper('camper1','group1',[BMX, Caving], []),
#            Camper('camper2','group1',[BMX,], [Maze, Caving]),
#            Camper('camper3','group2',[Caving,], [BMX]),]


# s = [(BMX, datetime(2014,7,5,9,0)),
#      (BMX, datetime(2014,7,5,10,0)),
#      (BMX, datetime(2014,7,5,11,0)),
#      (Caving, datetime(2014,7,5,9,0)),
#      (Caving, datetime(2014,7,5,10,0)),
#      (Maze, datetime(2014,7,5,9,0)),
#      (Maze, datetime(2014,7,5,10,0))]

# sessions = [Session(_[0],_[1]) for _ in s]

# timetable = [random.choice([True,False]) for _ in range(0,len(campers)*len(sessions))]
# individual = Individual(timetable, campers, sessions)
# print(individual)


def get_source_data(use_cache=True):
    """Return the activities, sessions and campers."""
    if use_cache and os.path.exists(CACHE):
        (acts_wks, session_wks, campers_wks) = pickle.load(
            open(CACHE, 'rb'))
    else:
        gc = google.conn()
        spread = gc.open("Timetable")
        acts_wks = spread.worksheet("Activities").get_all_values()
        session_wks = spread.worksheet("Sessions").get_all_values()
        campers_wks = gc.open("Family Camp Bookings").worksheet(
            "Activities").get_all_values()

        pickle.dump((acts_wks, session_wks, campers_wks), open(CACHE, 'wb'))

    acts = {_[0]: Activity(_[0], timedelta(minutes=int(_[1])), _[2])
            for _ in acts_wks[1:] if _[0] != ''}

    sessions = [Session(acts[_[0]],
                        datetime.strptime(_[1], "%d/%m/%Y %H:%M:%S"))
                for _ in session_wks[1:]]

    campers = [Camper("{} {}".format(_[1], _[2]), _[0],
                      [acts[a.strip()]
                       for a in _[8].split(',') if a.strip() != ''],
                      [acts[b.strip()] for b in _[9].split(',')
                       if b.strip() != '']) for _ in campers_wks[1:]]

    return (acts, sessions, campers)


def evaluate(individual, campers, sessions, debug=False):
    # Do some hard computing on the individual
    ind = Individual(individual, campers, sessions)
    fitness = 1. / ind.fitness(debug=debug)
    goodness = 1. / ind.goodness(debug=debug)
    # print("fitness = {}, goodness = {}".format(fitness, goodness))
    return fitness, goodness


def mutate(ind1, sessions, campers):
    mutant = toolbox.clone(ind1)

    for _ in range(0, random.randrange(0, 3)):

        # Select a session at random
        session_idx = random.randrange(0, len(sessions))

        # Select a camper that has selected that activity
        act = sessions[session_idx].activity
        # print("Act: {}".format(str(act)))

        c = random.choice(
            [_ for _ in campers if (act in _.priorities or act in _.others)])
        # print("Camper: {}".format((str(c))))

        # get all family members that have selected the activity.
        matching_campers = [_ for _ in campers if (
            (_.group == c.group) and (act in _.priorities or act in _.others))]
        # print("Matching campers: {}".format(" ".join(str(_) for _ in
        # matching_campers)))

        # If they are already allocated to another session, remove them
        for s in [_ for _ in sessions if _.activity == act]:
            for indx in [campers.index(_) for _ in matching_campers]:
                # print("Removing {} from
                # {}.".format(str(campers[indx]),str(s)))
                old_session_idx = sessions.index(s) * len(campers)
                mutant[old_session_idx + indx] = False

        # Add them to the randomaly allocated session
        for indx in [campers.index(_) for _ in matching_campers]:
            # print("Adding {} to {}.".format(str(campers[indx]),
            # str(sessions[session_idx])))
            mutant[session_idx * len(campers) + indx] = True

        # Remove fitness values
        del mutant.fitness.values

    return mutant,


def gen_seed_individual(campers, sessions, creator):
    activities = set([s.activity for s in sessions])
    campers_per_activity = {}
    for c in campers:
        for activity in activities:
            if activity in c.priorities or activity in c.others:
                if activity in campers_per_activity.keys():
                    campers_per_activity[activity].append(c)
                else:
                    campers_per_activity[activity] = [c, ]
    timetable = []
    for s in sessions:
        families = []
        for c in campers:
            if ((s.activity in campers_per_activity.keys()) and
                (c in campers_per_activity[s.activity]) and
                    ((c.group in families) or random.choice([True, False]))):
                timetable.append(True)
                campers_per_activity[s.activity].pop(
                    campers_per_activity[s.activity].index(c))
                families.append(c.group)
            else:
                timetable.append(False)
    ind = creator(timetable)
    return ind


def gen_individual(seed_individual, toolbox):
    return toolbox.mutate(seed_individual)[0]


def print_individual(individual):
    out = ["Fitness = {}".format(individual.fitness()),
           "Goodness = {}\n\n".format(individual.goodness())]

    previous_f = None
    previous_i = None
    for f, s in individual.export_by_family().items():
        for i, campers in sorted(s.items(), key=lambda s: s[0].session.start):
            previous_c = None
            for c in campers:
                out.append("{:<20} {:<20} {:<20} {:<20}".format(
                    f if f != previous_f else '',
                    i.session.start.strftime(DATEFORMAT) if i != previous_i else '',
                    i.session.activity.name if i != previous_i else '',
                    c.name if c != previous_c else ''
                ))
                previous_f = f
                previous_i = i
                previous_c = c
            out.append('\n')

    out.append("**********************************************************\n")

    previous_a = None
    previous_i = None
    previous_c = None
    for a, s in individual.export_by_activity().items():
        for i in s:
            for c in i.campers:
                out.append("{:<20} {:<20} {:<20}".format(
                    a.name if a != previous_a else '',
                    i.session.start.strftime(DATEFORMAT)
                    if i != previous_i else '',
                    c.name if c != previous_c else ''
                ))
                previous_a = a
                previous_i = i
                previous_c = c
        out.append('\n')

    return "\n".join(out)

from scoop import futures

(acts, sessions, campers) = get_source_data(use_cache=True)

toolbox = base.Toolbox()

creator.create("FitnessMin", base.Fitness, weights=(1.0, -1.0))
creator.create("Individual", list, fitness=creator.FitnessMin)

toolbox.register("individual", partial(gen_individual, toolbox=toolbox),
                 gen_seed_individual(campers, sessions,
                                     creator=creator.Individual))
toolbox.register(
    "population", tools.initRepeat, list, toolbox.individual, n=500)
toolbox.register("mate", tools.cxUniform, indpb=0.5)
toolbox.register("mutate", partial(mutate, campers=campers,
                                   sessions=sessions))
toolbox.register("select", tools.selTournament, tournsize=10)
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
        toolbox, cxpb=0.2, mutpb=0.5, ngen=500,
        stats=stats,
        halloffame=hof,
        verbose=True)

    print(print_individual(Individual(hof[0], campers, sessions)))


    # gc = gs.login(*creds.creds)
    # spread = gc.open("Timetable")
    # results_wks = spread.worksheet("Timetable")

    # ind_sheet = individual.export_map()

    # for row in range(0, len(ind_sheet)):
    #     cells = []
    #     for col in range(0, len(ind_sheet[row])):
    #         for i in range(0, 10):
    #             try:
    #                 cell = results_wks.cell(row + 1, col + 1)
    #                 cell.value = ind_sheet[row][col]
    #                 cells.append(cell)
    #                 break
    #             except:
    #                 print("row = {}, col = {}".format(row, col))
    #                 print("sleep 5")
    #                 time.sleep(5)
    #                 gc = gs.login(*creds.creds)
    #                 spread = gc.open("Timetable")
    #                 results_wks = spread.worksheet("Timetable")

    #     for i in range(0, 10):
    #         try:
    #             results_wks.update_cells(cells)
    #             break
    #         except:
    #             print("Get exception writing row: {}".format(row))
    #             print("wait 5 and try again...")
    #             time.sleep(5)
    #             gc = gs.login(*creds.creds)
    #             spread = gc.open("Timetable")
    #             results_wks = spread.worksheet("Timetable")


