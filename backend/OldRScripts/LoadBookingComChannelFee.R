source("myFunctions.R")

packResult <- getPackages(c("tidyverse","lubridate"))
#### define the file numbers to load
invoices <- 3
####################################################################################
transactionNumber <- 'Booking.com'
df <- head(getLastTransactions(transactionNumber),2)  ## Leave it here

if (nrow(df) <2){
    df <- rbind(df,df)  
}
### Set proper account codes
df$Debet[1] <- "4007"
df$Debet[2] <- "2010"
df$Credit[1] <- "1600"
df$Credit[2] <- '4007'

################################################################################ 
## Provide unique file id
folderId <- "1hsk9PUCArG4fgrwmPFYDEJASQ4TXe8WL" ## Unique ID of folder containing Files

for (i in 1 : invoices) {
    result <- getTextFromPdf(folderId, transactionNumber, i)

    ##################################################################################
    df$Ref3 <- result$fileUrl
    df$Ref4 <- result$fileName

    ### Define listing name
    accomLookUp <- getBnbLookup('bdc') ## Get match linsting Id on Listing Name
    accomodatie <- gsub("[[:alpha:]]|:|\\s","", result$txt[grep("Accommodatie ID:|Accommodation number:",result$txt)])
    df$Ref1 <- accomLookUp$name[grep(accomodatie, accomLookUp$id)]

    ##### df$TransactionDate###########
    df$TransactionDate <- dmy(result$txt[grep("Datum:|Date:", result$txt)])

################################################################
    df$TransactionAmount[1] <- round(getAmount(result$txt[grep("Totaal EUR|Total amount due EUR",result$txt)]),2)
    df$TransactionAmount[2] <- round((df$TransactionAmount[1] /121)*21,2)



    df$TransactionDescription[1] <- paste(df$Ref1[1],
                                      result$txt[grep("Factuurnummer:|Invoice number:", result$txt)], 
                                      df$TransactionDate[1], sep = " ")
    df$TransactionDescription[2] <- paste( df$TransactionDescription[1], "BTW",  sep = " ")

    df$TransactionNumber <- paste(transactionNumber,df$TransactionDate, sep = " ")
###################################################################
## Append records
    x <- writeTransactions(df)
    
}