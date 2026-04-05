# Bewerken & goedkeuren

> Uitgelezen factuurgegevens controleren, aanpassen en opslaan als transacties.

## Overzicht

Na het uploaden en de AI-extractie verschijnen er voorbereide transactierecords. Deze zijn gebaseerd op sjablonen van eerdere facturen van dezelfde leverancier. Je controleert de gegevens, past aan waar nodig en keurt goed om op te slaan.

## Wat je nodig hebt

- Een geüploade factuur met uitgelezen gegevens
- Toegang tot de module Facturen

## Stap voor stap

### 1. Bekijk de voorbereide transacties

Na de upload verschijnen een of meer transactierecords onder het kopje "New Transaction Records (Ready for Approval)". Meestal zijn er twee records:

| Record   | Inhoud                             |
| -------- | ---------------------------------- |
| Record 1 | Hoofdbedrag (totaal inclusief BTW) |
| Record 2 | BTW-bedrag (apart geboekt)         |

!!! info
Het aantal records hangt af van het sjabloon voor de leverancier. Sommige leveranciers hebben meer dan twee boekingsregels.

### 2. Controleer en bewerk de velden

Elk record bevat de volgende bewerkbare velden:

| Veld             | Beschrijving                         | Automatisch ingevuld? |
| ---------------- | ------------------------------------ | --------------------- |
| Transactienummer | Leveranciersnaam                     | ✅                    |
| Referentienummer | Leveranciersnaam                     | ✅                    |
| Datum            | Factuurdatum uit AI-extractie        | ✅                    |
| Omschrijving     | Factuurnummer en identificatie       | ✅                    |
| Bedrag           | Totaalbedrag of BTW-bedrag           | ✅                    |
| Debet            | Debetrekening (grootboeknummer)      | ✅ (uit sjabloon)     |
| Credit           | Creditrekening (grootboeknummer)     | ✅ (uit sjabloon)     |
| Ref1             | Accommodatienaam of extra referentie | Soms                  |
| Ref2             | Factuurnummer (bij Booking.com e.d.) | Soms                  |
| Ref3             | Google Drive-link naar het bestand   | ✅                    |
| Ref4             | Bestandsnaam                         | ✅                    |
| Administratie    | Je huidige tenant                    | ✅                    |

Klik op een veld om het te bewerken. Alle velden zijn aanpasbaar.

### 3. Keur goed en sla op

Als alle gegevens correct zijn, klik je op **Approve & Save to Database**.

Het systeem:

- Slaat de transacties op in de database
- Transacties met een bedrag van €0,00 worden automatisch overgeslagen
- Bevestigt het aantal opgeslagen records

!!! warning
Controleer altijd het bedrag en de debet/creditrekeningen. Verkeerde toewijzingen beïnvloeden je rapportages en belastingaangiften.

### 4. Duplicaatcontrole bij goedkeuring

Als het systeem detecteert dat vergelijkbare transacties al bestaan, verschijnt een waarschuwingsdialoog. Je kunt:

- **Toch opslaan** — De transactie wordt opgeslagen ondanks de mogelijke duplicaat
- **Annuleren** — De goedkeuring wordt gestopt

## Sjablonen

Het systeem gebruikt sjablonen om de debet- en creditrekeningen automatisch in te vullen. Sjablonen zijn gebaseerd op eerdere transacties van dezelfde leverancier:

- **Eerste keer**: Debet en credit zijn leeg — vul ze handmatig in
- **Volgende keren**: Het systeem gebruikt de vorige toewijzing als sjabloon

!!! tip
Zorg dat de eerste factuur van een nieuwe leverancier correct wordt ingevoerd. Alle volgende facturen van dezelfde leverancier gebruiken deze als sjabloon.

## Tips

- Controleer vooral het **bedrag** en de **datum** — dit zijn de meest kritische velden
- De **omschrijving** bevat vaak het factuurnummer — handig voor je administratie
- Klik op de **URL** om het originele bestand in Google Drive te openen
- Transacties met €0,00 worden automatisch overgeslagen bij het opslaan

## Problemen oplossen

| Probleem                   | Oorzaak                                            | Oplossing                                                             |
| -------------------------- | -------------------------------------------------- | --------------------------------------------------------------------- |
| Geen transacties zichtbaar | Geen sjabloon gevonden voor deze leverancier       | Maak handmatig een transactie aan via de module Bankzaken             |
| Verkeerde rekeningen       | Sjabloon gebaseerd op verkeerde eerdere transactie | Pas de rekeningen handmatig aan — het nieuwe sjabloon wordt onthouden |
| Bedrag is 0.00             | AI kon het bedrag niet uitlezen                    | Vul het bedrag handmatig in                                           |
