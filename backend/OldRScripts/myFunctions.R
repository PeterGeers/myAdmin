## The following command disables printing your results in scientific notation.
options(scipen = 999)
## WEnsure global parameters are loaded
config <- config::get(config = "production", file = "conf/config.yml")
# Install packages not yet installed
getPackages <- function(packages) {
  installed_packages <- packages %in% rownames(installed.packages())
  if (any(installed_packages == FALSE)) {
    install.packages(packages[!installed_packages])
  }
  ##### packages loading
  pack_result <- lapply(packages, library, character.only = TRUE)
  return(pack_result)
}

############## Connect to MariaDV #################################
connectSql <- function(){
    getPackages(c("RMariaDB"))
    con <- dbConnect(RMariaDB::MariaDB(), dbname = config$database, username = config$user, password = config$passwd)
    return(con)
}

##############################################################################
## Function to retrieve records of TransactionNumber based on Max Date
getLastTransactions <- function(x) {
  getPackages(c("RMariaDB"))
  con <- connectSql()
  selectStr <- paste0("SELECT * FROM mutaties WHERE TransactionNumber like '", x, "%' AND TransactionDate = (SELECT MAX(TransactionDate) FROM  mutaties WHERE TransactionNumber like '", x, "%')ORDER BY mutaties.Debet DESC")
  res <- dbSendQuery(con, statement = selectStr)
  df <- dbFetch(res, n = -1)
  if (nrow(df) == 0) {
    x1 <- "Gamma"
    selectStr <- paste0("SELECT * FROM mutaties WHERE TransactionNumber like '", x1, "%' AND TransactionDate = (SELECT MAX(TransactionDate) FROM  mutaties WHERE TransactionNumber like '", x1, "%')ORDER BY mutaties.Debet DESC")
    res <- dbSendQuery(con, statement = selectStr)
    df <- dbFetch(res, n = -1)
    df$TransactionNumber <- x
    df$ReferenceNumber <- x
  }

  if (nrow(df) < 2) {
    df <- rbind(df, df)
    df$Debet[2] <- "2010"
    df$Credit[2] <- df$Debet[1]
  }

  xx <- dbDisconnect(con)

  return(df)
}

######################################################################################
## Function to retrieve text from PDF file in Google Drive based on folderId, lastFile in Folder and replica of file in Drive on PC

getTextFromPdf <- function(folderId, transactionNumber, fileNr) {

  getPackages(c("pdftools", "googledrive"))
  config <- config::get(config = "production", file = "./conf/config.yml")
  
  # Ensure Google Drive authentication
  if (!drive_has_token()) {
    drive_auth()
  }
  if (missing("fileNr")) {
      fileNr <- 1
  }
  ## drive_ls(path = as_id(id), trashed = FALSE, n_max = Inf)
  folderContent <- drive_ls(as_id(folderId), n_max = Inf, recursive = FALSE, trashed = FALSE) ## Retrieves content of folder
  fileName <- folderContent$drive_resource[[fileNr]]$name  ## Most recent added file to folder
  fileUrl  <- folderContent$drive_resource[[fileNr]]$webViewLink
  fileDir <- file.path(config$gdrive, "Facturen/", transactionNumber, "/") #############################
  ####################################################################################

  pdf_file <- file.path(fileDir, fileName)
  
  # Downloads-map
  downloads_path <- file.path("C:/Users/peter/Downloads", fileName)
 
  # Check if file exists locally, otherwise download from Google Drive
  if (!file.exists(pdf_file)) {
      if (file.exists(downloads_path)) {
          pdf_file <- downloads_path
      } else {
          tryCatch({
              # Use drive_download for reliable Google Drive downloads
              drive_download(as_id(folderContent$id[fileNr]), path = downloads_path, overwrite = TRUE)
              pdf_file <- downloads_path
          }, error = function(e) {
              stop("Download failed: ", e$message)
          })
      }
  }
  
  text <- pdf_text(pdf_file)
   
  txt <- ""
  pattern <- "\\s+"
##  for (i in 1:length(text)) {
##  x <- strsplit(text, "\n")[[i]]
##    x <- gsub(pattern, " ", x)
##    txt <- append(txt, x)
##  }
  
  txt <- unlist(lapply(text, function(page) {
      x <- strsplit(page, "\n")[[1]]
      gsub("\\s+", " ", x)
  }))
  

  my_list <- list("fileName" = fileName, "fileUrl" = fileUrl, "fileDir" = fileDir, "text" = text, "txt" = txt)
  return(my_list)
}

#####################################################################################
## Append data to Mutaties

