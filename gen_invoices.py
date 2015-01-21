# coding=utf-8
"""Process Family Camp Invoices.

Usage:
  gen_invoices.py [-d]
  gen_invoices.py (-h | --help)
  gen_invoices.py --version


Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
import os
import smtplib
import sys
import socket
from docopt import docopt
import gspread
import creds
import camp_records as cr
import logging
from InvoiceGenerator.generator import Address, Item, Invoice, Remittance

log = logging.getLogger(__name__)

from email import encoders
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

HOSTNAME = 'www.thegrindstone.me.uk' \
           if not socket.gethostname() == 'rat' else 'localhost'
FROM = "7th Lichfield Family Camp <noreply-familycamp@thegrindstone.me.uk>"
#FROM = "7th Lichfield Family Camp <7th.family.camp@gmail.com>"
COPY_TO = "7th.family.camp@gmail.com"

def send_email_with_attachment(subject, body_text, to_emails,
                               cc_emails, bcc_emails, file_to_attach):
    """
    Send an email with an attachment
    """
    header = ['Content-Disposition',
              'attachment; filename="{}"'.format(file_to_attach)]

    # create the message
    msg = MIMEMultipart()
    msg["From"] = FROM
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    if body_text:
        msg.attach(MIMEText(body_text))

    msg["To"] = ', '.join(to_emails)
    msg["cc"] = ', '.join(cc_emails)

    attachment = MIMEBase('application', "octet-stream")
    try:
        with open(file_to_attach, "rb") as fh:
            data = fh.read()
        attachment.set_payload(data)
        encoders.encode_base64(attachment)
        attachment.add_header(*header)
        msg.attach(attachment)
    except IOError:
        log.error("Error opening attachment file {}".format(file_to_attach),
                  exc_info=True)

    emails = to_emails + cc_emails

    server = smtplib.SMTP(HOSTNAME)
    server.sendmail(FROM, emails, msg.as_string())
    server.quit()


def make_invoice(booking):
    client = Address()
    client.firstname = "Group Name: {}".format(booking[cr.I_GROUP])
    client.lastname = ""
    client.address = ""
    client.city = ""
    client.zip = ""
    client.phone = "Contact Tel: {}".format(booking[cr.I_TEL])
    client.email = "Contact Email: {}".format(booking[cr.I_EMAIL])
    client.bank_name = ""
    client.bank_account = ""
    client.note = "Please pay."

    provider = Address()
    provider.firstname = "Family"
    provider.lastname = "Camp"
    provider.address = "7th Lichfield Scout Group"
    provider.city = "Lichfield"
    provider.zip = ""
    provider.phone = ""
    provider.email = "familycamp@7thlichfield.org.uk"
    provider.bank_name = "Please see remittance slip below."
    provider.bank_account = ""
    provider.note = ""

    item1 = Item()
    item1.name = "Campers (Over 18)".format()
    item1.count = float(booking[cr.I_ADULTS])
    item1.price = 24

    item2 = Item()
    item2.name = "Campers (Under 18)"
    item2.count = float(booking[cr.I_CHILD])
    item2.price = 24

    item3 = Item()
    item3.name = "Campers (Infants)"
    item3.count = float(booking[cr.I_INFANTS])
    item3.price = 0

    remittance = Remittance()
    remittance.reference = booking[cr.I_REF]
    remittance.message = "Payment must be made by cheque.\n" \
                         "Please print out this slip and place it in a "\
                         "sealed envelope with the cheque. \nAddress the "\
                         "envelope to Family Camp and post it in the box at the "\
                         "Scout Hut. \n\n" \
                         "Alternatively, if you do not routinely visit "\
                         "the Scout Hut you can send the envelope\nto the "\
                         "following address:\n\n"\
                         "7th Lichfield Family Camp\n"\
                         "41 Burton Old Road West\n"\
                         "Lichfield WS13 6EN\n\n"\
                         "Please make the cheque payable to: 7th Lichfield "\
                         "Scout Group."
    remittance.total = item1.total() + item2.total() + item3.total()

    invoice = Invoice()
    invoice.setClient(client)
    invoice.setProvider(provider)
    invoice.setTitle("7th Lichfield Family Camp 2015")
    invoice.setVS(booking[cr.I_REF])
    invoice.setCreator("Family Camp Booking")
    invoice.addItem(item1)
    invoice.addItem(item2)
    invoice.addItem(item3)
    invoice.setPaytype("Cheque only.")
    invoice.setRemittance(remittance)
    invoice.currency_locale = 'en_US.UTF-8'

    filename = "{}.pdf".format(
        booking[cr.I_REF].replace('/', '_'))
    f = open(filename, "bw")
    f.write(bytes(invoice.getContent()))
    f.close()

    return (filename, remittance.total)


def get_camper_age(camper):
    if camper[cr.A_FIELDS.index(cr.OVER18.format(""))] == "Yes":
        return "Over 18"
    else:
        return camper[cr.A_FIELDS.index(cr.AGE.format(""))]


def get_booking_details(campers, invoice):
    A_FIELDS = cr.A_FIELDS
    ret = []
    for camper in campers.get_by_ref(invoice[cr.I_REF]):
        ret.append("\n".join([
            "{} {} \n".format(
                camper[A_FIELDS.index(cr.NAME.format(""))],
                camper[A_FIELDS.index(cr.SURNAME.format(""))]),
            "   Dietary Requirements: {}".format(
                camper[A_FIELDS.index(cr.DIET.format(""))]),
            "   Age: {}".format(get_camper_age(camper)),
            "   Priority Activites: {}".format(
                camper[A_FIELDS.index(cr.PRI.format(""))]),
            "   Other Activites: {}".format(
                camper[A_FIELDS.index(cr.OTHER.format(""))])]))

    return "\n\n".join(ret)


def _main(gs):

    # Connect to booking workbook.
    spread = gc.open(cr.BOOKING_SPREADSHEET_NAME)

    # Fetch Invoice Data.
    log.debug("Processing invoices ...")
    invoices = cr.Invoices(spread)
    campers = cr.Activities(spread)

    # Get list of rows which have not yet been sent.
    pending_invoices = invoices.invoices_not_yet_sent()

    # Generate invoices and send emails
    for invoice in pending_invoices:
        (filename, total) = make_invoice(invoice)
        send_email_with_attachment(
            "Family Camp Invoice  - {}".format(invoice[cr.I_REF]),
            ''.join(
                ["Thank you for booking your place at Family Camp.\n\n",
                 "Camper Details:\n\n",
                 get_booking_details(campers, invoice),
                 "\n\nPlease find your invoice attached and note that your",
                 " place is not confirmed until we have received payment.\n\n",
                 "Please send any queries to familycamp@7thlichfield.org.uk.",
                 "Yours in Scouting.\n\n7th Lichfield Social Team."]),
            [invoice[cr.I_EMAIL]],
            [COPY_TO], [COPY_TO], filename)
        # Update invoice sheet.
        invoices.mark_sent(invoice, total)




if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    if args['--debug']:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    # creds needs to contain a tuple of the following form
    #     creds = ('username','password')
    gc = gspread.login(*creds.creds)

    _main(gc)
