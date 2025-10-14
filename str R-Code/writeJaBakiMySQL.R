source("myFunctions.R")

packResult <- getPackages(c("tidyverse","lubridate","readxl", "RMariaDB"))
config <- config::get(config= 'production', file = "./conf/config.yml")

source("loadAirBnB.r")
##source("loadBooking.r")  ## Earlier files reservations
source("loadBooking.r") ## recent files rstatement
source("loadDirect.r")

####### merge files
dfJaBaKi <- bind_rows(airBnB, dfBook, dfDirect)

######## VAT and Tourist Tax
dfJaBaKi$amountVat <- (dfJaBaKi$amountGross / 115) * 9
dfJaBaKi$amountTouristTax <- (dfJaBaKi$amountGross / 115) * 6


dfJaBaKi$year <- year(dfJaBaKi$checkinDate)
dfJaBaKi$q <- quarter(dfJaBaKi$checkinDate)
dfJaBaKi$m <- month(dfJaBaKi$checkinDate)
dfJaBaKi$amountNett <- dfJaBaKi$amountGross - dfJaBaKi$amountTouristTax - dfJaBaKi$amountVat - dfJaBaKi$amountChannelFee
dfJaBaKi$pricePerNight <- dfJaBaKi$amountNett / dfJaBaKi$nights

dfJaBaKi$daysBeforeReservation <- as.numeric(-difftime(dfJaBaKi$reservationDate, dfJaBaKi$checkinDate , units = "days"))
## remove characters from guestName that cause problems in update String
dfJaBaKi$guestName <- gsub("'"," ",dfJaBaKi$guestName)


##    subset realised and planned
## Realised
df <- subset(dfJaBaKi , grepl("real|cancel", status ))
reservationCodes <- getReservationCodes("vw_reservationcode")
df <- subset(df,!grepl(reservationCodes, df$reservationCode))
Encoding(df$guestName) <- "UTF-8"
if (nrow(df) >0) {writeBookings(df, "bnb")}

## Planned
df <- subset(dfJaBaKi , grepl("plan", status ))
## delete all records from bnbplanned is only valid for actuals
deleteAllRecords("bnbplanned")
writeBookings(df, "bnbplanned")

## Write status update of planned subtotals for trend analysis
dfTot <- df %>% 
  group_by(channel, listing) %>% 
  reframe(amount = sum(amountGross), items=n())
  ## summarise(across(where(is.numeric), list(sum = sum)))
dfTot$date <-as.character(Sys.Date())

writeStamps(dfTot, "bnbfuture")

#########################################################
##### Write results in xlsx 
## source("createJaBaKiResults.R")
