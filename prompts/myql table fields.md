mutaties fields:
---
| Field | Type |
|-------|------|
| ID | int |
| TransactionNumber | char(50) |
| TransactionDate | date |
| TransactionDescription | varchar(512) |
| TransactionAmount | decimal(20,2) |
| Debet | char(10) |
| Credit | char(10) |
| ReferenceNumber | varchar(255) |
| Ref1 | varchar(255) |
| Ref2 | varchar(255) |
| Ref3 | varchar(1020) |
| Ref4 | varchar(255) |
| Administration | char(20) |

vw_mutaties fields
---
| Field | Type 
| Aangifte | varchar(255) 
| TransactionNumber | char(50) 
| TransactionDate | date 
| TransactionDescription | varchar(512) 
| Amount | decimal(21,2) 
| Reknum | char(10) 
| AccountName | varchar(255)
| ledger | varchar(266) 
| Parent | char(20) 
| VW | char(1)
| jaar | int 
| kwartaal | int 
| maand | int 
| week | int 
| ReferenceNumber | varchar(255) 
| Administration | char(20)
| Ref3 | text
| Ref4 | varchar(255) 


bnb fields:
---
| Field | Type |
|-------|------|
| id | int |
| sourceFile | varchar(128) |
| channel | varchar(128) |
| listing | varchar(128) |
| checkinDate | date |
| checkoutDate | date |
| nights | int |
| guests | int |
| amountGross | double |
| amountNett | double |
| amountChannelFee | double |
| amountTouristTax | double |
| amountVat | double |
| guestName | varchar(128) |
| phone | varchar(20) |
| reservationCode | varchar(128) |
| reservationDate | date |
| status | varchar(128) |
| pricePerNight | double |
| daysBeforeReservation | int |
| addInfo | varchar(2048) |
| year | int |
| q | int |
| m | int |

bnbplanned fields:
---
| Field | Type |
|-------|------|
| id | int |
| sourceFile | varchar(128) |
| channel | varchar(128) |
| listing | varchar(128) |
| checkinDate | date |
| checkoutDate | date |
| nights | int |
| guests | int |
| amountGross | double |
| amountNett | double |
| amountChannelFee | double |
| amountTouristTax | double |
| amountVat | double |
| guestName | varchar(128) |
| phone | varchar(20) |
| reservationCode | varchar(128) |
| reservationDate | date |
| status | varchar(128) |
| pricePerNight | double |
| daysBeforeReservation | int |
| addInfo | varchar(1024) |
| year | int |
| q | int |
| m | int |

bnbfuture fields:
---
| Field | Type |
|-------|------|
| id | int |
| date | char(12) |
| channel | varchar(128) |
| listing | varchar(128) |
| amount | double |
| addInfo | varchar(1024) |
| items | int |