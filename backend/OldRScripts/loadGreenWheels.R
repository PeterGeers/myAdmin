source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate", "googledrive"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'GreenWheels'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "1za_aX51r6zOuoX1shwhxBvf6iOgNzhjB" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving


## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

df$TransactionDate <- dmy(result$txt[grep("Factuur [0-9]", result$txt)])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Factuurbedrag €", result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("Btw-bedrag €", result$txt)])*-1

df$TransactionDescription <- paste(transactionNumber, result$txt[grep("Klantnummer",result$txt)], result$txt[grep("Factuurnummer",result$txt)], sep = '')

###Write to DB #####################################################################################
x <- writeTransactions(df)