writeTransactions <- function(df) {
  getPackages(c("RMariaDB"))
##  config <- config::get(config = "production", file = "./conf/config.yml")
  refcols <- c("TransactionNumber", "TransactionDate", "TransactionDescription", 
               "TransactionAmount", "Debet", "Credit", "ReferenceNumber", 
               "Ref1", "Ref2", "Ref3", "Ref4", "Administration")
  ##    df  <- df[, c(refcols)]
  df <- subset(df, select = refcols)
  ## Build updateString <- apply(final, 1, function(x) paste0("('", paste0(x, collapse = "', '"), "')"))
  p1 <- paste("INSERT INTO", config$table, "(     TransactionNumber,     TransactionDate,    TransactionDescription,    TransactionAmount,     Debet,    Credit,    ReferenceNumber,    Ref1,   Ref2,    Ref3,  Ref4,     Administration)    VALUES")
  ##  updateString <- paste0( apply(df, 1, function(x) paste0("('", paste0(x, collapse = "', '"), "')")), collapse = ", ")
  updateString <- paste0(apply(df, 1, function(x) paste0('("', paste0(x, collapse = '", "'), '")')), collapse = ", ")
  updateString2 <- paste0(p1, updateString, ";")
  ##############################################################################################
  ## dbExecute(con, "INSERT INTO cars (speed, dist) VALUES (1, 1), (2, 2), (3, 3);")
  con <- connectSql()
  nrOfRecords <- dbExecute(con, updateString2)
  dbDisconnect(con)
  return(nrOfRecords)
}


####################################################################
## Parse all monetary amounts from string
getAmount <- function(amount_string) {
  if (is.na(amount_string) || amount_string == "") return(NA)
  
  # Find all monetary amounts (with decimals or 4+ digits)
  pattern <- "([0-9]{1,3}([.,][0-9]{3})*[.,][0-9]{2}|[0-9]+[.,][0-9]{2}|[0-9]{4,})"
  matches <- regmatches(amount_string, gregexpr(pattern, amount_string))[[1]]
  
  if (length(matches) == 0) return(NA)
  
  # Convert all matches to numeric
  amounts <- sapply(matches, function(match) {
    cleaned <- gsub("[^0-9.,]", "", match)
    separators <- gsub("[^.,]", "", cleaned)
    
    if (nchar(separators) == 0) {
      return(as.numeric(cleaned))
    }
    
    decimal_sep <- substr(separators, nchar(separators), nchar(separators))
    
    if (decimal_sep == ",") {
      cleaned <- gsub("\\.", "", cleaned)
      cleaned <- gsub(",", ".", cleaned)
    } else {
      cleaned <- gsub(",", "", cleaned)
    }
    
    return(as.numeric(cleaned))
  }, USE.NAMES = FALSE)
  
  return(amounts)
}

getAmountString <- function(text, searchString) {
  pat <- "([0-9]|€|\\$|\\.|,|-| )+"
  pattern <- paste0(searchString, pat)
  m <- regexpr(pattern, text, ignore.case = TRUE, fixed = FALSE)
  xRes <- regmatches(text, m) ## resulting string
  return(xRes)
}

#########################################################################
getRecords <- function(table) {
  getPackages(c("RMariaDB"))
  con <- connectSql()
  df <- dbReadTable(con, table)
  dbDisconnect(con)
  return(df)
}
###############################################################################
getReservationCodes <- function(x) {
  getPackages(c("RMariaDB"))
  con <- connectSql()
  codes <- dbReadTable(con, x)
  dbDisconnect(con)
  ### data to string to verify existing reservationCodes (pattern string)
  xCodes <- paste0(codes$Ref2, collapse = "|")
  return(xCodes)
}

##############################################################################
## Function to retrieve records of TransactionNumber based on Max Date
getBnbLookup <- function(x) {
  getPackages(c("RMariaDB"))
  #### SELECT * FROM bnblookup WHERE bnblookup.lookUp LIKE 'bdc'
  selectStr <- paste0("SELECT * FROM bnblookup WHERE bnblookup.lookUp like ", "'", x, "'")
  con <- connectSql()
  res <- dbSendQuery(con, statement = selectStr)
  df <- dbFetch(res, n = -1)
  dbDisconnect(con)
  return(df)
}

