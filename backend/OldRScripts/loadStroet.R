source("myFunctions.R")

packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Stroet'
df <- tail(getLastTransactions(transactionNumber),2)

################################################################################ 
## Provide unique file id
folderId <- "1Lx9s0cvIqrFu6Q1rEfpVllaufYUoR3oL" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

################  CONTIINUE HERE ###########################
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## datum <- content$TransactionDescription[[row]][4]

x <- str_split(result$txt[grep("Datum", result$txt)+1], " ")[[1]]

df$TransactionDate <- dmy(x[2])
df$TransactionDescription <- paste("Klantnr", x[3], " Factuur:", x[1] )


## Bedrag en BTW starts with "Verzenddatum"
df$TransactionAmount[1] <-getAmount(result$txt[grep(" Totaal €", result$txt)])
x <- str_split(result$txt[grep("Verwijderingsbijdrage", result$txt)+1], "€")[[1]]
df$TransactionAmount[2] <- getAmount(x[2])

###Write to DB #####################################################################################
x <- writeTransactions(df)
