source("myFunctions.R")
packResult <- getPackages(c("DBI", "stringi","lubridate"))
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'ToolStation'
df <- getLastTransactions(transactionNumber)
if (nrow(df) <2){
    df <- rbind(df,df)  
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
}

################################################################################ 
## Provide unique file id
folderId <- "1JCAYuT5-ykn-vfdKkEFTLbs7Nw-lpYoY" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber)
##################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

##### Under Construction ###########
## Factuur datum
df$TransactionDate <- date(ymd_hms(result$txt[grep("Datum bestelling",result$txt)]))
################################################################

df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep("Toolstation NL B.V Btw-code Tarief Netto Btw Totaal",result$txt)+3],"€")[[1]][4])
df$TransactionAmount[2] <- getAmount(str_split(result$txt[grep("Toolstation NL B.V Btw-code Tarief Netto Btw Totaal",result$txt)+3],"€")[[1]][3])


df$TransactionDescription <- paste(transactionNumber, result$txt[grep("Factuurnummer:",result$txt)], sep = " ")
df$TransactionDescription <- sub("Beste Meneer:", "Klantnummer: ", df$TransactionDescription)

###################################################################
## Append records
x <- writeTransactions(df)
