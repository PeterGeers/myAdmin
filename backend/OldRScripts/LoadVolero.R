source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Volero'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1ByKRDCVzrkX6PDNtchkqJOMPh3n-rU5i" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

## TransactionDate
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

lst <- str_split(result$txt[grep("Datum",result$txt)+1]," ")[[1]]
df$TransactionDate <- paste(lst[7], 
                  formatC(as.numeric(grep(lst[6], maandList,)), width=2, flag = "0"),
                  formatC(as.numeric(lst[5]), width=2, flag = "0"),
                  sep = "-" )

## transaction Amount build sub step to handle txt changes
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal incl. BTW €", result$txt)])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep(" BTW 21% €", result$txt)],"€")[[1]][2])

## Description
df$TransactionDescription <- paste(result$txt[grep("Datum",result$txt)],result$txt[grep("Datum",result$txt)+1], sep = "; ")


###Write to DB #####################################################################################
x <- writeTransactions(df)
result$txt[grep("Datum",result$txt)+1]
