#!/bin/sh
# USAGE: ./concat-pdf.sh *.pdf output-file.pdf

ALL_FILES=""
BLANK_FILE="/tmp/blank.pdf"

for OUTPUT_FILE; do true; done
if test -f "$OUTPUT_FILE"; then
    echo "$OUTPUT_FILE already exists"
    exit 1
fi

echo "" | ps2pdf -sPAPERSIZE=letter - $BLANK_FILE
for PDF_FILE; do
    if [ "$PDF_FILE" != "$OUTPUT_FILE" ]; then
        pages=$(strings < "$PDF_FILE" | sed -n 's|.*Count -\{0,1\}\([0-9]\{1,\}\).*|\1|p' | sort -rn | head -n 1)
        ALL_FILES="$ALL_FILES $PDF_FILE"
        [ $((pages%2)) -ne 0 ] && ALL_FILES="$ALL_FILES $BLANK_FILE"
    fi
done

echo "pdftk $ALL_FILES cat output \"$OUTPUT_FILE\""

pdfunite $ALL_FILES "$OUTPUT_FILE"

rm -f $BLANK_FILE

