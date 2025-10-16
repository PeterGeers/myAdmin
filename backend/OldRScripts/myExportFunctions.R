exportFiles <- function(df, jaar, admin) {
    ## Function to retrieve text from PDF file in Google Drive based on folderId, lastFile in Folder and replica of file in Drive on PC
    source("myFunctions.R")
    getPackages(c("googledrive"))
    config <-
        config::get(config = 'production', file = "./conf/config.yml")
    folder <- paste0(config$finReports, admin, jaar, "/")
    if (!dir.exists(folder)) {
        dir.create(folder)
    }
    df <- filter(df, grepl("drive.google", df$DocUrl))
    df$ReferenceNumber <- trimws(df$ReferenceNumber)
    df <- unique(df)
    
    newFolders <- sort(unique(df$ReferenceNumber))
    if (length(newFolders) > 0){
    for (i in 1:length(newFolders)) {
        tobe <- paste0(folder, newFolders[i], "/")
        if (!dir.exists(tobe)) {
            dir.create(tobe)
        }
    }

    for (i in 1:nrow(df)) {
        docUrl <- df$DocUrl[i]
        destFolder <- paste0(folder, df$ReferenceNumber[i], "/")
        ##    folderContent <- drive_ls(as_id(folderId), n_max = 1, recursive = FALSE) ## Retrieves content of folder
        ##    fileCode <- folderContent$id[[1]]  ## Most recent added file to folder
        fileDetails <- drive_get(as_id( str_split(docUrl, "&")[[1]][1]))
        dwnFile <- paste0(destFolder, fileDetails$drive_resource[[1]]$name)
        ##    download.file(docUrl, destfile = dwnFile, method = "curl", mode = "w")
        
        dl <-
            drive_download(as_id(fileDetails$drive_resource[[1]]$webViewLink),
                           path = dwnFile,
                           overwrite = TRUE)
##        print(paste(i , nrow(df), sep = " van "))
        
    }
        
    }   
    return(nrow(df))
    
}
########################################################################################################################################
makeLedgers <- function (df, doelJaar,doelAdministratie)
{
    config <- config::get(config = 'production', file = "conf/config.yml")
    ## read vw_mutaties to process
     ## Select only Balans rekeningen voor berekenen Begin Balans
    dfBalans <- filter(df, VW =="N", Administration == doelAdministratie, jaar < doelJaar)
    dfBalans <- dfBalans %>%
        group_by(Reknum,AccountName, SubParent, Parent, Administration) %>%
        reframe(across(c("Amount"), ~ sum(.x, na.rm = TRUE)))
    dfBalans$Amount <- round(dfBalans$Amount,2)
    dfBalans <- filter(dfBalans, Amount != 0)
    dfBalans$TransactionNumber <- paste0("Beginbalans ",doelJaar)
    dfBalans$TransactionDate <- ymd(paste0(doelJaar,"-01-01"))
    dfBalans$TransactionDescription <- paste0("Beginbalans van het jaar ",doelJaar, " van Administratie ", doelAdministratie)
    #### ad missing columns to frame dfBalans
    dfBalans$VW <- "N"
    dfBalans$jaar <- doelJaar
    dfBalans$kwartaal <- 1
    dfBalans$maand <- 1
    dfBalans$week <- 1
    dfBalans$ReferenceNumber <-""
    dfBalans$DocUrl <- ""
    dfBalans$Document <- ""
    
    ##################Read all mutaties voor het specifieke jaar
    dfMutaties <- filter(df, Administration == doelAdministratie)
    dfMutaties <- filter(dfMutaties, jaar== doelJaar)
    dfSet <- bind_rows(dfBalans, dfMutaties)
    ###############################################################################

    ## Start write dfSet in fileName
    folder <- paste0(config$finReports, doelAdministratie, doelJaar, "/")
    if (!dir.exists(folder)) {
        dir.create(folder)
    }
    
    fileName <- paste0(folder,doelAdministratie,doelJaar,".xlsx")
    fileName <- writeWorkbook (dfSet, fileName, "data")

    return(fileName)
}