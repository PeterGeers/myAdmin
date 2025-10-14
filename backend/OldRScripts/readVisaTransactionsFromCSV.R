# Package names
source("myFunctions.R")
voorkeur <- "Default"

packResult <- getPackages(c("tidyverse", "lubridate", "tidyr"))
##config <- config::get(config = 'test', file = "./conf/config.yml")
config <- config::get(config = 'production', file = "conf/config.yml")
file <- list.files(config$download,pattern ="^CSV_CC",full.names = TRUE)
for (i in 1:length(file)){
    df <- read_csv(file[i], quote = "\"", 
                   locale=locale(encoding="latin1"),
                   col_types = cols(.default = col_character()),
                   col_names = TRUE)
    print(i)
    if (i == 1){
        bookings <- df 
    } 
    else {
        bookings <- bind_rows(df, bookings)  
    }
}


## fileName <- list.files(config$download,pattern ="CSV_CC", full.names = TRUE)
## df <- read_lines(fileName, skip=1)
bookings <- as.data.frame(bookings)
names(bookings)[1] <- "Ref3"

## Start processing determine TransactionNumber
names(bookings)[1] <- "Ref3"
names(bookings)[grep("Datum", names(bookings))] <- "TransactionDate"
names(bookings)[grep("Transactiereferentie", names(bookings))] <- "Ref1"
names(bookings)[grep("Bedrag", names(bookings))] <- "TransactionAmount"
names(bookings)[grep("Productnaam", names(bookings))] <- "Ref2"

bookings$TransactionDescription <- paste_cols_by_index(bookings, c(10:length(bookings)))

bookings$TransactionNumber <- paste('Visa ',format(Sys.Date(), "%Y-%m-%d"))
bookings$Administration <- ifelse (grepl("NL71RABO0148034454", bookings$Ref3), "PeterPrive", "GoodwinSolutions")
bookings$ReferenceNumber <- voorkeur
bookings$Ref4 <- ""
##################################################################################################################################

## Debet en Credit Reknum 
## Bij is deb 4001 en cred 4002
pattern <- ","
bookings$TransactionAmount <- as.numeric(sub(pattern,".",bookings$TransactionAmount))

## Always 4001 (total Booking is already against 4001) Manually adjust if wanted
vMin <- c("4002","2001") ## Vakantie default
vPlus <- c("2001","2001")
bookings$Debet <- ifelse(bookings$TransactionAmount > 0 , vPlus[1], vMin[1])
bookings$Credit <- ifelse(bookings$TransactionAmount < 0 , vPlus[2], vMin[2])

bookings$TransactionAmount <- abs(bookings$TransactionAmount)

x <- writeTransactions(bookings)

