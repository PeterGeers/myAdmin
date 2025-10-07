source("myFunctions.R")


packResult <- getPackages(c("tidyverse", "lubridate","devtools","tesseract","magick", "googledrive"))
## devtools::install_github("ropensci/magick")

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'TEMU'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "1TIrDJ69MflFhBzcovDRTjN9nwRZ8MF1f" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving


## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
x <- str_split(result$txt[grep("Betaald op|Order time", result$txt)][1], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[5],x[3], x[4])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal bestelbedrag:|Order total:", result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("Inclusief btw van|Includes VAT of", result$txt)])

df$TransactionDescription <- paste(result$txt[grep("Bestel-id:|Order ID:",result$txt)], result$txt[grep("iDEAL",result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)