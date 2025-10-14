################Load airBnB files ############
channel <- "AirBnB"
## channelFeeFactor  <- 1.176470588
channelFeeFactor  <- 0.15 ## 15%
  ## Gross amount based on Paid out + channel fee
xDate <- Sys.Date()       ## Date starting point for procvess
pathName <- config$download
## Make sure tax is not included
filenames <- list.files(pathName, "reservation", full.names = FALSE)
for(i in 1:length(filenames)){
  x <- read.csv2(paste0(pathName,filenames[i]), header=TRUE, sep = ",", quote = "\"", dec = ".", fill = TRUE, comment.char = "")
  x$sourceFile <- paste(xDate, filenames[i], sep = " ")
  if (i == 1){airBnB <- x} else {airBnB <- bind_rows(airBnB, x)}
}

names(airBnB)
## Rename fieldNames 

names(airBnB)[1] <- "reservationCode"
names(airBnB)[3] <- "guestName"
names(airBnB)[4] <- "phone"
names(airBnB)[5] <- "adult"
names(airBnB)[6] <- "child"
names(airBnB)[7] <- "baby"
names(airBnB)[8] <- "checkinDate"
names(airBnB)[9] <- "checkoutDate"
names(airBnB)[10] <- "nights"
names(airBnB)[11] <- "reservationDate"
names(airBnB)[12] <- "listing"
names(airBnB)[13] <- "paidOut"

## Channel
airBnB$channel <- channel

## dates
airBnB$checkinDate <- dmy(airBnB$checkinDate)
airBnB$checkoutDate <-dmy(airBnB$checkoutDate)
airBnB$reservationDate <-ymd(airBnB$reservationDate)

############ 20220109 Channel Fee added to Amount#####################
airBnB$paidOut <-  getAmount(airBnB$paidOut)
airBnB$amountChannelFee <- airBnB$paidOut * channelFeeFactor
airBnB$amountGross <- airBnB$paidOut + airBnB$amountChannelFee

airBnB$guests <- airBnB$adult + airBnB$child + airBnB$baby

airBnB$addInfo <- paste(airBnB$reservationCode,airBnB$Status, airBnB$adult,airBnB$child, 
                        airBnB$baby, airBnB$listing, sep = "|" )

###################################################################################################

airBnB$listing[grep("One|[G|g]roen|[G|g]reen", airBnB$listing)] <- config$green
airBnB$listing[grep("Tuinhuis|[g|G]arden|Child|kinder", airBnB$listing)] <- config$child
airBnB$listing[grep("[R|r]ode|[R|r]ed|[R|r]ood", airBnB$listing)] <- config$red
###################################################################################################
########################## Define realised or pending
airBnB$status <- ifelse (airBnB$checkinDate > xDate, "planned", "realised") ## Depends on date
### remove bookings cancelled Geannuleerd

filter(airBnB, grepl("Geannuleerd", airBnB$Status))
#######################################################################################
transferColumns <- c("sourceFile", "channel", "listing", 
                     "checkinDate", "checkoutDate",    "nights", "guests",
                     "amountGross", "amountChannelFee", "guestName", "phone",
                     "reservationCode", "reservationDate",
                     "status",  "addInfo"  )
airBnB <- subset(airBnB, select = transferColumns)
