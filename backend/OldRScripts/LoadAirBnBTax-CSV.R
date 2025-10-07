################Load airBnB files ############
source("myFunctions.R")
# Package names

packResult <- getPackages(c("tidyverse", "lubridate", "googledrive"))
config <- config::get(config = "production", file = "conf/config.yml")

####################################################################################
transactionNumber <- "AirBnB"
df <- head(getLastTransactions(transactionNumber),1)

folderId <- "19NR7Qd_ThTZ0J37E87fBeH9-kh8xMX-p"
###################################################################################

folderContent <- drive_ls(as_id(folderId)) ## Retrieves content of folder
fileCode <- folderContent$id[[1]]  ## Most recent added file to folder
fileDetails <- drive_get(id=fileCode)
fileName <- fileDetails[[1]]  ## Most recent added file to folder
fileUrl <- fileDetails$drive_resource[[1]]$webViewLink
fileDir <- paste0(config$gdrive,"Facturen/",transactionNumber,"/" )#############################
fileToRead <- paste0(fileDir, fileName)
airBnB <- read_delim(fileToRead)
xNames <- names(airBnB)
xNames[grep("Servicekosten", xNames)] <- "Servicekosten"
colnames(airBnB) <- xNames
################################################
## Retrieve relevant figures 
hostFee <- sum(na.omit(airBnB$Nettobedag)) ## Nett Hosting Fee paid to AirBnB

################### Calculate transaction data
## Hosting Fee
df4 <- c('4007','1600','Hosting Fee') ## 4007, 1600 adds to outstanding amount

### define records for Database transaction
df$TransactionNumber <- paste("AirBNB ", Sys.Date())
df$TransactionDate <- max(airBnB$`Datum van dienst`)
df$Debet <- df4[[1]]
df$Credit <- df4[[2]]
df$Ref1 <- df4[[3]]
df$TransactionAmount <- hostFee
df$TransactionDescription <- paste(df4[[3]], fileName, sep = "; ")
df$Ref2 <- fileName
df$Ref3 <- fileUrl
df$Ref4 <- fileName
###############################################################################################

## Append records
x <- writeTransactions(df)
