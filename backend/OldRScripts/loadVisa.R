source("myFunctions.R")

packResult <- getPackages(c("data.table","plyr", "dplyr", "DBI", "stringi"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'VISA'
dfTo <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1MmRkMWVjNTYtYzU3OS00MTY1LWEzOWItZDI5MmQxYmFlMzE5" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####
## Remove double spaces in omschrijving
pattern <- "[ ][ ]*"
result$text <- gsub(pattern,' ',result$text)

factuurNummer <- sub('.pdf','',result$fileName)

## Hardcoded variables 
boekJaar <- "2020"

content <- strsplit(result$text, "\r\n")
df <- setNames(do.call(cbind.data.frame, content), c("TransactionDescription"))    

## Remove special characters in text
df$TransactionDescription <- gsub("'",'', df$TransactionDescription)

## Select valid rows
## if (Bij | Af ) only 1 instance allowed
pattern <- "(^.[0-9][0-9]-[0-9][0-9]-20[0-9][0-9])" ## Letop spatie als eerste teken
df <- subset(df, lengths(regmatches(df$TransactionDescription, gregexpr(pattern, df$TransactionDescription))) == 1)

## define df$date 
df$dag <- substr(df$TransactionDescription,2,3)
df$maand <- substr(df$TransactionDescription,5,6)
df$jaar <- substr(df$TransactionDescription,8,11)
df$TransactionDate <- paste(df$jaar, df$maand, df$dag, sep = "-")

## Build bedrag numeric
df$spend <- grepl(" - ", df$TransactionDescription)
pattern <- "[0-9]*,[0-9][0-9]"
df$TransactionAmount <- stri_match_last(df$TransactionDescription, regex = pattern)
df$TransactionAmount <- as.numeric(gsub(",",".",df$TransactionAmount[,1]))

df$TransactionNumber <- paste('Visa', format(Sys.Date(),'%Y-%m-%d'))
df$Administration <- 'PeterPrive'

debet <- '4001'
credit <- '1300'

## if (Bij | Af )
df$Debet <- ifelse(df$spend, debet, credit)
df$Credit <- ifelse(df$spend, credit, debet)
## Define vfixed values
df$ReferenceNumber <- 'RABO Visa Rekening'
df$Ref1 <- ''
df$Ref2 <- ''
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

#############################################################################################################
x <- writeTransactions(df)



