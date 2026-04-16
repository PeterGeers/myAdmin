It says Invoice sent

This is stored:
{"ID": 63422, "TransactionNumber": "ITILITY", "TransactionDate": "2026-02-01", "TransactionDescription": "Factuur INV-2026-0003 ITILITY BTW 21%", "TransactionAmount": 262.50, "Debet": "8001", "Credit": "2020", "ReferenceNumber": "ITILITY", "Ref1": "", "Ref2": "INV-2026-0003", "Ref3": "", "Ref4": "INV-2026-0003.pdf", "administration": "GoodwinSolutions"}
{"ID": 63421, "TransactionNumber": "ITILITY", "TransactionDate": "2026-02-01", "TransactionDescription": "Factuur INV-2026-0003 ITILITY", "TransactionAmount": 1512.50, "Debet": "1300", "Credit": "8001", "ReferenceNumber": "ITILITY", "Ref1": "", "Ref2": "INV-2026-0003", "Ref3": "", "Ref4": "INV-2026-0003.pdf", "administration": "GoodwinSolutions"}


Ref3 still missing


# E-mail 
E-Mail invoice arrived at client pjageers@gmail.com and BCC also did arrive

Invoice layout (pdf file INV-2026-0003.pdf)

Logo present and a thick verb INV-2026-0003

Datum: 01-02-2026 Vervaldatum: 15-02-2026
Betalingstermijn: 14 dagen Valuta: EUR
Itility B.V.

Omschrijving Aantal Prijs BTW Totaal
Uren Genmab 10 € 125,00 21% € 1.250,00

Subtotaal € 1.250,00
high (21%) € 1.250,00 € 262,50
Totaal € 1.512,50

Betalingsgegevens
Referentie: ITILITY
Factuurnummer: INV-2026-0003
Betreft opdracht xyz001

Missing invoice header details for client and tenant

# Storage
url not filled in Ref3 (still empty)
INV-2026-0002 not found in gdrive

## VAT Rules
2010	Betaalde BTW	2010	201	2000	N	BTW	{"vat_netting": true, "vat_pri...
2020	Ontvangen BTW Hoog	2020	202	2000	N	BTW	{"vat_netting": true, "vat_pri...
2021	Ontvangen BTW Laag	2021	200	2000	N	BTW	{"vat_netting": true, "vat_pri...

 2010 (Betaalde BTW),  is for vat paid to suppliers and is deductable from received vat
 2020 (Received BTW low)
 2021 (Received BTW high)
 But this all should be driven by patameters

 Please make sure the formating llocales etc  are based ion the country of the client
 Please make sure all variables are parameter driven
 We need to add a variable to the invoice on which ledger the invoice should be charged 
 For this line
 "Debet": "1300", "Credit": "8001" 
 Debet account for the invoice should be a FIN parameter Debtor 1300
 Credit account 8001 shoud be a drop down list of defined parameters (invoice ledgers to use) to be selected by the user in the invoice default to 8001
 VAT Account is parameter for High and parameter for low

 We have to add the generic filters on the advanced parameters table


