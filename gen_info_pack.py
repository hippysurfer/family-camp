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
SUBTITLE = "2017 Family Camp"

ACTS = {
    'Archery (Outdoor and Indoor)':
        'Please meet your instructor by the archery range. (Please wear a top '
        'with long sleeves to protect your arms).',
    'Blindfold Trail':
        'Please meet your instructor at the Blindfold Trail. (You are advised to wear '
        'long trousers, long sleeves and sturdy shoes).',
    'BMX Biking':
        'Please meet your instructor at the BMX track. (You are strongly advised '
        'to ensure all those participating wear long trousers and long sleeves '
        'as it is a loose gravel track). Please note that all BMX riders must be '
        'at least 9 years old.',
    'Canoeing':
        'Please meet your instructor at the river bank. (No valuables i.e. '
        'watches, mobile phones, wallets, keys etc. as these may be lost or '
        'damaged as falling in is always a possibility. Wear old clothes).',
    'Climbing':
        'Please meet your instructor by the entrance to the kitchen. Here the '
        'instructor will issue your safety equipment before taking you to the '
        'Climbing Quarry.',
    'Caving':
        'Please meet your instructor at the man-made caves. (This activity '
        'can be a bit wet and muddy. If possible, please wear old '
        'clothes/waterproof\'s. It is also stony so long trousers are a good '
        'idea).',
    'The Crystal Maze':
        'Please meet your instructor at the Crystal Maze.',
    'Fire Lighting':
        'Please meet at the entrance to the fire area.',
    'Geocaching':
        'Please meet your instructor outside the tuckshop near the gents toilet.',
    'Woodland Craft':
        'Please meet your instructor in the hut near the fire area.'
}

