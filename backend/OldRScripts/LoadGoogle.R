source("myFunctions.R")

packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Google'
df <- getLastTransactions(transactionNumber)[1,]

################################################################################ 
## Provide unique file id
folderId <- "1f7FNI6hGTLtXs0Go2OhbL_eR5bYvT6Qc" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

df$TransactionDescription <- paste(result$txt[grep("Factuurnummer", result$txt)][2],
                                   result$txt[grep("Domein", result$txt)],
                                   result$txt[grep("Detail", result$txt)],
                                   sep=" ")

x <- str_split(result$txt[grep("Factuurdatum", result$txt)], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[4], x[3], x[2])

df$TransactionAmount <- getAmount(result$txt[grep("Totaal in EUR", result$txt)][2])

###Write to DB #####################################################################################
x <- writeTransactions(df)



