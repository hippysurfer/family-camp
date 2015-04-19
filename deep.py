# coding: utf-8
import os.path
import random
import itertools as it
from datetime import timedelta
from datetime import datetime
import logging
import pickle
import google
import scoop

from deap.tools import HallOfFame

log = logging.getLogger(__name__)


DATEFORMAT = "%a %H:%M"
CACHE = ".cache.pickle"

# List of activities that everyone must be allocated.
COMPULSARY_ACTIVITIES = ["Saturday Lunch", "Sunday Lunch"]


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


def overlapping_sessions2(session, sessions):
    """Return a list of sessions from sessions that overlap
    with session."""
    return [_ for _ in sessions
            if (_ != session
                and sessions_overlap(
                    _, session))]


class Individual:

    def __init__(self, timetable, campers, sessions, session_insts=None):
        self.campers = campers
        self.sessions = sessions
        if session_insts:
            self.session_inst = session_insts
        else:
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

    def export_by_camper(self):
        """Return a dictionary of the following form:

        camper => [sessions_inst]
        """

        campers = {}

        for c in self.campers:
            campers[c] = [s for s in self.session_inst if c in s.campers]

        return campers

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

    def export_cvs(self):
        """Return a cvs format:
        Group, Camper Name, Activity, Session
        """
        out = []
        for c, sessions in self.export_by_camper().items():
            for session in sessions:
                out.append(",".join([c.group, c.name,
                                     session.session.activity.name,
                                     str(session.session.start)]))

        return "\n".join(out)

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

    def goodness(self, campers, debug=False):
        # What percentage of the other activities have been met?

        # Total number of other activities requested.
        other_total = sum([len(c.others) for c in self.campers])
        met = 0
        for c in self.campers:
            activities = [s.session.activity for s in self.session_inst
                          if c in s.campers]
            # The intersection is the list of activities that have been met.
            # we divide this by the number that have been asked for. This
            # give 1 if they have all been met and 0 if none have been met.
            # It gives a weight score depending on how many have been
            # requested. The more requested the less the effect on the overall
            # goodness. This should favour those that have only request a
            # small number of activites.
            num_others = len(c.others)
            set_others = set(c.others)
            set_acts = set(activities)

            met += (1 if num_others == 0 else
                    len(set_others & set_acts) / num_others)

            if (len(set_others) > len(set_others & set_acts)):
                if debug:
                    print("Others not met: {} missing - {}".format(
                        str(c), " ".join(str(_) for _ in
                                         set_others - set_acts)))

        # If all campers have all activitites met == len(campers)
        # so met / len(campers) is the fraction of activities not met
        # wieghted by the greediness of each camper.
        percentage_met = ((met / len(campers)) * 100)

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
        # scoop.logger.info("fitness = {}, goodness = {}".format(ind.fitness(),
        #                                                       ind.goodness()))
        if ind.fitness() == 1 and ind.goodness(self.campers) == 100:
            path = os.path.join(self.dest, str(self.count))
            with open(path, 'w') as f:
                f.write(print_individual(self.campers, ind))
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

    def strpdelta(s):
        hr, min, sec = map(float, s.split(':'))
        return timedelta(hours=hr, minutes=min, seconds=sec)

    acts = {_[0]: Activity(_[0], strpdelta(_[1]), _[2])
            for _ in acts_wks[1:] if _[0] != ''}

    sessions = [Session(acts[_[0]],
                        datetime.strptime(_[1], "%d/%m/%Y %H:%M:%S"))
                for _ in session_wks[1:]]

    campers = [Camper("{} {}".format(_[1], _[2]), _[0],
                      [acts[a.strip()]
                       for a in _[8].split(',') if a.strip() != ''] +
                      [acts[c] for c in COMPULSARY_ACTIVITIES],
                      [acts[b.strip()] for b in _[9].split(',')
                       if b.strip() != '']) for _ in campers_wks[1:]]

    return (acts, sessions, campers)


def evaluate(individual, campers, sessions, debug=False):
    # Do some hard computing on the individual
    ind = Individual(individual, campers, sessions)
    fitness = 1. / ind.fitness(debug=debug)
    goodness = 1. / ind.goodness(campers, debug=debug)
    # print("fitness = {}, goodness = {}".format(fitness, goodness))
    return fitness, goodness