programme = [
    ['Friday', [
        ['8.00pm', 'Flag Break (camp opening ceremony)'],
        ['8:30pm', 'Games']
    ]],
    ['Saturday', [
        ['9.00am', 'Flag Break'],
        ['9.30am-4.30pm', 'Activities'],
        ['5.00pm-6.30pm', 'BBQ and Ice Cream Van'],
        ['6.00pm-7.00pm', 'Tuck shop and 7th Lichfield hoodies shop open'],
        ['7.15pm', 'Flag down'],
        ['7.30pm', 'Campfire (marquee if wet)']
    ]],
    ['Sunday', [
        ['9.00am', 'Flag Break'],
        ['9.30am-1.30pm', 'Activities'],
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
       ['Games', 'Kids bikes'],
       ['Fuel for your fire. (There is no firewood on site)']]

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
    e.append(title2("Welcome to Family Camp."))
    e.append(title2("Let the action begin!!"))

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

    e.append(subtitle('Night Owl Zone'))
    e.append(para('The area at the top of the field (near to the dining area) '
                  'tends to attract groups who stay up later into the night. '
                  'So if you would prefer an earlier night and '
                  'uninterrupted sleep please avoid this area.'))


    e.append(subtitle('Quiet Zone'))
    e.append(para('If you are camped in the Quiet Zone (marked on the map) '
                  'please keep noise to a minimum after 10:00pm.'))

    e.append(subtitle('Friday Evening Activities'))
    e.append(para('At approximately 8.30pm on Friday evening we will have a '
                  'social gathering for everyone, but most especially for '
                  'first timers. If you are new to Family Camp please come '
                  'along to meet others who are in the same '
                  'position. Everyone else is also welcome and we will have '
                  'some activities for those that wish to join in. '
                  'This will be a great way to meet others at the start of '
                  'the camp.'))

    e.append(subtitle("BBQ"))

    e.append(para('The BBQ will be on Saturday evening '
                  'Campers that have requested a vegetarian meal will '
                  'have a raffle ticket in their Welcome Pack. Please take this '
                  'ticket along with you so that the Catering Team know that '
                  'yours is one of the vegetarian meals. If you have other special '
                  'dietary requirements (but do not have a raffle ticket) please '
                  'speak to the Catering Team as soon as possible (well before '
                  'the BBQ) and they will do their best to provide for you. '
                  'The BBQ is an opportunity to gather together for a meal, so '
                  'please bring your tables and chairs, drinks & extra snacks '
                  'up to the BBQ area. We are hoping that an ice-cream van will pay '
                  'us a visit, so have some change ready as '
                  'these are not pre-paid.'))

    e.append(subtitle('Camp Fire'))
    e.append(para('Saturday 7.30pm - 8.30pm. If the weather is dry there '
                  'will be a campfire at the campfire circle. Please come '
                  'along and join in the fun and games. In previous year\'s we have '
                  'invited Beavers/Cubs and Scouts to perform at the campfire. '
                  'Unfortunately, the number of performances has meant that the '
                  'campfire has run on too late for many of the younger children. '
                  'This year we will be refocusing on more traditional Scout campfire '
                  'songs and will endeavour to finish earlier so that everyone can take '
                  'a full part.'))
    e.append(para('At the end of the campfire we will have marshmallows for all that '
                  'wish to toast them on the '
                  'embers. So that this activity can be conducted safely we will '
                  'issue the marshmallows to adults only and you will need to '
                  'supervise your own children while they are close to the fire. '
                  'Please listen carefully to the instructions that will be given at '
                  'the end of the campfire as it will take a little organising to '
                  'ensure that so many children can toast their marshmallows '
                  'in safety.'))

    e.append(PageBreak())

    e.append(subtitle('Flag Break & Flag Down'))
    e.append(para("This is when we all congregate round the flag to receive "
                  "information about camp and to update you on the day’s "
                  "activities. Please see the Programme for times. "
                  "Many campers choose to wear their 7th Lichfield Hoodie or "
                  "T-shirt (and knecker if they are invested). Beavers, Cubs, "
                  "Scouts and Leaders might like to wear uniform for the Sunday "
                  "morning Flag Break."))

    e.append(subtitle('Tuck Shop & 7th Lichfield Shop'))
    e.append(para('There is a tuck shop on site which will open over the '
                  'weekend to purchase souvenirs. There will '
                  'also be an opportunity to purchase or order 7th Lichfield '
                  'T-Shirts, Hoodies, Family Camp Badges and 7th Lichfield '
                  'Camp Blankets. Please remember cash or cheques only. '
                  'Opening hours will be Sat 6.00pm-7:00pm.'))

    e.append(subtitle('Astronomy'))
    e.append(para("We are delighted that the Rosliston Astronomy Group will be joining "
                  "us on Saturday afternoon. They will arrange safe solar viewing "
                  "during daylight and then give us the opportunity to view "
                  "the wider universe as darkness descends. Come along and "
                  "see the universe through first class equipment."))

    e.append(subtitle('Other Activities'))
    e.append(para("Other activities such as pond dipping and "
                  "local walks are available. Information and equipment can "
                  "be sourced from the site managers, so please see them in "
                  "the main office should you require nets or further information."))

    e.append(subtitle('Recycling'))
    e.append(para('Entrust operates a recycling policy at Shugborough, there are '
                  'separate bins for recyclable and non recyclable waste. Please '
                  'ensure that you separate your waste and dispose of it in the correct bins. '))

    e.append(para('Recyclable materials are: all glass, all plastic bottles, '
                  'all cans, all tetrapacks, all foil and all plastic tubs and trays. '
                  'All other waste, including any cardboard waste must be place in the general waste bins. '
                  'For the avoidance of doubt polystyrene food containers and cups must go in general waste. '
                  'Sorting our waste was a major problem for the site last year, lets do the right thing '
                  'this year and recycle our waste responsibly. Thank you for your cooperation.'))

    e.append(subtitle('General Information'))
    e.append(para('The campsite does not permit pets but does allow BBQs '
                  'and fires, providing they are up off the ground. You will need to bring '
                  'your own fuel as there is no firewood on site. There are '
                  'recycling and rubbish bins near the canteen building.'))

    e.append(para('If you have any queries, please do not hesitate to come '
                  'and ask. The Family Camp Committee members will be wearing yellow '
                  'arm bands to help you know who they are. They may not have all the answers '
                  'but they will always be happy to try to help. The Service Team will be '
                  'wearing hiviz neckers. The Service Team are Explorer Scouts that are on '
                  'site for the weekend to help with some of the tasks that need to be '
                  'done. If you need something such as toilet rolls for the loos, the '
                  'Service Team should be able to help. If you need us urgently, '
                  'please call Dave on 07708950547.'))

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
    
    map = Image(MAP_FILE, 17.5 * cm, 24.5 * cm)
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
