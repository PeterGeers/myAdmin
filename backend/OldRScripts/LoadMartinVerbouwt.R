source("myFunctions.R")

packResult <- getPackages(c("tidyverse","lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Martin Verbouwt'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1swZ2R0_6WFUSc63Em_N9ZzaGBEvazc7f" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)

##################################################################################
## Process data
df$Ref3 <- result$fileUrl
df$ref4 <- result$fileName

## TransactionDate "Datum: 15 Oktober 2023"
x <- str_split_1(result$txt[grep("Datum:", result$txt)]," ")
df$TransactionDate <- getDateFromTxt(x[4], x[3],x[2])

## Totaal € 21.74
df$TransactionAmount[1] <-  getAmount(str_split(result$txt[grep("Te betalen: € ", result$txt)],"€")[[1]][2])
## BTW 21.00% € 3.77
df$TransactionAmount[2] <-  getAmount(str_split(result$txt[grep("21% BTW €", result$txt)],"€")[[1]][2])

df$TransactionDescription <- paste(transactionNumber,  getAmountString(result$txt, "Factuurnummer: "),   sep = ' ')
###################################################################
## Append records
x <- writeTransactions(df)

