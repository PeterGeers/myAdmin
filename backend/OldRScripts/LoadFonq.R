source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Fonq'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1-A3DbmeFAAQz9HuhXfFBXTU5rexRUork" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName


##### df$TransactionDate seems to change regular ###########
df$TransactionDate <- dmy(result$txt[grep("Orderdatum", result$txt)])

################################################################
df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("Totaal EUR incl. btw", result$txt)], "incl. btw")[[1]][2])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("21% btw", result$txt)], "btw")[[1]][2])

df$TransactionDescription <- paste(result$txt[grep("Factuurnr", result$txt)], "Ordernr" ,str_extract(result$txt[grep("Factureren", result$txt)], "[0-9]{8}"), sep = "; ")
###################################################################
## Append records
x <- writeTransactions(df)
