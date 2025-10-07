source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'RVS Products'
df <- getLastTransactions(transactionNumber)
## df <- getLastTransactions("Gamma")
## df$TransactionNumber <- transactionNumber
## df$ReferenceNumber   <- transactionNumber
################################################################################ 
folderId <- "167muhqcgywkYZGd6zdwoh9GeB5lwZ2qA" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages

df$TransactionDate <- dmy(result$txt[grep("Factuurdatum:",result$txt)])
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal €", result$txt)])
df$TransactionAmount[2] <-  getAmount(result$txt[grep("BTW €", result$txt)])

df$TransactionDescription <- paste(result$txt[8], 
                                   strsplit(result$txt[grep("Factuurnummer:",result$txt)]," ")[[1]][3], 
                                   strsplit(result$txt[grep("Factuurnummer:",result$txt)]," ")[[1]][4], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
