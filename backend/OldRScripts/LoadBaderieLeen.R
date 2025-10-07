source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Baderie Leen'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1RbqRL_VVvGNZaNAN8MjNksiH4v7QhcjM" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

##### Under Construction ###########
## Factuur datum
df$TransactionDate <- dmy(result$txt[grep("Datum",result$txt)])
################################################################

df$TransactionAmount[1] <- getAmount(result$txt[grep("Factuurbedrag €",result$txt)])
df$TransactionAmount[2] <- df$TransactionAmount[1] - getAmount(result$txt[grep("Totaal exclusief BTW €",result$txt)])


df$TransactionDescription <- paste("Baderie Leen", result$txt[grep("Factuur$",result$txt)+1],result$txt[grep("Werkbon",result$txt)], sep = " ")
###################################################################
## Append records
x <- writeTransactions(df)
