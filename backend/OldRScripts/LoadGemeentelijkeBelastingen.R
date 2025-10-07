source("myFunctions.R")

packResult <- getPackages(c("DBI", "stringi"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Gemeente Haarlemmermeer'
df <- head(getLastTransactions(transactionNumber),1)


################################################################################ 
## Provide unique file id
folderId <- "1e_H_pRIDPTEQQYl8KlDymBeJ7JiZR1qN" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$ref4 <- result$fileName

df$TransactionDate <- dmy(result$txt[grep("Verzenddatum", result$txt)])




df$TransactionAmount <- getAmount(result$txt[grep(Totaalbedrag"", result$txt)]) ## Totaalbedrag

df$TransactionDescription <- paste(result$txt[grep("klantnummer", result$txt)],
                                   result$txt[grep("Aanslagbiljet", result$txt)],
                                   sep = '; ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
