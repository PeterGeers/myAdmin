source("myFunctions.R")
packResult <- getPackages(c("tidyverse","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Xenos'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1Ihda09R4UuofmJVy6cgsEAkKkUhKtXG6" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName


##### df$TransactionDate seems to change regular ###########
df$TransactionDate <- ymd("2024-12-20")

################################################################
df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("Totaal € ", result$txt)],"€")[[1]][2])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("BTW 9% €", result$txt)],"€")[[1]][2])

df$TransactionDescription <- str_split(result$txt[grep("Schutweg 8", result$txt)], " 8 ")[[1]][2]
###################################################################
## Append records
x <- writeTransactions(df)
