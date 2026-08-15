#!/usr/bin/env bash

csv="$1"
outdir="$2"
root="/home/rjt/Devel/Personal/Cubs/family_camp/family_camp"

export PYTHONPATH="${root}":$PYTHONPATH


python -m family_camp.schedule check "${csv}" "${outdir}" 2> "${outdir}/errors.txt"
#python -m family_camp.schedule check "${csv}" "${outdir}" 2> "${outdir}/errors.txt" | sed '1,/\*\*\*/d' > "${outdir}/activities.txt"

(
   cd "$outdir" && {
   #enscript campers.txt --output=- | ps2pdf - | pdfcrop --margins '-2 10 -25 10' - campers.pdf
   for f in campers inactive_campers inactive_groups
   do
    enscript "${f}.txt" --output=- | ps2pdf - "${f}.pdf"
    pdfxup -o "${f}_3_1.pdf" --nup 3x1 "${f}.pdf"
   done

   ACT_DIR=".activities_$$"

   mkdir -p "${ACT_DIR}"
   (
      cd "${ACT_DIR}"
      csplit ../activites.txt "/^Total in activity/" '{*}'
      for i in *
      do
           enscript "${i}" -N n --output=- | ps2pdf - | pdfcrop --margins '0 10 -25 10' - "${i}".pdf
           pdfxup -o "${i}-nup.pdf" --nup 3x1 "${i}".pdf
      done
      pdfunite *nup*.pdf xx15-nup-joined.pdf
      cp xx15-nup-joined.pdf ../activities-nup.pdf
   )
   # rm -rf "${ACT_DIR}"

   #enscript activities.txt --output=- | ps2pdf - | pdfcrop --margins '-2 10 -25 10' - activities.pdf
   #pdfxup --nup 3x1 activities.pdf
   
   }
)

python ${root}/pack/family2pdf.py "${csv}" "${outdir}"

python ${root}/pack/pad_pdf.py "${outdir}"/*_timetable.pdf > "${outdir}/all_timetables.pdf"

