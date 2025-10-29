source("myFunctions.R")
source("myExportFunctions.R")

packResult <- getPackages(c("tidyverse", "xlsx"))

################# Parameters ################
begin <- 2014
end <- 2023
##administration <- c("PeterPrive")
administration <- c("GoodwinSolutions")

df <- getSQLtable("vw_mutaties")

for (jr in begin:end){
##    doelJaar <- jr
##    doelAdministratie <- administration
    fileName <- makeLedgers(df, jr, administration)
    dfNxt <- filter(df, jaar == jr, Administration == administration)
    nrOfFiles <- exportFiles(select(dfNxt, ReferenceNumber, DocUrl), jr, administration)
    print(paste(nrOfFiles, fileName, sep = ":"))
}


