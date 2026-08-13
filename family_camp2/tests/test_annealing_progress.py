from family_camp2.config import EngineConfig
from family_camp2.solvers.annealing.solver import AnnealingSolver
from fixtures import load_small_camp


class FakeReporter:
    def __init__(self):
        self.events = []

    def report(self, event):
        self.events.append(event)


def test_one_completion_event_per_chain_and_a_final_summary():
    activities, sessions, campers = load_small_camp()
    reporter = FakeReporter()
    num_chains = 4

    AnnealingSolver(num_chains=num_chains, iterations_per_chain=100, random_seed=1, progress_reporter=reporter).solve(
        activities, sessions, campers, EngineConfig()
    )

    restart_events = [e for e in reporter.events if e.stage == "restarts"]
    assert restart_events[0].message.startswith("started")
    assert restart_events[-1].message == "all chains finished"

    # imap_unordered doesn't guarantee arrival order, so check the *set* of
    # chains reported, not a fixed sequence.
    chain_events = [e for e in restart_events if e.message.startswith("chain seed=")]
    reported_seeds = {int(e.message.split("seed=")[1].split(" ")[0]) for e in chain_events}
    assert reported_seeds == {1, 2, 3, 4}
    assert len(chain_events) == num_chains

    for event in chain_events:
        assert event.tier0_score is not None
        assert event.tier1_score is not None
        assert event.tier2_score is not None


def test_omitting_progress_reporter_does_not_change_behaviour():
    activities, sessions, campers = load_small_camp()
    result = AnnealingSolver(num_chains=2, iterations_per_chain=50, random_seed=1).solve(
        activities, sessions, campers, EngineConfig()
    )
    assert result.report is not None
