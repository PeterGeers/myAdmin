source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Warm en Sfeervol Wonen'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "1VxbLZHEqKNmWG5x3-o14Z3tS1K_rLx5k" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
df$TransactionDate <-  dmy(result$txt[grep("Factuurdatum", result$txt)])

df$TransactionAmount[1] <- round(getAmount(str_split_1(result$txt[grep("Totaal", result$txt)], " ")[3]), 2)
df$TransactionAmount[2] <- round(getAmount(str_split_1(result$txt[grep("btw", result$txt)], " ")[2]), 2)
df$TransactionDescription <- paste(result$txt[grep("Factuurnummer",result$txt)[1]], 
                                   result$txt[grep("Bestelnummer",result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)