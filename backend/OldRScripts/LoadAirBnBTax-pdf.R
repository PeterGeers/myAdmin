source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- "AirBnB"
df <- head(getLastTransactions(transactionNumber),1)
folderId <- "19NR7Qd_ThTZ0J37E87fBeH9-kh8xMX-p"

################################################################################ 
## Provide unique file id

result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
x <- str_split(result$txt[grep("Rapport aangemaakt:", result$txt)], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[6], x[5], x[4])
    

## transaction Amount build sub step to handle txt changes
amount <- str_split(result$txt[grep("Inkomsten €",result$txt)],"-€ | € ")[[1]][4]
df$TransactionAmount[1] <- getAmount(amount) ## BTW Bedrag ## Totaalbedrag

## Description
df$TransactionDescription <- paste("AirBnB","Service kosten",result$txt[grep("Inkomstenrapport", result$txt)-1] ,sep = " ")
df$TransactionNumber <- paste("AirBNB ", Sys.Date())

## Hosting Fee
x <- c('4007','1600','Hosting Fee') ## 4007, 1600 adds to outstanding amount
df$Debet <- x[[1]]
df$Credit <- x[[2]]
df$Ref1 <- x[[3]]

###Write to DB #####################################################################################
x <- writeTransactions(df)