####################################################################################
###### get patterns for transaction coding##########################################
getPatterns <- function() {
  getPackages(c("plyr", "RMariaDB"))
  df <- getSQLtable("vw_ReadReferences")
  ## adapt for special characters
  pattern <- "\\/"
  df$referenceNumber <-
    gsub(pattern, "\\\\/", df$referenceNumber, ignore.case = TRUE)
  dfDebet <- subset(df, df$debet < "1300")
  dfCredit <- subset(df, df$credit < "1300")
  ## Select only unique values
  dfCredit <-
    dfCredit[row.names(unique(dfCredit[, c("credit", "administration", "referenceNumber")])), ]
  dfDebet <-
    dfDebet[row.names(unique(dfDebet[, c("debet", "administration", "referenceNumber")])), ]
  byEx <- c("administration", "debet", "credit")
  ## setDT(dfCredit)
  patternsCredit <-
    ddply(dfCredit,
      byEx,
      summarise,
      pattern = paste0(referenceNumber, collapse = "|")
    )
  ## setDT(dfDebet)
  patternsDebet <-
    ddply(dfDebet,
      byEx,
      summarise,
      pattern = paste0(referenceNumber, collapse = "|")
    )
  ### keep patterns in and remove dataframes no longer needed
  patterns <- rbind(patternsDebet, patternsCredit)

  return(patterns)
}
###########################################################################################
getSQLtable <- function(x) {
    getPackages(c("RMariaDB"))
  con <- connectSql()
  response <- dbReadTable(con, x)
  dbDisconnect(con)
  return(response)
}

############################# Find month number from ranjrge
maandPattern <- "Januari|Februari|Maart|April|Mei|Juni|Juli|Augustus|September|Oktober|November|December"
maandList <- c("Januari", "Februari", "Maart", "April", "Mei", "Juni", "Juli", "Augustus", "September", "Oktober", "November", "December")
## maandPattern <- "Jan|Feb|Maa|Apr|Mei|Jun|Jul|Aug|Sep|Okt|Nov|Dec"
## maandList <- c("Jan","Feb","Maa","Apr","Mei","Jun","Jul","Aug","Sep","Okt","Nov","Dec")

getDateFromTxt <- function(jr, mnd, dag) {
  # Convert month names to numbers
  month_map <- c(jan=1, feb=2, maa=3, mar=3, mrt=3, apr=4, mei=5, may=5, 
                 jun=6, jul=7, aug=8, sep=9, oct=10, okt=10, nov=11, dec=12, dez=12)
  
  # Clean and format year
  jr <- as.numeric(gsub("[^0-9.-]", "", jr))
  jr <- ifelse(jr < 100, jr + 2000, jr)
  
  # Extract month number
  mnd_key <- tolower(substr(mnd, 1, 3))
  mnd_num <- month_map[mnd_key]
  if (is.na(mnd_num)) mnd_num <- 12  # Default to December
  
  # Clean day
  dag <- as.numeric(gsub("[^0-9.-]", "", dag))
  
  # Format as YYYY-MM-DD
  return(sprintf("%04d-%02d-%02d", jr, mnd_num, dag))
}


