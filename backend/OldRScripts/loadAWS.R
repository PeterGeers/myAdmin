source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate", "stringr"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'AWS'
df <- tail(getLastTransactions(transactionNumber),2)
ledgers <- getLedgerCodes("A")
df$Debet[1] <- ledgers[1] 
df$Credit[1] <- ledgers[2]
df$Debet[2] <- ledgers[3]
df$Credit[2] <- ledgers[4]

################################################################################ 
folderId <- "1On1kv17cWXF22z4mR_a34m4QEedMlRD5" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages


df$TransactionDate <- mdy(str_extract(result$txt[grep("VAT Invoice Date:", result$txt)], "[A-Za-z]+ [0-9]{1,2}, [0-9]{4}"))

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
wisselkoers <- as.numeric(sub(".*\\(1 USD = ([0-9\\.]+) EUR.*", "\\1", result$txt[grep("VAT in EUR \\(1 USD = ", result$txt)]))
df$TransactionAmount[1] <- round(getAmount(result$txt[grep("TOTAL AMOUNT USD", result$txt)]) * wisselkoers, 2)
df$TransactionAmount[2] <- as.numeric(sub(".*TOTAL VAT EUR ([0-9\\.]+).*", "\\1", result$txt[grep("TOTAL VAT EUR", result$txt)]))
df$TransactionDescription <- paste(transactionNumber,"Account:",result$txt[grep("VAT Invoice Number:", result$txt)] , sep = ' ')
###Write to DB #####################################################################################
x <- writeTransactions(df)
if (!x) warning("Transactie kon niet worden weggeschreven.") else
{print(df)
message("Transacties succesvol verwerkt voor ", transactionNumber)}
