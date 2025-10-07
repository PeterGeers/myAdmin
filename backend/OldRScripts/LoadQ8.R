source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Q8'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1ZzBlNFhqcUJveWs" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

df$TransactionDate <- dmy(str_split(result$txt[grep("^ Datum :",result$txt)],"9429002351 ")[[1]][1])

## transaction Amount build sub step to handle txt changes
amounts <- str_split(result$txt[grep("TOTAAL FACTUUR :",result$txt)]," : ")[[1]][2]
df$TransactionAmount[2] <- getAmount(str_split(amounts, " ")[[1]][3]) ## BTW Bedrag
df$TransactionAmount[1] <- getAmount(str_split(amounts, " ")[[1]][4]) ## BTW Bedrag ## Totaalbedrag

## Description
df$TransactionDescription <- paste(result$txt[grep("FACTUUR NR :",result$txt)],result$txt[grep("TOTAAL FACTUUR :",result$txt)][1], sep = "; ")


###Write to DB #####################################################################################
x <- writeTransactions(df)
