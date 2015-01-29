# coding=utf-8
"""Process Family Camp Bookings.

Usage:
  process_fam_bookings.py [-d]
  process_fam_bookings.py (-h | --help)
  process_fam_bookings.py --version


Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

import sys
import logging
import socket
from docopt import docopt
from oauth2client.client import SignedJwtAssertionCredentials

import bufferingsmtphandler
import gspread
import creds

import camp_records

log = logging.getLogger(__name__)

KEY_FILE = "key.pem"
ACCOUNT = '111027059515-1iafiu8cv4h8m3i664s578vt7pngcsun@developer'\
          '.gserviceaccount.com'


def _main(gc):
    # Connect to booking workbook.
    scope = ['https://spreadsheets.google.com/feeds',
             'https://docs.google.com/feeds']
    SIGNED_KEY = open(KEY_FILE, 'rb').read()
    credentials = SignedJwtAssertionCredentials(ACCOUNT, SIGNED_KEY, scope)
    gc = gspread.authorize(credentials)

    spread = gc.open(camp_records.BOOKING_SPREADSHEET_NAME)

    # Extract the bookings sheet from the workbook.
    bookings = camp_records.Bookings(spread)

    # Look for any booking references that are not on the payment sheet.
    log.debug("Processing invoices ...")
    invoices = camp_records.Invoices(spread)

    nb = bookings._norm
    missing_refs = nb[
        ~nb[camp_records.I_REF].isin(
            invoices.get_booking_refs())].drop_duplicates(
                subset=camp_records.I_REF)[camp_records.I_REF]

    for i, ref in missing_refs.iteritems():
        b_rec = nb[nb[camp_records.I_REF] == ref]
        log.info("Adding booking for: {}".format(
            b_rec[camp_records.FAMILY].iloc[0]))
        invoices.add_booking(
            ref=ref,
            group_name=b_rec[camp_records.FAMILY].iloc[0],
            tel=b_rec[camp_records.TEL].iloc[0],
            email=b_rec[camp_records.EMAIL].iloc[0],
            addr=b_rec[camp_records.ADDR].iloc[0],
            willing_to_help=("Y" if b_rec[camp_records.HELP].iloc[0] == camp_records.WILLING_TO_HELP else "N"),
            need_help=("Y" if b_rec[camp_records.HELP].iloc[0] == camp_records.NEED_HELP else "N"),
            num_adults=len(
                b_rec[b_rec[camp_records.OVER18.format('')] == "Yes"]),
            num_infants=len(
                b_rec[(b_rec[camp_records.OVER18.format('')] != "Yes") &
                      (b_rec[camp_records.AGE.format('')] <= 5)]),
            num_child=len(
                b_rec[(b_rec[camp_records.OVER18.format('')] != "Yes") &
                      (b_rec[camp_records.AGE.format('')] > 5)]),
            num_tents=b_rec[camp_records.TENTS].iloc[0],
            num_caravans=b_rec[camp_records.CARAVANS].iloc[0])

    log.debug("Processing activities ...")
    activities = camp_records.Activities(spread)

    b = bookings._campers
    missing_refs = b[
        ~b[camp_records.I_REF].isin(
            activities.get_booking_refs())].drop_duplicates(
                subset=camp_records.I_REF)[camp_records.I_REF]

    for i, ref in missing_refs.iteritems():
        b_recs = b[b[camp_records.I_REF] == ref]
        for i, b_rec in b_recs.iterrows():
            log.info("Adding camper: {}".format(b_rec[camp_records.FAMILY]))
            activities.add_booking(
                b_rec)

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    if args['--debug']:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    HOST = 'www.thegrindstone.me.uk' \
           if not socket.gethostname() == 'rat' else 'localhost'
    FROM = "rjt@thegrindstone.me.uk"
    TO = "hippysurfer@gmail.com"
    SUBJECT = "Family Camp: process_fam_bookings"
    handler = bufferingsmtphandler.BufferingSMTPHandler(
        HOST, FROM, TO, SUBJECT)
    log.addHandler(handler)

    try:
        # creds needs to contain a tuple of the following form
        #     creds = ('username','password')
        gc = gspread.login(*creds.creds)

        _main(gc)

    except:
        log.error("Uncaught exception.", exc_info=True)
        sys.exit(1)
