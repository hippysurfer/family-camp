
# @functools.lru_cache(maxsize=None)
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


def get_overlapping_sessions(session, sessions):
    """Return a list of sessions from sessions that overlap
    with session."""
    return [_ for _ in sessions
            if (_ != session
                and sessions_overlap(
                    _, session))]