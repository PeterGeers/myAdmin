source("myFunctions.R")
packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Ziggo VT'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1a25BYzMySDVPVjg" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)## Load packages##### Load packages####

#########################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName
###################################################################
## TransactionDate
xDate <- str_split(result$txt[grep("Factuurdatum", result$txt)],"Factuurdatum")[[1]][2]
xDate <- str_split_1(xDate, " ")
df$TransactionDate <- getDateFromTxt(xDate[4], xDate[3],xDate[2])
               
#########################################################################################
## transactinon Amount
df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal te betalen €", result$txt, ignore.case = TRUE)][3])

df$TransactionAmount[2] <- getAmount(str_split_1(result$txt[grep("Totaal €", result$txt)][1], "€")[3])
## df$TransactionAmount[2] <- df$TransactionAmount[1] - getAmount(result$txt[grep("Factuurbedrag excl. btw", result$txt, ignore.case = TRUE)])

df$TransactionDescription <- paste(result$txt[grep("Klantnummer", result$txt, ignore.case = TRUE)], "Factuurnummer ", 
                                   str_split_1(result$txt[grep("Factuurnummer", result$txt, ignore.case = FALSE)], "Factuurnummer")[2],  sep = ' ')

###Write to DB #####################################################################################
x <- writeTransactions(df)
