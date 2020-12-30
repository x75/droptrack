for f in autodeck-*.pdf ; do inkscape -z --export-dpi 150 --export-png ${f%.pdf}.png $f ; done
