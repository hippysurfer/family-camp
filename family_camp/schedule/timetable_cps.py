import os
import pickle
import google
from datetime import datetime, timedelta
from ortools.constraint_solver import pywrapcp
import collections
DATEFORMAT = "%a %H:%M"


CACHE = ".cache.pickle"
COMPULSARY_ACTIVITIES = ["Saturday Lunch", "Sunday Lunch", "Saturday BBQ"]


def get_source_data(use_cache=True, limit_campers=None):
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

    # Deal with the problem of non-empty rows in the worksheet after the
    # end of the table that we are interested in.
    raw_acts = []
    for row in acts_wks[1:]:
        if row[0] == '':
            break
        raw_acts.append(row)

    acts = [Activity(_[0], strpdelta(_[1]), _[2])
            for _ in raw_acts if _[0] != '']
    acts_by_name = { act.name: act for act in acts}

    sessions = [Session(acts_by_name[_[0]],
                        _[1],
                        datetime.strptime(_[2], "%d/%m/%Y %H:%M:%S"))
                for _ in session_wks[1:]]

    campers_from_spread = campers_wks[1:][:limit_campers] if limit_campers else campers_wks[1:]

    group_names = [ _[0] for _ in campers_from_spread ]

    groups = [ Group(group_name) for group_name in set(group_names) ]
    groups_by_name = { group.name: group for group in groups}

    campers = [Camper("{} {}".format(_[1], _[2]), groups_by_name[_[0]],
                      [acts_by_name[a.strip()]
                       for a in _[8].split(',') if a.strip() != ''] +
                      [acts_by_name[c] for c in COMPULSARY_ACTIVITIES],
                      [acts_by_name[b.strip()] for b in _[9].split(',')
                       if b.strip() != '']) for _ in campers_from_spread]


    return (acts, sessions, campers, groups)


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

        group.add_camper(self)

    def __str__(self):
        return "{}/{}".format(self.group, self.name)

    __repr__ = __str__


class Group:

    def __init__(self, name):
        self.name = name
        self.campers = []
        self.activities = collections.defaultdict(list)


    def add_camper(self, camper):
        self.campers.append(camper)
        for act in camper.priorities + camper.others:
            self.activities[act.name].append(camper)


class Session:

    def __init__(self, activity, label, start):
        self.activity = activity
        self.label = label
        self.start = start
        self.end = start + activity.duration

    def __str__(self):
        return "Session:{} ({}) {}".format(self.activity.name,
                                           self.label,
                                           self.start.strftime(DATEFORMAT))

    __repr__ = __str__


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


def overlapping_sessions(session, sessions):
    """Return a list of sessions from sessions that overlap
    with session."""
    return [sessions.index(_) for _ in sessions
            if (_ != session
                and sessions_overlap(
                    _, session))]


def possible_family_arrangements_for_activity(activity, groups):
    """Return the allowable arrangements of families for the given activity.
    """

    # Get the indexes for all families that requested this activity.
    filtered_groups = [_ for _ in range(len(groups)) if len(groups[_].activities[activity.name]) > 0]

    # - number of members of each family that want the activity
    members = [len(groups[_].activities[activity.name]) for _ in filtered_groups]

    solver = pywrapcp.Solver("Act")

    # x = [ 0,1,1,0 ] - boolean for each family
    x = [solver.IntVar(0, 1, "x%d" % i) for i in range(len(filtered_groups))]


    #
    # sum (a[i] * b[i] ) for all i <= limit of activity
    solver.Add(solver.ScalProd(x, members) <= activity.limit)

    all_solutions = solver.AllSolutionCollector()
    all_solutions.Add(x)

    db = solver.Phase(x,
                      solver.INT_VAR_SIMPLE,
                      solver.INT_VALUE_SIMPLE)

    solver.Solve(db, all_solutions)

    # Retrieve the solutions
    number_solutions = all_solutions.SolutionCount()

    print("Number of solutions for activity: {} - {}".format(number_solutions, activity.name))

    #solution = solver.Assignment()

    # build a list of the possible solutions.
    options = [0] * number_solutions
    for index in range(number_solutions):
        solution = all_solutions.Solution(index)
        option = [0] * len(groups)
        for grp in range(len(filtered_groups)):
            option[filtered_groups[grp]] = solution.Value(x[grp])
        options[index] = option

    solver.EndSearch()

    return options



