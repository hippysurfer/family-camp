# !/usr/bin/env python

import io
import copy, sys
from PyPDF2 import PdfWriter, PdfReader

output = PdfWriter()
output_page_number = 0
alignment = 2  # to align on even pages

for filename in sys.argv[1:]:

    # This code is executed for every file in turn
    #hack = io.StringIO(open(filename, 'r').readlines())
    input = PdfReader(filename)

    for p in [input.pages[i] for i in range(0, len(input.pages))]:
        # This code is executed for every input page in turn
        output.add_page(p)
        output_page_number += 1
    while output_page_number % alignment != 0:
        output.addBlankPage()
        output_page_number += 1


output.write(sys.stdout.buffer)
