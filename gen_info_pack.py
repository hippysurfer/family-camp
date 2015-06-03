#!/usr/bin/env python
# coding: utf-8
"""Create PDF for individual family's Timetable.

Usage:
  family2pdf.py [-d|--debug] DIR
  family2pdf.py (-h | --help)
  family2pdf.py --version

Arguments:
  DIR     output directory.

Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Image,
    Paragraph,
    Spacer,
    PageBreak)
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from docopt import docopt
import csv
import logging
log = logging.getLogger(__name__)

from deep import get_source_data, timetable_from_list

W, H = A4
TITLE_FONT = "Helvetica-Bold"
TITLE_SIZE = 16
TH_LOGO = "7thlogo.png"
MAP_FILE = "map.png"

TITLE = "7th Lichfield Family Camp"
SUBTITLE = "2015 Family Camp"

ACTS = {
    'Archery (Outdoor and Indoor)':
    'Please meet your instructor by the archery range. (Please wear a top '
    'with long sleeves to protect your arms).',
    'Blindfold Trail':
    'Please meet your instructor at the flag. (You are advised to wear '
    'long trousers, long sleeves and sturdy shoes).',
    'BMX Biking':
    'Please meet your instructor at the BMX track. (You are strongly advised '
    'to ensure all those participating wear long trousers and long sleeves '
    'as it is a loose gravel track).',
    'Canoeing':
    'Please meet your instructor at the river bank. (No valuables i.e. '
    'watches, mobile phones, wallets, keys etc. as these may be lost or '
    'damaged as falling in is always a possibility. Wear old clothes).',
    'Caving':
    'Please meet your instructor at the man-made caves. (This activity '
    'can be a bit wet and muddy. If possible, please wear old '
    'clothes/waterproof\'s. It is also stony so long trousers are a good '
    'idea).',
    'Climbing Quarry':
    'Please meet your instructor in the climbing quarry.',
    'Climbing Tower':
    'Please meet your instructor by the climbing tower. (Note that the '
    'climbing tower is not on the map - head for the BMX track and you '
    'will see the climbing tower).',
    'The Crystal Maze':
    'Please meet your instructor at the flag.',
    'Pottery Painting':
    'Please wait outside the large Yurt.',
    'Fire Lighting':
    'Please meet at the entrance to the fire area.',
    "It’s a Knockout":
    'Please meet your instructor at the flag.',
}

programme = [
    ['Friday', [
        ['8.00pm', 'Flag Break (camp opening ceremony)'],
        ['8:30pm', 'Games']
    ]],
    ['Saturday', [
        ['8.40am', 'Flag Break'],
        ['9.00am-5.00pm', 'Site staff led Activities'],
        ['5.15pm-6.00pm', 'BBQ'],
        ['7.00pm-7.30pm', 'Tuck shop and 7th shop open'],
        ['7.45pm', 'Flag down'],
        ['8.00pm', 'Campfire (marquee if wet)']
    ]],
    ['Sunday', [
        ['8.40am', 'Flag Break'],
        ['9.00am-1.30pm', 'Activities'],
        ['1.40pm', 'Flag down (camp closing ceremony)'],
        ['2.00pm-4.00pm', 'Packing away and vacate site']
    ]]
]

KIT = [['Tent', 'Mallet'],
       ['Ground sheet', 'Airbed/ Karrimat'],
       ['Sleeping bags', 'Extra blanket'],
       ['Pillows', 'Folding chairs'],
       ['Fold up table',
        'Light (there is no electricity point provided on the field)'],
       ['Torch (batteries?)', 'Cooler box with ice packs'],
       ['Cooking gas (or use the on-site catering)', 'Pans'],
       ['Washing up liquid/ scourer', 'Water container'],
       ['Cooking utensils (corkscrew, sharp knife, can opener, wooden spoon)',
        'Matches'],
       ['Plates/cups/bowls/tumblers', 'Cutlery'],
       ['J-Cloths', 'Tea towels'],
       ['Bin liners', 'Food (Breakfast x2, Lunch x2, accompaniments '
        'for bbq on Sat eve, snacks, drinks)'],
       ['Clothes', 'Beaver/cub/scout uniform'],
       ['Wellies (hopefully not!)', 'Kagools (likewise)'],
       ['Toiletries', 'First aid kit'],
       ['Towels', 'Sunblock'],
       ['Insect repellent', 'Tissues'],
       ['Games', 'Kids bikes']]

styles = {
    'default': ParagraphStyle(
        'default',
        fontName='Times-Roman',
        fontSize=10,
        leading=12,
        leftIndent=0,
        rightIndent=0,
        firstLineIndent=0,
        alignment=TA_LEFT,
        spaceBefore=0,
        spaceAfter=0,
        bulletFontName='Times-Roman',
        bulletFontSize=10,
        bulletIndent=0,
        textColor= colors.black,
        backColor=None,
        wordWrap=None,
        borderWidth= 0,
        borderPadding= 0,
        borderColor= None,
        borderRadius= None,
        allowWidows= 1,
        allowOrphans= 0,
        textTransform=None,  # 'uppercase' | 'lowercase' | None
        endDots=None,         
        splitLongWords=1,
    )}
    
styles['Title'] = ParagraphStyle(
    'Title',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=22,
    spaceBefore=0,
    spaceAfter=6,
    leading=30,
    alignment=TA_CENTER,
    textColor=colors.purple,
)
styles['Title2'] = ParagraphStyle(
    'Title2',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=18,
    spaceBefore=0,
    spaceAfter=6,
    leading=30,
    alignment=TA_CENTER,
    textColor=colors.purple,
)
styles['Subtitle'] = ParagraphStyle(
    'SubTitle',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=14,
    spaceBefore=4,
    spaceAfter=1,
    leading=24,
    alignment=TA_LEFT,
    textColor=colors.purple,
)
styles['ActName'] = ParagraphStyle(
    'ActName',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=12,
    spaceBefore=3,
    spaceAfter=1,
    leftIndent=1 * cm,
    leading=20,
    alignment=TA_LEFT,
    textColor=colors.purple,
)
styles['ActDesc'] = ParagraphStyle(
    'ActDesc',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=10,
    spaceBefore=0,
    spaceAfter=1,
    leftIndent=2 * cm,
    leading=10,
    alignment=TA_LEFT,
    textColor=colors.black,
)

styles['Body'] = ParagraphStyle(
    'Body',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=11,
    spaceBefore=2,
    spaceAfter=2,
    leftIndent= 0.75 * cm,
    leading=14,
    alignment=TA_JUSTIFY,
    textColor=colors.black,
)

styles['BodySmall'] = ParagraphStyle(
    'BodySmall',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=9,
    spaceBefore=2,
    spaceAfter=2,
    leftIndent= 0.75 * cm,
    leading=14,
    alignment=TA_JUSTIFY,
    textColor=colors.black,
)

styles['TBody'] = ParagraphStyle(
    'TBody',
    parent=styles['default'],
    fontName='Helvetica-Bold',
    fontSize=12,
    spaceBefore=2,
    spaceAfter=2,
    leftIndent=0,
    leading=14,
    alignment=TA_LEFT,
    textColor=colors.black,
)


def pageTemplate():
    def familyTemplate(canvas, doc):
        canvas.saveState()
        canvas.drawImage(TH_LOGO, 1 * cm, H - 4.5 * cm,
                         width=5 * cm, height=5 * cm, mask=None,
                         preserveAspectRatio=True)

        canvas.setFont(TITLE_FONT, TITLE_SIZE)
        canvas.drawCentredString(W / 2.0, H - 1.3 * cm, TITLE)
        canvas.setFont(TITLE_FONT, TITLE_SIZE)
        canvas.drawCentredString(W / 2.0, H - 2 * cm, SUBTITLE)
        canvas.restoreState()

    return familyTemplate


def title(text):
    return Paragraph(text, styles['Title'])


def title2(text):
    return Paragraph(text, styles['Title2'])


def subtitle(text):
    return Paragraph(text, styles['Subtitle'])


def activity_name(text):
    return Paragraph(text, styles['ActName'])


def activity_desc(text):
    return Paragraph(text, styles['ActDesc'])


def para(text):
    return Paragraph(text, styles['Body'])

def para_small(text):
    return Paragraph(text, styles['BodySmall'])


def tbody(text):
    return Paragraph(text, styles['TBody'])


def gen_story(doc):
    e = []
    e.append(Spacer(0*cm, 1*cm))
    e.append(title2("Welcome to this year's family camp."))
    e.append(title2("We hope that you have a great weekend!!"))

    e.append(title2('Programme'))

    for day, acts in programme:
        e.append(subtitle(day))

        table = Table([[tbody(_) for _ in row] for row in acts])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0, -1), (-1, -1), 1 * cm),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            #('LINEABOVE', (0, 1), (-1, -1), 1, colors.purple),
            ]))
        e.append(table)

    e.append(PageBreak())

    e.append(title2("Activities"))
    e.append(para("Please find enclosed details of when your chosen "
                  "activities will be taking place and information "
                  "about other events that are available, should you "
                  "require them, during the weekend. "))

    e.append(para("Please wear suitable footwear for all activities "
                  "and remember that all children must be supervised. "
                  "All activities should take approximately 1 hour unless "
                  "stated otherwise. Please note that the times given are "
                  "the activity START time so please be 5 minutes early! "
                  "Please use your map provided for meeting places and "
                  "activities."))

    for name, desc in sorted(ACTS.items(), key=lambda x: x[0]):
        e.append(activity_name(name))
        e.append(activity_desc(desc))

    e.append(PageBreak())

    e.append(subtitle('Friday Evening Games'))
    e.append(para('Approximately 8.30pm on Friday evening we play a '
                  'traditional game for all who wish to take part. A '
                  'great way to meet others and take part in a scouting '
                  'favourite.'))

    e.append(subtitle("BBQ"))

    e.append(para('We will be serving hotdogs and burgers from '
                  '5.15pm – 6pm (approx) on Saturday evening '
                  '(see your timetable for your family\'s allocated time). '
                  'Please adhere to your allotted time slot to reduce queuing '
                  'times. Vegetarian & special diets alternatives are '
                  'available.'))
    e.append(para('The BBQ is an opportunity to gather together for a meal, so '
                  'please bring your tables and chairs, drinks & extra snacks '
                  'up to the bbq area. If conditions are wet we will use '
                  'indoor facilities. We are expecting an ice-cream van to pay '
                  'us a visit around 6pm so maybe have some change ready as '
                  'these are not pre-paid.'))
    e.append(para('After the BBQ join us to cut cake to celebrate 20 years of '
                  'family camp!'))

    e.append(subtitle('Camp Fire'))
    e.append(para('Saturday 8.00pm -9.00pm. If the weather is dry there '
                  'will be a campfire at the campfire circle. Please come '
                  'along and join in the fun and games. All children must '
                  'be supervised. If wet, this activity will take place '
                  'indoors.'))

    e.append(subtitle('Flag Break & Flag Down'))
    e.append(para("This is when we all congregate round the flag to receive "
                  "information about camp and to update you on the day’s "
                  "activities. If running a wet program we will hold this "
                  "indoors. Fri 8.00pm, Sat 8.40am, Sat 7.45pm, Sun 8.40am and "
                  "Sun 1.40pm."))

    e.append(subtitle('Tuck Shop'))
    e.append(para('There is a tuck shop on site which will open over the '
                  'weekend to purchase souvenirs. There will also be an '
                  'opportunity to have a look at 7th Lichfield t-shirts and '
                  'hoodies etc, all available to try and order. There will '
                  'also be an opportunity to purchase/order 7th Lichfield '
                  'hoodies. Please remember cash or cheques only for the Tuck '
                  'Shop/ hoodies. Opening hours will be Sat 7.00pm-7:30pm'))

    e.append(subtitle('Other activities'))
    e.append(para("Other activities such as orienteering, pond dipping and "
                  "local walks are available. Information and equipment can "
                  "be sourced from the site managers, so please see them in "
                  "the main office should you wish to do any of the above."))

    e.append(subtitle('General Information'))
    e.append(para('The campsite does not permit pets but does allow barbeques '
                  'and fires, providing they are up off the ground.'))

    e.append(para('If you have any queries, please do not hesitate to come '
                  'and ask. If you need us urgently, please call Carl on '
                  '07988685378.'))

    e.append(para('We hope you have a great weekend!'))

    # Kit list.

    e.append(PageBreak())

    e.append(title2('Suggested Kit List for Family Camp'))
    e.append(para("The following is just a suggested list of items that you "
                  "may find useful to take to camp."))

    kit_table = Table([[tbody(_) for _ in row] for row in KIT])
    kit_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, 0), 0.5 * cm),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEABOVE', (0, 1), (-1, -1), 1, colors.purple),
        ]))
    e.append(kit_table)

    # Map
    e.append(PageBreak())

    e.append(title2('Site Map'))
    
    map = Image(MAP_FILE, 16 * cm, 23 * cm)
    e.append(map)

    return e


def gen_pdf(filename):
    doc = SimpleDocTemplate(filename, pagesize=A4,
                            topMargin=3.25 * cm, bottomMargin=0)

    e = gen_story(doc)

    # write the document to disk
    doc.build(e, onFirstPage=pageTemplate(),
              onLaterPages=pageTemplate())


if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    level = logging.DEBUG if args['--debug'] else logging.INFO
    logging.basicConfig(level=level)
    log.debug("Debug On\n")

    out_dir = args['DIR']

    gen_pdf("{}/info_pack.pdf".format(out_dir))
