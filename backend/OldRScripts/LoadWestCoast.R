source("myFunctions.R")

packResult <- getPackages(c("DBI", "stringi","tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'WestCoast'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1N1FsaWtzX3lRNE0" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

result$txt

df$TransactionDescription <- paste(result$txt[grep("Debiteurnummer ", result$txt)[1]], 
                                   result$txt[grep("Factuurdatum", result$txt)[1]], sep = " ")
df$TransactionDate <-  dmy(str_split(result$txt[grep("Factuurdatum", result$txt)[1]],"Factuurdatum")[[1]][2])

## pattern <- "Totaal \200 [0-9]*,[0-9][0-9] \200 [0-9]*,[0-9][0-9] \200 [0-9]*,[0-9][0-9]"
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal €", result$txt)])
df$TransactionAmount[2] <- round(df$TransactionAmount[1]/121*21,2) ## BTW Bedrag

###Write to DB #####################################################################################
x <- writeTransactions(df)
