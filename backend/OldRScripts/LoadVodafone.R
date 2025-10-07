source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Vodafone'
df <- head(getLastTransactions(transactionNumber),2)

ledgers <- getLedgerCodes("A")
df$Debet[1] <- ledgers[1] 
df$Credit[1] <- ledgers[2]
df$Debet[2] <- ledgers[3]
df$Credit[2] <- ledgers[4]

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1T3FNY2M2b1NEMGs" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
x <- str_split_1(result$txt[grep("Datum", result$txt)], " ")
df$TransactionDate <- getDateFromTxt(x[5], x[4],x[3])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal inclusief btw",result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("Totaal btw-bedrag",result$txt)])


df$TransactionDescription <- paste(result$txt[grep("Klantnummer",result$txt)],
                                   result$txt[grep("Rekeningnummer",result$txt)],
                                     sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)


