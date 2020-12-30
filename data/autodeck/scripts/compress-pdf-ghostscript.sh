# compress a pdf file using ghostscript command line
#
# taken from https://itsfoss.com/compress-pdf-linux/
#
# need to know is the dPDFSETTINGS parameter. This is what determines the compression level and thus the quality of your compressed PDF file.
# 
# dPDFSETTINGS	Description
# /prepress (default)	Higher quality output (300 dpi) but bigger size
# /ebook	Medium quality output (150 dpi) with moderate output file size
# /screen	Lower quality output (72 dpi) but smallest possible output file size 

gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.5 -dPDFSETTINGS=/prepress -dNOPAUSE -dQUIET -dBATCH -sOutputFile=generated/autodeck-43-9-deck-7-comp.pdf generated/autodeck-43-9-deck-7.pdf
