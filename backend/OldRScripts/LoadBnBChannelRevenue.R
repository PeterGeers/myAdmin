source("myFunctions.R")
# Package names
packResult <- getPackages(c("tidyverse", "lubridate", "RMariaDB"))

###################################################################################
pattern <- "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
## pattern <- "AirBnB|Booking.com|Stripe"
jaar <- 2025
maand <-9
admin <- "GoodwinSolutions"
Ref1 <- paste0("BnB ",jaar, formatC(maand, width = 2, flag = "0"))
####################################################################################
qDatum <- paste(jaar,sprintf("%02d", maand), "01", sep="-") ## First day in month
qDatum <- paste(jaar,sprintf("%02d", maand), days_in_month(qDatum), sep = "-") ## Last day needed for filter

## load mutaties
df <- getSQLtable("vw_mutaties")
## Calculate saldo per channel

df <- subset(df, df$TransactionDate <= qDatum)
df <- subset(df, grepl(admin, df$Administration))
df <- subset(df,grepl("1600",df$Reknum))
df$ReferenceNumber <- ifelse(grepl("AIRBNB",df$ReferenceNumber),"AirBnB",df$ReferenceNumber )
df <- subset(df,grepl(pattern,df$ReferenceNumber))
## df1 <- subset(df,grepl("AIRBNB",df$ReferenceNumber))
df <- df %>% 
    group_by(Administration, ReferenceNumber, Reknum) %>% 
    reframe(TransactionAmount = sum(Amount), .groups="drop")
df$TransactionAmount <- round(df$TransactionAmount, 2)
df <- subset(df, df$TransactionAmount != 0)

df$TransactionAmount <- df$TransactionAmount*-1
dfBtw <- df
dfBtw$TransactionAmount <- round((dfBtw$TransactionAmount / 109)*9,2)
df$Debet <- df$Reknum
df$Credit <- "8003"
dfBtw$Debet <- "8003"
dfBtw$Credit <- "2021"
df$TransactionDescription <- paste(df$ReferenceNumber, "omzet", qDatum, sep = " ")
dfBtw$TransactionDescription <- paste(df$ReferenceNumber, "Btw", qDatum, sep = " ")
df <- bind_rows(df, dfBtw)
df$Ref1 <- Ref1
df$Ref2 <- ""
df$Ref3 <- ""
df$Ref4 <- ""
df$TransactionDate <- qDatum
df$TransactionNumber <- paste(df$ReferenceNumber, qDatum, sep = " ")
if (nrow(df) >0 ){
    x <- writeTransactions(df)}
