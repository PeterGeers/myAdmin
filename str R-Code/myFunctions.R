####################################### Package names
## packages <- c("DBI", "stringi", "RMariaDB", "pdftools", "googledrive")

# Install packages not yet installed
getPackages <- function(packages)
{
  installed_packages <- packages %in% rownames(installed.packages())
  if (any(installed_packages == FALSE)) {
    install.packages(packages[!installed_packages])
  }
  # Packages loading
  packResult <- lapply(packages, library, character.only = TRUE)
  return(packResult)
}

#####################################################################################
## Append data to BnB

writeBookings <- function(df, tabel)
{
  getPackages("RMariaDB")
  config <- config::get(config= 'production', file = "./conf/config.yml")
  con <- dbConnect(RMariaDB::MariaDB(), user = config$user,  password = config$passwd , dbname = "finance", host = "localhost")
## con <- dbConnect(RMySQL::MySQL(), dbname = "finance" , username = config$user, password = config$passwd)
## refcols <- c("sourceFile", "channel", "listing", "checkinDate", "checkoutDate", "nights", "guests", "amountGross",  "amountNett", "amountChannelFee", "amountTouristTax", "amountVat", "guestName", "reservationCode", "reservationDate", "status", "pricePerNight", "daysBeforeReservation", "addInfo", "year", "q", "m")
  refcols <- names(df)
  p1  <- paste('INSERT INTO',  tabel,"(",toString(refcols), ")", "VALUES ")
  
##  updateString <- paste0( apply(df, 1, function(x) paste0("('", paste0(x, collapse = "', '"), "')")), collapse = ", ")
  updateString <- paste0( apply(df, 1, function(x) paste0('("', paste0(x, collapse = '", "'), '")')), collapse = ", ")
  updateString2 <- paste0(p1, updateString,';')
  
  
  ##############################################################################################
  ## dbExecute(con, "INSERT INTO cars (speed, dist) VALUES (1, 1), (2, 2), (3, 3);")
  nrOfRecords <- dbExecute(con, updateString2)
  
  dbDisconnect(con)
  
  return(nrOfRecords)
}

#####################################################################################
#####################################################################################
## Delete data from  BnBplanned

deleteAllRecords <- function(table)
{
  getPackages("RMariaDB")
  config <- config::get(config= 'production', file = "./conf/config.yml")
  con <- dbConnect(RMariaDB::MariaDB(), user = config$user,  password = config$passwd , dbname = "finance", host = "localhost")
  updateString  <- paste0("delete from ", table)
  
  ##############################################################################################
  ## dbExecute(con, "INSERT INTO cars (speed, dist) VALUES (1, 1), (2, 2), (3, 3);")
  nrOfRecords <- dbExecute(con, updateString)
  
  dbDisconnect(con)
  return(nrOfRecords)
}
#########################################################################

## Append data to BnB

writeStamps <- function(df, table)
{
  getPackages("RMariaDB")
  config <- config::get(config= 'production', file = "./conf/config.yml")
  con <- dbConnect(RMariaDB::MariaDB(), user = config$user,  password = config$passwd , dbname = "finance", host = "localhost")
  refcols <- c("date", "channel", "listing", "amount", "items")
  df <- df[,refcols]
  
  p1  <- paste('INSERT INTO',  table,"(",toString(refcols), ")", "VALUES ")
  
  updateString <- paste0( apply(df, 1, function(x) paste0("('", paste0(x, collapse = "', '"), "')")), collapse = ", ")
  
  updateString2 <- paste0(p1, updateString,';')
  
  
  ##############################################################################################
  ## dbExecute(con, "INSERT INTO cars (speed, dist) VALUES (1, 1), (2, 2), (3, 3);")
  nrOfRecords <- dbExecute(con, updateString2)
  
  dbDisconnect(con)
  return(nrOfRecords)
}

###########################################################################################
getReservationCodes <- function(table)
{
  getPackages("RMariaDB")
  config <- config::get(config= 'production', file = "./conf/config.yml")
  con <- dbConnect(RMariaDB::MariaDB(), user = config$user,  password = config$passwd , dbname = "finance", host = "localhost")
  codes <- dbReadTable(con, table)
  dbDisconnect(con)
  ### data to string to verify existing reservationCodes (pattern string)
  x <- paste0(codes$reservationCode, collapse="|")
  rm(codes) ## remove data frame
  return(x)
}
###########################################################################################
getSQLtable <- function(x){
  getPackages("RMariaDB")
  config <- config::get(config= 'production', file = "./conf/config.yml")
  con <- dbConnect(RMariaDB::MariaDB(), user = config$user,  password = config$passwd , dbname = "finance", host = "localhost")
  response <- dbReadTable(con,x)
  dbDisconnect(con)
  return(response)
}

#############################################################################################
updateAdmin <-  function(data, tab, fileName) {
  x <- getPackages("xlsx")
  data <- mutate(data, across(where(is.character), trimws))
  data <- as.data.frame(data)
  config <- config::get(config= 'production', file = "./conf/config.yml")
  ## pathName <- paste0(getwd(),"/reports/")
  pathName <- config$share
  fileName <- paste0(pathName,fileName)
  wb <- loadWorkbook(fileName)
  
  ## Start writing data
  removeSheet(wb, sheetName= tab)
  newSheet <- createSheet(wb, sheetName= tab)
  ##  addDataFrame(fig, newSheet, startRow=1, startColumn=1,row.names=FALSE,col.names=TRUE) 
  cs1 <- CellStyle(wb) + Font(wb, isItalic=TRUE) # rowcolumns
  cs2 <- CellStyle(wb) + Font(wb, color="blue")
  cs3 <- CellStyle(wb) + Font(wb, isBold=TRUE) + Border() # header
  
  ## get cellRange A1:x1 where ncol of df ascii A [65]
  range <- paste0("A1:",rawToChar(as.raw(64+ncol(data))),"1")
  addAutoFilter(newSheet, cellRange = range)
  addDataFrame(data, newSheet, startRow=1, startColumn=1,row.names=FALSE,col.names=TRUE, colnamesStyle=cs3,
               rownamesStyle=cs1, colStyle=list(`1`=cs2))
  
  
  saveWorkbook(wb, file=fileName) 
  return(fileName)
}

###########################################################################
## Only for comma/dot seperated values function(x)
getAmount <- function(amount_string) {
  cleaned_string <- gsub("[^0-9.,]", "", amount_string)  ### Keep only numbers, commas and dots
  ## identify decimal seperator
  decimal_seperator <- gsub("[^.,]", "", cleaned_string) ## get seperators
  ##  Define last seperator as decimal seperator for each seperator
  for (i in 1:length(decimal_seperator)){
    if (nchar(decimal_seperator[i]) > 1){
      decimal_seperator[i]  <- substr(decimal_seperator[i], 
                                   nchar(decimal_seperator[i]),  nchar(decimal_seperator[i]))
    }
    
    if (decimal_seperator[i] == ",") { ## comma as decimal seperator
      cleaned_string[i] <- gsub("\\.",  "", cleaned_string[i]) ## Remove dots
      cleaned_string[i] <- gsub(",", ".", cleaned_string[i]) ## Replace comma by dot
    } else { ## dot as decimal seperator or whole number
      cleaned_string[i] <- gsub(",", "", cleaned_string[i])
    }
  }
  return(as.numeric(cleaned_string))
}