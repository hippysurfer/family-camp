"""Generate Family Camp Timetable.

Example:
  stdbuf -oL -eL python -m scoop -n 8 python -m family_camp/schedule/__main__.py outdir

Usage:
  schedule.py [-d|--debug] generate <outdir>
  schedule.py [-d|--debug] generate <timetable> <outdir>
  schedule.py [-d|--debug] check <timetable> <outdir>
  schedule.py [-d|--debug] print <timetable> <pdf_out_file>
  schedule.py (-h | --help)
  schedule.py --version

Arguments:

  outdir         Directory to hold results ("-" for stdout).
  timetable      A csv of an existing timetable.
  pdf_out_file   File path for output PDF

Options:

  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
import logging
import docopt
from pathlib import Path

from family_camp.schedule import generate_schedule, check_schedule, print_schedule

log = logging.getLogger(__name__)


def main():
    """The main routine."""

    args = docopt.docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    if args['generate']:
        generate_schedule.run(args)
    elif args['check']:
        check_schedule.run(
            args['<timetable>'],
            Path(args['<outdir>']) if args['<outdir>'] != "-" else None)
    elif args['print']:
        print_schedule.run(
            args['<timetable>'],
            args['<pdf_out_file>'])


if __name__ == "__main__":
    main()
