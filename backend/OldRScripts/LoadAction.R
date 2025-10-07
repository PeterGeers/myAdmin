source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Action'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "0B9OBNkcEDqv1WjJHVGhodWF3NjQ" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName


##### df$TransactionDate seems to work ###########
x <- str_split(result$txt[grep(maandPattern, result$txt, ignore.case = TRUE)]," ")[[1]]
df$TransactionDate <- getDateFromTxt(x[5], x[4], x[3])

################################################################
x <- str_split(result$txt[grep("^ Totaal € ", result$txt, ignore.case = TRUE)],"€")
df$TransactionAmount[1] <- getAmount(x[[1]][4])
df$TransactionAmount[2] <- getAmount(x[[1]][2])

df$TransactionDescription <-  paste("Action", result$txt[grep(maandPattern, result$txt, ignore.case = TRUE)][1], sep = "")
###################################################################
## Append records
x <- writeTransactions(df)
