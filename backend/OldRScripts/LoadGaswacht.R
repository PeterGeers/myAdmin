source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Gaswacht'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1TYrouQEDN3gitb_khHYf-rFhb2hbXESt" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
txt <- result$txt
## Factuur datum
df$TransactionDate <- dmy(result$txt[grep("Datum", result$txt)])

################################################################
#### Bedragen
df$TransactionAmount[1] <- getAmount(result$txt[grep("te betalen", result$txt)])
df$TransactionAmount[2] <-  round(df$TransactionAmount[1] /121*21,2)

df$TransactionDescription <- paste("Gaswacht", result$txt[grep("VF", result$txt)],"/", strsplit(result$txt[grep("Uw debite", result$txt)],":")[[1]][2], sep = "")
###################################################################
## Append records
x <- writeTransactions(df)
