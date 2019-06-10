import logging
import time
import json

log = logging.getLogger(__name__)

import gspread
# from gspread.httpsession import HTTPSession
# from oauth2client.client import SignedJwtAssertionCredentials
from oauth2client.service_account import ServiceAccountCredentials

scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

CREDS = ServiceAccountCredentials.from_json_keyfile_name('FamilyCampScripts.json', scope)

MAX_ATTEMPTS = 1
BACKOFF_FACTOR = 5
CREDS_THRESHOLD = 3


class TimeoutError(Exception):
    pass


def conn():
    return Google()


def retry(func, sheet=None):

    def _wrapper(*args, **kwargs):

        # log.debug("In retry wrapper for func: {} {!r} {!r}: ".format(
        #    func.__name__, args, kwargs))
        attempt = 1
        sleep_time = 1
        while attempt <= MAX_ATTEMPTS:
            try:
                if args and not kwargs:
                    # log.debug("{}({!r},{!r}): ".format(
                    #    func.__name__, args, kwargs))
                    ret = func(*args, **kwargs)
                elif args:
                    # log.debug("{}({!r}): ".format(
                    #    func.__name__, args))
                    ret = func(*args)
                else:
                    # log.debug("{}(): ".format(
                    #    func.__name__))
                    ret = func()

                # log.debug("ret = {!r} ".format(ret))

                break
            except gspread.exceptions.SpreadsheetNotFound:
                log.error("Not found")
                raise
            # except:
            #     if attempt > MAX_ATTEMPTS/2:
            #         log.warning("- retrying - "
            #                  "attempt: {} - delay: {}s".format(
            #                 attempt, sleep_time))
            #
            #         log.warning(
            #             "Caught exception in {} {!r} {!r}: ".format(func.__name__,
            #                                                         args, kwargs),
            #             exc_info=True)
            #
            #     if attempt == MAX_ATTEMPTS:
            #         log.warning("Retries exausted, giving up")
            #         raise
            #
            #
            #     attempt += 1
            #     time.sleep(sleep_time)
            #     sleep_time *= BACKOFF_FACTOR
            #
            #     if attempt > CREDS_THRESHOLD and sheet:
            #         log.warning("Attempting to refresh creds.")
            #         sheet.gc.gc.login()
        return ret

    return _wrapper


class Worksheet():

    def __init__(self, sheet, wks):
        self.sheet = sheet
        self.wks = wks

        self.get_all_values = retry(self.wks.get_all_values, self.sheet)
        self.row_values = retry(self.wks.row_values, self.sheet)
        self.add_rows = retry(self.wks.add_rows, self.sheet)
        self.row_count = self.wks.row_count
        self.col_values = retry(self.wks.col_values, self.sheet)
        self.cell = retry(self.wks.cell, self.sheet)
        self.update_cells = retry(self.wks.update_cells, self.sheet)
        self.update_cell = retry(self.wks.update_cell, self.sheet)


class Sheet():

    def __init__(self, gc, sheet):
        self.gc = gc
        self.sheet = sheet

    def worksheet(self, name):
        return Worksheet(self, retry(self.sheet.worksheet)(name))


class Google:

    def __init__(self):
        self.gc = gspread.authorize(CREDS)

    def open(self, name):
        return Sheet(self, retry(self.gc.open)(name))

    def open_by_key(self, key):
        return Sheet(self, self.gc.open_by_key(key))

    def open_by_ref(self, ref):
        return Sheet(self, retry(self.gc.open)(ref))
