source("myFunctions.R")


packResult <- getPackages(c("tidyverse", "lubridate","devtools","tesseract","magick", "googledrive"))
## devtools::install_github("ropensci/magick")

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Temu'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1TIrDJ69MflFhBzcovDRTjN9nwRZ8MF1f" ## Unique ID of folder containing Files

folderContent <- drive_ls(as_id(folderId), n_max = 1, recursive = FALSE) ## Retrieves content of folder

fileCode <- folderContent$id[[1]]  ## Most recent added file to folder
fileDetails <- drive_get(id=fileCode)
fileName <- fileDetails[[3]]  ## Most recent added file to folder
fileUrl <- fileDetails$drive_resource[[1]]$webViewLink
fileDir <- paste0("G:/My Drive/Facturen/",transactionNumber,"/" )#############################

text <-  image_read(paste0(fileDir, fileName[[1]][3])) %>%
    image_resize("2000") %>%
    image_convert(colorspace = 'gray') %>%
    image_trim() %>%
    image_ocr()

txt <- ""
pattern <- "\\s+"
for (i in 1: length(text)){
    x <- strsplit(text,"\n")[[i]]  
    x <- gsub(pattern," ",x)
    txt <- append(txt, x)
}
txt <- as_tibble(txt)
x <- strsplit(txt$value[grep("Besteldatum", txt$value)], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[4], x[3], x[2])

## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <- getAmount(txt$value[grep("Totaal bestelbedrag:", txt$value)])
df$TransactionAmount[2] <- getAmount(txt$value[grep("Inclusief btw van|Incilusief btw van", txt$value)])

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- fileUrl
df$Ref4 <- fileName[[1]][3]

df$TransactionDescription <- paste(transactionNumber, 
                                   txt$value[grep("Bestel-id:|Bestel-Id:", txt$value)],
                                   sep=" ")

###Write to DB #####################################################################################
x <- writeTransactions(df)
