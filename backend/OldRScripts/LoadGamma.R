source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Gamma'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1vQgZszViaPskVEmq0z0Ra_l5t-jNNjHd" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## Factuur datum
df$TransactionDate <- date(dmy_hm(result$txt[grep("Datum:",result$txt)]))
################################################################

df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("TOT.OMZET TOT.BTW", result$txt)+1], " ")[[1]][2])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("TOT.OMZET TOT.BTW", result$txt)+1], " ")[[1]][3])


df$TransactionDescription <- paste("Gamma", result$txt[grep("Ticket",result$txt)], sep = " ")
###################################################################
## Append records
x <- writeTransactions(df)
