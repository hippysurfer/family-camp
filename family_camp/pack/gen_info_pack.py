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
import family_camp.schedule.deep as deep

log = logging.getLogger(__name__)

get_source_data = deep.get_source_data
timetable_from_list = deep.timetable_from_list

W, H = A4
TITLE_FONT = "Helvetica-Bold"
TITLE_SIZE = 16
TH_LOGO = "7thlogo.png"
MAP_FILE = "map.png"

TITLE = "7th Lichfield Scout Group"
SUBTITLE = "2023 Family Camp"

ACTS = {
    'Archery (Map Ref 1)':
        'Please meet your instructor by the archery range. (Please wear a top with long '
        'sleeves to protect your arms and tie back long hair) '
        'Please bear in mind the bows used are compound bows which may be a little heavy for some.',
    'Potholing/caving (Map Ref 2)':
        'Please meet your instructor at the man-made caves in the courtyard (This activity can be a bit '
        'wet and muddy. If possible, please wear old clothes/waterproof\'s. It is also stony '
        'so long trousers are a good idea).',
    'Climbing/Abseiling (Map Ref 3)':
        'Please meet your instructors at the climbing wall just to the north of the main courtyard',
    'Air rifle (Map Ref 4)':
        'Please meet your instructor at the rifle range in the courtyard. ' 
        'To participate in the shooting activity you must have completed a "Shooting permission form" and bring it along to ' 
        'the activity with you, this includes adults and children. No form, no shooting! (the form will be included in '
        'the information pack that will be handed to you on arrival at camp)'
        'Please bear in mind also that the rifles are quite heavy and may not be suitable for some.',
    'Zip Wire (Map Ref 5)':
        'Please meet your instructor at the Zip Wire tower to the South of the main courtyard. '
        'all are welcome on the low zip line. To ride the high zip line you must be at least 1.2 metres tall ' 
        'and be at least ten years old.',
    'Spiders Web/Bouldering (Map Ref 6)':
        'Please meet your instructor at the Spiders web/bouldering behind the nothern most building '
        'of the courtyard.',
    'Karts (Map Ref 7)':
        'Please meet your instructor at the carting area to the South West of the courtyard.',
    'Rubber Band Alley (Map Ref 8)':
        'Please meet your instructor in the courtyard adjacent to the air rifle range.',
    'Laser Clay Pigeon':
        'The venue for this activity is subject to weather and will therefore be announced at flag break each day',
    'Escape Boxes - (Map Ref 10)':
        'Meet for this activity in the northernmost building in the courtyard'
}

