source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Verkaik'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1bMADSdnIZGQh21en0rGnur7IqFbfE-2E" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## TransactionDate
df$TransactionDate <- dmy(str_split_1(result$txt[grep("^Datum", result$txt)]," ")[2])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal Factuurbedrag €", result$txt)])
## BTW-bedrag €  NOTE minus sign in txt results in negative value therefor MINUS needed
df$TransactionAmount[2] <- -getAmount(result$txt[grep("BTW-bedrag €", result$txt)])

df$TransactionDescription <- paste("Verf tbv JaBaKi studios", 
                                   result$txt[grep("Clientnr", result$txt)],
                                   result$txt[grep("Factuurnr", result$txt)],  sep=" ")

###Write to DB #####################################################################################
x <- writeTransactions(df)