def mutate(ind1, sessions, campers, toolbox):
    mutant = toolbox.clone(ind1)
    # Remove fitness values
    del mutant.fitness.values

    for _ in range(0, random.randrange(0, 10)):

        #import ipdb
        #ipdb.set_trace()

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
        #                                             matching_campers)))

        # If they are already allocated to another session, remove them
        for s in [_ for _ in sessions if _.activity == act]:
            for indx in [campers.index(_) for _ in matching_campers]:
                # print("Removing {} from {}.".format(
                #    str(campers[indx]), str(s)))
                old_session_idx = sessions.index(s) * len(campers)
                mutant[old_session_idx + indx] = False

        # Add them to the randomaly allocated session
        for indx in [campers.index(_) for _ in matching_campers]:
            # print("Adding {} to {}.".format(str(campers[indx]),
            #                                str(sessions[session_idx])))
            mutant[session_idx * len(campers) + indx] = True

        # Remove the group from any other sessions that overlap
        # with the session we have just added them to.
        group_campers = [_ for _ in campers if _.group == c.group]
        for overlapping_session in overlapping_sessions2(
                sessions[session_idx],
                sessions):
            for indx in [campers.index(_) for _ in group_campers]:
                # print("Removing {} from {}.".format(
                #    str(campers[indx]), str(overlapping_session)))
                mutant[sessions.index(overlapping_session) * len(campers)
                       + indx] = False

    return mutant,


def gen_seed_individual(campers, sessions, creator):
    activities = set([s.activity for s in sessions])
    campers_per_activity = {}

    # Build a map of the list of campers that wish to do
    # each activity.
    for c in campers:
        for activity in activities:
            if activity in c.priorities or activity in c.others:
                if activity in campers_per_activity.keys():
                    campers_per_activity[activity].append(c)
                else:
                    campers_per_activity[activity] = [c, ]

    # Place holder for final timetable. The timetable is represented as
    # a list of True/False values. Each session has a list element for
    # each camper.
    timetable = []

    # For each session decided randomly whether a camper will be allocated.
    # If a camper is allocated all of the family members of that camper
    # (that also selected the activity) will also be added. This ensures that

    # families are not split.
    for s in sessions:
        campers_in_session = 0  # keep track of campers in session
        session_timetable = [False] * len(campers)
        for c in campers:
            # short cut to stop once the session is full.
            if campers_in_session >= s.activity.limit:
                break

            # Deal with the special case of an activity that has
            # noone signed up.
            if not (s.activity in campers_per_activity.keys()):
                continue
            # If the camper has selected the activity, flip the coin to see if
            # they will be allocated.
            if ((c in campers_per_activity[s.activity]) and
                random.choice([True, False])):

                # Find all members of the family that have selected
                # the activity
                f_members = [_ for _ in campers_per_activity[s.activity]
                             if _.group == c.group]

                # If there is room in this session for this family.
                if (campers_in_session + len(f_members)) <= s.activity.limit:
                    # For each member of the family, add them to this
                    # session and remove them from the list waiting to
                    # be allocated to this activity.
                    for member in f_members:
                        session_timetable[campers.index(member)] = True

                        campers_per_activity[s.activity].pop(
                            campers_per_activity[s.activity].index(member))

                    campers_in_session += len(f_members)

        # Add the session to the timetable
        timetable.extend(session_timetable)

    ind = creator(timetable)
    return ind


def mate(ind1, ind2, campers, sessions):
    """Mate two timetables by selecting families at random and swaping
    their schedules from one timetable to the other."""

    # create a list of all families to keep track of which have been
    # considered.
    families = list(set([_.group for _ in campers]))

    # for each family randomly swap the families schedule between
    # the two timetables.
    for c in campers:
        # Stop if we have considered every family.
        if len(families) == 0:
                break

        # Only proced of the family has not already been swapped.
        if (c.group in families):
            # remove from the list so that we do not process this
            # family again.
            families.pop(families.index(c.group))

            # Flip a coin to decide whether to swap the schedules.
            if random.choice([True, False]):
                for s_indx, s in enumerate(sessions):
                    for c_indx, l_c in enumerate(campers):
                        # search for each occurance of this family
                        # in the timetable. Then swap their schedule
                        # from one timetable to the other.
                        if l_c.group == c.group:
                            indx = (s_indx*len(campers)) + c_indx
                            tmp = ind1[indx]
                            ind1[indx] = ind2[indx]
                            ind1[indx] = tmp

    # Remove fitness values
    del ind1.fitness.values
    del ind2.fitness.values

    return (ind1, ind2)


def gen_individual(seed_individual, toolbox):
    return toolbox.mutate(seed_individual)[0]


def print_individual(individual, campers):
    out = ["Fitness = {}".format(individual.fitness(debug=True)),
           "Goodness = {}\n\n".format(individual.goodness(campers, debug=True))]

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


