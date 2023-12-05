"""Fetch data for Family Camp Timetable.

Usage:
  refresh.py [-d|--debug] <google_doc_id>
  refresh.py (-h | --help)
  refresh.py --version

Arguments:

  google_doc_id  ID of the Google Spreadsheet that hold the data.

Options:

  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
import logging
import docopt
from itertools import takewhile, dropwhile



log = logging.getLogger(__name__)

import pickle

try:
    from . import google
except FileNotFoundError:
    print("Failed to load google module.")
except ImportError:
    import google

import logging

log = logging.getLogger(__name__)

CACHE = ".cache.pickle"

def remove_title_rows(table, marker):
    for row in dropwhile(lambda x: x[0] == marker,
                       dropwhile(lambda x: x[0] != marker,
                                 table)):
        yield row

def remove_bad_rows(table):
    """We know that valid rows will always have something in the first column.
    This removes any leading or tailing rows that have empty first columns."""

    for row in takewhile(lambda x: x[0] != "",
                       dropwhile(lambda x: x[0] == "",
                                 table)):
        yield row


def fetch(google_doc_id):
    log.info('Fetching fresh data.')

    gc = google.conn()
    spread = gc.open_by_key(google_doc_id)
    log.info(f'Fetched Family Camp Sheet: "{spread.sheet.title}"')
    acts_wks = spread.worksheet("Activities for schedule").get_all_values()
    session_wks = spread.worksheet("Sessions for schedule").get_all_values()
    campers_wks = spread.worksheet("Activities").get_all_values()

    # Do a bit of tidying up - remove blank rows and headers
    acts_wks = list(remove_bad_rows(remove_title_rows((_ for _ in acts_wks), "Activity")))
    session_wks = list(remove_bad_rows(remove_title_rows((_ for _ in session_wks), "Activity")))
    campers_wks = list(remove_bad_rows(remove_title_rows((_ for _ in campers_wks), "Group Ref")))

    log.info(f'Activities: {len(acts_wks)}, Sessions: {len(session_wks)}, Campers: {len(campers_wks)}')


    log.info(f'Saving to cache: "{CACHE}"')
    pickle.dump((acts_wks, session_wks, campers_wks), open(CACHE, 'wb'))


    log.info('Done. Now run "generate".')

def main():
    """The main routine."""

    args = docopt.docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    fetch(args['<google_doc_id>'])



if __name__ == "__main__":
    main()
