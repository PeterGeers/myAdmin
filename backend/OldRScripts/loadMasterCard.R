## install.packages('pdftools')
source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

folderId <- "1G8GoZspB4fF1Ktzpk5kcf-xSgiZ6RA92"
transactionNumber <- "MasterCard"

df <- head(getLastTransactions(transactionNumber),1)
result <- getTextFromPdf(folderId, transactionNumber)

## Select valid rows to process
dfx <- as_tibble(result$txt[grep("^[0-9]{2}-[0-9]{2}-[0-9]{4}", result$txt)])

## define df$date 
dfx$TransactionDate <- dmy(substr(dfx$value, 1, 10))
## df$bedrag
dfx$TransactionAmount <- 0
pattern <- "([-]|[ ]|[+])[0-9]*,[0-9][0-9]"
for (i in 1:nrow(dfx)){
    dfx$TransactionAmount[i] <- getAmount(stri_match_last(dfx$value, regex = pattern)[i,1])

}

debet <- '4001'
credit <- '1300'

## Define booking code
dfx$TransactionNumber <- paste(transactionNumber, max(dfx$TransactionDate), sep = " ")
dfx$Administration <- df$Administration[1]
## if bedrag < 0 change debet aand credit
dfx$Debet <- ifelse(dfx$TransactionAmount < 0 , credit, debet)
dfx$Credit <- ifelse(dfx$TransactionAmount < 0 , debet,  credit)
dfx$TransactionAmount <- abs(dfx$TransactionAmount)
## Fill in the blanks
dfx$ReferenceNumber <- transactionNumber
dfx$Ref1 <- ''
dfx$Ref2 <- result$fileName
dfx$Ref3 <- result$fileUrl
dfx$Ref4 <- ''
names(dfx)[1] <- "TransactionDescription"

#####################################################################
x <- writeTransactions(df)
