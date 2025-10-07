source("myFunctions.R")
packResult <- getPackages(c("tidyverse", "lubridate","devtools","tesseract","magick", "googledrive"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Albert Heijn'
df <- getLastTransactions(transactionNumber)

################################################################################ 
folderId <- "17MF0ZVA0xyXUHWCQbHnVn3B0tSz4NoqP" ## Unique ID of folder containing Files

result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################

df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

x <- str_split(result$txt[grep("BETALING Datum", result$txt)][1], " ")[[1]]
df$TransactionDate <- dmy(x[3])

df$TransactionAmount[1] <- getAmount(result$txt[grep("PINNEN", result$txt)])
x <- str_split(result$txt[grep("^TOTAAL", result$txt)][2], " ")[[1]][3]
df$TransactionAmount[2] <- getAmount(x)

df$TransactionDescription <- paste(result$txt[grep("KLANTTICKET",result$txt)], result$txt[grep("Transactie",result$txt)], sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)