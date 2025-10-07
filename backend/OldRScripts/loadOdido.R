source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Odido'
df <- head(getLastTransactions(transactionNumber),2)

################################################################################ 
folderId <- "1-iCimq0QVzEs5oYrrbUwWpYd1HubDuyl" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

if(grepl("Internet", result$fileName)){
    df$TransactionDate <-    dmy(result$txt[grep("Datum factuur:", result$txt)] )
    df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal inclusief BTW", result$txt)])
    df$TransactionAmount[2] <-  df$TransactionAmount[1] - getAmount(result$txt[grep("Totaal exclusief BTW", result$txt)])
    df$TransactionDescription <- paste("Internet", result$txt[grep("Klantnummer:",result$txt)[1]], 
                                       result$txt[grep("Factuurnummer:",result$txt)], sep = ' ')
    df$Ref1 <- "Internet"
    
} else {
    
    x <- str_split(result$txt[(grep("Datum: ", result$txt))], " ")[[1]]
    df$TransactionDate <-  getDateFromTxt(x[5], x[4], x[3])

    df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal €", result$txt)])
    df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("btw 21%", result$txt)],":")[[1]][2])
    df$TransactionDescription <- paste(result$txt[grep("Je nummer:",result$txt)[1]], 
                                       result$txt[grep("Klantnummer:",result$txt)[1]], 
                                       result$txt[grep("Factuurnummer:",result$txt)], sep = ' ')
    df$Ref1 <- str_extract(result$txt[grep("Je nummer:",result$txt)[1]], "[0-9]{10}")
}




###Write to DB #####################################################################################
x <- writeTransactions(df)