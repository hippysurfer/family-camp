"""Test Register for Family Camp Bookings.

Usage:
  test_register_family.py
  test_register_family.py <email> <adults> <children> <infants>


Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

from splinter import Browser
from time import sleep
import datetime
import random

from docopt import docopt

ACTIVITIES = ['Archery',
              'Blindfold Trail',
              'BMX Biking',
              'Canoeing',
              'Caving',
              'Climbing',
              'Crystal Maze',
              'Fire Lighting',
              'Pottery Painting',
              "It's a Knockout"]

URL = "https://docs.google.com/forms/d/1v-m3d7kMGW8QXxFaqMRQf7sZk66BsMWy1m52NWMuRaU/viewform"


def fill_camper(browser, NAME, camper_no, age_type=None):
    age_type = age_type if age_type is not None else random.choice(("adult", "child", "infant"))

    browser.find_by_xpath(
        '//input[starts-with(@aria-label,"First Name (Camper {})")]'
        ''.format(camper_no)).fill("First {}".format(camper_no))
    browser.find_by_xpath(
        '//input[starts-with(@aria-label,"Surname (Camper {})")]'
        ''.format(camper_no)).fill(NAME)
    browser.find_by_xpath(
        '//input[starts-with(@aria-label,"Dietary Requirements (Camper {})")]'
        ''.format(camper_no)).fill(random.choice(("None","Vegy","Vegan")))

    if (age_type == "adult"):
        browser.find_by_xpath(
            '//div[@class="ss-form-entry"]//input[@value="Adult (over 18 years)"]'
            '[./../../../../../label/div[contains(.,"Camper {}")]]'.format(camper_no)).click()
        browser.find_by_xpath(
            '//select[starts-with(@aria-label,"DBS Status")]').select(
                random.choice(('Pending', 'Received', 'Unknown', 'None')))
    elif (age_type == "child"):
        browser.find_by_xpath(
            '//div[@class="ss-form-entry"]//input'
            '[@value="Child (between 5 and 18 years)"]'
            '[./../../../../../label/div[contains(.,"Camper {}")]]'.format(camper_no)).click()
        browser.find_by_xpath(
            '//input[starts-with(@aria-label,"Age at start of camp (if under 18) (Camper {})")]'
            ''.format(camper_no)).fill(str(random.randint(5, 18)))
    else: # infant
        browser.find_by_xpath(
            '//div[@class="ss-form-entry"]//input'
            '[@value="Infant (under 5 years)"]'
            '[./../../../../../label/div[contains(.,"Camper {}")]]'.format(camper_no)).click()
        browser.find_by_xpath(
            '//input[starts-with(@aria-label,"Age at start of camp (if under 18) (Camper {})")]'
            ''.format(camper_no)).fill(str(random.randint(0, 4)))
        
    for act in random.sample(ACTIVITIES, 2):
        browser.find_by_xpath(
            '//input[starts-with(@value,"{}")]'
            '[./../../../../../label/div'
            '[contains(.,"Primary Activities (Camper {})")]]'
            ''.format(act, camper_no)).click()

    for act in random.sample(ACTIVITIES, random.randint(0, len(ACTIVITIES))):
        browser.find_by_xpath(
            '//input[starts-with(@value,"{}")]'
            '[./../../../../../label/div'
            '[contains(.,"Other Activities (Camper {})")]]'
            ''.format(act, camper_no)).click()


def register(email, adults, children, infants):
    NAME = datetime.datetime.now().strftime("%Y%m%d%H%M")

    with Browser() as browser:
        browser.visit(URL)
        sleep(5)

        browser.find_by_xpath('//label[*[text()[contains(.,"My child")]]]').click()

        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Name")]').fill(NAME)
        browser.find_by_xpath('//input[starts-with(@aria-label,"Email Address")]').fill(email)
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Address")]').fill("Address")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Telephone Number")]').fill("123")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Association with 7th Lichfield")]').fill("Test")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Number of Tents")]').fill(str(random.randint(1, 2)))
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Number of Caravans  or Motorhomes")]').fill(str(random.randint(1, 2)))
        browser.find_by_xpath('//input[starts-with(@aria-label,"Home Contact Name")]').fill("Home")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Home Contact Number")]').fill("123")

        browser.find_by_xpath('//input[starts-with(@value,"We are happy to provide")]').click()
        browser.find_by_xpath('//input[starts-with(@value,"We would like to have another")]').click()

        browser.find_by_xpath("//input[@name='continue']").click()

        fill_camper(browser, NAME, "1", "adult")
        adults -= 1

        browser.find_by_xpath('//input[@aria-label="Yes"]').click()
        browser.find_by_xpath("//input[@name='continue']").click()

        camper_no = 2
        if adults > 0:
            age_type = 'adult'
        elif children > 0:
            age_type = 'child'
        else:
            age_type = 'infant'

        
        while (camper_no < 10):
            if (age_type == 'adult' and (adults > 0)):
                fill_camper(browser, NAME, str(camper_no), "adult")
                adults -= 1
                if adults == 0:
                    age_type = 'child'
            elif (age_type == 'child' and (children > 0)):
                fill_camper(browser, NAME, str(camper_no), "child")
                children -= 1
                if children == 0:
                    age_type = 'infant'
            elif (age_type == 'infant' and (infants > 0)):
                fill_camper(browser, NAME, str(camper_no), "infant")
                infants -= 1

            if (camper_no == 5):
                browser.find_by_xpath('//input[@aria-label="Yes"]').click()
                browser.find_by_xpath("//input[@name='continue']").click()

            camper_no += 1


        # import pdb;pdb.set_trace()
        browser.find_by_xpath("//input[@name='submit']").click()
                
                

def register_random():
    NAME = datetime.datetime.now().strftime("%Y%m%d%H%M")

    with Browser() as browser:
        browser.visit(URL)
        sleep(5)

        browser.find_by_xpath('//label[*[text()[contains(.,"My family")]]]').click()
        browser.find_by_xpath('//label[*[text()[contains(.,"My child")]]]').click()

        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Name")]').fill(NAME)
        browser.find_by_xpath('//input[starts-with(@aria-label,"Email Address")]').fill("rjt-family-{}@gmail.com".format(NAME))
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Address")]').fill("Address")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Telephone Number")]').fill("123")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Association with 7th Lichfield")]').fill("Test")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Number of Tents")]').fill(str(random.randint(1, 2)))
        browser.find_by_xpath('//input[starts-with(@aria-label,"Family Number of Caravans  or Motorhomes")]').fill(str(random.randint(1, 2)))
        browser.find_by_xpath('//input[starts-with(@aria-label,"Home Contact Name")]').fill("Home")
        browser.find_by_xpath('//input[starts-with(@aria-label,"Home Contact Number")]').fill("123")

        browser.find_by_xpath('//input[starts-with(@value,"We are happy to provide")]').click()
        browser.find_by_xpath('//input[starts-with(@value,"We would like to have another")]').click()

        browser.find_by_xpath("//input[@name='continue']").click()

        fill_camper(browser, NAME, "1")

        browser.find_by_xpath('//input[@aria-label="Yes"]').click()
        browser.find_by_xpath("//input[@name='continue']").click()

        fill_camper(browser, NAME, "2")
        fill_camper(browser, NAME, "3")
        fill_camper(browser, NAME, "4")
        fill_camper(browser, NAME, "5")

        browser.find_by_xpath('//input[@aria-label="Yes"]').click()
        browser.find_by_xpath("//input[@name='continue']").click()

        fill_camper(browser, NAME, "6")
        fill_camper(browser, NAME, "7")
        fill_camper(browser, NAME, "8")
        fill_camper(browser, NAME, "9")
        fill_camper(browser, NAME, "10")


        browser.find_by_xpath("//input[@name='submit']").click()


if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    if (args['<email>']):
        register(args['<email>'],
                 int(args['<adults>']),
                 int(args['<children>']),
                 int(args['<infants>']))
    else:
        register_random()
