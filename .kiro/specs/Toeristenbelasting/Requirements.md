Aangifte toeristenbelasting:
Select jaar dropdown [2025]
Data to use is bnbtotal and vw_mutaties

Fields to be provided and or calculated
 Functie:     DGA
 Telefoonnummer : 06921893861
 E-mailadres : peter@pgeers.nl

 Periode waarop aangifte betrekking heeft: 1-1-2025 t/m 31-12-2025
 Aantal kamers in 2025 : 3
 Aantal beschikbare slaapplaatsen : 8

 Totaal verhuurde kamers : 8
 No-shows : bnb.status = cancelled
 Verhuurde kamers aan inwoners : 0
 Totaal belastbare kamerverhuren : nrow (bnb in 2025) minus No-Shows
 Kamerbezettingsgraad (%) : Sum(kamerverhuren * nights)/ sum(3 * 365)
 Bedbezettingsgraad (%) : Kamerbezettingsgraad * 90%

 Saldo totaal ingehouden toeristenbelasting: (sum(vw_mutaties.account = 8003) / 106.2) * 6.2
 Logiesomzet incl./excl. BTW: ecl. BTW 
 Logiesomzet incl./excl. toeristenbelasting: incl. toeristenbelasting
 

 [1] Ontvangsten excl BTW en excl Toeristen belasting  sum(vw_mutaties.account = 8003-JaBaKi verhuur) minus *(Saldo totaal ingehouden toeristenbelasting)
 [2] ontvangsten logies inwoners excl. BTW (2) : 0
 [3] Kortingen / provisie / commissie (3) : 0
 [4] No-show omzet (4) : Sum (amount.net bnb.status = cancelled)
 
 [5] Totaal 2 + 3 + 4 (5): [2]+[3]+]4]
 
[6] Belastbare omzet logies (6) [1] - [5]]

 Verwachte belastbare omzet 2026 [6*] 1.05

 Naam   : Peter Geers
 Plaats : Hoopfddorp
 Handtekening :
 Datum:  Sys.date
 Aantal bijlagen: 0
