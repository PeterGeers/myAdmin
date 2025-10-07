source("myFunctions.R")
##### Load packages####
packResult <- getPackages(c("DBI", "tidyverse","lubridate"))

####################################################################################
transactionNumber <- 'BTW'
df <- getLastTransactions(transactionNumber)[1,]
folderId <- "0B9OBNkcEDqv1NFBjTm9PbFNnNzQ"
result <- getTextFromPdf(folderId, transactionNumber)
###################################################################################
## file location
df$Ref1 <- ""
df$Ref2 <- ""
df$Ref3 <- result$fileUrl
df$Ref4 <- result$fileName

## define te ontvangen of te betalen
## status <- grep("Totaal te betalen", result$txt)
status <- ifelse (length(grep("Totaal te betalen", result$txt)) == 0, 
                  "Te ontvangen", "Te betalen")

df$TransactionDescription<- ifelse(status == "Te betalen",
                                  paste("BTW Aangifte BSN 812613764", status,
                                  result$txt[grep("Aangiftenummer", result$txt)[[1]]], 
                                  str_split(result$txt[grep("betalingskenmerk", result$txt)[[1]]], 
                                            "Belastingdienst. Vermeld bij uw betaling het")[[1]][2], 
                                  sep = " - "),
                                  
                                  paste("BTW Aangifte BSN 812613764", status,
                                        result$txt[grep("Aangiftenummer", result$txt)[[1]]],
                                        sep = " - ")
                                    )

df$TransactionDate <- dmy(str_split(result$txt[grep("Tijdvak ", result$txt)[1]],"t/m")[[1]][2])


##################### Totaal € 5.115 ((what about dot seperator in NL))

a <- getAmount(result$txt[grep("^ Totaal$", result$txt)+1])
### No decimal in amount only whole numbers
if (a != floor(a)){
 a <- a * 1000   
}

ledgers <- getLedgerCodes("A")
df$TransactionAmount <- a

df$Debet <- ifelse(status == "Te betalen" ,ledgers[3], ledgers[2])
df$Credit <-ifelse(status == "Te betalen" ,ledgers[2], ledgers[3])
###############################################################################################

x <- writeTransactions(df)
