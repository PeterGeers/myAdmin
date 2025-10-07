source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'DekbedDiscounter'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1qqBh7x94rN2HbFCXTlYwSFk-esdBP_Ch" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName


##### df$TransactionDate seems to change regular ###########
x <- str_split(result$txt[grep("Datum", result$txt)+1], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[7], x[5], x[6])

################################################################
df$TransactionAmount[1] <-  getAmount(str_split(result$txt[grep("incl. BTW €", result$txt)],"€")[[1]][2])
df$TransactionAmount[2] <- df$TransactionAmount[1] -  getAmount(str_split(result$txt[grep("excl. BTW €", result$txt)],"€")[[1]][2])

df$TransactionDescription <- result$txt[grep("Factuurnummer", result$txt)+1]
###################################################################
## Append records
x <- writeTransactions(df)
