source("myFunctions.R")

packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'XXL Horeca'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide u1nique file id
folderId <- "1ciByFK0CAZDnU9HSzi1LmqQOMA-zuf00" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving
txt <- strsplit(result$text, "\n")[[1]]


## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

datum <- txt[grep("Factuurdatum:", txt)+1]
df$TransactionDate <- dmy(substr(datum,1,10))

df$TransactionAmount[1] <- round(getAmount(txt[grep("Totaal", txt)]),2) ## Totaalbedrag
df$TransactionAmount[2] <-round((df$TransactionAmount[1] / 121) *21,2) ## BTW Bedrag

## factuurNummer txt[1]
factnr <- gsub("\\s+","", txt[1])
df$TransactionDescription <- paste(transactionNumber, factnr,  sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
