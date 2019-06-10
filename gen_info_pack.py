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

TITLE = "7th Lichfield Scout Group"
SUBTITLE = "2019 Family Camp"

ACTS = {
    'Archery (Outdoor and Indoor)':
        'Please meet your instructor by the archery range. (Please wear a top '
        'with long sleeves to protect your arms and tie back long hair). Take a '
        'moment to check your timetable to see if you are meant to be indoor or '
        'outdoor and ensure you join the correct session.',
    'Blindfold Trail':
        'Please meet your instructor at the Blindfold Trail. (You are advised to wear '
        'long trousers, long sleeves and sturdy shoes).',
    'BMX Biking':
        'Please meet your instructor at the BMX track. (You are strongly advised '
        'to ensure all those participating wear long trousers and long sleeves '
        'as it is a loose gravel track). PLEASE NOTE THAT ALL BMX RIDERS MUST BE '
        'AT LEAST 9 YEARS OLD.',
    'Canoeing':
        'Please meet your instructor at the river bank. (No valuables i.e. '
        'watches, mobile phones, wallets, keys etc. as these may be lost or '
        'damaged as falling in is always a possibility. Wear old clothes). '
        'Please note that if smaller children do not fit securely into a buoyancy '
        'aid they will not be allowed to take part.',
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
    'Pond Dipping':
        'Please meet your instructor at the pond, which is behind the gents toilet, '
        'near the Crystal Maze.',
    'Woodland Craft':
        'Please meet your instructor in the hut near the fire area.'
}