##############################################################################
## Function to retrieve used transaction numbers from RaboBank by account#######
getUsedTrxNumber <- function(x) {    
    selectStr <- paste0("SELECT mutaties.Ref2 as existing FROM mutaties
                      WHERE mutaties.ref1 = '", x, "'AND mutaties.TransactionDate > (curdate() - INTERVAL 2 YEAR)")
    
    con <- connectSql()
    res <- dbSendQuery(con, statement = selectStr)
    existing <- dbFetch(res, n = -1)
    xx <- dbDisconnect(con)
    
    return(existing)
}

#####################################################################################
## Update data in table
sqlUpdateRecords <- function(sqlString) {
  getPackages(c("RMariaDB"))
  con <- connectSql()
  nrOfRecords <- dbExecute(con, sqlString)
  dbDisconnect(con)
  return(nrOfRecords)
}

#############################################################################
writeWorkbook <- function(fig, fileName, xlsxTab) {
  x <- getPackages(c("xlsx", "readxl", "tidyverse"))
##  config <- config::get(config = "production", file = "./conf/config.yml")
  ### Cleanup data
  fig <- as.data.frame(fig)
  fig <- mutate(fig, across(where(is.character), trimws))

  ## Test if targetfile exists If exist update else load new template
  if (!file.exists(fileName)) {
    wb <- xlsx::loadWorkbook(config$template)
    sheets <- readxl::excel_sheets(config$template)
  } else {
    wb <- xlsx::loadWorkbook(fileName)
    sheets <- readxl::excel_sheets(fileName)
  }

  ## check if xlsxTab exists remove sheet
  if (length(grep(xlsxTab, sheets)) != 0) {
    x <- xlsx::removeSheet(wb, sheetName = xlsxTab)
  }

  ## add empty sheet
  newSheet <- xlsx::createSheet(wb, sheetName = xlsxTab)

  ##  addDataFrame(fig, newSheet, startRow=1, startColumn=1,row.names=FALSE,col.names=TRUE)
  cs1 <- CellStyle(wb) + Font(wb, isItalic = TRUE) # rowcolumns
  cs2 <- CellStyle(wb) + Font(wb, color = "blue")
  cs3 <- CellStyle(wb) + Font(wb, isBold = TRUE) + Border() # header

  ## get cellRange A1:x1 where ncol of df ascii A [65]
  range <- paste0("A1:", rawToChar(as.raw(64 + ncol(fig))), "1")
  xlsx::addAutoFilter(newSheet, cellRange = range)
  xlsx::addDataFrame(fig, newSheet,
    startRow = 1, startColumn = 1,
    row.names = FALSE, col.names = TRUE,
    colnamesStyle = cs3,
    rownamesStyle = cs1,
    colStyle = list(`1` = cs2)
  )
  xlsx::saveWorkbook(wb, file = fileName)
  ###################
  return(fileName)
}

################# Read file details from Google Drive #####################
getDriveFileDetails<- function(folderName, fileNmbr){
    getPackages(c("googledrive"))
    folderContent <- drive_ls(path = paste0("Facturen/", folderName,"/"), trashed = FALSE, n_max = Inf)
    fileName <- folderContent$drive_resource[[fileNmbr]]$name  ## Most recent added file to folder
    fileUrl  <- folderContent$drive_resource[[fileNmbr]]$webViewLink
    return(c(fileName, fileUrl))
}

###########################################################################
paste_cols_by_index <- function(data, indices, sep = "_") {
    selected_cols <- data[, indices, drop = FALSE] #select columns by index
    
    #use reduce to paste the columns
    vect <- Reduce(function(x, y) paste(x, y, sep = sep), selected_cols)
    for (i in 1 : length(vect)){
        vect[i] <- gsub("_NA|  ", "", vect[i]) 
    }
    return(vect)
}
##############################################################################
getTransactionsCodes <- function(data) {
    deb  <- "1002|1003|1021|1022|1023"
    cred <- "1002|1003|1021|1022|1023"
    
    ###############################################################
    
    ### Build patterns in module
    patterns <- getPatterns()
    ## filter for Administration and for existing debet or credit
    admin <- unique(data$Administration)
    patterns <- patterns[grep(admin, patterns$administration), ] ## Note , at the end to select rows
    patternsCredit <- patterns[grep(cred, patterns$credit), ]
    patternsDebet <- patterns[grep(cred, patterns$debet), ]
    
    ## Retrieve ReferenceNumber and accountnumber for opposite account
    for (i in 1:nrow(data)) {
        description <- data$TransactionDescription[i] ## String to match pattern
        ## Load data where debet is empty
        if (data$Credit[i] == "") {
            #############################################################################
            if (nrow(patternsDebet) > 0) {
                for (y in 1:nrow(patternsDebet)) {
                    if (grepl(
                        patternsDebet[y, 4],
                        description,
                        ignore.case = TRUE,
                        fixed = FALSE
                    ) == TRUE)
                    {
                        m <- regexpr(
                            patternsDebet[y, 4],
                            description,
                            ignore.case = TRUE,
                            fixed = FALSE
                        )
                        data$ReferenceNumber[i] <- regmatches(description, m) ## Reference
                        data$Credit[i] <- patternsDebet[y, 3]
                    }
                }
            }
            ##################################################################################
        }
        else {
            if (nrow(patternsCredit) > 0) {
                for (y in 1:nrow(patternsCredit)) {
                    if (grepl(
                        patternsCredit[y, 4],
                        description,
                        ignore.case = TRUE,
                        fixed = FALSE
                    ) == TRUE)
                    {
                        m <- regexpr(
                            patternsCredit[y, 4],
                            description,
                            ignore.case = TRUE,
                            fixed = FALSE
                        )
                        data$ReferenceNumber[i] <- regmatches(description, m)  ## Reference
                        data$Debet[i] <- patternsCredit[y, 2]
                    }
                }
            }
        }
    }
    return(data)
}

getLedgerCodes <- function(ln) {
    ledger <- ifelse(ln == "A",ledger <- config$ledgerA,"")
    ledger <- str_split_1(ledger, " ")
    return(ledger)
    
    
}

####################### Google sheets etc. #####################
#Alternative, more robust check using tryCatch:
drive_has_token <- function() {
    tryCatch({
        googledrive::drive_token()
        TRUE
    }, error = function(e) {
        FALSE
    })
}

gs4_has_token <- function() {
    tryCatch({
        googlesheets4::gs4_token()
        TRUE
    }, error = function(e) {
        FALSE
    })
}
