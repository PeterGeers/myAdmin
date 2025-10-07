source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "pdftools"))
fileDir <- "C:/Users/peter/Downloads/"
fileName <- "printable.pdf"
pdf_file <-  paste0(fileDir, fileName)
text <- pdf_text(pdf_file) 
text <- as_tibble(text)
x <- bind_rows(text[1,],text[2,],text[3,],text[4,],text[5,],text[6,],text[7,],text[8,])
class(x)
names(x)

for (i in 1:nrow(x)){

    y <- strsplit(x[i,]$value, "\n") 
    print(y)

}