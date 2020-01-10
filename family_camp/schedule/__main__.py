"""Generate Family Camp Timetable.

Example:
  stdbuf -oL -eL python -m scoop -n 8 python -m family_camp/schedule/__main__.py outdir

Usage:
  schedule.py [-d|--debug] refresh
  schedule.py [-d|--debug] generate <outdir>
  schedule.py [-d|--debug] generate <timetable> <outdir>
  schedule.py [-d|--debug] check <timetable>
  schedule.py (-h | --help)
  schedule.py --version

Arguments:

  outdir         Directory to hold results.
  timetable      A csv of an existing timetable.

Options:

  -r,--refresh   Refresh cache from Google Docs
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
import logging
import sys
import docopt

from family_camp.schedule import generate_schedule, check_schedule

log = logging.getLogger(__name__)


def main(args=None):
    """The main routine."""
    if args is None:
        args = sys.argv[1:]

    args = docopt.docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    refresh = args['refresh']

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    if refresh or args['generate']:
        generate_schedule.run(refresh, args)
    elif args['check']:
        check_schedule.run(args['<timetable>'])


if __name__ == "__main__":
    main()