programme = [
    ['Friday', [
        ['5.00pm', 'Arrival at campsite'],
        ['8.00pm', 'Flag Break (camp opening ceremony)'],
    ]],
    ['Saturday', [
        ['8.45am', 'Flag Break (announcement of badge competition winner)'],
        ['9.30am-4.30pm', 'Activities'],
        ['4.30pm-7.00pm', 'Dinosaur and Prehistoric Show'],
        ['4.30pm-7.00pm', 'Silent Disco'],
        ['5.00pm-6.30pm', 'Hog Roast'],
        ['6.00pm', 'Ice Cream Van'],
        ['7.15pm', 'Flag down'],
        ['7.30pm', 'Campfire (marquee if wet)'],
        ['9.30pm-10:30pm', 'Silent Disco (after campfire)']
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

    e.append(title2("Welcome to Family Camp"))

    e.append(para("We hope that you and your family have a lovely weekend. "))

    e.append(para("This welcome pack should provide you with all of the information that you need "
                  "about the camp. If you have questions or concerns please speak to any of the team or "
                  "your fellow campers."))

    e.append(para("On arrival at camp we will give you a printed copy of this welcome pack "
                  "with a personalised family activity schedule attached. "))

    e.append(para("Please note that your children remain your responsibility throughout the weekend. "))

    e.append(title2("Activities"))
    e.append(para("Below you will find details of all of the activities. Your personalised family schedule "
                  "(which will be handed to you as you arrive on Friday) will tell you which activities you "
                  "are doing and the session times."))

    e.append(para("Please note: an adult member of your family group MUST accompany your child to every activity. "
                  "We do not have supervision arrangements in place to safely supervise unaccompanied children."))

    e.append(para("Please wear suitable footwear for all activities. "
                  "All activities should take approximately 1 hour unless "
                  "stated otherwise. Please note that the times given are "
                  "the activity START time so please be 5 minutes early! "
                  "Please use your map provided for meeting places and "
                  "activities."))

    e.append(para("Participation in activities allocated to Under 5’s will always be "
                  "at the discretion of the site instructor."))

    e.append(para("Please remember that all of the instructors manning the activities "
                  "and everyone else on site over the weekend are volunteers please treat them with "
                  "respect and follow their instructions."))

    for name, desc in sorted(ACTS.items(), key=lambda x: x[0]):
        e.append(activity_name(name))
        e.append(activity_desc(desc))

    e.append(PageBreak())

    e.append(subtitle('Where To Go'))

    e.append(para('Willesley Scout Campsite, Willesley, Ashby-De-La-Zouch, Leicestershire, LE65 2UP.'))

    e.append(para('What three words: https://w3w.co/rebounded.helpfully.payer'))
    e.append(para('Approximate distance/time from Lichfield: 24 miles, 30 - 40 minutes.'))
    e.append(para('From Junction 12 of the A42, follow the B5006 (Measham Road) towards Ashby-de-la-Zouch. As you '
                  'enter Ashby, take a left onto Willesley Road. Follow Willesley Road for 1.5 miles until you reach '
                  'a crossroad. At the cross road, turn left towards Willesley Woodside. '
                  'Follow the lane towards Willesley Woodside and continue until you reach a set of metal bollards and '
                  'a house. Turn left up the narrow track (to the right of the house). Follow this track and do not '
                  'turn off – at the top of the track you will see the entrance to the car park.'))
    e.append(para('Using a Satnav: If you use the postcode, you will be taken to Hicks Lodge Visitor Centre. To get '
                  'from there to the campsite, exit their car park, turn right and follow the road (south) to a '
                  'crossroads. At the crossroad, go straight on until you reach a house on the left. Turn left up '
                  'the narrow track immediately after the house. Follow this track past the scout signs on the trees '
                  'and go through the black gate on the left next to the large campsite sign.'))

    e.append(subtitle('Camping Arrangements'))

    e.append(para('When you arrive at the site you will be instructed as to where you can camp. '
                  'There is a cinder track which leads to the main camping area, if weather conditions are good this is '
                  'ok for vehicles and should be used as the main access to the site. The main campsite is to the left '
                  'and directly ahead of this track. (See Map)'))
    e.append(para(
        'The Quiet Zone camping is further up the main playing field to the right of the track. This will be clearly '
        'marked. Please set up your equipment and then remove your vehicles to the parking area shown on the map '
        'following the route shown.'))
    e.append(para(
        'No Vehicles are allowed to remain on the Campsite as we do not have space for them and they could '
        'potentially get stuck if we have bad weather. Be warned we do not have any towing vehicles if you get '
        'stranded!!'))
    e.append(para(
        'Caravans and  motorhomes: if the weather is good they should camp just at the end of the track and slightly to '
        'the right if the weather makes access difficult then these vehicles should camp on the hard standing ground '
        'to the right of the main entrance. '
        'As with tents, any vehicles accompanying caravans should be parked in the main parking area.'))
    e.append(para(
        'Please at all times obey the instructions of the marshals who will be organising the camping layout on '
        'Friday evening.'))

    e.append(subtitle('Quieter Zone'))
    e.append(para('If you are camped in the Quieter Zone (marked on the map) please keep noise to a '
                  'minimum after 10:00pm. Please note that the Family Camp team is not responsible '
                  'or empowered to enforce the quiet policy.'))

    e.append(subtitle('Site Safety'))
    e.append(para(
        'The site is a safe site for children to play in and there is no restriction on where they can '
        'roam when activities are not running.  However there is water nearby at Willesley fisheries, albeit '
        'seperated by a fence from the site. Please remember that as parents or carers, you are responsible '
        'for your children this weekend, so it might be sensible upon your arrival to walk the '
        'site with them and agree with them what is acceptable and what areas are "no go" zones.'))

    e.append(subtitle("Hog Roast"))

    e.append(para('The Hog Roast will be on Saturday evening. The cost of the Hog Roast is included in your camp fee. '
                  'Campers that have requested a vegetarian '
                  'or gluten free meal will have a raffle ticket in their Welcome Pack.  This ticket is redeemable at '
                  'the normal food stall and not the Hog Roast stall. Please bring '
                  'this ticket along with you to claim your dietary option. '
                  'The Hog Roast event is an opportunity to gather together for a meal, so please '
                  'bring your tables and chairs, drinks & extra snacks up to the courtyard area. We are '
                  'hoping that an ice-cream van will pay us a visit, so have some money ready as '
                  'these are not pre-paid.'))

    e.append(subtitle('Camp Fire'))
    e.append(para(
        'Saturday 7.30pm - 8.30pm. If the weather is dry there will be a campfire at the '
        'campfire circle. Please come along, with your chairs, to join in with the singing.'))

    e.append(para(
        'At the end of the campfire we will have marshmallows for all that wish to toast '
        'them. So that this activity can be conducted safely it will take place outside the '
        'campfire circle using our backwoods cooking equipment. This will involve the '
        'movement of the hot embers so we ask that you please be patient and listen '
        'carefully to any safety instructions given at the close of the campfire whilst this '
        'is organised. Please note that for additional safety you will need to supervise '
        'your own children so marshmallows will only be issued to adults.'))

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
                  'to purchase for £1.50 at the same time. We can only accept card payments for this.'))

    e.append(subtitle('Tuck Shop'))
    e.append(para('There will be a tuck shop in the courtyard area where '
                  'you will be able to purchase sweets, cakes and soft drinks. This will be '
                  'manned over the weekend by our Scouts who are raising money for overseas adventures.'))
    e.append(para('There is also a site shop that will be open at times over the weekend '
                  'that sells camp site badges, woggles and some toys etc. NOTE: the site shop does not sell food.'))

    e.append(subtitle('Dinosaur and Prehistoric Show'))
    e.append(para('Enjoy a fun filled presentation of live animals and discover their prehistoric relatives '
                  'Live animals will be available to interactive with in this exciting and fascinating show. '
                  'Beware, there may be spiders! The venue for this event will be weather dependant and will '
                  'be announced at flag break.'
                  ))

    e.append(subtitle('Silent Disco'))
    e.append(para('New for 2023! Come along and bop till you drop at our Silent Disco. Three channels of music '
                  'will cater for all tastes from kiddies tunes through Pop to Dance Music. So it your musical '
                  'taste is Baby Shark, Rock Lobster or Big Fish, Little Fish you will find the groove '
                  "you need in the 7th's dance palace. P.S. Dad Dancing is encouraged."
                  ))
    e.append(para('The silent disco will be in the courtyard buildings.'))
    e.append(para('Please do not remove the headphones from the disco.'))

    e.append(subtitle('Bikes'))

    e.append(para('The Vehicle-free site is an excellent area for your children to play and ride bikes, so '
                  'if you have room don\'t forget to bring your bikes with you'))

    e.append(PageBreak())

    e.append(subtitle('Recycling'))
    e.append(para('The site does not have separate bins for recycling. There is a single skip at the top end of '
                  'the car park. We understand that the site pay for a sorting service that will sort the skip after '
                  'collection.'))

    e.append(subtitle('General Information'))
    e.append(para('The campsite does not permit pets but does allow BBQs '
                  'and fires, providing they are up off the ground and standing on the slabs provided. '
                  'You will need to bring your own fuel as there is no firewood on site.'))
    e.append(para('Any fire pits must be placed on four paving slabs, which will be laid out by the site in '
                  'different areas prior to our arrival. This is something the site is very clear about so please '
                  'comply with their request. We hope that families will gather together in the evening around '
                  'shared fires.'))
    e.append(para('Please ensure that you have a small first aid kit with you to deal with minor cuts, '
                  'grazes or stings which may happen over the course of the weekend. There will be first '
                  'aiders on site, but they are also on camp with their families. Please only ask for assistance if '
                  'the matter is more serious than above.'))

    e.append(para('If you have any queries, please do not hesitate to come '
                  'and ask the Family Camp organising team. They may not have all the answers '
                  'but they will always be happy to try to help. '))
    e.append(para('The Service Team will be '
                  'wearing hiviz neckers. The Service Team are older Scouts that are on '
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