programme = [
    ['Friday', [
        ['8.00pm', 'Flag Break (camp opening ceremony)'],
    ]],
    ['Saturday', [
        ['8.45am', 'Flag Break (announcement of badge competition winner)'],
        ['9.00am-1.00pm and 1.30pm-4.30pm', 'Escape Boxes'],
        ['9.30am-4.30pm', 'Activities'],
        ['11.00am-7.00pm', 'Face Painting and Glitter Tattoos'],
        ['2.00pm-11.00pm', 'Astronomy group'],
        ['2.30pm-6.30pm', 'Crazy Golf'],
        ['5.00pm-6.30pm', 'BBQ and Ice Cream Van'],
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
        textColor=colors.black,
        backColor=None,
        wordWrap=None,
        borderWidth=0,
        borderPadding=0,
        borderColor=None,
        borderRadius=None,
        allowWidows=1,
        allowOrphans=0,
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
    leftIndent=0.75 * cm,
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
    leftIndent=0.75 * cm,
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
    e.append(Spacer(0 * cm, 1 * cm))
    e.append(title2("Welcome to Family Camp."))
    e.append(title2("Let the action begin!!"))

    e.append(title2('Programme'))

    for day, acts in programme:
        e.append(subtitle(day))

        table = Table([[tbody(_) for _ in row] for row in acts])
        table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0, -1), (-1, -1), 1 * cm),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            # ('LINEABOVE', (0, 1), (-1, -1), 1, colors.purple),
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

    e.append(para("Participation in activities allocated to Under 5’s will always be "
                  "at the discretion of the Entrust instructor."))

    for name, desc in sorted(ACTS.items(), key=lambda x: x[0]):
        e.append(activity_name(name))
        e.append(activity_desc(desc))

    e.append(PageBreak())

    e.append(subtitle('Camping Arrangements'))
    e.append(para(
        'Please note that the camping arrangements have changed from '
        'previous years due to reorganization of the Shugborough '
        'site. Please see below:-'))

    e.append(subtitle('Night Owl Zone'))
    e.append(para('The area at the bottom of the field to the left of the main entrance is intended '
                  'for groups who stay up later into the night. Please camp as far away as '
                  'possible from the main buildings and the quieter zone if you intend to stay up late.'))

    e.append(para('Please be aware that noise travels a long way on a quiet campsite at night and tent '
                  'walls provide no sound proofing. We want everyone to enjoy their evening and sitting '
                  'around the campfire is a big part of family camp for many of us. But please have '
                  'a thought for those that have gone to bed and for the children that will be listening '
                  'to your late night chat in their sleeping bags.'))

    e.append(subtitle('Quieter Zone'))
    e.append(para('If you are camped in the Quieter Zone (marked on the map) please keep noise to a '
                  'minimum after 10:00pm. Please note that the Family Camp team is not responsible '
                  'or empowered to enforce the quiet policy.'))

    e.append(subtitle("BBQ"))

    e.append(para('The BBQ will be on Saturday evening '
                  'Campers that have requested a vegetarian or gluten free meal will '
                  'have a raffle ticket in their Welcome Pack. Please take this '
                  'ticket along with you so that the Catering Team know that '
                  'yours is one of the vegetarian or gluten free meals. If you have other special '
                  'dietary requirements (but do not have a raffle ticket) please '
                  'speak to the Catering Team as soon as possible (well before '
                  'the BBQ) and they will do their best to provide for you. '
                  'The BBQ is an opportunity to gather together for a meal, so '
                  'please bring your tables and chairs, drinks & extra snacks '
                  'up to the BBQ area. We are hoping that an ice-cream van will pay '
                  'us a visit, so have some change ready as '
                  'these are not pre-paid.'))

    e.append(subtitle('Camp Fire'))
    e.append(para(
        'Saturday 7.30pm - 8.30pm. If the weather is dry there will be a campfire at the '
        'campfire circle. Please come along, with your chairs, to join in with the singing.'))

    e.append(para(
        'At the end of the campfire we will have marshmallows for all that wish to toast them. '
        'So that this activity can be conducted safely it will take place outside the campfire '
        'circle using our backwoods cooking equipment. This will involve the movement of '
        'the hot embers so we ask that you please be patient and listen carefully to any '
        'safety instructions given at the close of the campfire whilst this is organised. '
        'Please note that for additional safety you will need to supervise your own children '
        'so marshmallows will only be issued to adults.'))

    e.append(PageBreak())

    e.append(subtitle('Flag Break & Flag Down'))
    e.append(para("This is when we all congregate round the flag to receive "
                  "information about camp and to update you on the day’s "
                  "activities. Please see the Programme for times. "
                  "Many campers choose to wear their 7th Lichfield Hoodie or "
                  "T-shirt (and knecker if they are invested). Beavers, Cubs, "
                  "Scouts and Leaders might like to wear uniform for the Sunday "
                  "morning Flag Break."))

    e.append(subtitle('Family Camp Badge'))
    e.append(para('Each family group will have a voucher in their pack to obtain a '
                  'Family Camp Badge free of charge. We will be happy to exchange these directly '
                  'after flag breaks on Saturday and Sunday. Additional badges will be available '
                  'to purchase for £1.50 at the same time.'))

    e.append(subtitle('Tuck Shop'))
    e.append(para('There will be a tuck shop in the dining area next to the caterers where '
                  'you will be able to purchase sweets, cakes and soft drinks. This will be '
                  'manned over the weekend by our Scouts who are raising money for overseas adventures.'))

    e.append(subtitle('Astronomy'))
    e.append(para("The Rosliston Astronomy Group will be joining us on Saturday afternoon. "
                  "They will arrange safe solar viewing during daylight along with the opportunity to make "
                  "and launch paper rockets. As darkness descends you will be given the chance to view "
                  "the wider universe through first class equipment."))

    e.append(subtitle('Escape Boxes'))
    e.append(para(
        'If you want to exercise your brain then this could be the activity for you. Solve a '
        'series of problems to find the codes you need to unlock the box. Will you be the first '
        'to get inside to stop the timer? Groups of up to 7 can work on each box allowing '
        'families to work together. This activity will be available on Saturday in the small green '
        'yurt and is suitable for ages 7 and above. If you would like to have a go at this brand '
        'new activity then add your name to the sign-up sheet (location to be advised at flag '
        'break).'))

    e.append(para(
        'Thank you to The Problem Solving Company for loaning us their Escape Boxes.'))

    e.append(subtitle('Face painting and Glitter Tattoos'))
    e.append(para(
        'On site from late Saturday morning will be a Face Painting and Glitter Tattoo Artiste. '
        'Everyone aged 3 and above can go along to get their face painted and/or get a glitter '
        'tattoo of their choice, including one of our very own 7th logo. Children aged 2-3 will be '
        'able to have a design painted on their arm. You will find her at the top of the field '
        'near the large tree with the picnic benches. As this activity marks the skin there are a '
        'number of terms and conditions that we must adhere to. We recommend that you '
        'read them (copy in the pack) before participating. Ultimately the artiste’s decision is '
        'final and we ask that you respect that.'))

    e.append(PageBreak())

    e.append(subtitle('Crazy Golf'))
    e.append(para(
        'To add to the fun there will be a 9 hole Crazy Golf course on site on Saturday '
        'afternoon situated near to the catering block. Challenge your putting skills over holes '
        'that include bunkers, ramps, tunnels and rebound bars to name but a few. This '
        'activity is suitable for all ages. Just turn up to have a go. Parents, please ensure '
        'younger children are supervised.'))

    e.append(subtitle('Recycling'))
    e.append(para('Entrust operates a recycling policy at Shugborough, there are '
                  'separate bins for recyclable and non recyclable waste. Please '
                  'ensure that you separate your waste and dispose of it in the correct bins. '))

    e.append(para('Recyclable materials are: all glass, all plastic bottles, '
                  'all cans, all tetrapacks, all foil and all plastic tubs and trays. '
                  'All other waste, including any cardboard waste must be placed in the general waste bins. '
                  'For the avoidance of doubt polystyrene food containers and cups must go in general waste bins.'))

    e.append(para('There are recycling and rubbish bins near the canteen building.'))

    e.append(subtitle('General Information'))
    e.append(para('The campsite does not permit pets but does allow BBQs '
                  'and fires, providing they are up off the ground. You will need to bring '
                  'your own fuel as there is no firewood on site.'))

    e.append(para('If you have any queries, please do not hesitate to come '
                  'and ask the Family Camp organising team. They may not have all the answers '
                  'but they will always be happy to try to help. '))
    e.append(para('The Service Team will be '
                  'wearing hiviz neckers. The Service Team are Explorer Scouts that are on '
                  'site for the weekend to help with some of the tasks that need to be '
                  'done. If you need something such as toilet rolls for the loos, the '
                  'Service Team should be able to help.'))

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
