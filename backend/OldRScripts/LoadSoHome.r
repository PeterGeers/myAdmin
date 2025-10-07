source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'SoHome'
df <- getLastTransactions(transactionNumber)
######################## Parameters to fill ########################################################
## Provide unique file id
folderId <- "1LFCLXrTT4lruR31mwcxjJWb-DUcJ9CIx" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

###################################################################
x <- str_split(result$txt[grep("Datum:", result$txt)], " ")[[1]]
df$TransactionDate <-  getDateFromTxt(x[4], x[3], x[2])

x <- str_split(result$txt[grep("Inc",result$txt)], "€")[[1]]
df$TransactionAmount[1] <- getAmount(x[2])  ## Totaalbedrag
x <- str_split(result$txt[grep("BTW:",result$txt)], "€")[[1]]
df$TransactionAmount[2] <- getAmount(x[2])  ## Totaalbedrag
df$TransactionDescription <- paste(result$txt[grep("Factuurnummer", result$txt)], 
                                   result$txt[grep("Bestelnummer", result$txt)], 
                                   result$txt[grep("Datum", result$txt)], 
                                   sep = " - ")

## Append records
x <- writeTransactions(df)