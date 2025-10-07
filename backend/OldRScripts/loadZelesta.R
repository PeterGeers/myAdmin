source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Zelesta'
df <- tail(getLastTransactions(transactionNumber),2)

################################################################################ 
## Provide unique file id
folderId <- "1THhTgvXyl-Ra4qVXhbw-V_lDmmrMC3B_" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## datum <- content$TransactionDescription[[row]][4]

x <- str_split(result$txt[grep("INV#", result$txt)][1], " ")

df$TransactionDate <- getDateFromTxt(x[[1]][4],x[[1]][3], x[[1]][2])
df$TransactionDescription <- paste("Factuur", result$txt[grep("INV#", result$txt)][1])


## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <-getAmount(result$txt[grep("Totaal EUR ", result$txt)])
df$TransactionAmount[2] <- getAmount(strsplit(result$txt[grep("NL btw 21% EUR", result$txt)], "NL btw 21% EUR")[[1]][2])

###Write to DB #####################################################################################
x <- writeTransactions(df)
