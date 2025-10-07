source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Bol.com'
df <- head(getLastTransactions(transactionNumber),2)
######################## Parameters to fill ########################################################
## Provide unique file id
folderId <- "1w0y19t4a0GhUGh0bIkAgedg1p1UF7tc9" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

###################################################################
## df$TransactionDate <-  dmy(result$txt[grep("Factuurdatum:",result$txt, ignore.case = TRUE)])
x <-str_split(result$txt[grep("Aankoopdatum", result$txt)]," ")[[1]]
df$TransactionDate <-  getDateFromTxt(x[5],x[4],x[3])
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaalbedrag € ",result$txt)])  ## Totaalbedrag
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("21% BTW € ",result$txt)],"BTW")[[1]][2])  ## Totaalbedrag
df$TransactionDescription <- trimws(paste(result$txt[grep("Factuurnummer", result$txt)], result$txt[grep("Klantnummer", result$txt)], sep = " - "))

## Append records
x <- writeTransactions(df)