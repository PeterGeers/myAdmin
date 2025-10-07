source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Tegeldepot'
df <- getLastTransactions(transactionNumber)
################################################################################ 
folderId <- "15cFgvcxXBmkD7QAnEI6DbLvrHfC-CnxB" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages


x <- str_split_1(result$txt[grep("Datum",result$txt)]," ")
df$TransactionDate <- getDateFromTxt(x[4], x[3], x[2])

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionAmount[1] <- getAmount(result$txt[grep("Te Betalen: €", result$txt)])
df$TransactionAmount[2] <-  getAmount(result$txt[grep("^ BTW: €", result$txt)])

df$TransactionDescription <- paste(result$txt[grep("Factuurnummer:",result$txt)], 
                                   result$txt[grep("Bestelnummer:",result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
