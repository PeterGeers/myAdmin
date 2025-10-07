source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Briters'
df <- tail(getLastTransactions(transactionNumber),2)
ledgers <- getLedgerCodes("A")
df$Debet[1] <- ledgers[1] 
df$Credit[1] <- ledgers[2]
df$Debet[2] <- ledgers[3]
df$Credit[2] <- ledgers[4]

################################################################################ 
folderId <- "1OO2Mnm5DKtNW_Ls5l3nvkkicnlMAux-j" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages

df$TransactionDate <- dmy(result$txt[3])
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionAmount[1] <- getAmount(result$txt[grep("Total paid", result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("VAT €", result$txt)])
df$TransactionDescription <- paste(transactionNumber,"wasmiddel", result$txt[2], result$txt[3], result$txt[13], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
