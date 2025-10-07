source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'toppy'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1H2i0v3ec8UuFRbPXOx-cRe8ZG5I1wdkM" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## Factuur datum
df$TransactionDate <- ymd(result$txt[grep("Factuurdatum:",result$txt)])
################################################################

df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("Eindtotaal", result$txt)],"€")[[1]][2])
df$TransactionAmount[2] <- getAmount(result$txt[grep("BTW €", result$txt)])

df$TransactionDescription <- paste("Toppy", result$txt[grep("Factuurnummer:", result$txt)], sep = " ")
###################################################################
## Append records
x <- writeTransactions(df)
