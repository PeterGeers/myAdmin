* Calculate STR Revenue for last month see LoadBnBChannelRevenue.R for R Logic. The parameters can change and must be managed:
** pattern <- "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
** jaar <- 2025
** maand <-9
** admin <- "GoodwinSolutions"
** Vat is 9% and changes 2026-01-01 to 21%
** dfBtw$TransactionAmount <- round((dfBtw$TransactionAmount / 109)*9,2)  becomes dfBtw$TransactionAmount / 100+vat)*vat,2 if vat = 21 or 9
Show result records in table before insert in to mutataies




* Add regex to select ReferenceNumber (Google folder should be equal to ReferenceNumber) for pdf processing

* Check saldo before update trx by account ???

* Process import Business VisaCard Rabo (GoodwinSolutions)