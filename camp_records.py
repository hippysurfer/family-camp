# coding=utf-8
import logging
import functools
import datetime
import pandas as pd


log = logging.getLogger(__name__)


BOOKING_SPREADSHEET_NAME = "Family Camp Bookings"
RESPONSE_SHEET_NAME = "Form responses 9"
INVOICE_SHEET_NAME = "Invoicing"
ACTIVITIES_SHEET_NAME = "Activities"
MAX_NUM_OF_CAMPERS = 10

I_REF = "Group Ref"
I_GROUP = "Group Name"
I_TEL = "Tel"
I_EMAIL = "Email"
I_ADDR = "Address"
I_NEED_HELP = "Need Help"
I_WILLING_TO_HELP = "Willing to Help"
I_ADULTS = "Num. Adults"
I_CHILD = "Num. Children"
I_INFANTS = "Num. Infants"
I_TENTS = "Num. Tents"
I_CARAVANS = "Num. Caravans"

I_FIELDS = [I_REF, I_GROUP, I_TEL, I_EMAIL, I_ADDR,
            I_NEED_HELP, I_WILLING_TO_HELP,
            I_ADULTS, I_INFANTS, I_CHILD, I_TENTS, I_CARAVANS]
I_IDX_OF_FIRST_NON_EMPTY_COLUMN = 14  # Amount Due

# Exact text used in the "willing to help" question.
WILLING_TO_HELP = "We are happy to provide help and advice "\
                  "to another family if they need us."
NEED_HELP = "We would like to have another family on camp to "\
            "support us if we need it."

I_INVOICE_SENT = "Invoice Sent"
I_AMOUNT_DUE =  "Invoiced Total"

REF = "Timestamp"
FAMILY = "Family Name"
EMAIL = "Email Address"
ADDR = "Family Address"
TEL = "Family Telephone Number"
ASSO = "Family Association with 7th Lichfield"
TENTS = "Family Number of Tents"
CARAVANS = "Family Number of Caravans  or Motorhomes"
HELP = "Please indicate if you would like support or if "\
       "you can provide support for another family."
HOME_CONTACT = "Home Contact Name"
HOME_NUMBER = "Home Contact Number"

GROUP_FIELDS = [REF, FAMILY, EMAIL, ADDR, TEL, TENTS,
                CARAVANS, ASSO, HELP, HOME_CONTACT, HOME_NUMBER]

NAME = "First Name{}"
SURNAME = "Surname{}"
DIET = "Dietary Requirements{}"
OVER18 = "Over 18 at the start of the camp?{}"
AGE = "Age at start of camp (if under 18){}"
DBS = "DBS Status (if over 18){}"
PRI = "Primary Activities{}"
OTHER = "Other Activities{}"

BASE_CAMPER_FIELDS = [
    NAME, SURNAME, DIET, OVER18, AGE, DBS, PRI, OTHER]
CAMPER_FIELDS = [field.format('') for field in BASE_CAMPER_FIELDS]

A_IDX_OF_FIRST_NON_EMPTY_COLUMN = 20  # The last activity column

# List of available actvities.
# This must be consistent with the names on the form
# and in the Activities tab on the spreadsheet.


ACTIVITIES = ['Archery',
              'Blindfold Trail',
              'BMX Biking',
              'Canoeing',
              'Caving',
              'Climbing',
              'Crystal Maze',
              'Backward Cooking',
              'Pottery Painting',
              "It's a Knockout"]

A_FIELDS = [I_REF, FAMILY] + CAMPER_FIELDS + ACTIVITIES


def camper_fields(camper):
    return [
        f.format(camper) for f in BASE_CAMPER_FIELDS]


