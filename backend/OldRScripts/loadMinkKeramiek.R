source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Mink keramiek'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "1NoSD5Bi5HfNSnBySc1YDVPtQh8wXXUOZ" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

df$TransactionDate <-    dmy(result$txt[grep("Factuurdatum:", result$txt)] )
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaalbedrag incl. btw €", result$txt)])
df$TransactionAmount[2] <-  df$TransactionAmount[1] - getAmount(result$txt[grep("Totaalbedrag excl. btw €", result$txt)])

df$TransactionDescription <- paste(result$txt[grep("Factuur:",result$txt)[1]], 
                                   result$txt[grep("Kittec",result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)