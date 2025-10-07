source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'CoolBlue'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "107ytj1QumN3Py8rG2dgpGKD_ymwo2J2Y" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages


df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

x <- str_split(result$txt[grep("Factuurdatum", result$txt)]," ")[[1]]
df$TransactionDate <- getDateFromTxt(x[5],x[4], x[3])

df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal €", result$txt)][1])
df$TransactionAmount[2] <- getAmount(strsplit(result$txt[grep(" BTW 21% € ", result$txt)], "€")[[1]][2])

df$TransactionDescription <- paste(result$txt[grep("Klantnummer", result$txt)], 
                                   result$txt[grep("Factuurnummer", result$txt)],
                                   result$txt[grep("Ordernummer", result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)