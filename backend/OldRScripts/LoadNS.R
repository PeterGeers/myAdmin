source("myFunctions.R")

packResult <- getPackages(c("DBI","stringi"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'NS Business Card'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1R3VIVjg4Z3pjNEk" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages


klant <- "Debiteurnummer 207830547"

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## identify and format TransactionDate
x <- str_split_1(result$txt[grep("Factuurdatum ", result$txt)]," ")
df$TransactionDate <- getDateFromTxt(x[12], x[11], x[10])

#################################################################################
df$TransactionDescription <- paste(klant, result$txt[grep("Factuurnummer", result$txt)], sep = ' ')

## Door u te betalen
df$TransactionAmount[1] <- getAmount(str_split_1(result$txt[grep("Door u te betalen", result$txt)],"€")[2])
## bedrag excl BTW deduct from Totals
df$TransactionAmount[2] <- df$TransactionAmount[1] - getAmount(str_split_1(result$txt[grep("Totaal exclusief BTW €", result$txt)],"€")[2]) 

###############################################################################################

x <- writeTransactions(df)
