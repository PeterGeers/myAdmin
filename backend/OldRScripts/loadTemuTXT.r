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
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

x <- strsplit(result$txt[grep("Besteldatum|Order time:", result$txt)], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[5], x[3], x[4])

## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal bestelbedrag:|Order total:", result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("Inclusief btw van|Incilusief btw van|Includes VAT of", result$txt)])

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''

df$TransactionDescription <- paste(transactionNumber, 
                                   result$txt[grep("Bestel-id:|Bestel-Id:|Order ID:", result$txt)],
                                   sep=" ")

###Write to DB #####################################################################################
x <- writeTransactions(df)
