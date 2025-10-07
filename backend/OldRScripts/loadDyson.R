source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Dyson'
df <- tail(getLastTransactions(transactionNumber),2)

################################################################################ 
## Provide unique file id
folderId <- "1sji1hO2zy86BlYtQBKQ9SZZL7uDWiA_T" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## datum <- content$TransactionDescription[[row]][4]
df$TransactionDate <- dmy(str_split(result$txt[grep("Factuurdatum", result$txt)], "Factuurdatum")[[1]][2])
df$TransactionDescription <- paste(result$txt[grep("Factuurnummer", result$txt)], result$txt[grep("Klant-nr", result$txt)], sep = ":")


## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <-getAmount(result$txt[grep("Totaal EUR", result$txt)])
x <- str_split(result$txt[grep("BTW 21,00 % ", result$txt)], "BTW 21,00 % ")[[1]]
df$TransactionAmount[2] <- getAmount(x[2])

###Write to DB #####################################################################################
x <- writeTransactions(df)
