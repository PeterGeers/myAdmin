################Load JaBaKi files ############
pathname <- paste0(getwd(),"/data/")
filenames <- list.files(pathname, "jabakiRechtstreeks", full.names = FALSE)
fileToRead <- list.files(pathname, "jabakiRechtstreeks", full.names = TRUE)
dfDirect <- read_xlsx(fileToRead, sheet= 1)
  ##  x <- readxl(paste0(pathName,filenames[i]), header=TRUE, sep = ",", quote = "\"", dec = ".", fill = TRUE, comment.char = "")
dfDirect$sourceFile <- paste(format(Sys.Date(), "%Y-%m-%d"), filenames, sep = ":")
################################################
dfDirect <- subset(dfDirect, type == "reservation")
dfDirect$channel <- ifelse( grepl("goodwin", dfDirect$typeTrade, ignore.case = TRUE),"dfDirect",
                    ifelse( grepl("VRBO|vrbo", dfDirect$typeTrade, ignore.case = TRUE),"VRBO",
                            'dfZwart'))

dfDirect$addInfo <- paste(filenames,dfDirect$guestName, dfDirect$type,dfDirect$typeTrade, dfDirect$details, dfDirect$reservationCode, dfDirect$currency, dfDirect$amountGross, dfDirect$amountChannelFee, dfDirect$cleaningFee, sep = " | " )

## dates
dfDirect$checkinDate <- as.Date(dfDirect$startDate)
dfDirect$checkoutDate <-dfDirect$checkinDate + as.difftime(dfDirect$nights, units="days")

currentDate <- as.POSIXct(Sys.Date())
dfDirect$status <- ifelse (dfDirect$checkinDate > currentDate, "planned", "realised") ## Depends on currentDate

dfDirect$listing[grep("One|green|Green", dfDirect$listing)] <- config$green
dfDirect$listing[grep("[T|t]uinhuis|[G|g]arden|[C|c]hild|[K|k]inder", dfDirect$listing)] <- config$child
dfDirect$listing[grep("Rode|Red|rood|red", dfDirect$listing)] <- config$red
###################################################################################################
 
dfDirect$reservationDate <- dfDirect$checkinDate ## not in file
dfDirect <- dfDirect[,c("sourceFile", "channel", "listing", "checkinDate", "checkoutDate", "nights", "guests", "amountGross",  "amountChannelFee", "guestName", "reservationCode", "reservationDate", "status", "addInfo")]
## dfDirect <- as.data.frame(dfDirect)