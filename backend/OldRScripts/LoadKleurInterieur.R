source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'KleurInterieur'
df <- getLastTransactions(transactionNumber)
######################## Parameters to fill ########################################################
## Provide unique file id
folderId <- "1gp8vfrW-CAhGF9amzr5ZX70D__WBh5gO" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

###################################################################
df$TransactionDate <-  dmy(str_split(result$txt[grep("Factuurdatum:",result$txt, ignore.case = TRUE)],"Factuurdatum:")[[1]][2])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal inclusief € ",result$txt)])  ## Totaalbedrag
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("btw over",result$txt)],"€")[[1]][3])  ## Totaalbedrag
df$TransactionDescription <- paste(result$txt[grep("Factuurnummer", result$txt)], result$txt[grep("Debiteurnummer", result$txt)], sep = " - ")

## Append records
x <- writeTransactions(df)