source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Bol.com'
df <- getLastTransactions(transactionNumber)
######################## Parameters to fill ########################################################
## Provide unique file id
folderId <- "1w0y19t4a0GhUGh0bIkAgedg1p1UF7tc9" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

###################################################################
## df$TransactionDate <-  mdy(result$txt[grep("Factuurdatum:",result$txt, ignore.case = TRUE)])
df$TransactionDate <-  mdy(str_split(result$txt[grep("1401104406 ", result$txt)]," ")[[1]][3])
## getDateFromTxt(x[5],x[4],x[3])
df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("BEDRAG INCL. BTW",result$txt)], "BTW")[[1]][2]) ## Totaalbedrag
df$TransactionAmount[2] <- getAmount(result$txt[grep("^ BTW",result$txt)])  ## Totaalbedrag
df$TransactionDescription <- paste(result$txt[grep("^ Factuur$", result$txt)][[1]], 
                                   result$txt[grep("^ Factuur$", result$txt)+ 4], sep = " - ")

## Append records
x <- writeTransactions(df)