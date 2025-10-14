################Load rstatement.xlsx ############ Download Nederlandse taal
priceUplift <- 0.054409 ## Uplift from commisiaanble amount to Total price
paymentFee <- 1.11425 ## Uplift for BDC Fee to handle payments
channel <- "Booking.com"
pathName <- config$download
pattern <- "Check-in"
filenames <- list.files(pathName, pattern, full.names = FALSE)
fileNM <- list.files(pathName, pattern, full.names = TRUE)
for(i in 1:length(filenames)){
  x <- read_xls(fileNM[i], sheet = 1, col_types = "text")
##  x <- readxl(paste0(pathName,filenames[i]), header=TRUE, sep = ",", quote = "\"", dec = ".", fill = TRUE, comment.char = "")
  x$sourceFile <- paste(format(Sys.Date(), "%Y-%m-%d"), filenames[i], sep = ":")
  if (i == 1){dfBook <- x} else {dfBook <- bind_rows(dfBook, x)}
}

names(dfBook)[17] <- "paymentMethod"

dfBook$channel <- channel
dfBook$addInfo <- paste(dfBook$channel, 
                        dfBook$'Book number',
                        dfBook$'Booked by', 
                        dfBook$'Booked on', 
                        dfBook$'Guest name(s)',
                        dfBook$'Status',
                        dfBook$Price,
                        dfBook$`Commission %`,
                        dfBook$`Commission amount`,
                        dfBook$'Payment status',
                        dfBook$'paymentMethod',
                        dfBook$'Remarks',
                        dfBook$'Booker group',
                        dfBook$'Booker country',
                        dfBook$'Travel purpose',
                        dfBook$'Device',
                        dfBook$'Unit type',
                        dfBook$'Duration (nights)',
                        dfBook$'Address',
                        sep = "|" )

names(dfBook)

dfBook <- dfBook[c(1:16, 18, 19, 23, 24, 28, 29, 30)]

## Select all entries where BDC gets commission (Even cancelled ones)
dfBook <- subset(dfBook, !is.na(dfBook$`Commission amount`))

## correct listings to unified
dfBook$listing <- ""
dfBook$listing[grep("One|green|Green", dfBook$`Unit type`)] <- config$green
dfBook$listing[grep("^Apartment$|Tuinhuis|[G|g]arden|Child", dfBook$`Unit type`)] <- config$child
dfBook$listing[grep("Rode|Red|rood|red", dfBook$`Unit type`)] <- config$red

## Prijs 
## Remove following EUR
## sub(" EUR","", dfBook$Price)
dfBook$Price <- as.numeric(sub(" EUR","", dfBook$Price))
dfBook$amountGross <- round(dfBook$Price + dfBook$Price*priceUplift,2) ## Adds some TouristTax to Price 


### Add payment fee to Channel fee
dfBook$amountChannelFee <- as.numeric(sub(" EUR","", dfBook$`Commission amount`)) * paymentFee
## dfBook$amountNett <- dfBook$amountGross - dfBook$amountTouristTax - dfBook$amountVat - dfBook$amountChannelFee
## dates
dfBook$checkinDate <- ymd(dfBook$`Check-in`)
dfBook$checkoutDate <- ymd(dfBook$`Check-out`)
dfBook$nights <- as.integer(dfBook$`Duration (nights)`)
currentDate <- as.POSIXct(Sys.Date())
dfBook$status <- ifelse (dfBook$checkinDate > currentDate, "planned", "realised") ## Depends on currentDate
dfBook$status <- ifelse(grepl('cancel',dfBook$Status),"cancelled", dfBook$status)
dfBook$guests <- as.numeric(dfBook$Persons)
dfBook$guestName <- dfBook$'Booked by'
dfBook$reservationCode <- as.character(dfBook$'Book number')
dfBook$reservationDate <- as.Date(ymd_hms(dfBook$'Booked on'))

dfBook <- dfBook[,c("sourceFile", "channel", "listing", "checkinDate", "checkoutDate", "nights", "guests", "amountGross", "amountChannelFee", "guestName", "reservationCode", "reservationDate", "status", "addInfo")]
