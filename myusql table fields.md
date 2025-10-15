vw_mutaties fields
---
| Field | Type | Null | Key | Default | Extra | 
| Aangifte | varchar(255) | YES |  | \N |  | 
| TransactionNumber | char(50) | YES |  | \N |  | 
| TransactionDate | date | YES |  | \N |  | 
| TransactionDescription | varchar(512) | YES |  | \N |  | 
| Amount | decimal(21,2) | YES |  | \N |  | 
| Reknum | char(10) | YES |  | \N |  | 
| AccountName | varchar(255) | YES |  | \N |  | 
| ledger | varchar(266) | YES |  | \N |  | 
| Parent | char(20) | YES |  | \N |  | 
| VW | char(1) | YES |  | \N |  | 
| jaar | int | YES |  | \N |  | 
| kwartaal | int | YES |  | \N |  | 
| maand | int | YES |  | \N |  | 
| week | int | YES |  | \N |  | 
| ReferenceNumber | varchar(255) | YES |  | \N |  | 
| Administration | char(20) | YES |  | \N |  | 
| Ref3 | text | YES |  | \N |  | 
| Ref4 | varchar(255) | YES |  | \N |  | 


bnbtotal fields:
{
  "fields": [
    "id",
    "sourceFile",
    "channel",
    "listing",
    "checkinDate",
    "checkoutDate",
    "nights",
    "guests",
    "amountGross",
    "amountNett",
    "amountChannelFee",
    "amountTouristTax",
    "amountVat",
    "guestName",
    "phone",
    "reservationCode",
    "reservationDate",
    "status",
    "pricePerNight",
    "daysBeforeReservation",
    "addInfo",
    "year",
    "q",
    "m"
  ],
  "success": true