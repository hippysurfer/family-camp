from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.tiers import UnmetOptionalRequest, find_unmet_optional_requests, score_tier1, score_tier2

DAY = datetime(2026, 8, 1)


def activity(name, minutes=60, min_occ=1, max_occ=10):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ)


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_tier1_camper_with_no_optional_requests_contributes_one():
    c = camper("Kid")  # no optional requests at all
    tt = Timetable()
    assert score_tier1(tt, [c]) == 1.0


def test_tier1_fully_satisfied_camper_contributes_one():
    craft = activity("Craft")
    c = camper("Kid", optional=(craft,))
    s = session(craft, "A", 10)
    tt = Timetable().with_assignment(c, s)
    assert score_tier1(tt, [c]) == 1.0


def test_tier1_partially_satisfied_camper_contributes_fraction():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    c = camper("Kid", optional=(craft, canoeing))
    s = session(craft, "A", 10)
    tt = Timetable().with_assignment(c, s)
    assert score_tier1(tt, [c]) == 0.5


def test_tier1_fairness_one_request_vs_five_requests_both_fully_met_score_equally():
    acts = [activity(f"Act{i}") for i in range(5)]
    frugal = camper("Frugal", optional=(acts[0],))
    greedy = camper("Greedy", optional=tuple(acts))

    tt = Timetable()
    tt = tt.with_assignment(frugal, session(acts[0], "A", 9))
    for i, a in enumerate(acts):
        tt = tt.with_assignment(greedy, session(a, "A", 9 + i))

    assert score_tier1(tt, [frugal]) == score_tier1(tt, [greedy]) == 1.0


def test_tier2_single_session_activity_excluded_from_score():
    craft = activity("Craft")
    s = session(craft, "A", 10)
    tt = Timetable()
    assert score_tier2(tt, [s]) == 0.0


def test_tier2_even_spread_scores_lower_than_uneven_spread():
    craft = activity("Craft", max_occ=10)
    s1 = session(craft, "A", 9)
    s2 = session(craft, "B", 14)

    campers = [camper(f"K{i}") for i in range(4)]

    even = Timetable()
    even = even.with_assignment(campers[0], s1).with_assignment(campers[1], s1)
    even = even.with_assignment(campers[2], s2).with_assignment(campers[3], s2)

    uneven = Timetable()
    for c in campers:
        uneven = uneven.with_assignment(c, s1)

    assert score_tier2(even, [s1, s2]) < score_tier2(uneven, [s1, s2])
    assert score_tier2(even, [s1, s2]) == 0.0


def test_find_unmet_optional_requests_reports_the_missing_camper_activity_pairs():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    c = camper("Kid", optional=(craft, canoeing))
    tt = Timetable().with_assignment(c, session(craft, "A", 10))

    unmet = find_unmet_optional_requests(tt, [c])

    assert unmet == [UnmetOptionalRequest(c, canoeing)]


def test_find_unmet_optional_requests_empty_when_fully_satisfied():
    craft = activity("Craft")
    c = camper("Kid", optional=(craft,))
    tt = Timetable().with_assignment(c, session(craft, "A", 10))

    assert find_unmet_optional_requests(tt, [c]) == []


def test_find_unmet_optional_requests_ignores_priorities():
    craft = activity("Craft")
    c = camper("Kid", priorities=(craft,))  # never assigned, but it's a priority not optional
    tt = Timetable()

    assert find_unmet_optional_requests(tt, [c]) == []
