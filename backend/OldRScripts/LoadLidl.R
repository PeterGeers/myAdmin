source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'LIDL'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1ZHJseFFFLWRZbW8" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## TransactionDate Datum: 27-04-2020

df$TransactionDate <- dmy(str_split(result$txt[grep("Factuurdatum", result$txt)],":")[[1]][2]) ## Check for client number row
## Totaal € 21.74
df$TransactionAmount[1] <-  getAmount(str_split(result$txt[grep("Totaal ", result$txt)],"  "))
## BTW 21.00% € 3.77
df$TransactionAmount[2] <-  getAmount(str_split(result$txt[grep("Totaal ",result$txt)+7],"EUR")[[1]][3])

df$TransactionDescription <- paste(transactionNumber, getAmountString(result$txt, "Klantnummer:"), getAmountString(result$txt, "Factuurnummer: "),   sep = ' ')
###################################################################
## Append records
x <- writeTransactions(df)

