# Laden van bonnetjes waar geen leesbare pdf van is. Hergebruik bestaande data en verander alleen datum bedragen en bronbestand
source("myFunctions.R")
# Package names
packResult <- getPackages(c("tidyverse","googledrive"))

######################## Parameters to fill ########################################################
transactionNumber <- "Diversen"

factuurBedrag <- 22.98
## btwBedrag <- round(factuurBedrag/121 *21, 2)
btwBedrag <- 3.99
factuurDatum <- "2025-09-10"
factuurOmschrijving <- "Etna Flessenrek Wit 475x110x95"

#####################################################################
df <- tail(getLastTransactions(transactionNumber),2)

if (nrow(df) <2) {  ## transactionNumber does not exist yet
    df[1:2,] <- "" ## Create 2 empty records
    df$Administration <- "GoodwinSolutions"
    df$ReferenceNumber <- transactionNumber
    df$TransactionNumber <- transactionNumber
}

###################################################################
ledgers <- getLedgerCodes("A")
df$Debet[1] <- ledgers[1] 
df$Credit[1] <- ledgers[2]
df$Debet[2] <- ledgers[3]
df$Credit[2] <- ledgers[4]

############### Read Goole Drive file details ##################
## Nr 1 is the last file in folder 1 To Max files in folder
x <- getDriveFileDetails(transactionNumber, 1)
df$Ref3 <- x[2] ## File Url
df$Ref4 <- x[1] ## File Name

## Transaction ##################################
df$TransactionDate <- factuurDatum
df$TransactionDescription <- factuurOmschrijving
df$TransactionAmount[2] <- btwBedrag
df$TransactionAmount[1] <- factuurBedrag ## Totaalbedrag

if(btwBedrag == 0){
    df <- df[1,]
}

###################################################################
## Append records
x <- writeTransactions(df)
