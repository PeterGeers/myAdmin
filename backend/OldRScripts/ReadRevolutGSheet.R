# Package names
source("myFunctions.R")
administration <- c("PeterPrive","")
account <- c("1022", "1021") ## Current status
accountNmbr <- c("NL08REVO7549383472", "NL05REVO8814090866")
toUse <- 1

nrFiles <- 1 ## Files to process based on nrOf Revo files loaded
nzd <- 0.5271
eur <- 1
packResult <- getPackages(c("lubridate", "tidyverse", "googledrive", "googlesheets4"))
##config <- config::get(config = 'test', file = "./conf/config.yml")
config <- config::get(config = 'production', file = "conf/config.yml")
# This is usually done once per R session.
#Example usage of robust functions:
if (!drive_has_token()) {
    drive_auth()
} 

if (!gs4_has_token()) {
    gs4_auth()
} 


folderId <- "1fAuEkTEXgiNUw4FahFWi-KdeuSbfia3k"
folderContent <- drive_ls(as_id(folderId), n_max = nrFiles, recursive = FALSE, trashed = FALSE) ## Retrieves content of folder


## fileName <- folderContent$drive_resource[[fileNr]]$name  ## Most recent added file to folder
for (i in 1:nrow(folderContent)){
    
    x <- read_sheet(folderContent$drive_resource[[i]]$webViewLink)
    x$fileName <- folderContent$name[i]
    if (i > 1) {
        df <- bind_rows(df,x)
    }
    else {
        df <- x
    }
}

x <- names(df)
x[6] <- "Amount"
x[7] <- "Fee"
x[9] <- "State"
x[10] <- "Balance"
names(df) <- x



df$Amount <- as.numeric(df$Amount)
df$Fee <- as.numeric(df$Fee)
df$Balance <- as.numeric(df$Balance)

## Remove REVERTED lines
df <- df %>%
    filter(!grepl("REVERTED|PENDING", df$State))

#### Manage fee columns to add lines and remove column
fees <- df %>%
     filter(Fee > 0)
fees$Amount <- fees$Fee * -1
fees$Type <- "Revo Charges"
df <- bind_rows(df, fees)
df <- select(df, -Fee) ## remove Fee column

########################################################
xNames <- names(df)
names(df)[grep("Started Date|Startdatum", xNames)] <- "TransactionDate"
names(df)[grep("Description|Beschrijving", xNames)] <- "TransactionDescription"
names(df)[grep("Amount|Bedrag", xNames)] <- "TransactionAmount"
names(df)[grep("fileName", xNames)] <- "Ref4"
names(df)[grep("Balance", xNames)] <- "Ref3"

#################Manage account info################################################
df$Ref1 <- accountNmbr[toUse]
df$Ref2 <- paste_cols_by_index(df, c(1, 5, 7, 6, 8, 9, 1, 3, 2), "_")
df$Account <- account[toUse]

##### Manage currencies  #################
## df$TransactionAmount <- ifelse(df$Currency == "NZD", round(df$TransactionAmount * nzd, 2), df$TransactionAmount)
## df$Ref3 <- ifelse(df$Currency == "NZD", round(df$Ref3 * nzd, 2), df$Ref3)

df$Debet <- ""
df$Credit <- ""

for (i in 1: nrow(df))
{
    df$Debet[i]  <- ifelse(df$TransactionAmount[i] > 0, df$Account, ""  )
    df$Credit[i] <- ifelse(df$TransactionAmount[i] < 0, df$Account, ""  )
}

####### TODO Adapt tegenrekening op basis van Referencenumber zoals in Rabo
df$Administration <- administration[toUse] 

df$ReferenceNumber <- ""
df <- getTransactionsCodes(df)

############################################################################

df$TransactionAmount <- abs(df$TransactionAmount)
df$TransactionDate <- as.Date(df$TransactionDate)
df$TransactionNumber <- paste('Revolut',format(Sys.Date(), "%Y-%m-%d"))


### filter lines already written in mutaties 
toWrite <- filter(df, !df$Ref2 %in% 
                      getUsedTrxNumber(accountNmbr[toUse])$existing)  

if (nrow(toWrite) >0) {
    x <- writeTransactions(toWrite)    
}
