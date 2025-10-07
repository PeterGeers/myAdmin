source("myFunctions.R")
packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Smulderstextiel'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "13iij5WOZYtTLJwYqrTq35adpthNqp-o-" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

#########################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
###################################################################
## TransactionDate
df$TransactionDate <- dmy(result$txt[grep("Factuurdatum", result$txt)])

#########################################################################################
## transactinon Amount
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal incl. BTW €", result$txt, ignore.case = TRUE)])
df$TransactionAmount[2] <- df$TransactionAmount[1] - getAmount(result$txt[grep("Totaal excl. BTW", result$txt, ignore.case = TRUE)])

df$TransactionDescription <- paste(result$txt[grep("Klantnummer", result$txt, ignore.case = TRUE)], 
                                   result$txt[grep("Factuurnummer", result$txt, ignore.case = TRUE)],  sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
