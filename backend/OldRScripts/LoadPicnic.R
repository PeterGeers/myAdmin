source("myFunctions.R")
packResult <- getPackages(c("tidyverse"))
###################################################################################
## Geef jaar op waarop betrekking
###################################################################################
###################################################################################
###################################################################################
jaar <-  year(Sys.Date())
####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Picnic'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1H2AkTJo-75TuPWNMfdcCIRcevXVBW48b" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber) 

##################################################################################
## Process data
df$Ref1 <- ""
df$Ref2 <- ""
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

################################################################
jaar <- "2025"
x <- str_split(result$txt[grep("Hier is het bonnetje bij je bezorging", result$txt)+1], " ")[[1]]
df$TransactionDate <- getDateFromTxt(x[length(x)], x[length(x)-1], x[length(x) - 2])

## df$TransactionAmount[1] <- getAmount(result$txt[grep("Totaal",result$txt)])
df$TransactionAmount[1] <- getAmount(str_split(result$txt[grep(" Totaal Wordt rond 2 dagen na de",result$txt)+1],"afgeschreven.")[[1]][2])/100
btwLaag <- getAmount(strsplit(result$txt[grep("Btw 9", result$txt)],")")[[1]][2])/100
btwHoog <- getAmount(strsplit(result$txt[grep("Btw 21", result$txt)],")")[[1]][2])/100
df$TransactionAmount[2] <- btwLaag + btwHoog

df$TransactionDescription <- paste("Picnic boodschappen voor studios",result$txt[grep("Order",result$txt)] ,df$Ref4[1])

###################################################################
## Append records
x <- writeTransactions(df)
