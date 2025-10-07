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
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

##### Under Construction ###########
## Factuur datum
df$TransactionDate <- dmy(result$txt[grep("Datum betaalopdracht",result$txt)])
################################################################

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal incl BTW €",result$txt)])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("Waarvan 21% over €",result$txt)],"€")[[1]][3])


df$TransactionDescription <- paste("Gamma", 
                                   str_split(result$txt[grep("Factuurnummer",result$txt)], "3830")[[1]][1],
                                   result$txt[grep("Ordernummer",result$txt)],
                                             sep = " ")
###################################################################
## Append records
x <- writeTransactions(df)
