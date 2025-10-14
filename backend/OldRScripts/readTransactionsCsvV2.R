## https://bankieren.rabobank.nl/online/nl/settings/betaal-en-spaarrekening/download-transaction-reports?origin=search&query=downloaden%20transacties&tab=all
source("myFunctions.R")
packResult <- getPackages(c("lubridate", "tidyverse", "RMariaDB"))
config <- config::get(config = 'production', file = "conf/config.yml")
#################  Get and Read all csv files in scope
file <- list.files(config$download, pattern = "^CSV_[O|A]", full.names = TRUE)
for (i in 1:length(file)) {
    df <- read_csv(
        file[i],
        quote = "\"",
        locale = locale(encoding = "latin1"),
        col_types = cols(.default = col_character()),
        col_names = TRUE
    )
    print(i)
    if (i == 1) {
        bookings <- df
    }
    else {
        bookings <- bind_rows(df, bookings)
    }
}


### Get rid of special character in column names
names(bookings)[12] <- "iniPartij"

## Load RABO bank account numbers
accounts <- getRecords("lookupbankaccounts_R")

names(bookings)[1] <- "rekeningNummer"

bookings <- left_join(bookings, accounts, by = "rekeningNummer")

colnames(bookings)[1] <- 'Ref1'
colnames(bookings)[4] <- 'Ref2'
colnames(bookings)[5] <- 'TransactionDate'
names(bookings)[7] <- "TransactionAmount"

## Start processing determine Transaction Number
bookings$TransactionNumber <- paste('Rabo', format(Sys.Date(), "%Y-%m-%d"))

## define aand clean Transactiondescription
bookings$Ref2 <-  as.character(as.numeric(bookings$Ref2))
x <- names(bookings)

bookings$TransactionDescription <- ""

####################################################################################################
bookings$`Naam tegenpartij`[grep("SHELL TO", bookings$`Naam tegenpartij`)] <- "Shell Kosovar"
###################################################################################################

vector <- c(
    grep("Naam tegenpartij", x),
    grep("Naam uiteindelijke partij", x),
    grep("Code", x),
    grep("Omschrijving", x),
    grep("Betalingskenmerk", x),
    grep("Tegenrekening", x),
    grep("BIC tegenpartij", x),
    grep("Transactiereferentie", x),
    grep("Machtigingskenmerk", x),
    grep("Incassant ID", x),
    grep("Ref2", x),
    grep("Saldo na trn", x)
) ## Sequence in bookings$description


for (i in 1:nrow(bookings)) {
    bookings$TransactionDescription[i] <- paste(bookings[i, vector], collapse = " ")
    bookings$TransactionDescription[i] <- gsub("NA", " ", bookings$TransactionDescription[i])
    bookings$TransactionDescription[i] <- gsub("\\s+", " ", bookings$TransactionDescription[i])
    bookings$TransactionDescription[i] <- gsub("Google Pay", "GPay", bookings$TransactionDescription[i])
    bookings$TransactionDescription[i] <- gsub("Google Pay", "GPay", bookings$TransactionDescription[i])
}

bookings$dc <- substring(bookings$TransactionAmount, 1, 1)
bookings$TransactionAmount <- substring(bookings$TransactionAmount, 2)
pattern <- ","
bookings$TransactionAmount <- as.numeric(gsub(pattern, ".", bookings$TransactionAmount))

## Add colums for use
bookings$Debet <- ifelse(bookings$dc == "+", bookings$Account, "")
bookings$Credit <- ifelse(bookings$dc == "-", bookings$Account, "")

bookings$ReferenceNumber <- ''
bookings$Ref3 <- ""
bookings$Ref4 <- ""

x <- unique(bookings$Administration)

for (i in 1:length(x)) {
    x1 <-  getTransactionsCodes(filter(bookings, Administration == x[i]))
    if (i == 1) {
        df <- x1
    }
    else {
        df <- bind_rows(df, x1)
    }
}

#####################################################################################
## Prevent double entries due to changing RABO Behavior
### filter lines already written in mutaties based on Ref2
nmbrs <- sort(unique(df$Ref1))
for (i in 1:length(nmbrs)) {
    used <- getUsedTrxNumber(nmbrs[i])
    toWrite <- filter(df, df$Ref1 == nmbrs[i] &
                          !df$Ref2 %in% used$existing)
    ###Write to DB if exist###########################################################
    if (nrow(toWrite > 0)) {
        x <- writeTransactions(toWrite)
    }
}

#################   Remove input files processed ###################
x1 <- list.files(config$download, pattern = "CSV_[O|A]_accounts", full.names = TRUE)
x2 <- file.remove(x1)