def gen_test_data():

    a1 = Activity('a1',timedelta(minutes=59),10)
    a2 = Activity('a2',timedelta(minutes=59),10)

    activities = [ a1, a2 ]

    a1s1 = Session(a1, 'a1', datetime.strptime("1/1/2016 09:00:00", "%d/%m/%Y %H:%M:%S"))
    a1s2 = Session(a1, 'a1', datetime.strptime("1/1/2016 10:00:00", "%d/%m/%Y %H:%M:%S"))
    a1s3 = Session(a1, 'a1', datetime.strptime("1/1/2016 11:00:00", "%d/%m/%Y %H:%M:%S"))

    a2s1 = Session(a2, 'a2', datetime.strptime("1/1/2016 09:30:00", "%d/%m/%Y %H:%M:%S"))
    a2s2 = Session(a2, 'a2', datetime.strptime("1/1/2016 10:30:00", "%d/%m/%Y %H:%M:%S"))

    sessions = [a1s1,
                a1s2,
                a1s3,
                a2s1,
                a2s2]

    g1 = Group('g1')
    g2 = Group('g2')
    g3 = Group('g3')

    groups = [ g1, g2, g3 ]

    campers = [Camper('c1', g1, [a1], []),
               Camper('c2', g1, [a1], []),
               Camper('c3', g1, [a1], []),

               Camper('c4', g2, [a1,a2], []),
               Camper('c5', g2, [a1,a2], []),
               Camper('c6', g2, [a1], []),

               Camper('c7', g3, [a1,a2], []),
               Camper('c8', g3, [a1,a2], []),
               Camper('c9', g3, [a1,a2], []),
               Camper('c10', g3, [a1], []),
               Camper('c11', g3, [a1], []),
               Camper('c12', g3, [a1], [])
              ]

    return activities, sessions, campers, groups


class SearchMonitorTest(pywrapcp.SearchMonitor):
    def __init__(self, solver, nexts, acts):
        pywrapcp.SearchMonitor.__init__(self, solver)
        self._nexts = nexts
        self._solver = solver
        self._acts = acts

    def BeginInitialPropagation(self):
        print("BeginInitialPropagation: {}".format(self._nexts))

    def EndInitialPropagation(self):
        print("EndInitialPropagation: {}".format(self._nexts))

    def BeginFail(self):
        print("BeginFail: {}".format([s.Value() for s in self._nexts]))


