#### https://www.netflix.com/billingActivity

source("myFunctions.R")
packResult <- getPackages(c("tidyverse", "lubridate"))

####################################################################################
# Load last Transanctions from db Finance
transactionNumber <- 'Netflix'
df <- getLastTransactions(transactionNumber)

################################################################################ 
## Provide unique file id
folderId <- "1mGTSylVOZ9oQedCbrzUeKra87vg5IaS1" ## Unique ID of folder containing Files
result <- getTextFromPdf(folderId, transactionNumber, 1)## Load packages

####################################################################################
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

### Combined row
x <- result$txt[grep("Streaming Service",result$txt, ignore.case = TRUE)]
############## Description
df$TransactionDescription <- x
### isolate date 2nd field
x <- str_split(x, " ")
df$TransactionDate <- dmy(x[[1]][2])

## transactinon Amount

df$TransactionAmount[1] <- getAmount(result$txt[grep("^ TOTAL €",result$txt)])
df$TransactionAmount[2] <- getAmount(result$txt[grep("^ VAT TOTAL €",result$txt)])
###Write to DB #####################################################################################
x <- writeTransactions(df)
