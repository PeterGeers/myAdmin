source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'JCB Ventilatie'
df <- getLastTransactions(transactionNumber)
df <- getLastTransactions("CoolBlue")
df$TransactionNumber <- transactionNumber
################################################################################ 
folderId <- "1qa_tsvTRRBMn2h0g4ixFoi9RKuxN87Fa" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages


df$TransactionDate <- dmy(result$txt[grep("Datum:",result$txt)])
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionAmount[1] <- getAmount(result$txt[grep("TOTAAL EUR", result$txt)])
df$TransactionAmount[2] <-  getAmount(result$txt[grep("BTW hoog", result$txt)])

df$TransactionDescription <- paste(result$txt[2], result$txt[9], result$txt[10], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)