
Setup Python
============

sudo apt-get install python3-dev python3-openssl
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt


Generating the Schedule
=======================

First download the data
-----------------------

```python ./refresh_data.py <google-doc-id>```

Run the schedule
----------------

```python ./schedule.py generate <outdir>```

Check a schedule
----------------

You can modify the timetable.csv file by hand to resolve issues
and then recheck it against the downloaded data.

```python ./schedule.py check <path-to-timetable.csv> <outdir>```

<outdir> must already exist. The updated schedule results will be
created in <outdir>.


PDF creation
============


for i in *.txt; do filename=$(basename $i); enscript "$i" --output=- | ps2pdf - > "${filename}.pdf"; pdfjam --nup 2x2 "${filename}.pdf" --outfile "${filename}_2x2.pdf"; done
