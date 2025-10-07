### Display kassabon op website and Ctrl P generates pdf van kassabo
source("myFunctions.R")
packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- "Action"
df <- head(getLastTransactions(transactionNumber),2)
folderId <- "0B9OBNkcEDqv1WjJHVGhodWF3NjQ"

################################################################################ 
## Provide unique file id

result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
x <- str_split(result$txt[grep("Polderplein ", result$txt)+1], " ")[[1]]
## year(Sys.Date())
df$TransactionDate <- getDateFromTxt(year(Sys.Date()), x[4], x[3])
    
## transaction Amount build sub step to handle txt changes
x <- str_split(result$txt[grep("Totaal €", result$txt)], " ")[[1]]
df$TransactionAmount[1] <- getAmount(x[8]) ## BTW Bedrag ## Totaalbedrag
df$TransactionAmount[2] <- getAmount(x[4]) ## BTW Bedrag ## Totaalbedrag

## Description
df$TransactionDescription <- paste("Action",result$txt[grep("Bonnummer", result$txt)] ,sep = " ")

## Ledgers to use
x <- getLedgerCodes("A")
df$Debet[1] <- x[1]
df$Credit[1] <- x[2]
df$Debet[2] <- x[3]
df$Credit[2] <- x[4]

###Write to DB #####################################################################################
x <- writeTransactions(df)
