source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Avance'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "1NKj_wbFq2FhkSgzElOA19R2GQSKa_6XQ" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages

df$TransactionDate <- ymd(strsplit(result$txt[grep("Datum", result$txt)],"Datum ")[[1]][2])
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionAmount[1] <- round(getAmount(strsplit(result$txt[grep("BTW Bedrag", result$txt)], "BTW")[[1]][2]),2)
df$TransactionAmount[2] <- round(getAmount(result$txt[grep("Te betalen", result$txt)]),2)
df$TransactionDescription <- paste(result$txt[grep("Factuurnummer",result$txt)[1]], result$txt[grep("Kenm:",result$txt)[1]], df$TransactionDate[1], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)