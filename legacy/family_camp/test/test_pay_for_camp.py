"""Test Payment for Family Camp Bookings.

Usage:
  test_pay_for_camp.py <email> <adults> <children> <infants>


Options:
  -d,--debug     Turn on debug output.
  -h,--help      Show this screen.
  --version      Show version.

"""

from splinter import Browser
from time import sleep

from docopt import docopt

URL = "http://www.7thlichfield.org.uk/family-camp/"
PP_EMAIL = "rjt-paypal-buyer@thegrindstone.me.uk"
PP_PASSWD = "ZdIcQM9L2Qfl"

def interact():
    import code
    code.InteractiveConsole(locals=globals()).interact()


def pay(email, adults, children, infants):

    with Browser() as browser:
        browser.visit(URL)

        browser.is_element_present_by_xpath(
            "//input[@value='Go to PayPal checkout']")

        browser.fill('custom', email)
        browser.fill('quantity_1', adults)
        browser.fill('quantity_2', children)
        browser.fill('quantity_3', infants)

        browser.find_by_xpath(
            "//input[@value='Go to PayPal checkout']").click()
        
        browser.find_by_xpath('//input[@name="login_button"]').click()
        sleep(3)
        
        browser.fill('login_email', PP_EMAIL)
        browser.fill('login_password', PP_PASSWD)

        browser.find_by_xpath('//input[@id="submitLogin"]').click()
        browser.is_element_present_by_xpath('//input[@value="Pay Now"]',
                                            wait_time=10)
        browser.find_by_xpath('//input[@value="Pay Now"]').click()

        browser.is_element_present_by_xpath('//strong[starts-with(.,"You just completed")]',
                                            wait_time=10)
        

if __name__ == '__main__':

    args = docopt(__doc__, version='1.0')

    pay(args['<email>'],
        args['<adults>'],
        args['<children>'],
        args['<infants>'])