class Bookings(object):
    """Represents the bookings sheet that is populated by the booking form."""

    def __init__(self, gs):
        self._gs = gs
        self._wks = self._gs.worksheet(RESPONSE_SHEET_NAME)

        self._df = pd.DataFrame(data=self._wks.get_all_values()[1:],
                                columns=self._wks.row_values(1))

        self._norm = self._normalize()
        self._campers = self._get_campers()

    def _normalize(self):
        "Take each of the camper field and move them so that we end up with"
        "a row for each camper."

        # Extract each camper.
        campers = [self._df[GROUP_FIELDS+camper_fields(
            " (Camper {})".format(i))] for i in range(1, MAX_NUM_OF_CAMPERS+1)]
        for camper in campers:
            camper.columns = [GROUP_FIELDS+camper_fields('')]

        norm = pd.concat(campers)
        norm.reset_index(drop=True, inplace=True)

        def conv(x):
            try:
                return int(x)
            except:
                return 0
        norm[AGE.format('')] = norm[AGE.format('')].map(conv)

        # Create booking reference column.
        def create_ref(row):
            (d, mo, y) = row[REF].split(' ')[0].split('/')
            (h, mi, s) = row[REF].split(' ')[1].split(':')
            return "{}/{}{}{}{}".format(row[FAMILY], d, mo, h, mi)

        norm[I_REF] = [create_ref(row) for index, row
                       in norm.iterrows()]

        # remove rows where there is no camper
        norm = norm[~((norm[NAME.format('')] == '') &
                      (norm[SURNAME.format('')] == ''))]

        return norm

    def _get_campers(self):
        "Create a table with a row for each camper and columns for the"
        "camper specific information."

        def priority(act, cell):
            if act in [c.strip() for c in cell.split(',')]:
                return 'P'
            return None

        def other(act, cell):
            if act in [c.strip() for c in cell.split(',')]:
                return 'Y'
            return 'N'

        try:
            # Start with just the camper fields.
            campers = self._norm[[I_REF, FAMILY]+CAMPER_FIELDS].copy()

            for activity in ACTIVITIES:
                pri_sequence = campers[PRI.format("")].copy().map(
                    functools.partial(priority, activity))
                other_sequence = campers[OTHER.format("")].copy().map(
                    functools.partial(other, activity))
                pri_sequence[pri_sequence != 'P'] = other_sequence
                campers[activity] = pri_sequence
        except:
            log.error("Failed to create camper table. "
                      "norm tables is {}.".format(
                          self._norm), exc_info=True)

        return campers


def get_next_row(wks, num_active_fields):
    "Return the row number of the next empty row."

    rows = wks.get_all_values()
    empty_row = len(rows)+1
    for i, row in enumerate(rows):
        if row == []:
            # We have reached the end of the sheet and move add a new row.
            wks.add_rows(1)
            empty_row = i+1
            break
        is_empty = (not any(
            row[0:num_active_fields]))
        if is_empty:
            empty_row = i+1
            break

    if empty_row >= wks.row_count:
        wks.add_rows(1)

    return empty_row


class Invoices(object):

    def __init__(self, gs):
        self._gs = gs
        self._wks = self._gs.worksheet(INVOICE_SHEET_NAME)

    def get_booking_refs(self):
        "Return a list of booking refs"
        return self._wks.col_values(I_FIELDS.index(I_REF)+1)[1:]

    def add_booking(self, ref, group_name, tel, email, addr,
                    need_help, willing_to_help, num_adults,
                    num_infants, num_child, num_tents, num_caravans):

        row = get_next_row(self._wks, I_IDX_OF_FIRST_NON_EMPTY_COLUMN)

        # Insert the new records
        cells = []
        insert_list = [ref, group_name, tel, email, addr,
                       need_help, willing_to_help, num_adults,
                       num_infants, num_child, num_tents, num_caravans]
        for idx, val in zip(range(1, len(insert_list)+1),
                            insert_list):
            cell = self._wks.cell(row, idx)
            cell.value = val
            cells.append(cell)

        self._wks.update_cells(cells)

    def invoices_not_yet_sent(self):
        rows = self._wks.get_all_values()
        headers = self._wks.row_values(1)

        return [dict(zip(headers, row)) for row in rows if
                (row[headers.index(I_REF)] != ''
                 and not row[headers.index(I_INVOICE_SENT)])]

    def mark_sent(self, invoice, total):
        rows = self._wks.get_all_values()
        headers = self._wks.row_values(1)

        matches = [i for i, row in enumerate(rows)
                   if row[headers.index(I_REF)] == invoice[I_REF]]

        if len(matches) != 1:
            log.warn("Expected only 1 invoice line with ref {}"
                     " got {} using last one".format(invoice[I_REF],
                                                     len(matches)))
        row = matches[-1]+1
        log.debug("Updateing invoice row: {}".format(row))
        self._wks.update_cell(row, headers.index(I_INVOICE_SENT) + 1,
                              str(datetime.date.today()))
        self._wks.update_cell(row, headers.index(I_AMOUNT_DUE) + 1, total)



class Activities(object):
    def __init__(self, gs):
        self._gs = gs
        self._wks = self._gs.worksheet(ACTIVITIES_SHEET_NAME)

    def get_booking_refs(self):
        "Return a list of booking refs"
        return self._wks.col_values(A_FIELDS.index(I_REF)+1)[1:]

    def get_by_ref(self, ref):
        "Return a list of rows that have matching booking refs."

        #import ipdb
        #ipdb.set_trace()

        return [row for row in self._wks.get_all_values()[1:]
                if row[A_FIELDS.index(I_REF)] == ref]

    def add_booking(self, booking):

        row = get_next_row(self._wks, A_IDX_OF_FIRST_NON_EMPTY_COLUMN)

        # Insert the new records
        cells = []
        for col in A_FIELDS:
            cell = self._wks.cell(row, A_FIELDS.index(col)+1)
            cell.value = booking[col]
            cells.append(cell)
        self._wks.update_cells(cells)
