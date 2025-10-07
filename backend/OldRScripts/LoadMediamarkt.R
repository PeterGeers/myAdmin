source("myFunctions.R")

packResult <- getPackages(c("DBI", "stringi"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Mediamarkt'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1cnlvaWhseG56S2c" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving


## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
txt <- str_split(result$txt[grep("Datum:", result$txt)], " ")
df$TransactionDate <- dmy(txt[[1]][5])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal Bruto", result$txt)]) ## Bedrag
df$TransactionAmount[2] <- df$TransactionAmount[1] - getAmount(result$txt[grep("BTW Totaal Netto", result$txt)]) ## Totaalbedrag

df$TransactionDescription <- paste("Mediamarkt",  txt[[1]][1],  txt[[1]][2],  txt[[1]][3] , sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
