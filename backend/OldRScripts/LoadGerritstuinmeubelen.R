source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Gerritstuinmeubelen'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1tlWUZZGF-fBKTg27FxIYbj5H0sALVPgU" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
x <- str_split(result$txt[grep("Factuurdatum", result$txt)], " ")[[1]]
## Factuur datum
df$TransactionDate <- getDateFromTxt(x[4], x[3], x[2])
################################################################
exBTW <- getAmount(str_split(result$txt[grep("Eindtotaal \\(excl. BTW):",result$txt)], ":")[[1]][2])
btw <- getAmount(str_split(result$txt[grep("BTW 21% \\(21%):",result$txt)], ":")[[1]][2])
df$TransactionAmount[1] <- exBTW + btw
df$TransactionAmount[2] <- btw


df$TransactionDescription <- paste(result$txt[grep("Factuurnummer",result$txt)], 
                                   result$txt[grep("Ordernr",result$txt)], 
                                   sep = " ")
###################################################################
## Append records
x <- writeTransactions(df)