def find_timetable(activities, activity_selection_options,
                   sessions, campers, groups):
    num_acts = len(activities)
    num_sessions = len(sessions)
    num_groups = len(groups)

    overlaps = [ overlapping_sessions(session, sessions) for session in sessions]

    session_to_activity_idx = { sessions.index(sess): activities.index(sess.activity) for sess in sessions}

    sessions_by_activity = [ len([ _ for _ in sessions if _.activity == act])
                             for act in activities ]

    act_session_index = [ [ (sum(sessions_by_activity[:act_idx])*num_groups) + (sess*num_groups)
                           for sess in range(sessions_by_activity[act_idx]) ]
                             for act_idx in range(num_acts) ]
    #
    #              sessions1        sessions2
    #          i=0                 i=len(groups)
    # act1  [ fam1, fam2, fam3 ] [fam1, fam2, fam3]
    # act2  [ i=len(groups)*len(sessions), fam2, fam3 ] [fam1, fam2, fam3]
    # act3  [ fam1, fam2, fam3 ] [fam1, fam2, fam3]

    # for i in len(groups):
    #    for j in len(acts):
    #       sum(x[i]+x[j*len(groups)*len(sessions)+i])

    solver_params = pywrapcp.SolverParameters()
    # Change the profile level
    solver_params.profile_level = pywrapcp.SolverParameters.NORMAL_PROFILING
    solver_params.profile_file = "/home/rjt/Devel/Personal/Cubs/family_camp/profile.txt"
    solver_params.export_file = True


    solver = pywrapcp.Solver("Timetable", solver_params)



    slots = [solver.IntVar(0, 1, "x({},{},{})".format(act, sess, grp))
             for act in range(num_acts)
             for sess in range(sessions_by_activity[act])
             for grp in range(num_groups)]


    # List of slots for each activity accross all sessions.
    acts = [slots[act_session_index[act][0]:act_session_index[act][0]+(sessions_by_activity[act]*num_groups)]
            for act in range(num_acts)]

    # List of lists which each element is a list of slots for each session for each activity
    act_sessions = [ [
            slots[act_session_index[act][sess]:act_session_index[act][sess]+num_groups]
                    for sess in range(sessions_by_activity[act]) ]
                    for act in range(num_acts) ]

    # List of lists of Lists in which each element is a list of slots in each session for each group for each activity
    act_groups = [ [ [ slots[ act_session_index[act][sess]+grp ]
                        for sess in range(sessions_by_activity[act]) ]
                        for grp in range(num_groups) ]
                        for act in range(num_acts) ]



    # We build a list of the overlapping sessions. For each of these we find, for each group, all of the possible slots
    # on those overlapping sessions. This can be used to check that a group is not doing something in overlapping
    # sessions.
    #session_groups = [ [[slots[sess*num_groups+grp]
    #        for sess in overlaps[overlap_indx] ]
    #       for grp in range(num_groups) ]
    #       for overlap_indx in range(len(overlaps))]

    session_groups = [[[slots[(overlap_indx*num_groups)+grp]] + [ slots[(sess*num_groups)+grp]
                                                           for sess in overlaps[overlap_indx] ]
                      for overlap_indx in range(len(overlaps)) ]
                      for grp in range(num_groups) ]

    # Get a list of the number of members of each group that want to do each activity.
    members = [ [len(g.activities[act.name]) for g in groups]
               for act in activities ]

    #
    # Setup the allowed assignments for each session. We only allow assignments of families that are valid
    # i.e. they only include groups that actually requested the activity and they do not exceed the allowed
    # activity limit of participants.
    for act in range(len(activities)):
        for sess in range(len(act_sessions[act])):
            solver.AllowedAssignments(act_sessions[act][sess],
                                      activity_selection_options[act])

    # Contraint to ensure that each activity session does not exceed the maximum number of allowed
    # participants. (this is not required if we use the allowed assignments above because they
    # only include sessions schedules that are below the activity limit.
    #for act in range(num_acts):
    #    for session in act_sessions[act]:
    #        solver.Add(solver.ScalProd(session, members[act]) <= activities[act].limit)

    # Constraint to ensure that no family does the same activity twice.
    for act in range(num_acts):
        for group in range(num_groups):
            s = solver.Sum(act_groups[act][group])
            solver.Add(s < 2)

    # Constraint to ensure that no family is doing two things at the same time.
    #for sess in range(len(session_groups)):
    #    for group in range(num_groups):
    #        s = solver.Sum(session_groups[sess][group])
    #        solver.Add(s < 2)
    for group in range(num_groups):
        for sess in range(len(session_groups[group])):
            s = solver.Sum(session_groups[group][sess])
            solver.Add(s < 2)

    #for sess in range(len(session_groups)):
    #        s = solver.Sum(session_groups[sess][group])
    #        solver.Add(s < 2)

    # Constraint to ensure all requested activities have been met.
    act_totals = [0] * num_acts
    act_products = [0] * num_acts
    for act in range(num_acts):
        print("Target: {} = {}".format(activities[act].name, sum(members[act])))
        act_totals[act] = solver.IntVar(0, sum(members[act]), activities[act].name)
        act_products[act] = solver.ScalProd(acts[act], (members[act]*sessions_by_activity[act]))
        solver.Add(act_products[act] == sum(members[act]))
        solver.Add(act_totals[act] == act_products[act].Var())


    # Maximise the total number of allocated sessions

    # list of number of family members that request each activity, expanded as an array
    # to match the slot array, so that they can be multiplied to get the current allocation.
    full_members = [ members[act]*sessions_by_activity[act] for act in range(num_acts)]
    full_members = [ i for j in full_members for i in j] # This just flattens the list of lists.

    total_requested_activities = sum( [ sum(_) for _ in members ])
    total_activities = solver.ScalProd(slots, full_members).Var()
    total = solver.IntVar(0, total_requested_activities*1000, 'totalacts')
    solver.Add(total == total_activities)

    #objective = solver.Maximize(total, 1)

    print('Trying for total of: {}'.format(total_requested_activities))

    limit = solver.SolutionsLimit(1)

    db = solver.Phase(slots,
                        solver.CHOOSE_RANDOM,
                        solver.ASSIGN_MAX_VALUE)

    solution = solver.Assignment()
    solution.Add(slots)
    solution.Add(total)
    solution.Add(act_totals)


    monitor = SearchMonitorTest(solver, slots, act_products)
    logger = solver.SearchLog(1000000)

    collector = solver.LastSolutionCollector(solution)
    solver.Solve(db, [collector, monitor, logger, limit])
    #solver.Solve(db, [objective, collector, monitor, logger, limit])
    #solver.Solve(db, [collector, monitor, limit])

    if collector.SolutionCount() == 1:
        print("total found: {}".format(collector.Value(0, total)))
        act_totals = [int(collector.Value(0, i)) for i in act_totals]
        for act in range(num_acts):
            print("{} = {}".format(activities[act].name, act_totals[act]))

        schedule = [int(collector.Value(0, i)) for i in slots]
        for grp in range(num_groups):
            for act in range(num_acts):
                print("{} - {}:".format(groups[grp].name, activities[act].name),end="")
                for sess in range(sessions_by_activity[act]):
                    print(" X " if schedule[act_session_index[act][sess]+grp] == 1 else " 0 ",end="")
                print("")
            print("")

    # solver.NewSearch(db)
    #
    # #count = 0
    # best = 0
    # num_solutions = 0
    # while solver.NextSolution():
    #     #count += 1
    #     num_solutions += 1
    #     if ((total_activities.Value() > (best + 10) ) or
    #             (total_activities.Value() >= total_requested_activities)):
    #         print("total: {} previous: {} target: {}\n".format(
    #             total_activities.Value(),
    #             best,
    #             total_requested_activities))
    #         best = total_activities.Value()
    #         print('x: {}\n'.format([slots[i].Value() for i in range(len(slots))]))
    #     if ((total_activities.Value() < (best - 10) ) or
    #             (total_activities.Value() >= total_requested_activities)):
    #         print("total: {} previous: {} target: {}\n".format(
    #             total_activities.Value(),
    #             best,
    #             total_requested_activities))
    #         best = total_activities.Value()
    #         print('x: {}\n'.format([slots[i].Value() for i in range(len(slots))]))
    #     #if ((count % 10000) == 0):
    #     #    print(count)
    #     if (total_activities.Value() >= total_requested_activities):
    #         break
    #
    #
    # #print('x: {}\n'.format([slots[i].Value() for i in range(len(slots))]))
    #
    #
    # # if solver.NextSolution():
    # #
    # #     #print("total: {}\n".format(total.Value()))
    # #     #    if num_solutions > 0:
    # #     print('x: {}\n'.format([slots[i].Value() for i in range(len(slots))]))
    # #     print("total: {}\n".format(total_activities.Value()))
    # #
    # #
    # # if solver.NextSolution():
    # #
    # #     #print("total: {}\n".format(total.Value()))
    # #     #    if num_solutions > 0:
    # #     print('x: {}\n'.format([slots[i].Value() for i in range(len(slots))]))
    # #     print("total: {}\n".format(total_activities.Value()))

    #print("total: {}\n".format(total_activities.Value()))
    #print('num_solutions: {}'.format(num_solutions))
    print('failures: {}'.format(solver.Failures()))
    print('branches: {}'.format(solver.Branches()))
    print('WallTime: {}'.format(solver.WallTime(), 'ms'))

    # Save profile in file
    #solver. ExportProfilingOverview()

    solver.EndSearch()


#(activities, sessions, campers, groups) = get_source_data(limit_campers=10)
(activities, sessions, campers, groups) = gen_test_data()

activity_selection_options = [possible_family_arrangements_for_activity(
    activities[_], groups) for _ in range(len(activities))]

find_timetable(activities, activity_selection_options, sessions, campers, groups)