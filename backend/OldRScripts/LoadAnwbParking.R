source("myFunctions.R")

packResult <- getPackages(c("tidyverse"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Yellowbrick'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide u1nique file id
folderId <- "0B9OBNkcEDqv1RHFfc1M1S2lXeDA" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####


## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionDate <- dmy(str_split(result$txt[grep("datum:", result$txt)+1],"Beem")[[1]][1])
df$TransactionDescription <- paste("Factuurnummer", str_split(result$txt[grep("Factuurnummer:", result$txt)+1], " ")[[1]][1] , "Datum ", df$TransactionDate[1] , sep = " ")


## ??? \200
amounts <- strsplit(result$txt[grep("Totaal", result$txt)][[2]], " € ")[[1]]

df$TransactionAmount[1] <- getAmount(amounts[4]) ## Bedrag
df$TransactionAmount[2] <- getAmount(amounts[3])  ## BTW Bedrag


###Write to DB #####################################################################################
x <- writeTransactions(df)
