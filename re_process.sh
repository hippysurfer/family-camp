#!/usr/bin/env bash

csv="$1"
outdir="$2"
root="/home/rjt/Devel/Personal/Cubs/family_camp"

export PYTHONPATH="${root}":$PYTHONPATH


${root}/check_schedule.py "${csv}" 2> "${outdir}/errors.txt" | sed '/\*\*\*/,$d' > "${outdir}/campers.txt"
${root}/check_schedule.py "${csv}" 2> "${outdir}/errors.txt" | sed '1,/\*\*\*/d' > "${outdir}/activities.txt"

(
   cd "$outdir" && {
   enscript campers.txt --output=- | ps2pdf - | pdfcrop --margins '-2 10 -25 10' - campers.pdf
   pdfnup --nup 3x1 campers.pdf

   ACT_DIR=".activities_$$"

   mkdir -p "${ACT_DIR}"
   (
      cd "${ACT_DIR}"
      csplit ../activities.txt "/^Total in activity/" '{*}'
      for i in *
      do
           enscript ${i} -N n --output=- | ps2pdf - | pdfcrop --margins '0 10 -25 10' - ${i}.pdf
           pdfnup --nup 3x1 ${i}.pdf
      done
      pdfjoin *nup*.pdf
      cp xx15-nup-joined.pdf ../activities-nup.pdf
   )
   # rm -rf "${ACT_DIR}"

   #enscript activities.txt --output=- | ps2pdf - | pdfcrop --margins '-2 10 -25 10' - activities.pdf
   #pdfnup --nup 3x1 activities.pdf
   
   }
)

python ${root}/family2pdf.py "${csv}" "${outdir}"

python ${root}/pad_pdf.py ${outdir}/*_timetable.pdf > "${outdir}/all_timetables.pdf"

