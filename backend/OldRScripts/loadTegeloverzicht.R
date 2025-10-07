source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- '123inkt'
df <- tail(getLastTransactions(transactionNumber),2)

################################################################################ 
## Provide unique file id
folderId <- "106p1IgqeDZQENC3d109iES0aQo1bzClW" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

df$TransactionDescription <- paste("Klantnr :", strsplit(result$txt[grep("Klantnummer", result$txt)+1], " ")[[1]][1], 
                                   "Factuurnr :", strsplit(result$txt[grep("Klantnummer", result$txt)+1], " ")[[1]][2],
                                   "Factuurdatum :", strsplit(result$txt[grep("Klantnummer", result$txt)+1], " ")[[1]][3],
                                   sep=" ")

## datum <- content$TransactionDescription[[row]][4]
df$TransactionDate <- dmy(strsplit(result$txt[grep("Klantnummer", result$txt)+1], " ")[[1]][3])

## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <- getAmount(strsplit(result$txt[grep("Verzenddatum", result$txt)], "€")[[1]][4])
df$TransactionAmount[2] <- getAmount(strsplit(result$txt[grep("Verzenddatum", result$txt)], "€")[[1]][3])



###Write to DB #####################################################################################
x <- writeTransactions(df)
